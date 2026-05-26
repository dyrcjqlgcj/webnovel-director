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


def find_split_point(text: str) -> int | None:
    """在正文中找自然断点，返回分割位置（字符索引）。

    优先级：场景分隔符(***/---) > 空行簇 > 时间跳跃 > 视角切换 > 中间点。
    """
    # 1. 场景分隔符
    for m in re.finditer(r"(?:^|\n)\*{3,}\s*\n|(?:^|\n)-{3,}\s*\n", text, re.MULTILINE):
        pos = m.start()
        # 只在中间 1/3 到 2/3 的位置找断点
        third, two_thirds = len(text) // 3, len(text) * 2 // 3
        if third < pos < two_thirds:
            return pos

    # 2. 时间标记后紧跟新段落
    for m in re.finditer(r"(?:^|\n)((?:过了|第二天|次日|几小时后|不久后|转眼|数日后|一周后|半夜|凌晨|清晨|黄昏|傍晚|入夜).*?)(?:\n\n|\n(?=\S))", text, re.MULTILINE):
        pos = m.start()
        third, two_thirds = len(text) // 3, len(text) * 2 // 3
        if third < pos < two_thirds:
            return pos

    # 3. 双空行（段落分隔）
    matches = list(re.finditer(r"\n\n\n+", text, re.MULTILINE))
    if matches:
        # 找中间区域的空行
        third, two_thirds = len(text) // 3, len(text) * 2 // 3
        for m in matches:
            if third < m.start() < two_thirds:
                return m.start()

    # 4. 取中间位置最近的段落边界
    mid = len(text) // 2
    boundary = text.rfind("\n\n", 0, mid)
    if boundary > 0:
        return boundary

    return None


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


def rename_and_shift(book_dir: Path, split_ch: int, split_pos: int, ch_files: dict[int, Path]):
    """执行拆章：重命名文件，后移后续章节。"""
    ch_dir = next((book_dir / d for d in ("正文", "chapters") if (book_dir / d).exists()), book_dir / "正文")
    ch_dir.mkdir(parents=True, exist_ok=True)

    # 1. 读取原章内容
    orig_file = ch_files[split_ch]
    full_text = read_full_text(orig_file)

    # 2. 拆分
    up_text = full_text[:split_pos].strip()
    down_text = full_text[split_pos:].strip()

    # 3. 解析原标题
    orig_name = orig_file.stem
    m = re.match(r"第0*(\d+)章\s*(.+)", orig_name)
    title_text = m.group(2).strip() if m and m.group(2) else ""

    # 去除已有的上下标记
    base_title, _ = parse_chapter_name(title_text)

    # 4. 从后往前重命名（避免覆盖）
    max_ch = max(ch_files.keys())
    for ch in range(max_ch, split_ch, -1):
        if ch in ch_files:
            old = ch_files[ch]
            m2 = re.match(r"第0*(\d+)章\s*(.+)", old.stem)
            t = m2.group(2).strip() if m2 and m2.group(2) else ""
            new_name = f"第{ch + 1:02d}章 {t}.md"
            new_path = ch_dir / new_name
            old.rename(new_path)
            print(f"  后移: {old.name} → {new_name}")
            # Update files dict
            ch_files[ch + 1] = new_path

    # 5. 写上下篇
    up_name = f"第{split_ch:02d}章 {base_title}（上）.md"
    down_name = f"第{split_ch + 1:02d}章 {base_title}（下）.md"

    (ch_dir / up_name).write_text(up_text, encoding="utf-8")
    print(f"  写入: {up_name} ({count_chars(up_text)}字)")

    (ch_dir / down_name).write_text(down_text, encoding="utf-8")
    print(f"  写入: {down_name} ({count_chars(down_text)}字)")

    # 6. 删除原文件
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
        print(f"  [{status}] 第{ch:02d}章: {chars}字")

        if chars > max_words:
            over_count += 1
            full = read_full_text(f)
            sp = find_split_point(full)
            if sp:
                print(f"      断点建议: 位置 {sp}/{len(full)} " +
                      f"({sp * 100 // len(full)}%)")
                # 显示前后各 50 字
                before = full[max(0, sp - 30):sp].strip().replace("\n", " ")
                after = full[sp:sp + 50].strip().replace("\n", " ")
                print(f"      分割处: ...{before[-30:]} | {after[:30]}...")
                to_split.append((ch, sp))
            else:
                print(f"      无合适断点（建议手动拆分）")

    if over_count == 0:
        print(f"\nOK 所有章节在 {max_words} 字以内")
        return 0

    if dry_run:
        print(f"\n!!  发现 {over_count} 个超长章节。使用 --split 执行拆分。")
        return over_count

    # 执行拆分
    print(f"\n>>> 开始拆分 {len(to_split)} 个章节...")
    # 从后往前拆分，避免章号冲突
    queue_file = book_dir / "director" / "chapter_queue.md"
    if queue_file.exists() and to_split:
        q_lines = parse_chapter_queue_text(read_full_text(queue_file))

    for ch, sp in sorted(to_split, reverse=True):
        print(f"\n  拆分第 {ch} 章...")
        # 重新获取文件（可能已被前面的拆分影响）
        current_files = find_chapter_files(book_dir)
        if ch in current_files:
            rename_and_shift(book_dir, ch, sp, current_files)
            # 更新 chapter_queue
            if queue_file.exists():
                q_lines = update_chapter_queue_rows(q_lines, ch)
        else:
            print(f"  跳过（文件已被后移）")

    # 写入 chapter_queue
    if queue_file.exists() and to_split:
        write_full_text(queue_file, "\n".join(q_lines) + "\n")
        print(f"\n>>> chapter_queue.md 已更新（后续章号已后移）")

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
