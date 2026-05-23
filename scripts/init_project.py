#!/usr/bin/env python3
"""Initialize a webnovel-director project skeleton.

Usage:
  python init_project.py <book_dir> --title "书名" [--book-id id] [--force]

Creates director/ and truth/ files from templates without overwriting existing
files unless --force is supplied.
"""
from __future__ import annotations
from pathlib import Path
import argparse, datetime, re, sys

SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = SKILL_ROOT / "templates"

FILES = {
    "director/premise.md": "premise.md",
    "director/director_state.json5": "director_state.json5",
    "director/chapter_queue.md": "chapter_queue.md",
    "director/last_audit.md": "last_audit.md",
    "director/audit_log.md": "audit_log.md",
    "truth/current_state.md": "current_state.md",
    "truth/resource_ledger.md": "resource_ledger.md",
    "truth/particle_ledger.md": "particle_ledger.md",
    "truth/relationship_graph.yaml": "relationship_graph.yaml",
    "truth/relationship_graph.yaml": "relationship_graph.yaml",
    "truth/pending_hooks.md": "pending_hooks.md",
    "story/outline/volume_map.md": "volume_map.md",
}

def slug(s: str) -> str:
    s = re.sub(r"\s+", "-", s.strip().lower())
    s = re.sub(r"[^\w\-\u4e00-\u9fff]", "", s)
    return s or "book"

def render(text: str, title: str, book_id: str) -> str:
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    return (text
        .replace("{{TITLE}}", title)
        .replace("{{BOOK_ID}}", book_id)
        .replace("{{UPDATED_AT}}", now)
        .replace("{{PREMISE_PROMISE}}", "待填写：这本书反复兑现给读者的核心承诺。"))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--title", required=True)
    ap.add_argument("--book-id")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    book = Path(args.book_dir).resolve()
    book_id = args.book_id or slug(args.title)
    created, skipped = [], []
    book.mkdir(parents=True, exist_ok=True)

    for rel, tmpl in FILES.items():
        dst = book / rel
        if dst.exists() and not args.force:
            skipped.append(rel)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = TEMPLATE_DIR / tmpl
        dst.write_text(render(src.read_text(encoding="utf-8"), args.title, book_id), encoding="utf-8")
        created.append(rel)

    print("结论：PASS")
    print(f"依据：book_dir={book}")
    if created:
        print("创建：" + ", ".join(created))
    if skipped:
        print("跳过：" + ", ".join(skipped))
    print("问题：" + ("已有文件未覆盖" if skipped else "暂无"))
    print("建议：1. 填写 premise.md 书名承诺与禁飞区；2. 运行 outline-gate；3. PASS 后再写入 chapter_queue")
    print("下一步：进入 outline-gate")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())


