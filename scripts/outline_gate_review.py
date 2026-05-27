#!/usr/bin/env python3
"""Full chapter-by-chapter outline-gate review for webnovel-director.

Usage:
  python outline_gate_review.py <book_dir> [--json] [--write-report]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import (  # noqa: E402
    DIRECTOR_PREMISE, DIRECTOR_QUEUE, TRUTH_PENDING_HOOKS,
    chapter_to_volume, extract_forbidden_zones, extract_premise_promise,
    extract_role_locks, extract_volume_zones, find_volume_map, now_iso,
    parse_chapter_queue, parse_hooks, parse_volume_map, read_text, write_text,
)

REQUIRED_FILE_LIST = [DIRECTOR_PREMISE, DIRECTOR_QUEUE, TRUTH_PENDING_HOOKS]

DEFAULT_FORBIDDEN_PATTERNS = [
    ("系统面板|状态栏|任务栏|系统商店|系统抽奖|系统任务|系统提示", "system_panel", "无系统世界观"),
    ("后宫|收后宫|开后宫", "harem", "禁后宫"),
    ("抢首通|独占BOSS|正面碾压|公会带飞|建公会碾压", "carry_by_guild", "禁公会带飞/抢首通"),
    ("反派降智|反派犯傻|反派送人头", "villain_stupid", "反派降智"),
    ("主角高调宣布|主动暴露底牌|公开核心秘密", "reveal_secret", "主角过早暴露"),
]


def extract_concept_anchors(text: str) -> list[str]:
    """Extract meaningful multi-char Chinese phrases as concept anchors."""
    chars = list(text)
    anchors = []
    i = 0
    while i < len(chars) - 1:
        for span in [6, 5, 4, 3, 2]:
            if i + span <= len(chars):
                chunk = "".join(chars[i:i + span])
                if re.match(r"^[一-鿿]{" + str(span) + r"}$", chunk):
                    anchors.append(chunk)
                    i += 1
                    break
        else:
            i += 1
    return anchors


# ── per-dimension checkers ──

def check_volume_promise(ch: dict, volume_zones: list[dict], ch_index: int,
                         total: int, volume_ranges: list[dict] | None = None) -> dict:
    issues = []
    goal = (ch.get("goal") or "").strip()
    forbidden_col = (ch.get("forbidden") or "").strip()

    if volume_ranges:
        vol = chapter_to_volume(ch["chapter"], volume_ranges)
    else:
        vol = None
    if vol is None:
        vol = 1
        if ch["chapter"] > 25:
            vol = 2
        if ch["chapter"] > 70:
            vol = 3
        if ch["chapter"] > 140:
            vol = 4
        if ch["chapter"] > 240:
            vol = 5
        if ch["chapter"] > 360:
            vol = 6
        if ch["chapter"] > 500:
            vol = 7

    vz = next((z for z in volume_zones if z.get("volume") == vol), None)
    if vz and vz.get("forbidden"):
        for keyword in re.split(r"[、,，]", vz["forbidden"]):
            kw = keyword.strip()
            if kw and kw in goal + forbidden_col:
                issues.append({"severity": "FAIL", "dimension": "volume_promise",
                               "issue": f"触犯卷{vol}禁区: {kw}"})
    if not goal and ch_index == 0:
        issues.append({"severity": "WARN", "dimension": "volume_promise",
                       "issue": "首章Goal缺失，无法判断卷目标衔接"})
    return {"pass": len([i for i in issues if i["severity"] == "FAIL"]) == 0, "issues": issues}


def check_premise_alignment(ch: dict, premise_text: str, forbidden_zones: list[dict]) -> dict:
    issues = []
    must_hit = (ch.get("premise_must_hit") or "").strip()
    goal = (ch.get("goal") or "").strip()
    combined = goal + " " + must_hit
    if not must_hit:
        issues.append({"severity": "WARN", "dimension": "premise_alignment", "issue": "缺少 Premise Must Hit"})
    elif len(must_hit) < 10:
        issues.append({"severity": "WARN", "dimension": "premise_alignment", "issue": "Premise Must Hit 过短"})
    if premise_text and must_hit:
        premise_anchors = extract_concept_anchors(premise_text)
        meaningful = [a for a in premise_anchors if len(a) >= 3]
        if not meaningful:
            meaningful = [a for a in premise_anchors if len(a) >= 2]
        hits = [a for a in meaningful if a in combined]
        if not hits:
            promise_words = set(re.findall(r"[一-鿿]{3,}", premise_text))
            hit_words = set(re.findall(r"[一-鿿]{3,}", combined))
            if not (promise_words & hit_words):
                issues.append({"severity": "WARN", "dimension": "premise_alignment",
                               "issue": "章节目标未命中书名任何概念锚点"})
    return {"pass": len([i for i in issues if i["severity"] == "FAIL"]) == 0, "issues": issues}


def check_forbidden_zone(ch: dict, forbidden_zones: list[dict], role_locks: list[dict]) -> dict:
    issues = []
    goal = (ch.get("goal") or "").strip()
    must_hit = (ch.get("premise_must_hit") or "").strip()
    ch_forbidden = (ch.get("forbidden") or "").strip()
    for pattern, tag, label in DEFAULT_FORBIDDEN_PATTERNS:
        if re.search(pattern, goal + " " + must_hit) and tag not in ch_forbidden and label not in ch_forbidden:
            issues.append({"severity": "FAIL", "dimension": "forbidden_zone",
                           "issue": f"疑似触犯 {label}：{tag}"})
    for fz in forbidden_zones:
        keywords = re.findall(r"[一-鿿]{2,}", fz.get("content", ""))
        for kw in keywords:
            if kw in goal + " " + must_hit and kw not in ch_forbidden and len(kw) >= 4:
                issues.append({"severity": "WARN", "dimension": "forbidden_zone",
                               "issue": f"可能接近禁飞区{fz.get('id','')}: {kw}"})
                break
    return {"pass": len([i for i in issues if i["severity"] == "FAIL"]) == 0, "issues": issues}


def check_satisfaction_progression(chapters: list[dict], idx: int) -> dict:
    if idx == 0:
        return {"pass": True, "issues": []}
    window = chapters[max(0, idx - 3):idx]
    hits = sum(1 for c in window if len((c.get("premise_must_hit") or "").strip()) > 10)
    current_hit = len((chapters[idx].get("premise_must_hit") or "").strip()) > 10
    if hits == 0 and not current_hit:
        return {"pass": True, "issues": [{"severity": "WARN", "dimension": "satisfaction_progression",
                                           "issue": "前3章无命题兑现，本章也未兑现"}]}
    return {"pass": True, "issues": []}


def check_hook_integration(ch: dict, hooks: list[dict]) -> dict:
    issues = []
    goal = (ch.get("goal") or "").strip()
    must_hit = (ch.get("premise_must_hit") or "").strip()
    combined = goal + " " + must_hit
    open_hooks = [h for h in hooks if h.get("status", "").lower()
                  in {"open", "🟡 未回收", "🟡 进行中", "active", "进行中"}]
    if len(open_hooks) > 5:
        used = sum(1 for h in open_hooks
                   if any(kw in combined for kw in re.findall(r"[一-鿿]{2,}", h.get("promise", ""))))
        if used == 0:
            issues.append({"severity": "WARN", "dimension": "hook_integration",
                           "issue": f"有{len(open_hooks)}条未回收钩子，本章未涉及任何一条"})
    return {"pass": len([i for i in issues if i["severity"] == "FAIL"]) == 0, "issues": issues}


def check_executability(ch: dict) -> dict:
    issues = []
    goal = (ch.get("goal") or "").strip()
    must_hit = (ch.get("premise_must_hit") or "").strip()
    if not goal:
        issues.append({"severity": "FAIL", "dimension": "executability", "issue": "缺少 Goal"})
    elif len(goal) < 15:
        issues.append({"severity": "WARN", "dimension": "executability", "issue": "Goal 过短（<15字）"})
    if not must_hit:
        issues.append({"severity": "FAIL", "dimension": "executability", "issue": "缺少 Premise Must Hit"})
    action_words = ["让读者", "推进", "揭露", "验证", "完成", "突破", "建立", "击败", "发现", "获得", "开启", "收束"]
    if goal and not any(w in goal for w in action_words):
        issues.append({"severity": "WARN", "dimension": "executability",
                       "issue": "Goal 缺少可执行动作词"})
    return {"pass": len([i for i in issues if i["severity"] == "FAIL"]) == 0, "issues": issues}


# ── main ──

def run_outline_review(book_dir: str | Path) -> dict:
    """Run the complete outline gate review and return result dict."""
    book = Path(book_dir).resolve()
    missing = [rel for rel in REQUIRED_FILE_LIST if not (book / rel).exists()]
    if missing:
        return {"status": "FAIL", "chapters": [],
                "issues": [{"severity": "FAIL", "issue": "缺少文件: " + ", ".join(missing)}]}

    premise_text = read_text(book / DIRECTOR_PREMISE)
    premise_promise = extract_premise_promise(premise_text)
    forbidden_zones = extract_forbidden_zones(premise_text)
    role_locks = extract_role_locks(premise_text)
    volume_zones = extract_volume_zones(premise_text)
    chapters = parse_chapter_queue(book / DIRECTOR_QUEUE)
    hooks = parse_hooks(book / TRUTH_PENDING_HOOKS)

    vol_map_path = find_volume_map(book)
    volume_ranges = parse_volume_map(vol_map_path) if vol_map_path else []

    if not chapters:
        return {"status": "FAIL", "chapters": [],
                "issues": [{"severity": "FAIL", "issue": "chapter_queue has no rows"}]}

    chapter_results = []
    pass_count = warn_count = fail_count = 0

    for idx, ch in enumerate(chapters):
        checks = {
            "volume_promise": check_volume_promise(ch, volume_zones, idx, len(chapters), volume_ranges),
            "premise_alignment": check_premise_alignment(ch, premise_text, forbidden_zones),
            "forbidden_zone": check_forbidden_zone(ch, forbidden_zones, role_locks),
            "satisfaction_progression": check_satisfaction_progression(chapters, idx),
            "hook_integration": check_hook_integration(ch, hooks),
            "executability": check_executability(ch),
        }
        ch_issues = []
        for dim, result in checks.items():
            ch_issues.extend(result["issues"])
        for i in ch_issues:
            i["chapter"] = ch["chapter"]
        has_fail = any(i["severity"] == "FAIL" for i in ch_issues)
        has_warn = any(i["severity"] == "WARN" for i in ch_issues)
        if has_fail:
            ch_status, fail_count = "FAIL", fail_count + 1
        elif has_warn:
            ch_status, warn_count = "WARN", warn_count + 1
        else:
            ch_status, pass_count = "PASS", pass_count + 1
        chapter_results.append({
            "chapter": ch["chapter"], "title_hint": ch["title_hint"],
            "status": ch_status, "issues": ch_issues,
            "checks": {k: {"pass": v["pass"], "issues_count": len(v["issues"])} for k, v in checks.items()},
        })

    status = "FAIL" if fail_count > 0 else ("WARN" if warn_count > 0 else "PASS")
    open_hooks = len([h for h in hooks if h.get("status", "").lower()
                      in {"open", "🟡 未回收", "🟡 进行中", "active", "进行中"}])
    return {
        "status": status, "total": len(chapters), "pass": pass_count,
        "warn": warn_count, "fail": fail_count,
        "premise_promise_length": len(premise_promise),
        "forbidden_zones": len(forbidden_zones), "role_locks": len(role_locks),
        "volume_zones": len(volume_zones), "open_hooks": open_hooks,
        "chapters": chapter_results,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-report", action="store_true", help="write report to director/outline_review.md")
    args = ap.parse_args()
    book = Path(args.book_dir).resolve()

    result = run_outline_review(book)
    now = now_iso()

    if result["status"] == "FAIL" and not result.get("chapters"):
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("结论：FAIL")
            print(f"依据：{book}")
            issues = result.get("issues", [])
            if issues:
                print("问题：" + issues[0].get("issue", "未知错误"))
            print("建议：运行 init_project / sync_inkos_state 补齐")
            print("下一步：停止")
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"=== outline-gate 审查报告 ===")
        print(f"时间：{now}")
        print(f"项目：{book}")
        print(f"结论：{result['status']}")
        print(f"章节：总计{result['total']}章 | PASS {result['pass']} | WARN {result['warn']} | FAIL {result['fail']}")
        print(f"依据：premise={result['premise_promise_length']}字; "
              f"forbidden_zones={result['forbidden_zones']}; role_locks={result['role_locks']}; "
              f"volume_zones={result['volume_zones']}; open_hooks={result['open_hooks']}")
        print("")
        for cr in result["chapters"]:
            icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[cr["status"]]
            print(f"--- Ch{cr['chapter']:04d} {cr['title_hint']} {icon} {cr['status']} ---")
            if not cr["issues"]:
                print("  OK 无问题")
            else:
                for i in cr["issues"]:
                    sev_icon = "[FAIL]" if i["severity"] == "FAIL" else "[WARN]"
                    print(f"  {sev_icon} [{i['dimension']}] {i['issue']}")
            print("")

        print("--- 建议 ---")
        st = result["status"]
        if st == "PASS":
            print("1. 所有章节已通过审查，可清空 blockers 设置 canWrite=true")
            print("2. 进入 execution-dispatch / build_task_package")
        elif st == "WARN":
            print("1. 修 WARN 后可考虑通过，但建议先逐章补强")
            print("2. 全部 WARN 项清除后再改 canWrite=true")
        else:
            print("1. 先修 FAIL 章节")
            print("2. FAIL 未清除不得生成任务包、不得写正文")
            print("3. 修后重跑 outline_gate_review.py")
        print(f"下一步：{'execution-dispatch' if st == 'PASS' else '修复 OUTLINE 章节' if st == 'FAIL' else '人工复核'}")

    if args.write_report:
        report_dir = book / "director"
        report_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Outline Gate 审查报告", "",
            f"时间：{now}", f"结论：{result['status']}", "",
            "## 摘要", "",
            f"| 维度 | 值 |", f"|---|---|",
            f"| 总章节 | {result['total']} |",
            f"| PASS | {result['pass']} |",
            f"| WARN | {result['warn']} |",
            f"| FAIL | {result['fail']} |",
            "", "## 逐章",
        ]
        for cr in result["chapters"]:
            lines.extend([
                "", f"### Ch{cr['chapter']:04d} {cr['title_hint']} — {cr['status']}", "",
            ])
            if not cr["issues"]:
                lines.append("  OK 无问题")
            else:
                for i in cr["issues"]:
                    lines.append(f"- **{i['severity']}** [{i['dimension']}] {i['issue']}")
        lines.extend([
            "", "## 下一步", "",
            "execution-dispatch" if result["status"] == "PASS"
            else "修复 OUTLINE 章节" if result["status"] == "FAIL"
            else "人工复核",
        ])
        write_text(report_dir / "outline_review.md", "\n".join(lines))
        print(f"\n报告已写入：{report_dir / 'outline_review.md'}")

    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
