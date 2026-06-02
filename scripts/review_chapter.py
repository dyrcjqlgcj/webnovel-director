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
import sys
_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import read_text, parse_chapter_queue
import argparse, datetime, json, re

# ── helpers ──

def load_task_package(path: Path) -> dict | None:
    text = read_text(path)
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


def load_from_chapter_queue(cq_path: Path, chapter: int) -> dict | None:
    """Extract a single chapter's data from chapter_queue.md table."""
    rows = parse_chapter_queue(cq_path)
    for r in rows:
        if r["chapter"] == chapter:
            goal = r.get("goal", "")
            premise_hit = r.get("premise_must_hit", "")
            forbidden = r.get("forbidden", "")
            return {
                "chapter": chapter,
                "title_hint": r.get("title_hint", ""),
                "chapter_goal": goal,
                "premise_must_hit": [premise_hit] if premise_hit and premise_hit != "-" else [],
                "forbidden": [forbidden] if forbidden and forbidden != "-" else [],
            }
    return None


# ── checkers ──

def check_length(text: str, target: int = 2500) -> dict:
    chars = len(text.replace("\n", "").replace(" ", ""))
    words_est = chars  # rough CJK approximation
    if words_est < 1000: return {"pass":False, "issue":f"过短（≈{words_est}字，目标{target}字）", "severity":"FAIL"}
    if words_est < 1800: return {"pass":True, "issue":f"偏短（≈{words_est}字）", "severity":"WARN"}
    if words_est > 5000: return {"pass":True, "issue":f"偏长（≈{words_est}字）", "severity":"WARN"}
    return {"pass":True, "issue":f"≈{words_est}字", "severity":"PASS"}

def check_hook(text: str) -> dict:
    tail = text[-600:] if len(text) > 600 else text
    # Weighted hook markers: strong(2pts) vs weak(1pt)
    strong = ["？", "!", "突然", "不是", "原来", "竟然", "居然", "只见"]
    weak = ["…", "——", "不再", "开始", "将要", "回头", "发现", "然而", "可是"]
    score = sum(2 for m in strong if m in tail) + sum(1 for m in weak if m in tail)
    # Also check paragraph count in tail (cliffhanger = short final paragraph)
    paras = [p for p in tail.split("\n\n") if p.strip()]
    if paras and len(paras[-1]) < 100:
        score += 1  # Short final paragraph = strong cliffhanger signal
    if score >= 4: return {"pass":True, "issue":"", "severity":"PASS"}
    if score >= 2: return {"pass":True, "issue":"章末钩子偏弱，建议增加反转/疑问/悬念", "severity":"WARN"}
    return {"pass":False, "issue":"章末 600 字未检测到有效钩子", "severity":"FAIL"}

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
        # Split premise on non-Chinese delimiters into meaningful chunks,
        # then extract 2-4 char windows for flexible matching
        chunks = re.split(r"[——：:（）()，。！？\s\-\"'=«»]+", term)
        keywords = []
        for chunk in chunks:
            if len(chunk) >= 2:
                keywords.append(chunk)  # full chunk
                # Also extract sliding 2-char windows for chunks >= 3 chars
                if len(chunk) >= 3:
                    for i in range(len(chunk) - 1):
                        w = chunk[i:i+2]
                        if w not in keywords:
                            keywords.append(w)
        keywords = list(dict.fromkeys(keywords))  # deduplicate
        if keywords and any(kw in text for kw in keywords):
            hits.append(term)
    if not must_hit: return {"pass":True, "issue":"任务包无 premise_must_hit", "severity":"WARN"}
    if len(hits) < max(1, len(must_hit) / 2): return {"pass":False, "issue":f"仅命中 {len(hits)}/{len(must_hit)} 条命题兑现", "severity":"FAIL"}
    if len(hits) < len(must_hit): return {"pass":True, "issue":f"命中 {len(hits)}/{len(must_hit)} 条", "severity":"WARN"}
    return {"pass":True, "issue":f"命中 {len(hits)}/{len(must_hit)} 条", "severity":"PASS"}

def check_structure(text: str) -> dict:
    # Check paragraph density only (dropped dialogue ratio — not meaningful)
    para_count = len([l for l in text.split("\n") if l.strip()])
    if para_count < 15:
        return {"pass": True, "issue": "段落偏少（叙事密度可能过高）", "severity": "WARN"}
    return {"pass": True, "issue": "结构合理", "severity": "PASS"}


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
        # Fallback: extract chapter row from chapter_queue.md
        cq_path = book / "director" / "chapter_queue.md"
        if not cq_path.exists():
            print("结论：FAIL")
            print(f"依据：任务包不存在且 chapter_queue 也不存在")
            print("下一步：运行 init_project / 补充 chapter_queue")
            return 1
        pkg = load_from_chapter_queue(cq_path, args.chapter)
        if not pkg:
            print("结论：FAIL")
            print(f"依据：chapter_queue 中未找到第{args.chapter}章")
            print("下一步：补充 chapter_queue 中的该章条目")
            return 1
    else:
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
            alt = book / "chapters" / f"第{ch_str}章-*.md"
            candidates = list(book.glob(f"chapters/第{ch_str}章-*.md")) + list(book.glob(f"chapters/第{ch_str}章-*.txt"))
            if candidates:
                tp_text = candidates[0]
            else:
                print("结论：FAIL")
                print(f"依据：章节文件不存在 {args.text}")
                print("下一步：停止")
                return 1
        chapter_text = read_text(tp_text)

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

    # Write review record to history file (shared with dashboard)
    rh_path = book / "director" / ".review_history.json"
    history = {}
    if rh_path.exists():
        try:
            history = json.loads(read_text(rh_path))
        except json.JSONDecodeError:
            pass
    history[str(args.chapter)] = {
        "time": datetime.datetime.now().strftime("%m/%d %H:%M"),
        "verdict": status,
        "issues": problems,
    }
    rh_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
