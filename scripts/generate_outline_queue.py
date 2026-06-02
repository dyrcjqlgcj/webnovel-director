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


def _get_volume_section(vm_text: str, vol_label: str) -> str:
    """Extract the detailed section for a specific volume from volume_map.md."""
    pattern = rf'^## 第{vol_label}卷'
    sections = []
    in_section = False
    for line in vm_text.split('\n'):
        if re.match(pattern, line):
            in_section = True
            sections = [line]
            continue
        if in_section:
            if re.match(r'^## ', line) and not re.match(pattern, line):
                break
            sections.append(line)
    return '\n'.join(sections) if sections else ''


def _batch_by_volume(start_ch: int, count: int, volumes: list, book_path: Path = None) -> list:
    """Split chapter range into per-volume batches.
    
    Rule: always split by CURRENT volume boundaries. At boundaries,
    pass BOTH volumes' context so the LLM can decide if the arc transitioned.
    """
    cum = 0
    for v in volumes:
        v['_start'] = cum + 1
        v['_end'] = cum + v['chapters']
        cum = v['_end']
    
    batches = []
    end_ch = start_ch + count - 1
    ch = start_ch
    while ch <= end_ch:
        vol = None
        vol_idx = -1
        for i, v in enumerate(volumes):
            if v['_start'] <= ch <= v['_end']:
                vol = v
                vol_idx = i
                break
        if vol is None:
            batches.append({'label': '', 'start': ch, 'count': end_ch - ch + 1, 'theme': ''})
            break
        
        batch_count = min(end_ch - ch + 1, vol['_end'] - ch + 1)
        batch = {'label': vol['num'], 'start': ch, 'count': batch_count, 'theme': vol.get('name', '')}
        
        # If this is the first chapter of a new volume, flag boundary context
        if vol_idx > 0 and ch == vol['_start']:
            prev_vol = volumes[vol_idx - 1]
            batch['boundary'] = True
            batch['prev_label'] = prev_vol['num']
            batch['prev_theme'] = prev_vol.get('name', '')
        
        batches.append(batch)
        ch += batch_count
    return batches


def _get_written_chapters(book_path: Path) -> set:
    """Return set of chapter numbers marked '已写' in chapter_queue.md."""
    qp = book_path / "director" / "chapter_queue.md"
    if not qp.exists():
        return set()
    text = read_text(qp)
    written = set()
    for line in text.split('\n'):
        s = line.strip()
        if s.startswith('|') and '---' not in s:
            cells = [c.strip() for c in s.strip('|').split('|')]
            if len(cells) >= 6:
                n_raw = re.sub(r'\D', '', cells[0])
                if n_raw:
                    ch_num = int(n_raw)
                    status_col = 7 if len(cells) >= 8 else 5
                    status = cells[status_col] if status_col < len(cells) else ''
                    if '已写' in status:
                        written.add(ch_num)
    return written


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
        # Generate detailed outlines via LLM - volume-aware batching
        from lib.llm import call_llm
        vol_text = read_text(vm_path) if vm_path else ""
        batches = _batch_by_volume(start_ch, num_chapters, volumes)
        
        MAX_RETRIES = 2
        all_ch_data = {}
        for batch in batches:
            b_start = batch['start']
            b_count = batch['count']
            b_end = b_start + b_count - 1
            
            # Build volume-specific context
            vol_ctx = f"## 卷纲表格\n{vol_text[:2000]}"
            if batch['label']:
                section = _get_volume_section(vol_text, batch['label'])
                if section:
                    vol_ctx += f"\n\n## 当前卷详情\n{section[:1500]}"
                    if not batch.get('boundary'):
                        vol_ctx += f"\n\nCh{b_start}-{b_end} 属于第{batch['label']}卷「{batch['theme']}」。按此卷主题和节奏设计。"
                if batch.get('boundary') and batch.get('prev_label'):
                    prev_section = _get_volume_section(vol_text, batch['prev_label'])
                    if prev_section:
                        vol_ctx += f"\n\n## 前卷详情（上一章所属的卷）\n{prev_section[:800]}"
            
            # Try generating this batch, retrying if chapters are missing
            for attempt in range(1, MAX_RETRIES + 2):
                # Determine which chapters still need to be generated
                pending = [ch for ch in range(b_start, b_end + 1) if ch not in all_ch_data]
                if not pending:
                    break
                pending_start, pending_end = pending[0], pending[-1]
                pending_count = pending_end - pending_start + 1
                
                # For retries, use smaller batches
                if attempt > 1 and pending_count > 3:
                    # Split into sub-batches of 2-3 chapters
                    sub_pending = pending[:3]
                    pending_start, pending_end = sub_pending[0], sub_pending[-1]
                    pending_count = pending_end - pending_start + 1
                    retry_note = f"（重试第{attempt}次，缩小批次到{pending_count}章）"
                elif attempt > 1:
                    retry_note = f"（重试第{attempt}次）"
                else:
                    retry_note = ""
                
                prompt = f"""你是网文大纲专家。根据以下信息为Ch{pending_start}-{pending_end}生成详细细纲。

{vol_ctx}

## 已有章节上下文（最近5章）
{last_few[:2000]}

## Premise
{premise_text[:1000]}

"""
                if batch.get('boundary') and pending_start == b_start:
                    prompt += f"""## 卷过渡判断
你正在生成的是第{batch['label']}卷「{batch['theme']}」的第1章。
上一章刚写完，其内容属于第{batch['prev_label']}卷「{batch['prev_theme']}」。

请根据上一章的细纲判断:
- 如果上一章已自然收尾前卷的弧光 → 按新卷主题生成本章
- 如果上一章仍在推进前卷主线 → 延续前卷的调性，暂不切换
"""
                prompt += f"""## 格式要求
| 章节 | 标题 | Goal（①-⑥ 具体情节步骤） | Premise Must Hit | Scenes | Words | Forbidden |

要求：
1. Goal列包含6个具体情节步骤，编号①-⑥，每步30-60字
2. 必须命中premise的核心概念（侦察、信息差、每日一格等）
3. 每章末尾有钩子衔接下一章
4. Forbidden列填写本章要避免的问题
5. Scenes=5, Words=3500
6. 如果这是新卷的第一章，需要设计新卷的开幕感
7. 所有内容写在一行内，不要在表格单元格内换行

直接输出表格行，从Ch{pending_start}开始。不要输出任何解释或前言。"""
                
                print(f"  [LLM] Ch{pending_start}-{pending_end} (第{batch['label']}卷「{batch['theme']}」) {retry_note}...")
                llm_response = call_llm(prompt, model="")
                
                if llm_response and len(llm_response) > 100:
                    parsed_count = 0
                    for line in llm_response.split('\n'):
                        s = line.strip()
                        m = re.match(r'\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|', s)
                        if m:
                            ch = int(m.group(1))
                            if ch not in all_ch_data:
                                all_ch_data[ch] = {'title': m.group(2).strip(), 'goal': m.group(3).strip(), 'pmh': m.group(4).strip()}
                                parsed_count += 1
                    
                    if parsed_count > 0:
                        print(f"    解析到 {parsed_count} 章")
                
                # Check if we got everything for this batch
                still_missing = [ch for ch in range(b_start, b_end + 1) if ch not in all_ch_data]
                if not still_missing:
                    break
                if attempt > 1 and len(still_missing) <= len(pending):
                    # Made partial progress, continue retrying remaining
                    pass
            
            # Warn about any chapters still missing after all retries
            final_missing = [ch for ch in range(b_start, b_end + 1) if ch not in all_ch_data]
            if final_missing:
                print(f"  [WARN] Ch{final_missing} 在 {MAX_RETRIES+1} 次尝试后仍无法生成，将使用占位符。请手动补充！")
        
        if all_ch_data:
            # Build table from parsed LLM data
            lines = [
                "# Chapter Queue",
                "",
                f"> LLM 生成 Ch{start_ch}-{start_ch + num_chapters - 1}",
                "| Ch | Title Hint | Goal | Premise Must Hit | Scenes | Words | Forbidden | Status |",
                "|---:|------|------|------------------|--------|-------|-----------|--------|",
            ]
            missing_count = 0
            for ch in range(start_ch, start_ch + num_chapters):
                if ch in all_ch_data:
                    d = all_ch_data[ch]
                    lines.append(f"| {ch:04d} | {d['title']} | {d['goal']} | {d['pmh']} | 5 | 3500 |  | 待写 |")
                else:
                    lines.append(f"| {ch:04d} | 第{ch:03d}章 | 待补充 | 待补充 | 5 | 3500 |  | 待写 |")
                    missing_count += 1
            if missing_count:
                print(f"  [WARN] 共 {missing_count} 章为占位符，需手动补充或重试")
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


def _shift_volumes(book_path: Path, old_last: int, new_last: int) -> None:
    """Shift volume boundaries when chapters overflow past the current volume end.
    
    If volume 1 was 1-60 and new chapters push to ch 65, this function:
    - Updates volume 1 to 1-65
    - Shifts all subsequent volumes by +5
    - Ex: 卷二 61-140 becomes 66-145, 卷三 141-250 becomes 146-255, etc.
    """
    vm_path = book_path / "director" / "volume_map.md"
    if not vm_path.exists():
        return
    
    text = read_text(vm_path)
    
    # Parse the volume table
    vol_entries = []
    table_start = None
    table_end = None
    lines = text.split('\n')
    in_table = False
    header_sep_count = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('|') and '---' in stripped:
            header_sep_count += 1
            if header_sep_count == 1:
                in_table = True
                continue
        if in_table and stripped.startswith('|'):
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            if len(cells) >= 2:
                # Parse volume number and chapter range
                ch_range = cells[1] if len(cells) > 1 else ''
                m = re.match(r'(\d+)\s*[-\u2013\u2014]\s*(\d+)', ch_range)
                if m:
                    vol_entries.append({
                        'line_idx': i,
                        'vol_label': cells[0].strip() if cells else '',
                        'start': int(m.group(1)),
                        'end': int(m.group(2)),
                        'raw_range': m.group(0),
                        'cells': cells
                    })
        elif in_table and not stripped.startswith('|'):
            if vol_entries:
                table_end = i
                break
    
    if not vol_entries:
        return
    
    # Find which volume contains old_last
    affected_vol = None
    for i, v in enumerate(vol_entries):
        if v['start'] <= old_last <= v['end']:
            affected_vol = i
            break
    
    if affected_vol is None:
        # old_last might be before the first volume or after the last
        if old_last < vol_entries[0]['start']:
            affected_vol = 0
        elif old_last > vol_entries[-1]['end']:
            affected_vol = len(vol_entries) - 1
        else:
            return
    
    v = vol_entries[affected_vol]
    if new_last <= v['end']:
        return  # No overflow
    
    overflow = new_last - v['end']
    print(f"  [卷边界] 第{v['vol_label']}卷溢出 {overflow} 章，向后平移后续卷...")
    
    # Update current volume's end too
    new_end_current = new_last
    new_range_current = f"{v['start']}-{new_end_current}"
    old_line = lines[v['line_idx']]
    new_line = old_line.replace(v['raw_range'], new_range_current)
    lines[v['line_idx']] = new_line
    # Update current volume's detailed header
    old_header_range = f"{v['start']}-{v['end']}"
    new_header_range = f"{v['start']}-{new_end_current}"
    for k in range(len(lines)):
        if f"第{v['vol_label']}卷" in lines[k] and old_header_range in lines[k]:
            lines[k] = lines[k].replace(old_header_range, new_header_range)
            break
    print(f"    第{v['vol_label']}卷: {v['start']}-{v['end']} -> {v['start']}-{new_end_current}")
    
    # Shift all volumes from affected_vol+1 onwards
    for j in range(affected_vol + 1, len(vol_entries)):
        ve = vol_entries[j]
        new_start = ve['start'] + overflow
        new_end = ve['end'] + overflow
        new_range = f"{new_start}-{new_end}"
        
        # Update the table row
        old_line = lines[ve['line_idx']]
        new_line = old_line.replace(ve['raw_range'], new_range)
        lines[ve['line_idx']] = new_line
        
        # Update the detailed header if it exists
        old_header_range = f"{ve['start']}-{ve['end']}"
        new_header_range = f"{new_start}-{new_end}"
        for k in range(len(lines)):
            if f"第{ve['vol_label']}卷" in lines[k] and old_header_range in lines[k]:
                lines[k] = lines[k].replace(old_header_range, new_header_range)
                break
        
        print(f"    第{ve['vol_label']}卷: {ve['start']}-{ve['end']} -> {new_start}-{new_end}")
    
    write_text(vm_path, '\n'.join(lines))
    print(f"  [卷边界] 已更新 volume_map.md")


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
