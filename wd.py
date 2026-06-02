#!/usr/bin/env python3
"""webnovel-director — 网文导演系统统一命令行入口

Usage:
  wd init <book_dir> --title "书名"        初始化新书项目
  wd gate concept <yaml_file>              概念闸门验证
  wd gate concept --inline "梗概: ..."    内联概念验证
  wd gate outline <book_dir>               大纲闸门审查
  wd gate outline <book_dir> --fix         大纲审查+自动修复
  wd build <book_dir> [--chapter N]        生成章节任务包
  wd review <book_dir> --chapter N         单章审查
  wd review <book_dir> --chapter N --text FILE  指定文本审查
  wd doctor <book_dir>                     一键体检
  wd doctor --self                         自检所有脚本语法
  wd dashboard <book_dir> [--port 8765]    启动 Web 仪表盘
  wd write <book_dir> --chapter N           调用 LLM 写章节正文
  wd premis <book_dir>                     自动提取 premise
  wd test                                  全链路冒烟测试
  wd status <book_dir>                     查看项目状态摘要
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"


def _run(script: str, *args, timeout: int = 120) -> int:
    """Run a script from the scripts/ directory."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script)] + list(args)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    result = subprocess.run(cmd, env=env, timeout=timeout)
    return result.returncode


def cmd_init(args):
    cargs = [args.book_dir, "--title", args.title]
    if args.book_id:
        cargs.extend(["--book-id", args.book_id])
    if args.force:
        cargs.append("--force")
    return _run("init_project.py", *cargs)


def cmd_gate_concept(args):
    cargs = []
    if args.inline:
        cargs.append("--inline")
    if args.concept_file:
        cargs.append(args.concept_file)
    if args.json:
        cargs.append("--json")
    if args.inline:
        cargs.append(args.inline)
    if not cargs:
        print("用法: wd gate concept <yaml_file> | --inline '...'")
        return 1
    return _run("concept_gate.py", *cargs)


def cmd_gate_outline(args):
    cargs = [args.book_dir]
    if args.json:
        cargs.append("--json")
    if args.write_report:
        cargs.append("--write-report")
    if args.fix:
        # Run review + causal + iterate
        ret = _run("outline_gate_review.py", *cargs)
        if ret == 0:
            ret2 = _run("outline_causal_check.py", args.book_dir, "--json")
            ret3 = _run("outline_iterate.py", args.book_dir, "--max-rounds", "3")
            return ret or ret2 or ret3
        return ret
    return _run("outline_gate_review.py", *cargs)


def cmd_build(args):
    cargs = [args.book_dir]
    if args.chapter:
        cargs.extend(["--chapter", str(args.chapter)])
    if args.out:
        cargs.extend(["--out", args.out])
    if args.json:
        cargs.append("--json")
    return _run("build_task_package.py", *cargs)


def cmd_review(args):
    if args.chapter:
        cargs = [args.book_dir, "--chapter", str(args.chapter)]
        if args.text:
            cargs.extend(["--text", args.text])
        if args.json:
            cargs.append("--json")
        if args.parallel:
            return _run("review_parallel.py", *cargs)
        return _run("review_chapter.py", *cargs)
    else:
        print("用法: wd review <book_dir> --chapter N")
        return 1


def cmd_doctor(args):
    cargs = []
    if getattr(args, 'self', False):
        cargs.append("--self")
    elif args.book_dir:
        cargs.append(args.book_dir)
    if args.json:
        cargs.append("--json")
    return _run("director_doctor.py", *cargs)


def cmd_dashboard(args):
    cargs = [args.book_dir, "--port", str(args.port)]
    if args.no_open:
        cargs.append("--no-open")
    return _run("dashboard_server.py", *cargs)


def cmd_write(args):
    cargs = [args.book_dir, "--chapter", str(args.chapter)]
    if args.model:
        cargs.extend(["--model", args.model])
    if args.provider:
        cargs.extend(["--provider", args.provider])
    if args.dry_run:
        cargs.append("--dry-run")
    if args.json:
        cargs.append("--json")
    return _run("write_chapter.py", *cargs, timeout=300)


def cmd_premise(args):
    return _run("extract_premise.py", args.book_dir)


def cmd_test(args):
    return _run("test_smoke.py", timeout=120)


def cmd_status(args):
    """Show a quick project status summary."""
    book = Path(args.book_dir).resolve()
    sys.path.insert(0, str(SKILL_ROOT))
    from lib.common import (load_director_state, parse_chapter_queue,
                            count_body_chars, latest_chapter, read_text)

    state = load_director_state(book)
    queue = parse_chapter_queue(book / "director" / "chapter_queue.md")
    total_chars = count_body_chars(book)

    total = len(queue)
    ready_count = sum(1 for r in queue if r["status"].lower() in {"pass", "ready", "待写", "通过", "可写", "written", "done"})
    fail_count = sum(1 for r in queue if r["status"].lower() in {"fail", "blocked", "stop", "未通过"})

    print(f"  书名: {state.get('title', book.name)}")
    print(f"  状态: {state.get('status', 'unknown')}")
    print(f"  已完成: {latest_chapter(book)} 章")
    print(f"  总字数: {total_chars / 10000:.1f} 万字")
    print(f"  计划: {total} 章 | 就绪: {ready_count} | 阻塞: {fail_count}")
    print(f"  canWrite: {state.get('canWrite', False)}")
    blockers = state.get("blockers", [])
    if blockers:
        print(f"  blockers: {', '.join(map(str, blockers))}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="webnovel-director — 网文导演系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  wd init ./我的小说 --title "轮回塔"
  wd gate concept concept.yaml
  wd gate outline ./我的小说 --fix
  wd build ./我的小说 --chapter 1
  wd doctor ./我的小说
  wd dashboard ./我的小说
  wd status ./我的小说
        """,
    )
    sub = ap.add_subparsers(dest="command", help="子命令")

    # init
    p_init = sub.add_parser("init", help="初始化新书项目")
    p_init.add_argument("book_dir")
    p_init.add_argument("--title", required=True)
    p_init.add_argument("--book-id")
    p_init.add_argument("--force", action="store_true")

    # gate concept
    p_gc = sub.add_parser("gate", help="闸门操作: concept / outline")
    p_gc_sub = p_gc.add_subparsers(dest="gate_type")
    p_gc_concept = p_gc_sub.add_parser("concept", help="概念闸门验证")
    p_gc_concept.add_argument("concept_file", nargs="?")
    p_gc_concept.add_argument("--inline")
    p_gc_concept.add_argument("--json", action="store_true")
    p_gc_outline = p_gc_sub.add_parser("outline", help="大纲闸门审查")
    p_gc_outline.add_argument("book_dir")
    p_gc_outline.add_argument("--json", action="store_true")
    p_gc_outline.add_argument("--write-report", action="store_true")
    p_gc_outline.add_argument("--fix", action="store_true", help="审查+逻辑验证+迭代修复")

    # build
    p_build = sub.add_parser("build", help="生成章节任务包")
    p_build.add_argument("book_dir")
    p_build.add_argument("--chapter", type=int)
    p_build.add_argument("--out")
    p_build.add_argument("--json", action="store_true")

    # review
    p_review = sub.add_parser("review", help="章节审查")
    p_review.add_argument("book_dir")
    p_review.add_argument("--chapter", type=int, required=True)
    p_review.add_argument("--text", help="章节文本文件")
    p_review.add_argument("--parallel", action="store_true", help="四 Agent 并行审查")
    p_review.add_argument("--json", action="store_true")

    # doctor
    p_doctor = sub.add_parser("doctor", help="一键体检")
    p_doctor.add_argument("book_dir", nargs="?")
    p_doctor.add_argument("--self", action="store_true", help="自检所有脚本")
    p_doctor.add_argument("--json", action="store_true")

    # dashboard
    p_dash = sub.add_parser("dashboard", help="启动 Web 仪表盘")
    p_dash.add_argument("book_dir")
    p_dash.add_argument("--port", type=int, default=8765)
    p_dash.add_argument("--no-open", action="store_true")

    # write
    p_write = sub.add_parser("write", help="调用 LLM 写章节正文")
    p_write.add_argument("book_dir")
    p_write.add_argument("--chapter", type=int, required=True)
    p_write.add_argument("--model", default="")
    p_write.add_argument("--provider", default="deepseek")
    p_write.add_argument("--dry-run", action="store_true")
    p_write.add_argument("--json", action="store_true")

    # premise
    p_prem = sub.add_parser("premise", help="自动提取 premise")
    p_prem.add_argument("book_dir")

    # test
    sub.add_parser("test", help="全链路冒烟测试")

    # status
    p_status = sub.add_parser("status", help="查看项目状态摘要")
    p_status.add_argument("book_dir")

    args = ap.parse_args()

    if not args.command:
        ap.print_help()
        return 0

    if args.command == "init":
        return cmd_init(args)
    elif args.command == "gate":
        if args.gate_type == "concept":
            return cmd_gate_concept(args)
        elif args.gate_type == "outline":
            return cmd_gate_outline(args)
        else:
            return cmd_gate_outline(args)  # default
    elif args.command == "build":
        return cmd_build(args)
    elif args.command == "review":
        return cmd_review(args)
    elif args.command == "doctor":
        return cmd_doctor(args)
    elif args.command == "dashboard":
        return cmd_dashboard(args)
    elif args.command == "write":
        return cmd_write(args)
    elif args.command == "premise":
        return cmd_premise(args)
    elif args.command == "test":
        return cmd_test(args)
    elif args.command == "status":
        return cmd_status(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
