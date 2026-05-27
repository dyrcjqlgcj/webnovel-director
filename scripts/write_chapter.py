#!/usr/bin/env python3
"""Execute a chapter writing task via LLM.

Usage:
  python write_chapter.py <book_dir> --chapter 1 [--model deepseek-chat] [--dry-run]

Reads the task package, premise, chapter_queue, and truth files, builds a
context-rich writing prompt, calls the LLM, and saves the output as a
chapter file in the book's chapters (or 正文) directory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import (  # noqa: E402
    DIRECTOR_PREMISE, DIRECTOR_QUEUE, DIRECTOR_STATE,
    TRUTH_CURRENT_STATE, TRUTH_RESOURCE_LEDGER, TRUTH_PENDING_HOOKS,
    excerpt_file, load_director_state, now_iso, parse_chapter_queue,
    read_text, status_ok, write_text,
)
from lib.llm import call_llm_writing  # noqa: E402


def build_writing_prompt(book: Path, chapter: int, row: dict, state: dict) -> str:
    """Construct a rich writing prompt for the LLM."""
    premise = excerpt_file(book / DIRECTOR_PREMISE, 2000)
    curr_state = excerpt_file(book / TRUTH_CURRENT_STATE, 1500)
    hooks = excerpt_file(book / TRUTH_PENDING_HOOKS, 1000)
    resources = excerpt_file(book / TRUTH_RESOURCE_LEDGER, 800)

    # Find previous chapter for continuity
    prev_text = ""
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book / ch_dir_name
        if ch_dir.exists():
            prev_files = sorted(ch_dir.glob(f"第*{chapter-1:03d}*章*.md"))
            if not prev_files:
                prev_files = sorted(ch_dir.glob(f"第*{chapter-1}*章*.md"))
            if prev_files:
                prev_text = read_text(prev_files[-1])[-800:]
                break

    return f"""你是中文网文作家。以下是本章写作任务。

## 书名承诺与世界观
{premise}

## 当前状态
{curr_state}

## 活跃伏笔（必须涉及或推进）
{hooks}

## 资源账（可用资源）
{resources}

## 本章任务
- 章节号：第{chapter}章
- 目标（Goal）：{row.get('goal', '推进主线')}
- 命题兑现（Premise Must Hit）：{row.get('premise_must_hit', '与核心命题关联')}
- 禁止（Forbidden）：{row.get('forbidden', '无特定禁忌')}

## 前一章末尾（衔接用）
{prev_text if prev_text else '（第一章，无前文）'}

## 写作要求
1. 字数：2000-3500 字（正文主体）
2. 章末必须有钩子（悬念/信息差/转折），让读者有动力点下一章
3. 对话占比 ≥ 15%，避免纯叙述
4. 使用短段落（手机阅读友好，≤150 字/段）
5. 禁止出现：系统面板/任务栏/属性面板/状态栏（除非世界观明确允许）
6. 不要使用 AI 味的过渡词：总的来说/总而言之/值得一提的是/此外/与此同时
7. 情绪有起伏：不要全程平淡叙述，每一段场景要有明确情绪基调
8. 承接上一章的结尾状态，本章开头自然衔接

## 输出格式
直接输出正文。第一行是章节标题「第{chapter}章 xxx」。不需要在前面加任何解释或标注。"""


def main() -> int:
    ap = argparse.ArgumentParser(description="执行章节写作任务")
    ap.add_argument("book_dir")
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--model", default="", help="LLM 模型覆盖")
    ap.add_argument("--provider", default="deepseek", help="LLM 提供商")
    ap.add_argument("--dry-run", action="store_true", help="只输出 prompt，不调用 LLM")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    book = Path(args.book_dir).resolve()

    if not (book / DIRECTOR_PREMISE).exists():
        print("错误: 找不到 premise.md，请先运行 init_project.py")
        return 1

    state = load_director_state(book)
    if not state.get("canWrite", False):
        print("错误: canWrite=false，请先通过 outline-gate 审查")
        if args.json:
            print(json.dumps({"status": "FAIL", "reason": "canWrite=false"}, ensure_ascii=False))
        return 1

    queue = parse_chapter_queue(book / DIRECTOR_QUEUE)
    row = next((r for r in queue if r["chapter"] == args.chapter), None)
    if not row:
        print(f"错误: chapter_queue 中未找到第 {args.chapter:04d} 章")
        return 1
    if not status_ok(row["status"]):
        print(f"错误: 第 {args.chapter:04d} 章状态不可写：{row['status']}")
        print("请先修复该章细纲并将状态改为 PASS/READY/待写")
        return 1

    prompt = build_writing_prompt(book, args.chapter, row, state)

    if args.dry_run:
        print("=== DRY RUN: 写作 Prompt ===")
        print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
        print(f"\n[总长度: {len(prompt)} 字符]")
        return 0

    print(f"正在调用 LLM 写作第 {args.chapter:04d} 章...")
    result = call_llm_writing(prompt, model=args.model, provider=args.provider)

    if not result:
        msg = "LLM 调用失败（已重试全部策略），请检查 API key 和网络连接"
        if args.json:
            print(json.dumps({"status": "FAIL", "reason": msg}, ensure_ascii=False))
        else:
            print(f"错误: {msg}")
        return 1

    # Save to chapters directory
    ch_dir = book / "chapters"
    ch_dir.mkdir(parents=True, exist_ok=True)
    filename = f"第{args.chapter:04d}章.md"
    out_path = ch_dir / filename
    write_text(out_path, result)

    # Update chapter_queue status
    row["status"] = "written"
    # Rewrite chapter_queue
    header = (
        "| Chapter | 标题提示 | Goal | Premise Must Hit | Forbidden | Status |\n"
        "|---------|----------|------|------------------|-----------|--------|"
    )
    body_lines = []
    for r in queue:
        body_lines.append(
            f"| {r['chapter']:04d} | {r.get('title_hint', '')} | "
            f"{r.get('goal', '')} | {r.get('premise_must_hit', '')} | "
            f"{r.get('forbidden', '')} | {r.get('status', '')} |"
        )
    write_text(book / DIRECTOR_QUEUE, header + "\n" + "\n".join(body_lines) + "\n")

    char_count = len(re.sub(r"\s+", "", result))
    print(f"✅ 第 {args.chapter:04d} 章完成")
    print(f"   文件: {out_path}")
    print(f"   字数: {char_count} 字")
    print(f"   下一步: review_chapter.py --chapter {args.chapter}")

    if args.json:
        print(json.dumps({
            "status": "PASS", "chapter": args.chapter,
            "file": str(out_path), "char_count": char_count,
        }, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
