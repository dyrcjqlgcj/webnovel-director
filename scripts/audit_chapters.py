#!/usr/bin/env python3
"""Level 1 quick chapter audit for webnovel-director.

Usage:
  python audit_chapters.py <chapters_dir> --start 1 --end 10 [--premise premise.md]

This is a fast filter, not a deep literary review.
"""
from pathlib import Path
import sys
_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import read_text
import argparse, re, json

DEFAULT_TERMS = {
    "premise": ["别人", "通关", "刷怪", "复利", "主线", "禁飞区"],
    "drift": ["建公会", "统一城市", "抢首通", "组队推", "正面击败", "收编"],
    "craft": ["章末", "转场", "伏笔", "目标", "后果"],
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters_dir")
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--premise")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.chapters_dir)
    files = sorted(root.glob("*.txt"))
    out=[]
    for f in files:
        m=re.match(r"^(\d{4})_", f.name)
        if not m: continue
        n=int(m.group(1))
        if args.start and n<args.start: continue
        if args.end and n>args.end: continue
        t=read_text(f)
        counts={k:{term:t.count(term) for term in terms} for k,terms in DEFAULT_TERMS.items()}
        drift_hits=[term for term,c in counts["drift"].items() if c]
        no_premise = all(c==0 for c in counts["premise"].values())
        status="PASS"
        notes=[]
        if drift_hits:
            status="FAIL"; notes.append("drift:"+",".join(drift_hits))
        elif no_premise:
            status="WARN"; notes.append("no premise terms")
        out.append({"chapter":n,"file":f.name,"status":status,"notes":notes,"counts":counts})
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for r in out:
            print(f"Ch{r['chapter']:04d} {r['status']} {r['file']} {'; '.join(r['notes'])}")
if __name__ == "__main__": main()
