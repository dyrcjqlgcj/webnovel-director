#!/usr/bin/env python3
"""One-shot health check for a webnovel-director project.

Usage:
  python director_doctor.py <book_dir> [--json]

Runs lightweight checks equivalent to validate_project + inkos sync sanity +
outline queue sanity. It does not write files.
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


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--json", action="store_true")
    args=ap.parse_args()
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
