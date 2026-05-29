#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""细纲自动扩展工具。

从卷纲+已写章节+人物矩阵推演新的细纲条目，写入 chapter_queue。

V3.0 变更: 不再调用外部 LLM，改为生成结构化请求文件，
        由 director（小爪爪）读取后直接生成细纲。

规则:
  - 始终保持当前章之前至少有 5 章细纲储备
  - 每次最多生成 10 章新细纲
  - 生成内容必须通过禁飞区+命题检查
  - 状态标记为 QUEUE

用法:
  python extend_outline.py <book_dir>                   # 仅检查储备状态
  python extend_outline.py <book_dir> --auto            # 自动: 储备<5章则生成请求文件
  python extend_outline.py <book_dir> --request-only    # 强制生成请求文件（不检查储备）
"""

from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="ignore") if p.exists() else ""

def write_text(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

def parse_queue(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 8 or not cells[0].isdigit():
            continue
        rows.append({
            "ch": int(cells[0]), "title": cells[1], "goal": cells[2],
            "premise": cells[3], "scenes": cells[4], "words": cells[5],
            "forbidden": cells[6], "status": cells[7],
        })
    return rows

def format_queue_row(row: dict) -> str:
    return f"| {row['ch']} | {row['title']} | {row['goal']} | {row['premise']} | {row['scenes']} | {row['words']} | {row['forbidden']} | {row['status']} |"

def check_reserve(book_dir: Path) -> dict:
    """检查细纲储备状态。"""
    state_path = book_dir / "director" / "director_state.json5"
    qp = book_dir / "director" / "chapter_queue.md"

    state_text = read_text(state_path)
    m = re.search(r"currentChapter\s*:\s*(\d+)", state_text)
    current_ch = int(m.group(1)) if m else 0

    if not qp.exists():
        return {"current_ch": current_ch, "last_outline": 0, "reserve": 0, "need_more": True}

    queue = parse_queue(read_text(qp))
    if not queue:
        return {"current_ch": current_ch, "last_outline": 0, "reserve": 0, "need_more": True}

    last_outline = max(r["ch"] for r in queue)
    reserve = max(0, last_outline - current_ch)
    need_more = reserve < 5
    return {
        "current_ch": current_ch, "last_outline": last_outline,
        "reserve": reserve, "need_more": need_more,
    }

def get_volume_context(book_dir: Path, current_ch: int) -> str:
    """获取当前卷的结构上下文。"""
    vm_path = book_dir / "director" / "volume_map.md"
    if not vm_path.exists():
        vm_path = book_dir / "story" / "outline" / "volume_map.md"
    if not vm_path.exists():
        return ""
    text = read_text(vm_path)
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and "---" not in s and re.match(r"\|\s*[一二三四五六]+\s*\|", s):
            lines.append(s)
        if re.match(r"\|\s*\d+\s*[-–]\s*\d+\s*\|", s):
            m2 = re.search(r"(\d+)\s*[-–]\s*(\d+)", s)
            if m2 and int(m2.group(1)) <= current_ch <= int(m2.group(2)):
                lines.append(s)
    return "\n".join(lines[-10:])

def get_recent_chapters(book_dir: Path, current_ch: int, count: int = 5) -> str:
    """获取最近N章正文摘要。"""
    ch_dir = book_dir / "正文"
    if not ch_dir.exists():
        return ""
    summaries = []
    for ch in range(max(1, current_ch - count + 1), current_ch + 1):
        candidates = list(ch_dir.glob(f"第{ch:02d}章*.md")) + list(ch_dir.glob(f"第0{ch}章*.md"))
        if not candidates:
            continue
        text = read_text(candidates[0])
        start = text.strip()[:200].replace("\n", " ")
        summaries.append(f"第{ch}章: {start}...")
    return "\n".join(summaries)

def build_extension_request(book_dir: Path, current_ch: int, count: int) -> str:
    """生成细纲扩展请求上下文，供 director 读取后手动生成。"""
    premise = read_text(book_dir / "director" / "premise.md")
    vol_ctx = get_volume_context(book_dir, current_ch)
    recent = get_recent_chapters(book_dir, current_ch)
    char_matrix = read_text(book_dir / "story" / "character_matrix.md")

    qp = book_dir / "director" / "chapter_queue.md"
    existing_queue = ""
    if qp.exists():
        existing = parse_queue(read_text(qp))
        recent_entries = [r for r in existing if r["ch"] <= current_ch][-5:]
        existing_queue = "\n".join(
            f"第{r['ch']}章 {r['title']}: Goal={r['goal'][:50]}, MustHit={r['premise'][:50]}"
            for r in recent_entries
        )

    request = f"""# 细纲扩展请求
# director 读取此文件后手动生成细纲并追加到 chapter_queue

## 基本信息
- 当前进度: 第 {current_ch} 章
- 需要生成: 第 {current_ch + 1} 到第 {current_ch + count} 章细纲

## 小说命题与禁飞区
{premise[:2000]}

## 当前卷纲
{vol_ctx[:1000]}

## 最近已写章节摘要
{recent[:2000]}

## 已写章节的细纲参考
{existing_queue[:1000]}

## 人物矩阵
{char_matrix[:1000]}

## 要求
- 每章包含: 标题、Goal（本章目标）、Premise Must Hit（必须兑现的命题元素）、Forbidden（本章禁飞区）
- 承接第 {current_ch} 章结尾
- 避免触犯禁飞区
- 生成后由 director 运行 outline-gate 审查
"""
    return request

def generate_request_file(book_dir: Path, count: int) -> Path:
    """生成细纲扩展请求文件。"""
    reserve = check_reserve(book_dir)
    current_ch = reserve["current_ch"]
    if current_ch == 0:
        print("错误: 未找到 currentChapter")
        return None

    actual_count = min(count, 10)
    print(f"当前进度: 第{current_ch}章, 细纲储备: {reserve['reserve']}章")
    print(f"需要扩展: +{actual_count}章")

    request = build_extension_request(book_dir, current_ch, actual_count)
    out_path = book_dir / "director" / "outline_extension_request.md"
    write_text(out_path, request)
    print(f"请求文件已生成: {out_path}")
    print("请 director 读取此文件手动生成细纲并追加到 chapter_queue。")
    return out_path

def main() -> int:
    ap = argparse.ArgumentParser(description="细纲自动扩展工具 (V3.0 - 无外部LLM)")
    ap.add_argument("book_dir", help="项目目录")
    ap.add_argument("--generate", type=int, help="生成N章细纲请求文件")
    ap.add_argument("--auto", action="store_true", help="自动: 储备<5章则生成请求文件")
    ap.add_argument("--request-only", action="store_true", help="强制生成请求文件（不检查储备，需配合--generate）")
    args = ap.parse_args()

    book_dir = Path(args.book_dir).resolve()
    if not (book_dir / "director").exists():
        print("不是有效的 webnovel-director 项目")
        return 1

    if args.request_only:
        count = args.generate or 5
        generate_request_file(book_dir, count)
        return 0

    if args.generate:
        generate_request_file(book_dir, args.generate)
        return 0

    if args.auto:
        reserve = check_reserve(book_dir)
        print(f"第{reserve['current_ch']}章 | 细纲储备: {reserve['reserve']}章 | 至第{reserve['last_outline']}章")
        if reserve["need_more"]:
            needed = 5 - reserve["reserve"]
            print(f"储备不足, 生成请求文件 (+{needed}章)")
            generate_request_file(book_dir, needed)
        else:
            print("储备充足, 无需生成")
        return 0

    # Default: just check
    reserve = check_reserve(book_dir)
    print(f"当前: 第{reserve['current_ch']}章 | 细纲至: 第{reserve['last_outline']}章 | 储备: {reserve['reserve']}章")
    print("状态: " + ("需要扩展" if reserve['need_more'] else "充足"))
    return 0 if not reserve['need_more'] else 1

if __name__ == "__main__":
    raise SystemExit(main())
