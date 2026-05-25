#!/usr/bin/env python3
"""Generate a chapter_queue.md skeleton from volume_map.md.

Usage:
  python generate_outline_queue.py <book_dir> [--chapters 20] [--json]

Reads volume_map.md and premise.md, generates a chapter_queue.md table
with Goal / Premise Must Hit / Forbidden columns pre-filled with
context-aware templates. User reviews and refines after generation.
"""

from __future__ import annotations
from pathlib import Path
import argparse, datetime, json, re, sys


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="ignore") if p.exists() else ""


def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


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

    m = re.search(r"书名[：:]\s*(.+)", premise_text)
    if m:
        concepts["title"] = m.group(1).strip()

    m = re.search(r"主角[：:]\s*(.+)", premise_text)
    if m:
        concepts["protagonist"] = m.group(1).strip()

    m = re.search(r"金手指[：:]\s*(.+)", premise_text)
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
        "status": "待写" if ch_num == 1 else "queue",
    }


def generate_queue(book_dir: str, num_chapters: int = 20) -> str:
    """Generate chapter_queue.md content."""
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

    premise_text = read(pm_path)
    concepts = extract_concepts(premise_text)

    volumes = parse_volumes(read(vm_path)) if vm_path else []

    lines = [
        "# Chapter Queue",
        "",
        f"> 自动生成于 {datetime.datetime.now().astimezone().isoformat(timespec='minutes')}",
        f"> 项目：{book.name}",
        f"> 书名：{concepts.get('title', '未设定')}",
        "",
        "| Chapter | 标题 | Goal | Premise Must Hit | Forbidden | Status |",
        "|---------|------|------|------------------|-----------|--------|",
    ]

    prev_goal = ""
    for ch_num in range(1, num_chapters + 1):
        entry = generate_chapter_entry(ch_num, "", concepts, prev_goal)
        prev_goal = entry["goal"]
        lines.append(
            f"| {entry['chapter']:04d} | {entry['title_hint']} | "
            f"{entry['goal']} | {entry['premise_must_hit']} | "
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
    premise_text = read(pm_path) if pm_path.exists() else ""
    concepts = {}
    if premise_text:
        m = re.search(r"书名[：:]\s*(.+)", premise_text); concepts["title"] = m.group(1).strip() if m else ""
        m = re.search(r"主角[：:]\s*(.+)", premise_text); concepts["protagonist"] = m.group(1).strip() if m else ""

    idx_text = read(idx_path)
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
        "| Chapter | Title Hint | Goal | Premise Must Hit | Forbidden | Status |",
        "|---------|------|------|------------------|-----------|--------|",
    ]

    for ch_num in range(start_ch, start_ch + count):
        entry = entries.get(ch_num, {"title": "", "event": ""})
        title = entry["title"] or f"第{ch_num:03d}章"
        event = entry["event"]
        goal = f"让读者{event}" if event else "待补充"
        status = "待写" if ch_num == start_ch else "queue"
        lines.append(
            f"| {ch_num:04d} | {title} | {goal} | 待补充 | {forbidden} | {status} |"
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
    ap.add_argument("--json", action="store_true",
                    help="JSON 输出到 stdout，不写文件")
    ap.add_argument("--dry-run", action="store_true",
                    help="仅输出预览，不写入文件")
    args = ap.parse_args()

    if args.from_index:
        content = generate_from_index(args.book_dir, args.start_chapter, args.chapters)
    else:
        content = generate_queue(args.book_dir, args.chapters)

    if args.json:
        print(content)
        return 0

    if args.dry_run:
        print(content)
        print(f"\n[dry-run] 以上内容不会写入文件。")
        return 0

    output_path = Path(args.book_dir) / "director" / "chapter_queue.md"
    if output_path.exists():
        bak = output_path.with_suffix(".md.bak")
        write(bak, read(output_path))
        print(f"已备份: {bak}")

    write(output_path, content)
    print(f"已生成: {output_path}")
    print(f"  章节数: {args.chapters}")
    print(f"  下一步: 逐章审查并细化 Goal/Premise Must Hit/Forbidden 列")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
