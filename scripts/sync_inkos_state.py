#!/usr/bin/env python3
"""Sync an existing inkos-style project into webnovel-director state.

Usage:
  python sync_inkos_state.py <book_dir> [--write] [--json]

Read-only by default: prints a sync report. With --write, updates director/truth
files only; never edits chapters or story/*.md source files.
"""
from __future__ import annotations
from pathlib import Path
import sys
_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import read_text, write_text
import argparse, datetime, json, re, shutil


def latest_chapter(chapters: Path) -> tuple[int, str]:
    best = (0, "")
    if not chapters.exists():
        return best
    for f in chapters.iterdir():
        if not f.is_file() or f.suffix.lower() not in {".md", ".txt"}:
            continue
        m = re.match(r"^(\d{4})_(.+)\.(md|txt)$", f.name, re.I)
        if not m:
            continue
        n = int(m.group(1))
        if n > best[0]:
            best = (n, m.group(2))
    return best


def parse_current_focus(text: str) -> int | None:
    m = re.search(r"当前第\s*(\d+)\s*章", text)
    if m:
        return int(m.group(1))
    m = re.search(r"Ch\s*(\d+)\s*[-~至]", text, re.I)
    if m:
        return int(m.group(1)) - 1
    return None


def load_book_json(book: Path) -> dict:
    p = book / "book.json"
    if not p.exists():
        return {}
    try:
        return json.loads(read_text(p))
    except Exception:
        return {}


def simple_state_json5(book_id: str, title: str, current: int, can_write: bool, blockers: list[str]) -> str:
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    blockers_s = ", ".join(json.dumps(b, ensure_ascii=False) for b in blockers)
    cw = "true" if can_write else "false"
    return f'''{{
  bookId: {json.dumps(book_id, ensure_ascii=False)},
  title: {json.dumps(title, ensure_ascii=False)},
  status: "drafting",
  activeVolume: {1 if current <= 25 else 2 if current <= 70 else 3},
  currentChapter: {current},
  premiseFile: "director/premise.md",
  lastAudit: "director/last_audit.md",
  chapterQueue: "director/chapter_queue.md",
  executor: "inkos",
  canWrite: {cw},
  blockers: [{blockers_s}],
  lastAuditStatus: {json.dumps("PASS" if can_write else "WARN", ensure_ascii=False)},
  updatedAt: {json.dumps(now, ensure_ascii=False)}
}}
'''


def make_resource_ledger(book: Path, current: int) -> str:
    vol2 = read_text(book / "story" / "volume_2_summary.md")
    cur = read_text(book / "story" / "current_state.md")
    rows = []
    def add(res, change, state, evidence):
        rows.append(f"| {current} | {res} | {change} | {state} | {evidence} |")
    if "标记" in vol2.lower() or "印记" in vol2.lower():
        add("核心标记", "主角标记", "待确认", "story/volume_summary.md")
    if "碎片" in vol2 or "碎片" in cur or "物品" in vol2:
        add("核心物品", "同步/连接器线索推进", "按 story 状态继续核对", "story/current_state.md + volume_summary.md")
    if "阶" in vol2 or "阶段" in cur:
        add("主角阶位", "当前阶位推进中", "需逐章更新", "story/current_state.md")
    if not rows:
        rows.append(f"| {current} | 待同步 | 从 story 文件自动同步未识别明确资源 | 待人工补全 | sync_inkos_state.py |")
    return "# Resource Ledger\n\n> 由 sync_inkos_state.py 从 inkos story 文件生成摘要。后续写后必须逐章更新。\n\n| Chapter | Resource | Change | Balance/State | Evidence |\n|---:|---|---|---|---|\n" + "\n".join(rows) + "\n"


def make_particle_ledger(book: Path, current: int) -> str:
    texts = "\n".join(read_text(book / "story" / name) for name in ["volume_2_summary.md", "pending_hooks.md", "book_rules.md"])
    candidates = [
        ("世界符号系统", "rule", "解析/理解相关线索"),
        ("世界规则来源", "clue", "规则起源/建造者线索"),
        ("核心物品用途", "object", "物品/连接器/同步线索"),
        ("主角标记", "mark", "主角被世界规则识别"),
        ("无系统面板", "rule", "世界观硬规则"),
        ("小怪刷新", "rule", "不杀 BOSS 的刷新盲区"),
    ]
    rows=[]
    for key, typ, note in candidates:
        if key in texts or (key == "无系统面板" and "无系统" in texts) or (key == "小怪刷新" and "刷新" in texts):
            rows.append(f"| {current} | {key} | {typ} | active | {note} |")
    if not rows:
        rows.append(f"| {current} | 待同步 | unknown | active | 自动同步未识别，待人工补全 |")
    return "# Particle Ledger\n\n| Chapter | Particle | Type | Status | Notes |\n|---:|---|---|---|---|\n" + "\n".join(rows) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    book = Path(args.book_dir).resolve()
    meta = load_book_json(book)
    current, latest_title = latest_chapter(book / "chapters")
    focus_n = parse_current_focus(read_text(book / "story" / "current_focus.md"))
    title = meta.get("title") or book.name
    book_id = meta.get("id") or book.name
    issues=[]
    if current == 0:
        issues.append({"severity":"FAIL", "issue":"未找到 chapters/ 下的章节文件"})
    if focus_n is not None and current and focus_n != current:
        issues.append({"severity":"WARN", "issue":f"story/current_focus.md 当前章={focus_n}，但章节文件最新={current}"})
    for rel in ["story/current_state.md", "story/pending_hooks.md"]:
        if not (book / rel).exists():
            issues.append({"severity":"WARN", "issue":f"缺少 {rel}"})
    blockers = []
    if any(i["severity"] == "FAIL" for i in issues):
        blockers.append("inkos 同步存在 FAIL")
    if focus_n is not None and current and focus_n != current:
        blockers.append("story/current_focus.md 与最新章节不同步")
    blockers.append("chapter_queue 尚未通过 outline-gate")
    can_write = False
    report = {
        "book": str(book),
        "title": title,
        "bookId": book_id,
        "latestChapter": current,
        "latestTitle": latest_title,
        "focusChapter": focus_n,
        "issues": issues,
        "write": args.write,
    }
    if args.write:
        # Only director/truth files are touched.
        write_text(book / "director" / "director_state.json5", simple_state_json5(book_id, title, current, can_write, blockers))
        if (book / "story" / "current_state.md").exists():
            shutil.copyfile(book / "story" / "current_state.md", book / "truth" / "current_state.md")
        if (book / "story" / "pending_hooks.md").exists():
            shutil.copyfile(book / "story" / "pending_hooks.md", book / "truth" / "pending_hooks.md")
        write_text(book / "truth" / "resource_ledger.md", make_resource_ledger(book, current))
        write_text(book / "truth" / "particle_ledger.md", make_particle_ledger(book, current))
        now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        audit = f"| {now} | sync-inkos-state | story/chapter state | {'WARN' if issues else 'PASS'} | latest=Ch{current:04d} {latest_title}; focus={focus_n} | outline-gate |\n"
        audit_path = book / "director" / "audit_log.md"
        if audit_path.exists():
            old = read_text(audit_path)
            if audit not in old:
                write_text(audit_path, old.rstrip() + "\n" + audit)
        else:
            write_text(audit_path, "# Audit Log\n\n| Time | Module | Object | Result | Summary | Next |\n|---|---|---|---|---|---|\n" + audit)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "FAIL" if any(i["severity"] == "FAIL" for i in issues) else ("WARN" if issues else "PASS")
        print(f"结论：{status}")
        print(f"依据：latest=Ch{current:04d} {latest_title}; focus={focus_n}; book={book}")
        print("问题：" + ("暂无" if not issues else ""))
        for i in issues:
            print(f"- {i['severity']} {i['issue']}")
        print("建议：1. 同步 current_focus；2. 审 chapter_queue；3. outline-gate PASS 后再 canWrite=true")
        print("下一步：outline-gate")
    return 1 if any(i["severity"] == "FAIL" for i in issues) else 0

if __name__ == "__main__":
    raise SystemExit(main())
