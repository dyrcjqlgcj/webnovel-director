#!/usr/bin/env python3
"""Generate a single next-chapter outline. Used by dashboard and CLI.
Usage: python gen_next.py <book_dir> <current_chapter>"""
import sys, re
from pathlib import Path

_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import read_text, write_text, parse_chapter_queue
from lib.llm import call_llm

book = Path(sys.argv[1])
ch = int(sys.argv[2])
next_ch = ch + 1

premise = read_text(book / "director" / "premise.md")
vm_text = read_text(book / "director" / "volume_map.md")

ch_text = ""
for d in ["story/chapters", "chapters"]:
    cd = book / d
    if cd.exists():
        for pat in [f"第*{ch:03d}*章*.md", f"第*{ch}*章*.md"]:
            cand = sorted(cd.glob(pat))
            if cand: ch_text = read_text(cand[0])[:800]; break
    if ch_text: break

qp = book / "director" / "chapter_queue.md"
queue = parse_chapter_queue(qp) if qp.exists() else []
prev = "\n".join(f"Ch{c['chapter']:04d}: {(c.get('goal') or '')[:100]}"
    for c in queue if len((c.get('goal') or '')) > 30)[-4:]

prompt = f"""你是网文大纲专家。为《领地战争：每日一格》生成第{next_ch}章细纲。

## Premise
{premise[:1200]}

## 卷纲
{vm_text[:1200]}

## 刚写完的第{ch}章正文开头
{ch_text[:600]}

## 前文细纲
{prev}

## 格式要求
| {next_ch:04d} | 章名 | ①步骤1(30-60字) ②步骤2 ③步骤3 ④步骤4 ⑤步骤5 ⑥步骤6 | MustHit |

Goal必须6个步骤①-⑥编号，每步30-60字。Hit premise核心概念。不要用|字符。直接输出。"""

resp = call_llm(prompt, model="", max_tokens=2000, timeout=120)
if not resp or len(resp) < 30:
    print(f"FAIL: LLM no response for Ch{next_ch:04d}")
    sys.exit(1)

for line in resp.split("\n"):
    s = line.strip()
    if not s.startswith("|") or "---" in s: continue
    cells = [c.strip() for c in s.strip("|").split("|")]
    if len(cells) < 3: continue
    try: cn = int(re.sub(r"\D", "", cells[0]))
    except: continue
    if cn != next_ch: continue
    title = cells[1] or f"第{next_ch:03d}章"
    rest = " | ".join(cells[2:])
    goal = rest; pmh = ""
    for sep in ["| MustHit:", "| MustHit", "MustHit:", "MustHit "]:
        if sep in rest:
            parts = rest.split(sep, 1)
            goal = parts[0].strip()
            pmh = parts[1].strip() if len(parts) > 1 else ""
            break
    if len(goal) < 30: continue
    new_row = f"\n| {next_ch:04d} | {title} | {goal} | {pmh} | 5 | 3500 |  | 待写 |"
    write_text(qp, read_text(qp).rstrip("\n") + new_row)
    print(f"Ch{next_ch:04d}: {title}")
    sys.exit(0)

print(f"FAIL: cannot parse LLM response for Ch{next_ch:04d}")
sys.exit(1)
