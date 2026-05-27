#!/usr/bin/env python3
"""Build a chapter task package for webnovel-director execution-dispatch.

Usage:
  python build_task_package.py <book_dir> --chapter 12 [--out task.yaml]

Reads director_state, premise, chapter_queue, last_audit and truth files, then
emits a YAML-like task package. This script is deliberately conservative: if
canWrite=false, blockers exist, or the chapter is not PASS/READY in queue, it
fails instead of producing a write prompt.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import (  # noqa: E402
    REQUIRED_FILES, excerpt_file, listify, load_director_state, now_iso,
    parse_chapter_queue, read_text, status_ok,
)


def fail(reason: str, evidence: str, suggestions: list[str], json_mode: bool = False) -> int:
    if json_mode:
        print(json.dumps({"status": "FAIL", "reason": reason, "evidence": evidence,
                          "suggestions": suggestions}, ensure_ascii=False, indent=2))
    else:
        print("结论：FAIL")
        print(f"依据：{evidence}")
        print(f"问题：{reason}")
        print("建议：")
        for i, s in enumerate(suggestions[:3], 1):
            print(f"{i}. {s}")
        print("下一步：停止")
    return 1


def build_package(book: Path, chapter: int, row: dict, state: dict) -> str:
    read_file_paths = REQUIRED_FILES
    update_file_paths = [
        "director/director_state.json5",
        "director/last_audit.md",
        "director/audit_log.md",
        "director/chapter_queue.md",
        "truth/current_state.md",
        "truth/resource_ledger.md",
        "truth/particle_ledger.md",
        "truth/pending_hooks.md",
    ]
    premise_hits = listify(row["premise_must_hit"])
    forbidden = listify(row["forbidden"])
    if not forbidden:
        forbidden = ["不得触犯 director/premise.md 与 director/forbidden_zones.md 中的禁飞区"]
    state_before = [
        "写前必须读取并遵守 truth/current_state.md",
        "写前必须核对 resource_ledger / particle_ledger / pending_hooks",
        f"director_state.currentChapter={state.get('currentChapter', '')}",
        f"director_state.activeVolume={state.get('activeVolume', '')}",
    ]
    beats = [{
        "goal": row["goal"] or "围绕本章目标建立场景推进",
        "conflict": "从 chapter_queue 目标中拆出直接阻碍；不得用无因果事故替代冲突",
        "turn": "本章中段必须产生状态变化、认知变化或资源变化",
        "hook": "章末钩子必须承接本章变化，并写入 pending_hooks 或 current_state",
    }]

    now = now_iso()

    def yq(s: str) -> str:
        return json.dumps(s or "", ensure_ascii=False)

    def yl(items: list[str], indent: int = 2) -> str:
        pad = " " * indent
        if not items:
            return f"{pad}- \"\""
        return "\n".join(f"{pad}- {yq(i)}" for i in items)

    lines = [
        f"chapter: {chapter:04d}",
        f"title_hint: {yq(row['title_hint'])}",
        f"book_id: {yq(str(state.get('bookId', '')))}",
        f"book_title: {yq(str(state.get('title', '')))}",
        f"executor: {yq(str(state.get('executor', 'inkos')))}",
        f"generated_at: {yq(now)}",
        f"chapter_goal: {yq(row['goal'])}",
        "premise_must_hit:",
        yl(premise_hits),
        "forbidden:",
        yl(forbidden),
        "state_before:",
        yl(state_before),
        "beats:",
    ]
    for b in beats:
        lines.extend([
            f"  - goal: {yq(b['goal'])}",
            f"    conflict: {yq(b['conflict'])}",
            f"    turn: {yq(b['turn'])}",
            f"    hook: {yq(b['hook'])}",
        ])
    lines.append("continuity:")
    lines.append("  read_files:")
    lines.append(yl(read_file_paths, 4))
    lines.append("  update_files:")
    lines.append(yl(update_file_paths, 4))
    lines.append('audit_after: "level_1"')
    lines.append("director_context:")
    for rel in ["director/premise.md", "director/last_audit.md", "truth/current_state.md", "truth/pending_hooks.md"]:
        key = rel.replace("/", "_").replace(".", "_")
        lines.append(f"  {key}: |-")
        ex = excerpt_file(book / rel)
        if not ex:
            lines.append("    ")
        else:
            for line in ex.splitlines():
                lines.append("    " + line)
    lines.append("post_write_required:")
    lines.append('  - "运行 chapter-review Level 1"')
    lines.append('  - "PASS 才能推进 currentChapter"')
    lines.append('  - "WARN/FAIL 必须写入 director/last_audit.md 与 director/audit_log.md"')
    lines.append('  - "更新 truth files，不得只输出正文"')
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--chapter", type=int)
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    book = Path(args.book_dir).resolve()

    missing = [rel for rel in REQUIRED_FILES if not (book / rel).exists()]
    if missing:
        return fail("缺少 director/truth 必需文件：" + ", ".join(missing), str(book),
                    ["先运行 project-init/init_project.py", "补齐 premise 与 truth files", "再进入 execution-dispatch"], args.json)

    state = load_director_state(book)
    blockers = state.get("blockers") or []
    if isinstance(blockers, str):
        blockers = [blockers]
    if not state.get("canWrite", False):
        return fail("director_state.canWrite=false", "director/director_state.json5",
                    ["先通过 outline-gate", "清空 blockers", "更新 canWrite=true 后再派发"], args.json)
    if blockers:
        return fail("存在未清除 blockers：" + ", ".join(map(str, blockers)), "director/director_state.json5",
                    ["进入 repair-feedback", "修复后更新 last_audit", "清空 blockers 再派发"], args.json)

    chapter = args.chapter or int(state.get("currentChapter", 0)) + 1
    queue = parse_chapter_queue(book / "director/chapter_queue.md")
    row = next((r for r in queue if r["chapter"] == chapter), None)
    if not row:
        return fail(f"chapter_queue 中没有第 {chapter:04d} 章", "director/chapter_queue.md",
                    ["先用 outline-gate 生成/审查该章细纲", "写入 chapter_queue", "状态必须为 PASS/READY/待写"], args.json)
    if not status_ok(row["status"]):
        return fail(f"第 {chapter:04d} 章状态不可写：{row['status']}", "director/chapter_queue.md",
                    ["修复该章细纲", "将状态改为 PASS/READY/待写", "再生成任务包"], args.json)
    if not row["goal"] or not row["premise_must_hit"]:
        return fail(f"第 {chapter:04d} 章缺少 Goal 或 Premise Must Hit", "director/chapter_queue.md",
                    ["补齐章节目标", "补齐本章必须兑现的命题元素", "重新过 outline-gate"], args.json)

    package = build_package(book, chapter, row, state)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(package, encoding="utf-8")
        print("结论：PASS")
        print(f"依据：chapter_queue 第 {chapter:04d} 章；director_state.canWrite=true；blockers=0")
        print("问题：暂无")
        print("建议：1. 将任务包交给 inkos/执行器；2. 写后运行 chapter-review Level 1；3. 回写 director/truth")
        print(f"下一步：调用执行器，任务包={out}")
    else:
        print(package)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
