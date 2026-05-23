#!/usr/bin/env python3
"""Auto-classify review FAIL/WARN into R0-R4 repair levels.

Usage:
  python repair_plan.py <book_dir> --chapter 31 [--from-review report.json] [--problem "..."] [--json]

Reads a review result (or manual problem description) and generates a
classified repair plan following webnovel-director"s repair-feedback protocol:

  R0: 记录 — 无需改正文，更新 last_audit/truth 即可
  R1: 局部修 — 修改片段/转场/钩子，不改变章节主事件
  R2: 整章回炉 — 章节目标未完成或结构错误
  R3: 细纲重排 — 多章方向错误
  R4: 卷级回滚 — 卷目标违背 premise
"""
from __future__ import annotations
from pathlib import Path
import argparse, datetime, json, re, sys


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore") if path.exists() else ""


# ── classification logic ──

SEVERITY_KEYWORDS = {
    "R0": ["记录", "无影响", "注意", "小问题", "可忽略", "轻微"],
    "R1": ["钩子", "转场", "片段", "局部", "对白", "密度", "字数", "偏短", "偏长", "修正", "弱", "章末"],
    "R2": ["目标未完成", "命题兑现", "禁词", "禁止", "禁飞区", "触犯", "未命中", "0/", "1/", "缺少", "FAIL"],
    "R3": ["连续", "多章", "队列", "细纲", "3章", "前.*章", "密度", "方向"],
    "R4": ["卷目标", "命题相反", "卷级", "背离", "书名承诺", "不可修复"],
}


def classify_issue(issue_text: str) -> str:
    """Classify a single issue into R0-R4."""
    lo = issue_text.lower()
    scores = {}
    for level, keywords in SEVERITY_KEYWORDS.items():
        scores[level] = sum(1 for kw in keywords if kw.lower() in lo)
    # Default to R2 for FAIL, R1 for WARN
    if not any(scores.values()):
        if "fail" in lo:
            return "R2"
        return "R1"
    return max(scores, key=scores.get)


def classify_problems(problems: list[str], verdict: str) -> tuple[str, list[dict]]:
    """Classify all problems and return the highest repair level + classified items."""
    classified = []
    highest = "R0"
    level_order = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}
    for p in problems:
        level = classify_issue(p)
        classified.append({"problem": p, "level": level})
        if level_order.get(level, 0) > level_order.get(highest, 0):
            highest = level
    # Ensure FAIL verdict gets at least R2
    if verdict == "FAIL" and level_order.get(highest, 0) < 2:
        highest = "R2"
    return highest, classified


# ── repair action generation ──

REPAIR_ACTIONS = {
    "R0": {
        "action": "记录",
        "steps": [
            "更新 last_audit.md 记录问题",
            "更新 audit_log.md",
            "不修改正文",
            "不修改 chapter_queue",
        ],
        "next": "继续下一章",
    },
    "R1": {
        "action": "局部修",
        "steps": [
            "定位问题文段（给出章内位置建议）",
            "修改不超过 30% 的章节内容",
            "不改变章节主事件和结局",
            "修后交 review_chapter 重审",
            "更新 truth files（如有 resource/particle 变化）",
        ],
        "next": "review_chapter 重审 → post_writeback",
    },
    "R2": {
        "action": "整章回炉",
        "steps": [
            "保留 chapter_queue 中的 goal/forbidden/must_hit",
            "重新生成该章任务包 build_task_package",
            "重写整章正文",
            "重写后必须通过 review_parallel 审查",
            "全部 PASS 后方可 post_writeback",
        ],
        "next": "build_task_package → 重写 → review_parallel → post_writeback",
    },
    "R3": {
        "action": "细纲重排",
        "steps": [
            f"标记 chapter_queue 受影响章节为 BLOCKED",
            "重新审查多个章节的 goal/forbidden/must_hit 方向",
            "更新 outline_gate_review 审查",
            "全部 PASS 后重新 build_task_package",
        ],
        "next": "outline_gate_review → build_task_package（受影响章节）",
    },
    "R4": {
        "action": "卷级回滚",
        "steps": [
            "暂停该卷所有章节的派发",
            "回到 premise.md 重新审查卷目标",
            "卷目标可能与书名命题矛盾——需要重写卷级细纲",
            "重新通过 outline-gate 全线审查",
            "⚠ 已发布章节需用户确认",
        ],
        "next": "停止派发 → 重审卷目标 → outline-gate → 用户确认",
    },
}


def generate_plan(chapter: int, highest_level: str, classified: list[dict], book_dir: Path, from_review: str) -> str:
    action = REPAIR_ACTIONS[highest_level]
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    lines = []
    lines.append(f"# 修复计划 — Ch{chapter:04d}")
    lines.append(f"")
    lines.append(f"时间：{now}")
    lines.append(f"来源：{from_review}")
    lines.append(f"修复级别：{highest_level} — {action['action']}")
    lines.append("")
    lines.append("## 问题清单")
    lines.append("")
    for i, c in enumerate(classified, 1):
        lines.append(f"{i}. [{c['level']}] {c['problem']}")
    lines.append("")
    lines.append("## 修复步骤")
    lines.append("")
    for i, step in enumerate(action["steps"], 1):
        lines.append(f"{i}. {step}")
    lines.append("")
    lines.append(f"## 下一步")
    lines.append("")
    lines.append(action["next"])
    lines.append("")
    lines.append("---")
    lines.append(f"由 `scripts/repair_plan.py` 生成。修后必须重审。")
    return "\n".join(lines) + "\n"


# ── main ──

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--from-review", help="JSON review report file (from review_chapter/review_parallel)")
    ap.add_argument("--problem", action="append", default=[], help="Problem description (repeatable)")
    ap.add_argument("--verdict", default="WARN", choices=["PASS", "WARN", "FAIL"], help="Overall verdict")
    ap.add_argument("--out", help="Write repair plan to file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    book = Path(args.book_dir).resolve()

    problems = list(args.problem)
    review_source = f"--problem 手动输入 ({len(problems)}条)"
    review_verdict = args.verdict

    if args.from_review:
        review_path = Path(args.from_review)
        if not review_path.exists():
            if args.json:
                print(json.dumps({"status": "FAIL", "reason": f"review file not found: {review_path}"}, ensure_ascii=False))
            else:
                print(f"结论：FAIL\n问题：审查报告不存在 {review_path}")
            return 1
        review_source = str(review_path)
        try:
            review_data = json.loads(read(review_path))
        except Exception:
            review_data = None
        if review_data:
            review_verdict = review_data.get("status", args.verdict)
            # Extract problems from review data
            if "chapters" in review_data:
                # outline_gate_review format
                for ch_data in review_data.get("chapters", []):
                    if ch_data.get("chapter") == args.chapter:
                        for i in ch_data.get("issues", []):
                            problems.append(f"[{i.get('dimension','?')}] {i.get('issue','?')}")
                        break
            if "all_issues" in review_data:
                problems.extend(review_data["all_issues"])
            if "checks" in review_data:
                for chk in review_data["checks"]:
                    if chk.get("severity") != "PASS":
                        problems.append(f"[{chk.get('name','?')}] {chk.get('issue','')}")
            if "issues" in review_data and isinstance(review_data["issues"], list):
                # outline_gate_check format
                for i in review_data.get("issues", []):
                    if isinstance(i, dict):
                        problems.append(f"[{i.get('area','?')}] {i.get('issue','?')}")
                    else:
                        problems.append(str(i))

    if not problems:
        if args.json:
            print(json.dumps({"status": "PASS", "level": "R0", "classified": [], "message": "无问题，无需修复"}, ensure_ascii=False))
        else:
            print("结论：PASS — 无问题，无需修复")
        return 0

    highest_level, classified = classify_problems(problems, review_verdict)
    plan = generate_plan(args.chapter, highest_level, classified, book, review_source)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(plan, encoding="utf-8")

    result = {
        "status": "FAIL" if highest_level in {"R3", "R4"} else ("WARN" if highest_level != "R0" else "PASS"),
        "chapter": args.chapter,
        "level": highest_level,
        "action": REPAIR_ACTIONS[highest_level]["action"],
        "classified": [{"problem": c["problem"], "level": c["level"]} for c in classified],
        "next": REPAIR_ACTIONS[highest_level]["next"],
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(plan)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
