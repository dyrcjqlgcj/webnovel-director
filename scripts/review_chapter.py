#!/usr/bin/env python3
"""Level 1 chapter review: check written prose against task package.

Usage:
  python review_chapter.py <book_dir> --chapter 31 [--text chapter.txt] [--json]

Without --text, reads the task package only and does a light structure check.
With --text, reads the actual chapter prose and does full Level 1 review.
Outputs a PASS/WARN/FAIL report suitable as input for post_writeback.
"""
from __future__ import annotations
from pathlib import Path
import argparse, json, re

# ── helpers ──

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore") if path.exists() else ""

def load_task_package(path: Path) -> dict | None:
    text = read(path)
    if not text: return None
    pkg = {}
    for key, default in [("chapter",0), ("chapter_goal",""), ("title_hint",""), ("executor","inkos")]:
        m = re.search(rf"^{key}:\s*(.+)$", text, re.M)
        if m:
            val = m.group(1).strip().strip('"')
            pkg[key] = int(val) if key == "chapter" and val.isdigit() else val
        else:
            pkg[key] = default
    # Premise must hit list
    pkg["premise_must_hit"] = []
    in_sec = False
    for line in text.splitlines():
        if line.strip() == "premise_must_hit:": in_sec = True; continue
        if in_sec:
            if line.strip().startswith("- "):
                pkg["premise_must_hit"].append(line.strip()[2:].strip('"'))
            elif not line.strip().startswith(" ") and line.strip():
                break
    # Forbidden list
    pkg["forbidden"] = []
    in_sec = False
    for line in text.splitlines():
        if line.strip() == "forbidden:": in_sec = True; continue
        if in_sec:
            if line.strip().startswith("- "):
                pkg["forbidden"].append(line.strip()[2:].strip('"'))
            elif not line.strip().startswith(" ") and line.strip():
                break
    return pkg


# ── checkers ──

def check_length(text: str, target: int = 2500) -> dict:
    chars = len(text.replace("\n", "").replace(" ", ""))
    words_est = chars  # rough CJK approximation
    if words_est < 1000: return {"pass":False, "issue":f"过短（≈{words_est}字，目标{target}字）", "severity":"FAIL"}
    if words_est < 1800: return {"pass":True, "issue":f"偏短（≈{words_est}字）", "severity":"WARN"}
    if words_est > 5000: return {"pass":True, "issue":f"偏长（≈{words_est}字）", "severity":"WARN"}
    return {"pass":True, "issue":f"≈{words_est}字", "severity":"PASS"}

def check_hook(text: str) -> dict:
    tail = text[-400:] if len(text) > 400 else text
    hook_markers = ["？", "!", "…", "——", "不再", "开始", "将要", "回头", "发现", "突然", "不是", "原来"]
    hits = sum(1 for m in hook_markers if m in tail)
    if hits >= 2: return {"pass":True, "issue":"", "severity":"PASS"}
    if hits >= 1: return {"pass":True, "issue":"章末钩子弱，建议增加转折/悬念", "severity":"WARN"}
    return {"pass":False, "issue":"章末 400 字未检测到钩子标记", "severity":"FAIL"}

def check_forbidden(text: str, forbidden: list[str]) -> dict:
    hits = []
    for term in forbidden:
        if term and term in text:
            hits.append(term)
    if hits: return {"pass":False, "issue":"正文含禁用词：" + ", ".join(hits), "severity":"FAIL"}
    return {"pass":True, "issue":"", "severity":"PASS"}

def check_premise_hits(text: str, must_hit: list[str]) -> dict:
    hits = []
    for term in must_hit:
        if not term: continue
        # Check if at least 50% of the term's key chars appear
        keywords = re.findall(r"[\u4e00-\u9fff]{2,}", term)
        if keywords and any(kw in text for kw in keywords):
            hits.append(term)
    if not must_hit: return {"pass":True, "issue":"任务包无 premise_must_hit", "severity":"WARN"}
    if len(hits) < len(must_hit) / 2: return {"pass":False, "issue":f"仅命中 {len(hits)}/{len(must_hit)} 条命题兑现", "severity":"FAIL"}
    if len(hits) < len(must_hit): return {"pass":True, "issue":f"命中 {len(hits)}/{len(must_hit)} 条", "severity":"WARN"}
    return {"pass":True, "issue":f"命中 {len(hits)}/{len(must_hit)} 条", "severity":"PASS"}

def check_structure(text: str) -> dict:
    # Check for basic story beats
    para_count = len([l for l in text.split("\n") if l.strip()])
    dialogue_ratio = len(re.findall(r"[「「""'']", text)) / max(len(text), 1) * 1000
    has_action = bool(re.search(r"[\u4e00-\u9fff]{3,}[。；！]", text[-2000:]))
    issues = []
    if para_count < 15: issues.append("段落偏少（叙事密度可能过高）")
    if dialogue_ratio < 1: issues.append("对白密度极低")
    if not issues: return {"pass":True, "issue":"结构基本合理", "severity":"PASS"}
    return {"pass":True, "issue":"; ".join(issues), "severity":"WARN"}


# ── main ──

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--text", help="Chapter text file (omit for task-package-only check)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    book = Path(args.book_dir).resolve()
    ch_str = f"{args.chapter:04d}"

    # Find task package
    tp_candidates = [
        book / "director" / "task_packages" / f"{ch_str}.yaml",
        book / "director" / "task_packages" / f"{args.chapter}.yaml",
    ]
    tp = next((t for t in tp_candidates if t.exists()), None)
    if not tp:
        # Fallback: use chapter_queue row directly
        cq_path = book / "director" / "chapter_queue.md"
        if not cq_path.exists():
            print("结论：FAIL")
            print(f"依据：任务包不存在 {tp_candidates[0]} 且 chapter_queue 也不存在")
            print("下一步：运行 init_project / 补充 chapter_queue")
            return 1
        pkg = load_task_package(cq_path)
        if not pkg:
            print("结论：FAIL")
            print("依据：无法解析 chapter_queue")
            print("下一步：修复 chapter_queue 格式")
            return 1
        # Mark that we used chapter_queue fallback
        args.chapter = ch_num

    pkg = load_task_package(tp)
    if not pkg:
        print("结论：FAIL")
        print("依据：无法解析任务包")
        print("下一步：停止")
        return 1

    results = []
    chapter_text = ""
    if args.text:
        tp_text = Path(args.text)
        if not tp_text.exists():
            # Try chapters dir
            alt = book / "chapters" / f"{ch_str}_*.txt"
            candidates = list(book.glob(f"chapters/{ch_str}_*.txt")) + list(book.glob(f"chapters/{ch_str}_*.md"))
            if candidates:
                tp_text = candidates[0]
            else:
                print("结论：FAIL")
                print(f"依据：章节文件不存在 {args.text}")
                print("下一步：停止")
                return 1
        chapter_text = read(tp_text)

    if chapter_text:
        results.append(("字长", check_length(chapter_text)))
        results.append(("钩子", check_hook(chapter_text)))
        results.append(("禁词", check_forbidden(chapter_text, pkg.get("forbidden", []))))
        results.append(("命题兑现", check_premise_hits(chapter_text, pkg.get("premise_must_hit", []))))
        results.append(("结构", check_structure(chapter_text)))

    # Judge
    fails = [r for _, r in results if r["severity"] == "FAIL"]
    warns = [r for _, r in results if r["severity"] == "WARN"]
    has_fail = bool(fails)
    has_warn = bool(warns)

    if has_fail: status = "FAIL"
    elif has_warn: status = "WARN"
    elif chapter_text: status = "PASS"
    else: status = "WARN"

    # Build summary for post_writeback
    summary_parts = []
    if has_fail: summary_parts.append(f"{len(fails)}项FAIL")
    if has_warn: summary_parts.append(f"{len(warns)}项WARN")
    if not summary_parts: summary_parts.append("通过")
    summary = f"Ch{ch_str} 审查{'/'.join(summary_parts)}"

    state_changes = []
    problems = []
    suggestions = []
    for name, r in results:
        if r["severity"] == "FAIL":
            problems.append(f"[{name}] {r['issue']}")
            suggestions.append(f"修复 {name}")
        elif r["severity"] == "WARN":
            problems.append(f"[{name}] {r['issue']}")

    if args.json:
        out = {"status": status, "chapter": args.chapter, "checks": [{"name": n, "severity": r["severity"], "issue": r["issue"]} for n, r in results], "summary": summary, "problems": problems, "suggestions": suggestions[:3]}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"=== Ch{ch_str} Level 1 审查 ===")
        print(f"结论：{status}")
        for name, r in results:
            icon = {"PASS":"  OK","WARN":"WARN","FAIL":"FAIL"}[r["severity"]]
            extra = f" — {r['issue']}" if r["issue"] else ""
            print(f"  {icon} [{name}]{extra}")
        if problems:
            print("问题：")
            for p in problems: print(f"  - {p}")
        if suggestions:
            print("建议：")
            for i, s in enumerate(suggestions[:3], 1): print(f"  {i}. {s}")
        if status == "PASS":
            print("下一步：post_writeback --audit PASS")
        elif status == "WARN":
            print("下一步：人工复核后 post_writeback --audit PASS|WARN")
        else:
            print("下一步：repair-feedback，修后重审")

    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
