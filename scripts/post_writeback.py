#!/usr/bin/env python3
"""Post-write state writeback for webnovel-director.

Usage:
  python post_writeback.py <book_dir> --chapter 31 --audit PASS \
    --summary "..." [--title "..."] [--state-change "..."] \
    [--resource-change "..."] [--particle "..."] [--hook "..."] [--write]

Dry-run by default. With --write, updates director/truth files only. It never
edits chapter prose. Designed to be called after chapter-review Level 1.
"""
from __future__ import annotations
from pathlib import Path
import sys
_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import read_text, write_text, strip_json5
import argparse, datetime, json, re

VALID_AUDITS = {"PASS", "WARN", "FAIL"}


def backup(path: Path) -> None:
    if path.exists():
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = path.with_name(path.name + f".bak.{stamp}")
        bak.write_text(read_text(path), encoding="utf-8")


def load_state(path: Path) -> dict:
    text = read_text(path)
    if not text:
        return {}
    try:
        return json.loads(strip_json5(text))
    except Exception:
        data = {}
        for key in ["bookId", "title", "status", "executor", "activeVolume", "currentChapter"]:
            m = re.search(rf"\b{key}\s*:\s*([^,\n}}]+)", text)
            if m:
                raw = m.group(1).strip().strip('"\'')
                data[key] = int(raw) if raw.isdigit() else raw
        return data


def dump_state_json5(state: dict) -> str:
    def v(x):
        if isinstance(x, bool): return "true" if x else "false"
        if isinstance(x, int): return str(x)
        if isinstance(x, list): return "[" + ", ".join(json.dumps(i, ensure_ascii=False) for i in x) + "]"
        return json.dumps(str(x), ensure_ascii=False)
    keys = ["bookId", "title", "status", "activeVolume", "currentChapter", "premiseFile", "lastAudit", "chapterQueue", "executor", "canWrite", "blockers", "lastAuditStatus", "updatedAt"]
    lines = ["{"]
    for i, k in enumerate(keys):
        if k in state:
            comma = "," if i < len(keys) - 1 else ""
            lines.append(f"  {k}: {v(state[k])}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def append_line(path: Path, line: str) -> None:
    old = read_text(path).rstrip()
    write_text(path, old + "\n" + line + "\n")


def update_queue(text: str, chapter: int, audit: str) -> tuple[str, bool]:
    new_lines=[]
    changed=False
    next_status = "已写" if audit == "PASS" else ("需修订" if audit == "WARN" else "阻塞")
    for line in text.splitlines():
        s=line.strip()
        if s.startswith("|") and "---" not in s and "Chapter" not in s:
            cells=[c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 6:
                n_raw=re.sub(r"\D", "", cells[0])
                if n_raw and int(n_raw) == chapter:
                    status_col = 7 if len(cells) >= 8 else 5
                    cells[status_col]=next_status
                    line="| " + " | ".join(cells) + " |"
                    changed=True
        new_lines.append(line)
    return "\n".join(new_lines) + "\n", changed


def make_last_audit(chapter: int, audit: str, summary: str, problems: list[str], suggestions: list[str], next_step: str) -> str:
    probs = "暂无" if not problems else "\n".join(f"- {p}" for p in problems)
    suggs = "暂无" if not suggestions else "\n".join(f"{i+1}. {s}" for i, s in enumerate(suggestions[:3]))
    return f"""# Last Audit

```text
结论：{audit}
依据：chapter-review Level 1；Ch{chapter:04d}
问题：
{probs}
建议：
{suggs}
下一步：{next_step}
```

## Summary

{summary}
"""



def upsert_section(text: str, chapter: int, content: str) -> str:
    """Replace or insert a ## Ch#### section."""
    header = "## Ch{:04d}".format(chapter)
    part = re.escape(header) + r".*?"
    delim = "(?:" + chr(10) + "## Ch" + chr(92) + "d{4} |" + chr(10) + "## [^C]|" + chr(92) + "Z)"
    pat = re.compile("(?:" + chr(10) + "|^)" + part + delim, re.S)
    NL = chr(10)
    if pat.search(text):
        return pat.sub(NL + header + NL + NL + content, text, count=1)
    else:
        return text.rstrip() + NL + NL + header + NL + NL + content + NL


def upsert_table_rows(text: str, chapter: int, new_rows: list) -> str:
    """Replace table rows for a given chapter."""
    lines = text.splitlines()
    marker = str(chapter)
    result = []
    for line in lines:
        s = line.strip()
        if s.startswith("|") and "---" not in s:
            first = s.strip("|").split("|")[0].strip()
            if re.sub(r"\D", "", first) == marker:
                continue
        result.append(line)
    while result and not result[-1].strip():
        result.pop()
    result.extend(new_rows)
    return chr(10).join(result) + chr(10)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--audit", required=True, choices=sorted(VALID_AUDITS))
    ap.add_argument("--summary", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--problem", action="append", default=[])
    ap.add_argument("--suggestion", action="append", default=[])
    ap.add_argument("--state-change", action="append", default=[])
    ap.add_argument("--resource-change", action="append", default=[])
    ap.add_argument("--particle", action="append", default=[])
    ap.add_argument("--hook", action="append", default=[])
    ap.add_argument("--expire-resource", action="append", default=[], help="mark resource expired: Chapter:Resource")
    ap.add_argument("--expire-particle", action="append", default=[], help="mark particle expired: Chapter:Particle")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    book = Path(args.book_dir).resolve()
    missing = [rel for rel in ["director/director_state.json5", "director/last_audit.md", "director/audit_log.md", "director/chapter_queue.md", "truth/current_state.md", "truth/resource_ledger.md", "truth/particle_ledger.md", "truth/pending_hooks.md"] if not (book/rel).exists()]
    if missing:
        status="FAIL"
        result={"status":status,"missing":missing,"write":False}
        if args.json: print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("结论：FAIL")
            print(f"依据：{book}")
            print("问题：缺少文件：" + ", ".join(missing))
            print("建议：先运行 init_project/validate_project/sync_inkos_state")
            print("下一步：停止")
        return 1

    state_path = book/"director/director_state.json5"
    state = load_state(state_path)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    next_step = "继续下一章" if args.audit == "PASS" else ("人工复核后可继续" if args.audit == "WARN" else "进入 repair-feedback，停止派发")
    blockers = [] if args.audit == "PASS" else ([f"Ch{args.chapter:04d} WARN 待复核"] if args.audit == "WARN" else [f"Ch{args.chapter:04d} FAIL 需修复"])

    changes=[]
    if args.audit == "PASS":
        state["currentChapter"] = max(int(state.get("currentChapter", 0) or 0), args.chapter)
        state["canWrite"] = True
    else:
        state["canWrite"] = False
    state["blockers"] = blockers
    state["lastAuditStatus"] = args.audit
    state["updatedAt"] = now
    for k, default in [("premiseFile","director/premise.md"),("lastAudit","director/last_audit.md"),("chapterQueue","director/chapter_queue.md"),("executor","inkos"),("status","drafting")]:
        state.setdefault(k, default)

    last_audit_text = make_last_audit(args.chapter, args.audit, args.summary, args.problem, args.suggestion, next_step)
    audit_row = f"| {now} | post-writeback | Ch{args.chapter:04d} | {args.audit} | {args.summary.replace('|','/')} | {next_step} |"
    q_text, q_changed = update_queue(read_text(book/"director/chapter_queue.md"), args.chapter, args.audit)

    # truth content: chapter-level sections that replace, not append
    state_content = "\n".join([f"- 审查：{args.audit}", f"- 摘要：{args.summary}"] + [f"- {x}" for x in args.state_change])
    expire_res_rows = []
    for ex in args.expire_resource:
        parts = ex.split(":", 1)
        resource = parts[1] if len(parts) > 1 else ex
        expire_res_rows.append(f"| {args.chapter} | {resource} | EXPIRED | {args.chapter} | post-writeback |")
    expire_part_rows = []
    for ex in args.expire_particle:
        parts = ex.split(":", 1)
        particle = parts[1] if len(parts) > 1 else ex
        expire_part_rows.append(f"| {args.chapter} | {particle} | expired |  | {args.chapter} | post-writeback |")
    res_rows = [f"| {args.chapter} | 写后变化 | {x.replace('|','//')} | 待下章核对 | post-writeback |" for x in args.resource_change]
    particle_rows = [f"| {args.chapter} | {x.replace('|','//')} | writeback | active | post-writeback |" for x in args.particle]
    hook_rows = [f"| H{args.chapter}-{i+1} | {args.chapter} | {x.replace('|','//')} | medium | 待定 | open | post-writeback |" for i, x in enumerate(args.hook)]

    if args.write:
        for rel in ["director/director_state.json5", "director/last_audit.md", "director/audit_log.md", "director/chapter_queue.md", "truth/current_state.md", "truth/resource_ledger.md", "truth/particle_ledger.md", "truth/pending_hooks.md"]:
            backup(book/rel)
        write_text(state_path, dump_state_json5(state))
        write_text(book/"director/last_audit.md", last_audit_text)
        append_line(book/"director/audit_log.md", audit_row)
        if q_changed:
            write_text(book/"director/chapter_queue.md", q_text)
        # Use upsert (replace-or-insert) for truth files
        write_text(book/"truth/current_state.md", upsert_section(read_text(book/"truth/current_state.md"), args.chapter, state_content))
        if expire_res_rows:
            write_text(book/"truth/resource_ledger.md", upsert_table_rows(read_text(book/"truth/resource_ledger.md"), args.chapter, expire_res_rows))
        if expire_part_rows:
            write_text(book/"truth/particle_ledger.md", upsert_table_rows(read_text(book/"truth/particle_ledger.md"), args.chapter, expire_part_rows))
        if res_rows:
            write_text(book/"truth/resource_ledger.md", upsert_table_rows(read_text(book/"truth/resource_ledger.md"), args.chapter, res_rows))
        if particle_rows:
            write_text(book/"truth/particle_ledger.md", upsert_table_rows(read_text(book/"truth/particle_ledger.md"), args.chapter, particle_rows))
        if hook_rows:
            write_text(book/"truth/pending_hooks.md", upsert_table_rows(read_text(book/"truth/pending_hooks.md"), args.chapter, hook_rows))
    result = {"status":"PASS", "audit":args.audit, "chapter":args.chapter, "write":args.write, "queueChanged":q_changed, "nextStep":next_step, "blockers":blockers}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("结论：PASS")
        print(f"依据：Ch{args.chapter:04d} audit={args.audit}; write={args.write}")
        print("问题：" + ("暂无" if args.audit == "PASS" else "; ".join(blockers)))
        print("建议：1. 核对 last_audit；2. 核对 truth files；3. " + ("可进入下一章任务包" if args.audit == "PASS" else "不要继续派发新章"))
        print(f"下一步：{next_step}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
