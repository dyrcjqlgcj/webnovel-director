#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""章节拆分与规范工具。

规则:
  - 字数 < 4000: 不拆分
  - 字数 > 4000: 拆分为 ceil(字数/4000) 段，每段 >= 2000 字
  - 拆分后自动继承父章 Goal/Premise/Forbidden
  - 后续章节自动后移
  - chapter_queue 自动同步

用法:
  python check_wordcount.py <book_dir>                     # 仅检查
  python check_wordcount.py <book_dir> --split             # 执行拆分
  python check_wordcount.py <book_dir> --fix-names         # 统一命名格式
"""

from __future__ import annotations
import argparse, re, sys, os
from pathlib import Path

MAX_WORDS = 4000
MIN_SEGMENT = 2000
SCRIPTS_DIR = Path(__file__).resolve().parent


def strip_markdown(text: str) -> str:
    text = re.sub(r"^#{1,6}\s+.+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+", "", text)


def count_chars(filepath: Path) -> int:
    if not filepath.exists():
        return 0
    return len(strip_markdown(filepath.read_text(encoding="utf-8-sig", errors="ignore")))


def find_chapter_files(book_dir: Path) -> dict[int, Path]:
    chapters = {}
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                m = re.match(r"第0*(\d+)章", f.name)
                if m:
                    chapters[int(m.group(1))] = f
    return chapters


def calculate_segments(char_count: int) -> int:
    """ceil(char_count/4000), max 6"""
    return min(max(1, (char_count + MAX_WORDS - 1) // MAX_WORDS), 6)


def find_balanced_points(text: str, n: int) -> list[int]:
    """找 n-1 个断点，保证每段 >= MIN_SEGMENT"""
    if n <= 1:
        return []

    total = len(strip_markdown(text))
    raw_len = len(text)
    target_per_seg = raw_len // n
    
    points = []
    cursor = 0
    for i in range(1, n):
        # Target for this break point
        target = target_per_seg * i
        # Enforce minimum segment size
        min_pos = cursor + int(raw_len * MIN_SEGMENT / total)
        actual_target = max(target, min_pos)
        
        pt = find_best_split(text, actual_target)
        if pt and pt > cursor:
            points.append(pt)
            cursor = pt
        else:
            # Fallback: use exact fraction position
            points.append(actual_target)
            cursor = actual_target

    # Validate: remove last point if it creates a final segment < MIN_SEGMENT
    if points and cursor > 0:
        final_seg_chars = count_chars_raw(text[cursor:])
        if final_seg_chars < MIN_SEGMENT and len(points) > 1:
            points.pop()

    return points[:n-1]


def count_chars_raw(text: str) -> int:
    """Count characters in raw text (for segment size estimation)"""
    return len(strip_markdown(text))


def find_best_split(text: str, target: int) -> int | None:
    """在目标附近找最佳断点——优先离目标最近的场景分隔/空行，而非第一个找到的"""
    total = len(text)
    window = max(total // 5, 300)
    lo = max(0, target - window)
    hi = min(total, target + window)
    search = text[lo:hi]

    # Collect ALL candidate break points with their distance from target
    candidates = []
    
    # 1. 场景分隔符
    for m in re.finditer(r"\n[-*]{3,}\s*\n", search):
        pos = lo + m.start()
        candidates.append((abs(pos - target), pos))
    # 2. 时间跳转
    for m in re.finditer(r"\n(?:过了|第二天|次日|几小时后|不久后|转眼|数日后|一周后|半夜|凌晨|清晨|黄昏|傍晚|入夜)", search):
        pos = lo + m.start()
        candidates.append((abs(pos - target), pos))
    # 3. 空行三连
    for m in re.finditer(r"\n\n\n+", search):
        pos = lo + m.start()
        candidates.append((abs(pos - target), pos))
    # 4. 双空行
    for m in re.finditer(r"\n\n", search):
        pos = lo + m.start()
        candidates.append((abs(pos - target), pos))

    if candidates:
        # Return the CLOSEST to target (not the first found)
        candidates.sort()
        return candidates[0][1]
    
    return target


def segment_suffix(i: int, total: int) -> str:
    if total <= 1:
        return ""
    if total == 2:
        return "（上）" if i == 0 else "（下）"
    if total == 3:
        return ["（上）", "（中）", "（下）"][i]
    cn = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    return f"（{cn[i]}）" if total <= 10 else f"（{i+1}）"


def parse_chapter_name(filename: str) -> tuple[int, str]:
    """Return (chapter_number, clean_title)"""
    m = re.match(r"第0*(\d+)章[_\s]*(.+)\.md", filename)
    if m:
        return int(m.group(1)), m.group(2).strip()
    return 0, filename


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="ignore")


def write_text(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def parse_queue_row(line: str) -> dict | None:
    """Parse a chapter_queue row, return None if not a data row."""
    s = line.strip()
    if not s.startswith("|") or "---" in s:
        return None
    cells = [c.strip() for c in s.strip("|").split("|")]
    if len(cells) < 8:
        return None
    m = re.match(r"\d+", cells[0])
    if not m:
        return None
    return {
        "ch": int(m.group()),
        "title": cells[1] if len(cells) > 1 else "",
        "goal": cells[2] if len(cells) > 2 else "",
        "premise": cells[3] if len(cells) > 3 else "",
        "scenes": cells[4] if len(cells) > 4 else "",
        "words": cells[5] if len(cells) > 5 else "",
        "forbidden": cells[6] if len(cells) > 6 else "",
        "status": cells[7] if len(cells) > 7 else "WRITTEN",
    }


def format_queue_row(row: dict) -> str:
    return f"| {row['ch']} | {row['title']} | {row['goal']} | {row['premise']} | {row['scenes']} | {row['words']} | {row['forbidden']} | {row['status']} |"


def rebuild_queue(book_dir: Path):
    """Rebuild chapter_queue to match actual chapter files, inheriting from old queue where possible."""
    qp = book_dir / "director" / "chapter_queue.md"
    old_text = read_text(qp) if qp.exists() else ""
    old_rows = {}
    for line in old_text.splitlines():
        row = parse_queue_row(line)
        if row:
            old_rows[row["ch"]] = row

    ch_files = find_chapter_files(book_dir)
    header = "# Chapter Queue\n\n> 只放已经通过 outline-gate 的待写章节。\n\n| Chapter | Title Hint | Goal | Premise Must Hit | Scenes | Words | Forbidden | Status |\n|---:|---|---|---:|---:|---|---|\n"

    lines = [header]
    for ch_num in sorted(ch_files.keys()):
        f = ch_files[ch_num]
        _, title = parse_chapter_name(f.name)
        chars = count_chars(f)

        # Inherit from old row or parent chapter
        goal = ""
        premise = ""
        forbidden = ""
        if ch_num in old_rows:
            goal = old_rows[ch_num]["goal"]
            premise = old_rows[ch_num]["premise"]
            forbidden = old_rows[ch_num]["forbidden"]
        else:
            # Find parent: chapter with same base title
            base_title = re.sub(r"（[^）]+）$", "", title)
            for old_ch, old_row in old_rows.items():
                old_base = re.sub(r"（[^）]+）$", "", old_row["title"])
                if old_base == base_title and old_row["goal"]:
                    goal = old_row["goal"]
                    premise = old_row["premise"]
                    forbidden = old_row["forbidden"]
                    break

        row = {"ch": ch_num, "title": title, "goal": goal, "premise": premise,
               "scenes": "", "words": str(chars), "forbidden": forbidden, "status": "WRITTEN"}
        lines.append(format_queue_row(row))

    write_text(qp, "\n".join(lines) + "\n")


def fix_chapter_names(book_dir: Path):
    """统一章节命名为 第XX章 标题.md 格式，去掉下划线"""
    ch_files = find_chapter_files(book_dir)
    ch_dir = ch_files[min(ch_files.keys())].parent

    renamed = 0
    for ch_num in sorted(ch_files.keys()):
        f = ch_files[ch_num]
        _, title = parse_chapter_name(f.name)
        title = title.strip()
        # Remove leading underscore if present
        if title.startswith("_"):
            title = title[1:].strip()

        target_name = f"第{ch_num:02d}章 {title}.md"
        target_path = ch_dir / target_name
        if f.name != target_name or f != target_path:
            f.rename(target_path)
            print(f"  重命名: {f.name} → {target_name}")
            renamed += 1

    if renamed:
        # Also rename Ch001 format to Ch01 if needed
        for f in sorted(ch_dir.glob("第00*.md")):
            m = re.match(r"第00(\d)章 (.+)\.md", f.name)
            if m:
                new_name = f"第0{m.group(1)}章 {m.group(2)}.md"
                target = ch_dir / new_name
                if not target.exists():
                    f.rename(target)
                    print(f"  修复: {f.name} → {new_name}")
                    renamed += 1

    return renamed


def rename_and_split(book_dir: Path, ch_num: int, points: list[int]):
    """拆分单个章节: 找断点→写N段→后移后续→删除原文件"""
    ch_files = find_chapter_files(book_dir)
    ch_dir = ch_files[ch_num].parent
    orig = ch_files[ch_num]
    full_text = read_text(orig)
    n = len(points) + 1

    # 分段
    prev = 0
    segments = []
    for p in points:
        segments.append(full_text[prev:p].strip())
        prev = p
    segments.append(full_text[prev:].strip())

    # 标题
    base = parse_chapter_name(orig.name)[1]
    base = re.sub(r"（[^）]+）$", "", base).strip()
    if base.startswith("_"):
        base = base[1:].strip()

    # 后移后续章节 (从后往前)
    max_ch = max(ch_files.keys())
    shift = n - 1
    for ch in range(max_ch, ch_num, -1):
        if ch in ch_files:
            old_f = ch_files[ch]
            _, t = parse_chapter_name(old_f.name)
            new_name = f"第{ch + shift:02d}章 {t}.md"
            old_f.rename(ch_dir / new_name)

    # 写入新段
    for i, seg in enumerate(segments):
        suffix = segment_suffix(i, n)
        seg_name = f"第{ch_num + i:02d}章 {base}{suffix}.md"
        write_text(ch_dir / seg_name, seg)
        chars = count_chars(ch_dir / seg_name)
        # Verify segment size
        status = "OK" if MIN_SEGMENT <= chars <= MAX_WORDS else ("SHORT" if chars < MIN_SEGMENT else "LONG")
        print(f"  → 第{ch_num + i:02d}章 {base}{suffix} ({chars}字) [{status}]")



def update_volume_map(book_dir: Path, shifts: list[tuple[int, int]]):
    """更新 volume_map.md 的卷章号范围以匹配拆分后编号。
    shifts: [(split_chapter, shift_amount), ...]
    例如: 第11章拆成3段 → shift=2，后续所有卷章号后移2。
    """
    vm_paths = [
        book_dir / "director" / "volume_map.md",
        book_dir / "story" / "outline" / "volume_map.md",
    ]
    for vm_path in vm_paths:
        if not vm_path.exists():
            continue
        text = read_text(vm_path)
        lines = text.splitlines()
        new_lines = []
        applied = 0

        for line in lines:
            s = line.strip()
            # Volume table: | 卷 | 1-99 | ... |
            m = re.match(r"\|\s*(.+?)\s*\|\s*(\d+)\s*[-–]\s*(\d+)\s*\|", s)
            if m:
                v_start = int(m.group(2))
                v_end = int(m.group(3))
                for split_ch, shift_amt in sorted(shifts):
                    if split_ch >= v_start and split_ch <= v_end:
                        v_end += shift_amt
                    elif split_ch < v_start:
                        v_start += shift_amt
                        v_end += shift_amt
                new_line = re.sub(r"(\d+)\s*[-–]\s*(\d+)", f"{v_start}-{v_end}", line)
                new_lines.append(new_line)
                applied += 1
                continue

            # Pace table: | 1-20 | ... |
            m2 = re.match(r"\|\s*(\d+)\s*[-–]\s*(\d+)\s*\|", s)
            if m2:
                p_start = int(m2.group(1))
                p_end = int(m2.group(2))
                for split_ch, shift_amt in sorted(shifts):
                    if split_ch >= p_start and split_ch <= p_end:
                        p_end += shift_amt
                    elif split_ch < p_start:
                        p_start += shift_amt
                        p_end += shift_amt
                new_line = re.sub(r"(\d+)\s*[-–]\s*(\d+)", f"{p_start}-{p_end}", line)
                new_lines.append(new_line)
                applied += 1
                continue

            new_lines.append(line)

        write_text(vm_path, "\n".join(new_lines) + "\n")
        if applied > 0:
            print(f"  >> volume_map 已更新: {vm_path.name} ({applied} 行)")
    return


def run(book_dir: Path, split: bool = False):
    print(f"[check_wordcount] 阈值={MAX_WORDS}字, 下限={MIN_SEGMENT}字, 模式={'拆分' if split else '检查'}")
    print()

    ch_files = find_chapter_files(book_dir)
    if not ch_files:
        print("未找到章节文件")
        return 1

    over_count = 0
    to_split = []

    for ch in sorted(ch_files.keys()):
        f = ch_files[ch]
        chars = count_chars(f)
        segments = calculate_segments(chars)
        if chars <= MAX_WORDS:
            print(f"  OK  第{ch:02d}章: {chars}字")
        else:
            over_count += 1
            full = read_text(f)
            points = find_balanced_points(full, segments)
            per_seg = chars // segments
            print(f"  SPLIT 第{ch:02d}章: {chars}字 → {segments}段 (~{per_seg}字/段)")
            if points:
                for i, pt in enumerate(points):
                    before = full[max(0, pt - 15):pt].strip().replace("\n", " ")[-15:]
                    after = full[pt:pt + 20].strip().replace("\n", " ")[:20]
                    print(f"    断点{i+1}: {pt}/{len(full)} ...{before} | {after}...")
                to_split.append((ch, points))
            else:
                print(f"    警告: 无合适断点")

    if over_count == 0:
        print(f"\nOK: 全部在 {MAX_WORDS} 字以内")
        rebuild_queue(book_dir)
        return 0

    if not split:
        print(f"\n发现 {over_count} 个超长章节。使用 --split 执行拆分。")
        return over_count

    # 执行拆分 (从后往前)
    print(f"\n>> 执行拆分 ({len(to_split)} 个章节)...")
    for ch, points in sorted(to_split, reverse=True):
        print(f"\n  第 {ch} 章 → {len(points) + 1} 段")
        rename_and_split(book_dir, ch, points)

    # 更新 volume_map
    update_volume_map(book_dir, [(ch, len(pts)) for ch, pts in sorted(to_split, reverse=True)])
    # 重建 queue
    rebuild_queue(book_dir)
    print(f"\n>> chapter_queue 已更新")

    # 验证
    print(f"\n>> 拆分后:")
    final = find_chapter_files(book_dir)
    for ch in sorted(final.keys()):
        chars = count_chars(final[ch])
        status = "OK" if chars <= MAX_WORDS else "OVER"
        print(f"  [{status}] 第{ch:02d}章: {chars}字")
    print(f"  总计 {len(final)} 章")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="章节拆分与规范工具")
    ap.add_argument("book_dir", help="项目目录")
    ap.add_argument("--split", action="store_true", help="执行拆分")
    ap.add_argument("--fix-names", action="store_true", help="统一章节命名格式")
    args = ap.parse_args()

    book_dir = Path(args.book_dir).resolve()
    if args.fix_names:
        n = fix_chapter_names(book_dir)
        print(f"\n重命名 {n} 个文件")
        rebuild_queue(book_dir)
        print("chapter_queue 已同步")
        return 0

    return run(book_dir, split=args.split)


if __name__ == "__main__":
    raise SystemExit(main())
