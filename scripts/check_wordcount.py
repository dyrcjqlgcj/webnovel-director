#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""章节字数检查与智能拆章工具。

检查所有已写章节的字数，对超长章节自动找自然断点拆分为上下章，
后续章节编号后移，细纲自动插入。

用法：
  python check_wordcount.py <book_dir>                      # 仅检查，不拆分
  python check_wordcount.py <book_dir> --max 5000           # 超过5000字触发
  python check_wordcount.py <book_dir> --split              # 实际执行拆分
  python check_wordcount.py <book_dir> --split --max 4500   # 阈值+执行
"""

from __future__ import annotations
import argparse, re, sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def strip_markdown(text: str) -> str:
    """移除 markdown 格式，只留正文。"""
    text = re.sub(r"^#{1,6}\s+.+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+", "", text)


def count_body_chars(filepath: Path) -> int:
    """统计正文字符数（去掉 markdown 格式）。"""
    if not filepath.exists():
        return 0
    text = filepath.read_text(encoding="utf-8-sig", errors="ignore")
    return len(strip_markdown(text))


def find_chapter_files(book_dir: Path) -> dict[int, Path]:
    """找到所有章节文件，返回 {章号: 路径}。"""
    chapters = {}
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                m = re.match(r"第0*(\d+)章", f.name)
                if m:
                    chapters[int(m.group(1))] = f
    return chapters


def find_best_split(text: str, target_pos: int) -> int | None:
    """在目标位置附近找最佳断点，返回分割位置。
    搜索范围：target_pos ± 20% 区间内。"""
    total = len(text)
    window = total // 5
    lo = max(0, target_pos - window)
    hi = min(total, target_pos + window)
    search = text[lo:hi]
    
    # 1. 场景分隔符
    for m in re.finditer(r"(?:^|\n)[-*]{3,}\s*\n", search, re.MULTILINE):
        return lo + m.end()
    # 2. 时间跳跃
    for m in re.finditer(r"\n(?:过了|第二天|次日|几小时后|不久后|转眼|数日后|一周后|半夜|凌晨|清晨|黄昏|傍晚|入夜)", search, re.MULTILINE):
        return lo + m.start()
    # 3. 空行簇
    for m in re.finditer(r"\n\n\n+", search, re.MULTILINE):
        return lo + m.start()
    # 4. 双空行
    m = re.search(r"\n\n", search)
    if m:
        return lo + m.start()
    # 5. 精确 target
    return target_pos if lo < target_pos < hi else lo + len(search) // 2


def find_n_split_points(text: str, n: int) -> list[int]:
    """找 n-1 个断点，将正文均匀分成 n 段。"""
    if n <= 1:
        return []
    total = len(text)
    targets = [total * i // n for i in range(1, n)]
    points = []
    for t in targets:
        pt = find_best_split(text, t)
        if pt:
            points.append(pt)
    return points


def segment_suffix(i: int, total: int) -> str:
    """段编号后缀。"""
    if total <= 1:
        return ""
    if total == 2:
        return "（上）" if i == 0 else "（下）"
    if total == 3:
        return ["（上）", "（中）", "（下）"][i]
    cn = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    if total <= 10:
        return f"（{cn[i]}）"
    return f"（{i + 1}）"


def calculate_segments(max_words: int, char_count: int, max_segments: int = 6) -> int:
    """根据字数计算需要几段，最多不超过 max_segments。"""
    needed = (char_count + max_words - 1) // max_words
    return min(max(1, needed), max_segments)


def parse_chapter_name(title: str) -> tuple[str, str]:
    """解析章节标题。返回 (正文标题, 上下标记)。"""
    m = re.match(r"(.+?)（([上下])）$", title)
    if m:
        return m.group(1), m.group(2)
    return title, ""


def read_full_text(filepath: Path) -> str:
    """读取完整章节文本。"""
    return filepath.read_text(encoding="utf-8-sig", errors="ignore")


def write_full_text(filepath: Path, text: str):
    """写入完整章节文本。"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(text, encoding="utf-8")


def parse_chapter_queue_text(text: str) -> list[str]:
    """解析 chapter_queue.md 为行列表。"""
    return text.splitlines()


def update_chapter_queue_rows(lines: list[str], split_ch: int) -> list[str]:
    """在 chapter_queue 中为拆分章插入新行，后续章号+1。"""
    new_lines = []
    for line in lines:
        s = line.strip()
        # 匹配章号开头的表格行
        m = re.match(r"\|\s*(\d+)\s*\|", s)
        if m:
            ch_num = int(m.group(1))
            if ch_num == split_ch:
                # 原行变「上」，新增一行「下」
                new_lines.append(line.replace(f"| {split_ch} |", f"| {split_ch} （上）|"))
                # 插入下篇，章号暂用原号，后续统一偏移
                down_row = re.sub(r"\|\s*\d+\s*\|", f"| {split_ch} （下）|", line)
                new_lines.append(down_row)
            elif ch_num > split_ch:
                # 后续章号+1
                new_lines.append(re.sub(r"\|\s*" + str(ch_num) + r"\s*\|", f"| {ch_num + 1} |", line))
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    return new_lines


def rename_and_shift(book_dir: Path, split_ch: int, points: list[int], ch_files: dict[int, Path]):
    """一次性拆分章节：计算段数→找断点→写N个文件→后移→更新queue。"""
    ch_dir = next((book_dir / d for d in ("正文", "chapters") if (book_dir / d).exists()), book_dir / "正文")
    ch_dir.mkdir(parents=True, exist_ok=True)

    orig_file = ch_files[split_ch]
    full_text = read_full_text(orig_file)
    n = len(points) + 1

    # 解析原标题
    orig_name = orig_file.stem
    m = re.match(r"第0*(\d+)章\s*(.+)", orig_name)
    title_text = m.group(2).strip() if m and m.group(2) else ""
    base_title, _ = parse_chapter_name(title_text)

    # 分段
    segments = []
    prev = 0
    for pt in points:
        segments.append(full_text[prev:pt].strip())
        prev = pt
    segments.append(full_text[prev:].strip())

    # 从后往前后移后续章节
    max_ch = max(ch_files.keys())
    shift = n - 1
    for ch in range(max_ch, split_ch, -1):
        if ch in ch_files:
            old = ch_files[ch]
            m2 = re.match(r"第0*(\d+)章\s*(.+)", old.stem)
            t = m2.group(2).strip() if m2 and m2.group(2) else ""
            new_name = f"第{ch + shift:02d}章 {t}.md"
            new_path = ch_dir / new_name
            old.rename(new_path)
            print(f"  后移: {old.name} → {new_name}")

    # 写入新段
    for i, seg in enumerate(segments):
        suffix = segment_suffix(i, n)
        ch_num = split_ch + i
        seg_name = f"第{ch_num:02d}章 {base_title}{suffix}.md"
        (ch_dir / seg_name).write_text(seg, encoding="utf-8")
        chars = count_chars(seg)
        print(f"  写入: {seg_name} ({chars}字)")

    # 删除原文件
    if orig_file.exists():
        orig_file.unlink()
        print(f"  删除: {orig_file.name}")


def count_chars(text: str) -> int:
    """统计文本字数（去 markdown）。"""
    return len(strip_markdown(text))


def check_and_report(book_dir: Path, max_words: int, dry_run: bool = True) -> int:
    """主函数：检查所有章节，报告或执行拆分。"""
    ch_files = find_chapter_files(book_dir)
    if not ch_files:
        print("未找到章节文件")
        return 0

    print(f"阈值: {max_words}字 | 模式: {'仅检查' if dry_run else '执行拆分'}")
    print(f"章节数: {len(ch_files)}")
    print()

    over_count = 0
    to_split = []

    for ch in sorted(ch_files.keys()):
        f = ch_files[ch]
        chars = count_body_chars(f)
        status = "OK" if chars <= max_words else "OVER"
        segments = calculate_segments(max_words, chars)
        print(f"  [{status}] 第{ch:02d}章: {chars}字", end="")

        if chars > max_words:
            over_count += 1
            full = read_full_text(f)
            points = find_n_split_points(full, segments)
            print(f" → 拆{segments}段", end="")
            if points:
                print()
                for i, pt in enumerate(points):
                    before = full[max(0, pt - 20):pt].strip().replace("\n", " ")
                    after = full[pt:pt + 30].strip().replace("\n", " ")
                    print(f"    断点{i+1}: {pt}/{len(full)} ({pt*100//len(full)}%) ...{before[-20:]} | {after[:20]}...")
                to_split.append((ch, points))
            else:
                print(" 无合适断点")
        else:
            print()

    if over_count == 0:
        print(f"\nOK 所有章节在 {max_words} 字以内")
        return 0

    if dry_run:
        print(f"\n!!  发现 {over_count} 个超长章节。使用 --split 执行拆分。")
        return over_count

    # 执行拆分（从后往前）
    print(f"\n>>> 开始拆分 {len(to_split)} 个章节...")
    queue_file = book_dir / "director" / "chapter_queue.md"
    if queue_file.exists() and to_split:
        q_lines = parse_chapter_queue_text(read_full_text(queue_file))

    for ch, points in sorted(to_split, reverse=True):
        print(f"\n  拆分第 {ch} 章 → {len(points)+1} 段...")
        current_files = find_chapter_files(book_dir)
        if ch in current_files:
            rename_and_shift(book_dir, ch, points, current_files)
            if queue_file.exists():
                q_lines = update_chapter_queue_rows(q_lines, ch)

    if queue_file.exists() and to_split:
        write_full_text(queue_file, "\n".join(q_lines) + "\n")
        print(f"\n>>> chapter_queue.md 已更新")

    # 验证
    print(f"\n>>> 拆分后验证...")
    final = find_chapter_files(book_dir)
    for ch in sorted(final.keys()):
        chars = count_body_chars(final[ch])
        status = "OK" if chars <= max_words else "OVER"
        print(f"  [{status}] 第{ch:02d}章: {chars}字")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="章节字数检查与智能拆章")
    ap.add_argument("book_dir", help="项目目录")
    ap.add_argument("--max", type=int, default=5000,
                    help="字数上限（默认5000）")
    ap.add_argument("--split", action="store_true",
                    help="实际执行拆分（默认仅检查）")
    args = ap.parse_args()

    book_dir = Path(args.book_dir).resolve()
    if not (book_dir / "director").exists():
        print(f"错误: {book_dir} 不是有效的 webnovel-director 项目")
        return 1

    return check_and_report(book_dir, args.max, dry_run=not args.split)


if __name__ == "__main__":
    raise SystemExit(main())
