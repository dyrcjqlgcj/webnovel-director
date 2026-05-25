#!/usr/bin/env python3
"""One-shot health check for a webnovel-director project.

Usage:
  python director_doctor.py <book_dir> [--json] [--self]

  --self  Check webnovel-director itself (script health, not project health)
"""
from __future__ import annotations
from pathlib import Path
import argparse, json, re, subprocess, sys

REQUIRED = [
    "director/premise.md",
    "director/director_state.json5",
    "director/chapter_queue.md",
    "director/last_audit.md",
    "director/audit_log.md",
    "truth/current_state.md",
    "truth/resource_ledger.md",
    "truth/particle_ledger.md",
    "truth/pending_hooks.md",
]

# Key scripts that should exist and be runnable
KNOWN_SCRIPTS = [
    "concept_gate.py", "init_project.py", "director_doctor.py",
    "outline_gate_review.py", "outline_causal_check.py", "outline_iterate.py",
    "build_task_package.py", "review_chapter.py", "review_parallel.py",
    "post_writeback.py", "repair_plan.py", "validate_relationships.py",
    "audit_chapters.py", "check_cron_prompt.py", "extract_premise.py",
    "sync_inkos_state.py", "director_meta_iterate.py",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore") if path.exists() else ""


def latest_chapter(book: Path) -> int:
    best=0
    for f in (book/"chapters").glob("*.*") if (book/"chapters").exists() else []:
        m=re.match(r"^(\d{4})_", f.name)
        if m: best=max(best, int(m.group(1)))
    return best


def parse_state(text: str) -> dict:
    out={}
    for key in ["currentChapter", "canWrite", "lastAuditStatus"]:
        m=re.search(rf"\b{key}\s*:\s*([^,\n}}]+)", text)
        if m:
            raw=m.group(1).strip().strip('"\'')
            if raw in {"true","false"}: out[key]=(raw=="true")
            elif raw.isdigit(): out[key]=int(raw)
            else: out[key]=raw
    bm=re.search(r"\bblockers\s*:\s*\[([^\]]*)\]", text, re.S)
    if bm:
        out["blockers"]=[x.strip().strip('"\'') for x in bm.group(1).split(',') if x.strip()]
    return out


def parse_queue(text: str) -> list[dict]:
    rows=[]
    for line in text.splitlines():
        s=line.strip()
        if not s.startswith('|') or '---' in s or 'Chapter' in s: continue
        cells=[c.strip() for c in s.strip('|').split('|')]
        if len(cells)>=6 and re.sub(r"\D", "", cells[0]):
            rows.append({"chapter":int(re.sub(r"\D", "", cells[0])), "status":cells[5], "goal":cells[2], "premise":cells[3]})
    return rows


def find_director_root() -> Path:
    """Find webnovel-director skill root from this script's location."""
    return Path(__file__).resolve().parent.parent


def check_self(json_output: bool = False) -> int:
    """Check webnovel-director's own script health."""
    root = find_director_root()
    scripts_dir = root / "scripts"
    issues = []

    for script_name in KNOWN_SCRIPTS:
        sp = scripts_dir / script_name
        if not sp.exists():
            issues.append({"severity": "FAIL", "area": "scripts",
                          "issue": f"脚本缺失: {script_name}"})
            continue
        # Syntax check
        try:
            with open(sp, "r", encoding="utf-8-sig") as f:
                compile(f.read(), script_name, "exec")
        except SyntaxError as e:
            issues.append({"severity": "FAIL", "area": "scripts",
                          "issue": f"{script_name} 语法错误: {e}"})

    # Check that key reports/scripts exist per roadmap
    key_checks = [
        ("subsystems/scanner/guide.md", "scanner 子系统 guide"),
        ("subsystems/analyzer/guide.md", "analyzer 子系统 guide"),
        ("subsystems/writer/guide.md", "writer 子系统 guide"),
        ("subsystems/reviewer/guide.md", "reviewer 子系统 guide"),
        ("subsystems/polisher/guide.md", "polisher 子系统 guide"),
        ("references/craft/banned-words.md", "共享 craft: banned-words"),
        ("references/craft/hooks-chapter.md", "共享 craft: hooks-chapter"),
    ]
    for rel_path, label in key_checks:
        if not (root / rel_path).exists():
            issues.append({"severity": "WARN", "area": "files",
                          "issue": f"{label} 缺失: {rel_path}"})

    status = "FAIL" if any(i["severity"] == "FAIL" for i in issues) else ("WARN" if issues else "PASS")
    result = {"status": status, "total_scripts": len(KNOWN_SCRIPTS), "issues": issues}

    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"webnovel-director 自检: {status}")
        print(f"脚本: {len(KNOWN_SCRIPTS)} 个已注册")
        for i in issues:
            print(f"  - {i['severity']} [{i['area']}] {i['issue']}")
        if not issues:
            print("  全部通过")

    return 1 if status == "FAIL" else 0


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("book_dir", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self", action="store_true", help="Check webnovel-director script health")
    args=ap.parse_args()

    # --self mode: check script availability
    if getattr(args, 'self', False):
        return check_self(args.json)

    if not args.book_dir:
        ap.print_help()
        return 1

    book=Path(args.book_dir).resolve()
    issues=[]
    for rel in REQUIRED:
        p=book/rel
        if not p.exists(): issues.append({"severity":"FAIL","area":"files","issue":f"missing {rel}"})
        elif p.stat().st_size == 0: issues.append({"severity":"WARN","area":"files","issue":f"empty {rel}"})
    state=parse_state(read(book/"director/director_state.json5"))
    latest=latest_chapter(book)
    current=state.get("currentChapter")
    if latest and current is not None and latest != current:
        issues.append({"severity":"WARN","area":"sync","issue":f"chapters latest={latest}, director_state.currentChapter={current}"})
    blockers=state.get("blockers", [])
    can_write=state.get("canWrite")
    if can_write and blockers:
        issues.append({"severity":"FAIL","area":"gate","issue":"canWrite=true but blockers non-empty"})
    rows=parse_queue(read(book/"director/chapter_queue.md"))
    if not rows:
        issues.append({"severity":"WARN","area":"queue","issue":"chapter_queue has no chapter rows"})
    for r in rows:
        st=r["status"].lower()
        if any(x in st for x in ["pass","ready","待写","可写"]):
            if not r["goal"] or not r["premise"]:
                issues.append({"severity":"FAIL","area":"queue","issue":f"Ch{r['chapter']:04d} ready but missing goal/premise"})
    status="FAIL" if any(i["severity"]=="FAIL" for i in issues) else ("WARN" if issues else "PASS")
    result={"status":status,"book":str(book),"latestChapter":latest,"directorCurrentChapter":current,"canWrite":can_write,"blockers":blockers,"queueRows":len(rows),"issues":issues}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"结论：{status}")
        print(f"依据：book={book}; latest={latest}; directorCurrent={current}; queueRows={len(rows)}")
        print("问题：" + ("暂无" if not issues else ""))
        for i in issues:
            print(f"- {i['severity']} [{i['area']}] {i['issue']}")
        print("建议：先修 FAIL；WARN 可进入人工确认；canWrite 只允许 outline-gate PASS 后开启")
        print("下一步：" + ("可进入 execution-dispatch" if status == "PASS" else "修复/同步"))
    return 1 if status=="FAIL" else 0

if __name__ == "__main__":
    raise SystemExit(main())
