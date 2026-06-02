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
import sys as _sys
_skill_root = Path(__file__).resolve().parent.parent
_sys.path.insert(0, str(_skill_root))
from lib.common import read_text
import argparse, datetime, json, re, sys


# ── classification logic ──

SEVERITY_KEYWORDS = {
    "R0": ["记录", "无影响", "注意", "小问题", "可忽略", "轻微"],
    "R1": ["钩子", "转场", "片段", "局部", "对白", "字数", "偏短", "偏长", "修正", "弱", "章末"],
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


# ── batch mode ──


def apply_auto_fix(book_dir: Path, ch_num: int, highest_level: str,
                   classified: list[dict]) -> list[str]:
    """Auto-apply R0 and R1 fixes. Returns list of actions taken."""
    actions = []

    if highest_level == "R0":
        # R0: Just log to audit_log, no content changes
        audit_path = book_dir / "director" / "audit_log.md"
        now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        entry = f"| {now} | repair_plan(auto) | 第{ch_num}章 | PASS | R0记录:{classified[0]['problem'][:30] if classified else '已记录'} | 继续 |"
        if audit_path.exists():
            with audit_path.open("a", encoding="utf-8") as f:
                f.write(entry + "\n")
        else:
            audit_path.write_text(
                "# Audit Log\n\n| Time | Module | Object | Result | Summary | Next |\n"
                "|---|---|---|---|---|---|\n" + entry + "\n",
                encoding="utf-8")
        actions.append(f"R0: 已记录到 audit_log — {classified[0]['problem'][:40] if classified else '已记录'}")

    elif highest_level == "R1":
        # R1: Update chapter_queue status to NEEDS_REVIEW, log to audit_log
        cq_path = book_dir / "director" / "chapter_queue.md"
        if cq_path.exists():
            content = read(cq_path)
            new_lines = []
            updated = False
            for line in content.splitlines():
                s = line.strip()
                if s.startswith("|") and "---" not in s and "Chapter" not in s:
                    cells = [c.strip() for c in s.strip("|").split("|")]
                    if len(cells) >= 6:
                        n = re.sub(r"\D", "", cells[0])
                        if n.isdigit() and int(n) == ch_num:
                            cells[5] = "NEEDS_REVIEW"
                            new_lines.append("| " + " | ".join(cells) + " |")
                            updated = True
                            continue
                new_lines.append(line)
            if updated:
                cq_path.write_text("\n".join(new_lines), encoding="utf-8")
                actions.append(f"R1: chapter_queue 第{ch_num}章状态 → NEEDS_REVIEW")

        # Log to audit_log
        audit_path = book_dir / "director" / "audit_log.md"
        now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        entry = f"| {now} | repair_plan(auto) | 第{ch_num}章 | WARN | R1局部修:{classified[0]['problem'][:30] if classified else '局部修复'} | review_chapter重审 |"
        if audit_path.exists():
            with audit_path.open("a", encoding="utf-8") as f:
                f.write(entry + "\n")
        else:
            audit_path.write_text(
                "# Audit Log\n\n| Time | Module | Object | Result | Summary | Next |\n"
                "|---|---|---|---|---|---|\n" + entry + "\n",
                encoding="utf-8")
        actions.append("R1: 已记录到 audit_log，需 review_chapter 重审")

    return actions


def run_batch_mode(book_dir: Path, auto_apply: bool = False) -> int:
    """Batch repair: scan chapter_queue for WARN/FAIL, classify & optionally auto-fix."""
    # Ensure UTF-8 output on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cq_path = book_dir / "director" / "chapter_queue.md"
    if not cq_path.exists():
        print(f"错误: {cq_path} 不存在")
        return 1

    queue_text = read(cq_path)
    warn_fail_chapters = []
    for line in queue_text.splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "Chapter" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) >= 6:
            n = re.sub(r"\D", "", cells[0])
            if n.isdigit():
                status = cells[5].upper()
                if status in ("WARN", "FAIL"):
                    warn_fail_chapters.append({
                        "chapter": int(n),
                        "title": cells[1],
                        "goal": cells[2],
                        "premise_hit": cells[3],
                        "forbidden": cells[4],
                        "status": status,
                    })

    if not warn_fail_chapters:
        print("[OK] 未找到 WARN/FAIL 章节，无需修复。")
        return 0

    print(f"\n[*] 批量修复模式: 发现 {len(warn_fail_chapters)} 个 WARN/FAIL 章节")
    if auto_apply:
        print("   --auto-apply: R0/R1级别修复将自动应用")
    print()

    results = []
    for ch in warn_fail_chapters:
        print(f"  [{ch['status']}] 第{ch['chapter']:3d}章 {ch['title']} ... ", end="", flush=True)

        # Try to get review data
        review_path = None
        for cand in [
            book_dir / "director" / "reviews" / f"ch{ch['chapter']:04d}_review.json",
            book_dir / "director" / f"ch{ch['chapter']:04d}_review.json",
        ]:
            if cand.exists():
                review_path = cand
                break

        problems = []
        verdict = ch["status"]
        review_source = "chapter_queue"

        if review_path:
            try:
                review_data = json.loads(read(review_path))
                verdict = review_data.get("status", ch["status"])
                review_source = str(review_path)
                # Extract issues
                if "issues" in review_data and isinstance(review_data["issues"], list):
                    for issue in review_data["issues"]:
                        if isinstance(issue, dict):
                            problems.append(f"[{issue.get('area','?')}] {issue.get('issue','?')}")
                        else:
                            problems.append(str(issue))
                if "checks" in review_data:
                    for chk in review_data.get("checks", []):
                        if chk.get("severity") != "PASS":
                            problems.append(f"[{chk.get('name','?')}] {chk.get('issue','')}")
            except Exception:
                pass

        # Fallback: no review file or couldn't parse
        if not problems:
            problems.append(f"章节队列状态为 {verdict}，需审查修复")

        highest_level, classified = classify_problems(problems, verdict)
        action_name = REPAIR_ACTIONS[highest_level]["action"]

        # Save plan
        plan = generate_plan(ch["chapter"], highest_level, classified, book_dir, review_source)
        plan_dir = book_dir / "director" / "repair_plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / f"第{ch['chapter']:04d}章_repair.md"
        plan_path.write_text(plan, encoding="utf-8")

        can_auto = auto_apply and highest_level in ("R0", "R1")
        auto_actions = []
        if can_auto:
            auto_actions = apply_auto_fix(book_dir, ch["chapter"], highest_level, classified)

        results.append({
            "chapter": ch["chapter"],
            "title": ch["title"],
            "status": ch["status"],
            "level": highest_level,
            "action": action_name,
            "auto_applied": can_auto and len(auto_actions) > 0,
            "auto_actions": auto_actions,
            "plan_path": str(plan_path),
            "problem_count": len(classified),
        })

        tag = "[OK]自动" if results[-1]["auto_applied"] else ("[!!]待处理" if highest_level in ("R0", "R1") else "[XX]需人工")
        print(f"→ {highest_level} {action_name} {tag}")

    # ═══ Summary report ═══
    print()
    print("=" * 64)
    print("  批量修复汇总报告")
    print("=" * 64)
    total = len(results)
    auto_done = sum(1 for r in results if r["auto_applied"])
    manual = total - auto_done
    r0_count = sum(1 for r in results if r["level"] == "R0")
    r1_count = sum(1 for r in results if r["level"] == "R1")
    r2_count = sum(1 for r in results if r["level"] == "R2")
    r3_count = sum(1 for r in results if r["level"] == "R3")
    r4_count = sum(1 for r in results if r["level"] == "R4")

    print(f"  总计: {total} 章 | 自动应用: {auto_done} | 需人工处理: {manual}")
    print(f"  R0(记录): {r0_count} | R1(局部修): {r1_count} | R2(回炉): {r2_count} "
          f"| R3(细纲重排): {r3_count} | R4(卷级回滚): {r4_count}")
    print()

    for r in results:
        tag_icon = "[OK]" if r["auto_applied"] else ("[!!]" if r["level"] in ("R0", "R1") else "[XX]")
        print(f"  {tag_icon} 第{r['chapter']:3d}章 [{r['status']}] → {r['level']} {r['action']}")
        if r["auto_actions"]:
            for act in r["auto_actions"]:
                print(f"          {act}")
        if not r["auto_applied"]:
            print(f"          修复计划: {r['plan_path']}")
    print()

    # Write summary to file
    summary_path = book_dir / "director" / "repair_plans" / "batch_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_data = {
        "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "total": total,
        "auto_applied": auto_done,
        "manual": manual,
        "levels": {"R0": r0_count, "R1": r1_count, "R2": r2_count, "R3": r3_count, "R4": r4_count},
        "results": [{
            "chapter": r["chapter"],
            "status": r["status"],
            "level": r["level"],
            "auto_applied": r["auto_applied"],
        } for r in results],
    }
    summary_path.write_text(json.dumps(summary_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  汇总已保存: {summary_path}")

    return 0


# ── main ──

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--chapter", type=int, help="章节号（单章模式，与--batch互斥）")
    ap.add_argument("--from-review", help="JSON review report file (from review_chapter/review_parallel)")
    ap.add_argument("--problem", action="append", default=[], help="Problem description (repeatable)")
    ap.add_argument("--verdict", default="WARN", choices=["PASS", "WARN", "FAIL"], help="Overall verdict")
    ap.add_argument("--out", help="Write repair plan to file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--batch", action="store_true",
                    help="批量模式: 扫描 chapter_queue 中所有 WARN/FAIL 章节")
    ap.add_argument("--auto-apply", action="store_true",
                    help="自动应用 R0/R1 级修复（需配合 --batch）")
    args = ap.parse_args()
    book = Path(args.book_dir).resolve()

    # ── Batch mode ──
    if args.batch:
        return run_batch_mode(book, auto_apply=args.auto_apply)

    # ── Single chapter mode ──
    if args.chapter is None:
        ap.error("需要 --chapter 或 --batch 参数")

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
            review_data = json.loads(read_text(review_path))
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
