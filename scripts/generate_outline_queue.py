#!/usr/bin/env python3
"""Generate a chapter_queue.md skeleton from volume_map.md.

Usage:
  python generate_outline_queue.py <book_dir> [--chapters 20] [--json]

Reads volume_map.md and premise.md, generates a chapter_queue.md table
with Goal / Premise Must Hit / Forbidden columns pre-filled with
context-aware templates. User reviews and refines after generation.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import read_text, write_text, parse_chapter_queue  # noqa: E402


def parse_volumes(text: str) -> list[dict]:
    """Parse volume structure from volume_map.md."""
    vols = []
    vol_pattern = re.compile(r"第([一二三四五六七八九十\d]+)卷[：:]\s*(.+)", re.MULTILINE)
    for m in vol_pattern.finditer(text):
        name = m.group(2).strip()
        chapters = 0
        range_match = re.search(r"(\d+)\s*[-–—]\s*(\d+)\s*章", name)
        if range_match:
            chapters = int(range_match.group(2)) - int(range_match.group(1)) + 1
        else:
            ch_match = re.search(r"(\d+)\s*章", name)
            if ch_match:
                chapters = int(ch_match.group(1))
        vols.append({"num": m.group(1), "name": name, "chapters": chapters})
    return vols


def extract_concepts(premise_text: str) -> dict:
    """Extract core concepts from premise.md for template injection."""
    concepts = {"title": "", "protagonist": "", "core_ability": "", "forbidden": []}

    m = re.search(r"书名承诺[：:]\s*\n*[> ]*(.+)", premise_text)
    if m:
        concepts["title"] = m.group(1).strip()

    m = re.search(r"(?:主角|主角处境)[：:]\s*\n*[*_]{0,2}\s*(.+)", premise_text)
    if m:
        concepts["protagonist"] = m.group(1).strip()

    m = re.search(r"(?:金手指|核心爽点机制|核心能力)[：:]\s*\n*[*_]{0,2}\s*(.+)", premise_text)
    if m:
        concepts["core_ability"] = m.group(1).strip()

    # Extract forbidden zones
    for m in re.finditer(r"禁飞区\s*\d*[：:]\s*(.+)", premise_text):
        concepts["forbidden"].append(m.group(1).strip())

    return concepts


def generate_chapter_entry(ch_num: int, vol_name: str, concepts: dict,
                           prev_goal: str = "") -> dict:
    """Generate a single chapter queue entry."""
    goal = ""
    premise_hit = ""
    forbidden = ""

    # Chapter 1: establish world + protagonist
    if ch_num == 1:
        goal = f"建立世界观基础，{concepts.get('protagonist', '主角')}首次接触核心机制"
        premise_hit = f"书名承诺首次兑现：{concepts.get('core_ability', '核心能力')}的初现"
    # Every 5th chapter: growth/payoff milestone
    elif ch_num % 10 == 0:
        goal = f"高潮章节——{concepts.get('protagonist', '主角')}的关键突破"
        premise_hit = f"爽点集中释放：{concepts.get('core_ability', '能力')}进化/关键战斗获胜"
    elif ch_num % 5 == 0:
        goal = f"阶段性进展——能力/资源的实质性获得"
        premise_hit = f"成长里程碑：技能/装备/地位可见变化"
    # Normal chapters
    else:
        goal = f"推进主线——承接上章事件发展"
        premise_hit = f"推进{concepts.get('core_ability', '核心能力')}相关线索"

    if prev_goal:
        goal = f"承接上章——{goal}"

    # Add forbidden zone checks
    if concepts.get("forbidden"):
        forbidden = f"避免：{'、'.join(concepts['forbidden'][:2])}"

    return {
        "chapter": ch_num,
        "title_hint": f"第{ch_num:03d}章",
        "goal": goal,
        "premise_must_hit": premise_hit,
        "forbidden": forbidden,
        "status": "待写",
    }


def generate_queue(book_dir: str, num_chapters: int = 20, start_ch: int = 1, use_llm: bool = False) -> str:
    """Generate chapter_queue.md content starting from start_ch.
    
    If use_llm=True, generates detailed 6-scene outlines via LLM.
    Otherwise falls back to template placeholder generation.
    """
    book = Path(book_dir)

    # Find volume_map and premise
    vm_paths = [book / "director" / "volume_map.md",
                book / "story" / "outline" / "volume_map.md"]
    vm_path = next((p for p in vm_paths if p.exists()), None)
    pm_paths = [book / "director" / "premise.md"]
    pm_path = next((p for p in pm_paths if p.exists()), None)

    if not pm_path:
        print("ERROR: premise.md not found. Run init_project.py first.")
        sys.exit(1)

    premise_text = read_text(pm_path)
    concepts = extract_concepts(premise_text)

    volumes = parse_volumes(read_text(vm_path)) if vm_path else []

    # Read existing queue for context
    queue_path = book / "director" / "chapter_queue.md"
    existing_queue = read_text(queue_path) if queue_path.exists() else ""
    
    # Build combined context for LLM
    vol_context = read_text(vm_path) if vm_path else ""
    last_few = ""
    if existing_queue:
        # Extract last 5 chapters from existing queue for continuity
        existing_lines = existing_queue.split('\n')
        ch_lines = [l for l in existing_lines if re.match(r'\| \d+ \|', l)]
        if ch_lines:
            last_few = "最近5章的细纲：\n" + "\n".join(ch_lines[-5:])

    if use_llm:
        # Generate detailed outlines via LLM
        from lib.llm import call_llm
        prompt = f"""你是网文大纲专家。请根据以下卷纲和上下文，为Ch{start_ch}-{start_ch+num_chapters-1}生成详细的章节细纲。

## 卷纲
{vol_context[:3000]}

## 已有章节上下文
{last_few[:2000]}

## Premise
{premise_text[:1000]}

## 格式要求
对每一章,按以下格式输出（用Markdown表格）：

| 章节 | 标题 | Goal（①-⑥ 具体情节步骤） | Premise Must Hit（本章要兑现的核心主题） | Scenes | Words | Forbidden |

要求：
1. Goal列包含6个具体情节步骤，编号①-⑥，每步30-60字
2. 必须命中premise的核心概念（侦察、信息差、每日一格等）
3. 每章末尾有钩子，衔接下一章
4. Forbidden列填写本章要避免的问题
5. Scenes=5, Words=3500
6. Status=待写

直接输出表格行，从Ch{start_ch}开始。"""
        
        print(f"  [LLM] 正在生成 Ch{start_ch}-{start_ch+num_chapters-1} 详细细纲 ...")
        llm_response = call_llm(prompt, model="")
        
        if llm_response and len(llm_response) > 200:
            # Parse LLM response into chapter entries
            lines = [
                "# Chapter Queue",
                "",
                f"> LLM 生成 Ch{start_ch}-{start_ch+num_chapters-1}",
                f"| Ch | Title Hint | Goal | Premise Must Hit | Scenes | Words | Forbidden | Status |",
                "|---:|------|------|------------------|--------|-------|-----------|--------|",
            ]
            
            ch_data = {}
            for line in llm_response.split('\n'):
                s = line.strip()
                if not s.startswith('|') or '---' in s or '章节' in s or 'Title' in s or 'Goal' in s or 'Ch' in s[:5] and '---' not in s:
                    # Try to match chapter rows
                    m = re.match(r'\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|', s)
                    if m:
                        ch = int(m.group(1))
                        title = m.group(2).strip()
                        goal = m.group(3).strip()
                        pmh = m.group(4).strip()
                        ch_data[ch] = {"title": title, "goal": goal, "pmh": pmh}
            
            for ch in range(start_ch, start_ch + num_chapters):
                if ch in ch_data:
                    d = ch_data[ch]
                    lines.append(f"| {ch:04d} | {d['title']} | {d['goal']} | {d['pmh']} | 5 | 3500 |  | 待写 |")
                else:
                    # Fallback for missing chapters
                    lines.append(f"| {ch:04d} | 第{ch:03d}章 | 待补充 | 待补充 | 5 | 3500 |  | 待写 |")
            
            return "\n".join(lines)
        else:
            print("  [WARN] LLM 调用失败或无响应，回退到模板生成")
    
    # Fallback: template generation
    lines = [
        "# Chapter Queue",
        "",
        f"> 自动生成于 {datetime.datetime.now().astimezone().isoformat(timespec='minutes')}",
        f"> 项目：{book.name}",
        f"> 书名：{concepts.get('title', '未设定')}",
        "",
        "| Ch | 标题 | Goal | Premise Must Hit | Scenes | Words | Forbidden | Status |",
        "|---:|------|------|------------------|--------|-------|-----------|--------|",
    ]

    prev_goal = ""
    for ch_num in range(start_ch, start_ch + num_chapters):
        entry = generate_chapter_entry(ch_num, "", concepts, prev_goal)
        prev_goal = entry["goal"]
        lines.append(
            f"| {entry['chapter']:04d} | {entry['title_hint']} | "
            f"{entry['goal']} | {entry['premise_must_hit']} | "
            f" |  | "
            f"{entry['forbidden']} | {entry['status']} |"
        )

    return "\n".join(lines)


def generate_from_index(book_dir: str, start_ch: int = 1, count: int = 20) -> str:
    """Generate chapter_queue from chapter_index.md (preferred method)."""
    book = Path(book_dir)
    idx_paths = [book / "story" / "outline" / "chapter_index.md"]
    idx_path = next((p for p in idx_paths if p.exists()), None)

    if not idx_path:
        print("ERROR: chapter_index.md not found. Run without --from-index to use template generation.")
        sys.exit(1)

    pm_path = book / "director" / "premise.md"
    premise_text = read_text(pm_path) if pm_path.exists() else ""
    concepts = {}
    if premise_text:
        m = re.search(r"书名承诺[：:]\s*\n*[> ]*(.+)", premise_text); concepts["title"] = m.group(1).strip() if m else ""
        m = re.search(r"(?:主角|主角处境)[：:]\s*\n*[*_]{0,2}\s*(.+)", premise_text); concepts["protagonist"] = m.group(1).strip() if m else ""

    idx_text = read_text(idx_path)
    entries = {}
    for line in idx_text.splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "Chapter" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue
        # Parse chapter range like "1" or "31-35"
        range_match = re.match(r"(\d+)(?:\s*[-–—]\s*(\d+))?", cells[0])
        if not range_match:
            continue
        ch_start = int(range_match.group(1))
        ch_end = int(range_match.group(2)) if range_match.group(2) else ch_start
        title = cells[1].strip() if len(cells) > 1 else ""
        event = cells[2].strip() if len(cells) > 2 else ""
        for ch in range(ch_start, ch_end + 1):
            entries[ch] = {"title": title, "event": event}

    # Extract forbidden zones from premise
    forbidden = ""
    if premise_text:
        fbs = re.findall(r"禁飞区\s*\d*[：:]\s*(.+)", premise_text)
        if fbs:
            forbidden = "; ".join(fbs[:2])

    lines = [
        "# Chapter Queue",
        "",
        f"> 从 chapter_index.md 生成 Ch{start_ch}-{start_ch+count-1}",
        "",
        "| Ch | Title Hint | Goal | Premise Must Hit | Scenes | Words | Forbidden | Status |",
        "|---:|------|------|------------------|--------|-------|-----------|--------|",
    ]

    for ch_num in range(start_ch, start_ch + count):
        entry = entries.get(ch_num, {"title": "", "event": ""})
        title = entry["title"] or f"第{ch_num:03d}章"
        event = entry["event"]
        goal = f"让读者{event}" if event else "待补充"
        status = "待写"
        lines.append(
            f"| {ch_num:04d} | {title} | {goal} | 待补充 |  |  | {forbidden} | {status} |"
        )

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="从卷纲+premise 自动生成 chapter_queue.md 骨架")
    ap.add_argument("book_dir")
    ap.add_argument("--chapters", type=int, default=20,
                    help="生成的章节数 (default: 20)")
    ap.add_argument("--from-index", action="store_true",
                    help="从 chapter_index.md 读取标题和事件生成（优先）")
    ap.add_argument("--start-chapter", type=int, default=1,
                    help="起始章节号 (配合 --from-index 使用)")
    ap.add_argument("--llm", action="store_true",
                    help="使用 LLM 生成详细细纲（而非模板占位）")
    ap.add_argument("--json", action="store_true",
                    help="JSON 输出到 stdout，不写文件")
    ap.add_argument("--dry-run", action="store_true",
                    help="仅输出预览，不写入文件")
    args = ap.parse_args()

    if args.from_index:
        content = generate_from_index(args.book_dir, args.start_chapter, args.chapters)
    else:
        content = generate_queue(args.book_dir, args.chapters, use_llm=args.llm)

    if args.json:
        print(content)
        return 0

    if args.dry_run:
        print(content)
        print(f"\n[dry-run] 以上内容不会写入文件。")
        return 0

    output_path = Path(args.book_dir) / "director" / "chapter_queue.md"
    if output_path.exists():
        # Read existing chapters to avoid overwriting
        bak = output_path.with_suffix(".md.bak")
        write_text(bak, read_text(output_path))
        print(f"已备份: {bak}")
        
        # Find last chapter number in existing queue
        existing_text = read_text(output_path)
        existing_chapters = parse_chapter_queue(existing_text)
        if existing_chapters:
            last_ch = max(c["chapter"] for c in existing_chapters)
            # Generate only NEW chapters starting from last+1
            if args.from_index:
                content = generate_from_index(args.book_dir, last_ch + 1, args.chapters)
            else:
                content = generate_queue(args.book_dir, args.chapters, start_ch=last_ch + 1, use_llm=args.llm)
            # Extract only the table rows from generated content (skip header)
            new_lines = content.split('\n')
            try:
                row_start = next(i for i, l in enumerate(new_lines) if l.startswith('|---')) + 1
            except StopIteration:
                row_start = 0
            new_rows = '\n'.join(new_lines[row_start:])
            # Append new rows to existing file
            result = existing_text.rstrip('\n') + '\n' + new_rows
            write_text(output_path, result)
            new_ch = len([r for r in new_rows.split('\n') if r.strip().startswith('|') and not r.strip().startswith('|--')])
            print(f"已追加 {new_ch} 章 (Ch{last_ch+1}-{last_ch+new_ch}) -> {output_path}")
        else:
            write_text(output_path, content)
            print(f"已生成: {output_path}")
    else:
        write_text(output_path, content)
        print(f"已生成: {output_path}")
    print(f"  章节数: {args.chapters}")
    print(f"  下一步: 逐章审查并细化 Goal/Premise Must Hit/Forbidden 列")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
