#!/usr/bin/env python3
"""Check whether a cron writing prompt obeys webnovel-director gates.

Usage:
  python check_cron_prompt.py <prompt.txt> <book_dir|premise.md> [--json]

The checker is conservative: it flags prompts that ask to write/continue chapters
without mentioning director files, canWrite/blockers, chapter_queue, and post-write
review/writeback.
"""
from __future__ import annotations
from pathlib import Path
import sys
_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import read_text
import argparse, json, re

REQUIRED_MENTIONS = [
    ("director/premise.md", ["director/premise.md", "premise.md"]),
    ("director/director_state.json5", ["director_state", "director/director_state.json5"]),
    ("director/chapter_queue.md", ["chapter_queue", "director/chapter_queue.md"]),
    ("director/last_audit.md", ["last_audit", "director/last_audit.md"]),
    ("truth/current_state.md", ["truth/current_state.md", "current_state.md"]),
    ("truth/pending_hooks.md", ["truth/pending_hooks.md", "pending_hooks.md"]),
]
GATE_TERMS = ["canWrite", "blockers", "outline-gate", "premise-guard"]
POST_TERMS = ["chapter-review", "Level 1", "post_writeback", "last_audit", "audit_log", "回写"]
WRITE_TERMS = ["写", "续写", "下一章", "正文", "生成第", "chapter", "write"]
BYPASS_TERMS = ["不用审", "跳过审查", "直接写", "不需要读取", "忽略premise", "忽略 director"]


def contains_any(text: str, terms: list[str]) -> bool:
    lo = text.lower()
    return any(t.lower() in lo for t in terms)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("target", help="book_dir or premise.md")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    prompt_path = Path(args.prompt)
    target = Path(args.target)
    prompt = read_text(prompt_path)
    issues=[]
    if not prompt:
        issues.append({"severity":"FAIL", "issue":"prompt 为空或无法读取"})
    is_write = contains_any(prompt, WRITE_TERMS)
    if is_write:
        for label, terms in REQUIRED_MENTIONS:
            if not contains_any(prompt, terms):
                issues.append({"severity":"FAIL", "issue":f"写作 cron 未提及必读文件：{label}"})
        if not contains_any(prompt, GATE_TERMS):
            issues.append({"severity":"FAIL", "issue":"写作 cron 未提及 canWrite/blockers/outline-gate/premise-guard 闸门"})
        if not contains_any(prompt, POST_TERMS):
            issues.append({"severity":"WARN", "issue":"写作 cron 未明确写后 chapter-review/post_writeback 回写"})
    for term in BYPASS_TERMS:
        if term.lower() in prompt.lower():
            issues.append({"severity":"FAIL", "issue":f"prompt 含绕过导演闸门表述：{term}"})
    # Optional target sanity.
    if target.is_dir():
        for rel in ["director/premise.md", "director/director_state.json5", "director/chapter_queue.md"]:
            if not (target / rel).exists():
                issues.append({"severity":"WARN", "issue":f"目标项目缺少 {rel}"})
    elif target.name == "premise.md" and not target.exists():
        issues.append({"severity":"WARN", "issue":"premise.md 不存在"})
    status = "FAIL" if any(i["severity"] == "FAIL" for i in issues) else ("WARN" if issues else "PASS")
    result={"status":status,"isWritePrompt":is_write,"issues":issues}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"结论：{status}")
        print(f"依据：prompt={prompt_path}; write_prompt={is_write}")
        print("问题：" + ("暂无" if not issues else ""))
        for i in issues:
            print(f"- {i['severity']} {i['issue']}")
        print("建议：写作 cron 必须先读 director/truth，检查 canWrite/blockers，写后执行 chapter-review/post_writeback")
        print("下一步：" + ("可保留" if status == "PASS" else "修复 cron prompt"))
    return 1 if status == "FAIL" else 0

if __name__ == "__main__":
    raise SystemExit(main())
