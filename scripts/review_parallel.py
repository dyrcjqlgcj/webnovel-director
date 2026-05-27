#!/usr/bin/env python3
"""Four-agent parallel chapter review.

Usage:
  python review_parallel.py <book_dir> --chapter 31 --text chapters/0031.txt [--json]

Spawns 4 independent review agents (threads), each checking a different dimension:
  1. premise_agent    — 命题偏离 + 禁飞区
  2. consistency_agent — 资源账/粒子账/关系图
  3. transition_agent  — 钩子/结构/对白
  4. hook_agent        — 伏笔回收/新增

Results are merged with cross-agent conflict detection.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import read_text  # noqa: E402


def load_task_package(path: Path) -> dict:
    text = read_text(path)
    pkg = {"chapter": 0, "chapter_goal": "", "title_hint": "", "executor": "inkos",
           "premise_must_hit": [], "forbidden": []}
    if not text:
        return pkg
    for key in ["chapter", "chapter_goal", "title_hint", "executor"]:
        m = re.search(rf"^{key}:\s*(.+)$", text, re.M)
        if m:
            val = m.group(1).strip().strip('"')
            pkg[key] = int(val) if key == "chapter" and val.isdigit() else val
    for field in ["premise_must_hit", "forbidden"]:
        items = []
        in_sec = False
        for line in text.splitlines():
            if line.strip() == f"{field}:":
                in_sec = True
                continue
            if in_sec:
                if line.strip().startswith("- "):
                    items.append(line.strip()[2:].strip('"'))
                elif not line.strip().startswith(" ") and line.strip():
                    break
        pkg[field] = items
    return pkg


# ── Agent 1: premise_agent ──

def premise_agent(chapter_text: str, task_pkg: dict, premise_text: str) -> dict:
    issues = []
    must_hit = task_pkg.get("premise_must_hit", [])
    forbidden = task_pkg.get("forbidden", [])

    if chapter_text:
        for term in forbidden:
            if term and len(term) >= 2 and term in chapter_text:
                issues.append({"severity": "FAIL", "detail": f"正文含禁词: {term}"})
        for pattern, label in [("系统面板", "无系统"), ("任务栏", "无系统"),
                                ("状态栏", "无系统"), ("后宫", "后宫")]:
            if pattern in chapter_text and pattern not in str(forbidden):
                issues.append({"severity": "FAIL", "detail": f"疑似触犯禁飞区[{label}]: {pattern}"})

    if chapter_text and must_hit:
        hits = 0
        for term in must_hit:
            if not term:
                continue
            keywords = re.findall(r"[一-鿿]{2,}", term)
            if keywords and any(kw in chapter_text for kw in keywords):
                hits += 1
        if hits == 0:
            issues.append({"severity": "FAIL", "detail": f"0/{len(must_hit)} 条命题兑现"})
        elif hits < len(must_hit):
            issues.append({"severity": "WARN", "detail": f"仅 {hits}/{len(must_hit)} 条命题兑现"})

    if chapter_text and premise_text:
        m = re.search(r"书名承诺.*?\n+>(.*?)(?:\n##|\Z)", premise_text, re.S)
        if m:
            core = m.group(1).strip()
            core_words = set(re.findall(r"[一-鿿]{3,}", core))
            text_words = set(re.findall(r"[一-鿿]{3,}", chapter_text[:2000]))
            if not (core_words & text_words):
                issues.append({"severity": "WARN", "detail": "章节开头未显式呼应书名承诺"})

    verdict = "FAIL" if any(i["severity"] == "FAIL" for i in issues) else ("WARN" if issues else "PASS")
    return {"agent": "premise_agent", "verdict": verdict, "issues": issues,
            "evidence": f"must_hit={len(must_hit)} forbidden={len(forbidden)}"}


# ── Agent 2: consistency_agent ──

def consistency_agent(chapter_text: str, task_pkg: dict, book_dir: Path) -> dict:
    issues = []
    rl = read_text(book_dir / "truth" / "resource_ledger.md")
    active_resources = []
    if rl and chapter_text:
        for line in rl.splitlines():
            s = line.strip()
            if s.startswith("|") and "---" not in s and "Chapter" not in s \
                    and "EXPIRED" not in s and "Expired" not in s:
                cells = [c.strip() for c in s.strip("|").split("|")]
                if len(cells) >= 4 and cells[0].isdigit():
                    active_resources.append(cells[1])
        mentioned = sum(1 for r in active_resources if r and r in chapter_text)
        if active_resources and mentioned == 0:
            issues.append({"severity": "WARN",
                           "detail": f"正文未提及任何活跃资源 ({len(active_resources)}条)"})

    rg = read_text(book_dir / "truth" / "relationship_graph.yaml")
    if rg and "edges:" in rg and chapter_text:
        edge_count = rg.count("source:")
        if edge_count > 2:
            entities = (set(re.findall(r"source:\s*\"?([^\"#\n]+)", rg))
                        | set(re.findall(r"target:\s*\"?([^\"#\n]+)", rg)))
            entities -= {"{{PROTAGONIST}}", "{{CORE_MECHANISM}}", "{{ANTAGONIST_FORCE}}"}
            mentioned = sum(1 for e in entities if e and e in chapter_text)
            if entities and mentioned == 0:
                issues.append({"severity": "WARN",
                               "detail": f"正文未涉及关系图中 {len(entities)} 个实体"})

    verdict = "FAIL" if any(i["severity"] == "FAIL" for i in issues) else ("WARN" if issues else "PASS")
    return {"agent": "consistency_agent", "verdict": verdict, "issues": issues,
            "evidence": f"resources_active={len(active_resources)}"}


# ── Agent 3: transition_agent ──

def transition_agent(chapter_text: str, task_pkg: dict) -> dict:
    issues = []
    if not chapter_text:
        return {"agent": "transition_agent", "verdict": "PASS", "issues": [], "evidence": "no text"}
    chars = len(chapter_text.replace("\n", "").replace(" ", ""))

    tail = chapter_text[-400:] if len(chapter_text) > 400 else chapter_text
    hook_markers = ["？", "…", "——", "不再", "开始", "将要", "发现", "突然", "不是", "原来"]
    hook_hits = sum(1 for m in hook_markers if m in tail)
    if hook_hits == 0:
        issues.append({"severity": "FAIL", "detail": "章末无钩子标记"})
    elif hook_hits < 2:
        issues.append({"severity": "WARN", "detail": "章末钩子弱"})

    para_count = len([l for l in chapter_text.split("\n") if l.strip()])
    if para_count < 15:
        issues.append({"severity": "WARN", "detail": f"段落偏少 ({para_count})"})

    dialog_chars = len(re.findall(r"[「」“”‘’：]", chapter_text))
    if chars > 1500 and dialog_chars < chars * 0.02:
        issues.append({"severity": "WARN", "detail": "对白密度极低"})

    if chars < 1000:
        issues.append({"severity": "FAIL", "detail": f"过短 ({chars}字)"})
    elif chars < 1800:
        issues.append({"severity": "WARN", "detail": f"偏短 ({chars}字)"})
    elif chars > 5000:
        issues.append({"severity": "WARN", "detail": f"偏长 ({chars}字)"})

    verdict = "FAIL" if any(i["severity"] == "FAIL" for i in issues) else ("WARN" if issues else "PASS")
    return {"agent": "transition_agent", "verdict": verdict, "issues": issues,
            "evidence": f"chars={chars} paras={para_count}"}


# ── Agent 4: hook_agent ──

def hook_agent(chapter_text: str, task_pkg: dict, book_dir: Path) -> dict:
    issues = []
    hooks_text = read_text(book_dir / "truth" / "pending_hooks.md")
    ch_num = task_pkg.get("chapter", 0)
    if not hooks_text:
        return {"agent": "hook_agent", "verdict": "PASS", "issues": [], "evidence": "no hooks file"}

    active_hooks = []
    for line in hooks_text.splitlines():
        s = line.strip()
        if s.startswith("|") and "---" not in s and "hook_id" not in s.lower() and "Hook ID" not in s:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 5:
                status = cells[-1].lower() if cells[-1] else ""
                if any(t in status for t in ["open", "进行中", "active", "🟡"]):
                    active_hooks.append({"id": cells[0],
                                         "promise": cells[2] if len(cells) > 2 else "",
                                         "priority": cells[3] if len(cells) > 3 else ""})

    if not active_hooks:
        return {"agent": "hook_agent", "verdict": "PASS", "issues": [], "evidence": "no active hooks"}

    if chapter_text:
        used = 0
        for h in active_hooks:
            keywords = re.findall(r"[一-鿿]{3,}", h["promise"])
            if keywords and any(kw in chapter_text for kw in keywords):
                used += 1
        if used == 0 and len(active_hooks) >= 3:
            issues.append({"severity": "WARN",
                           "detail": f"本章未涉及 {len(active_hooks)} 条活跃伏笔"})

    for h in active_hooks:
        due_str = h.get("priority", "")
        m = re.search(r"(\d+)", due_str)
        if m and ch_num > int(m.group(1)):
            issues.append({"severity": "WARN",
                           "detail": f"伏笔 {h['id']} 可能逾期 (due<{m.group(1)})"})

    verdict = "FAIL" if any(i["severity"] == "FAIL" for i in issues) else ("WARN" if issues else "PASS")
    return {"agent": "hook_agent", "verdict": verdict, "issues": issues,
            "evidence": f"active_hooks={len(active_hooks)}"}


# ── orchestrator ──

def run_parallel_review(chapter_text: str, task_pkg: dict, book_dir: Path) -> dict:
    """Run 4 agents in parallel and merge results."""
    premise_text = read_text(book_dir / "director" / "premise.md")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(premise_agent, chapter_text, task_pkg, premise_text): "premise",
            executor.submit(consistency_agent, chapter_text, task_pkg, book_dir): "consistency",
            executor.submit(transition_agent, chapter_text, task_pkg): "transition",
            executor.submit(hook_agent, chapter_text, task_pkg, book_dir): "hooks",
        }
        results = {}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = {"agent": f"{name}_agent", "verdict": "FAIL",
                                 "issues": [{"severity": "FAIL", "detail": f"Agent 异常: {e}"}],
                                 "evidence": "error"}

    conflicts = []
    verdicts = [r["verdict"] for r in results.values()]
    if "PASS" in verdicts and "FAIL" in verdicts:
        pass_agents = [r["agent"] for r in results.values() if r["verdict"] == "PASS"]
        fail_agents = [r["agent"] for r in results.values() if r["verdict"] == "FAIL"]
        conflicts.append(f"交叉矛盾: {', '.join(pass_agents)} 通过但 {', '.join(fail_agents)} 未通过")

    if any(r["verdict"] == "FAIL" for r in results.values()):
        status = "FAIL"
    elif any(r["verdict"] == "WARN" for r in results.values()):
        status = "WARN"
    else:
        status = "PASS"

    all_issues = []
    for r in results.values():
        for i in r.get("issues", []):
            all_issues.append(f"[{r['agent']}] {i['detail']}")

    return {
        "status": status, "agents": results, "conflicts": conflicts,
        "all_issues": all_issues,
        "fail_count": sum(1 for v in verdicts if v == "FAIL"),
        "warn_count": sum(1 for v in verdicts if v == "WARN"),
        "pass_count": sum(1 for v in verdicts if v == "PASS"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--text", help="Chapter text file (required for full review)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    book = Path(args.book_dir).resolve()
    ch_str = f"{args.chapter:04d}"

    tp = book / "director" / "task_packages" / f"{ch_str}.yaml"
    if not tp.exists():
        if args.json:
            print(json.dumps({"status": "FAIL", "reason": "task_package not found"}, ensure_ascii=False))
        else:
            print("结论：FAIL\n问题：任务包不存在\n下一步：build_task_package.py")
        return 1

    task_pkg = load_task_package(tp)

    chapter_text = ""
    if args.text:
        tp_text = Path(args.text)
        if not tp_text.exists():
            candidates = list(book.glob(f"chapters/{ch_str}_*.txt")) + list(book.glob(f"chapters/{ch_str}_*.md"))
            if candidates:
                tp_text = candidates[0]
        chapter_text = read_text(tp_text) if tp_text.exists() else ""

    result = run_parallel_review(chapter_text, task_pkg, book)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        print(f"=== 多 Agent 并行审查报告 ===")
        print(f"时间：{now}")
        print(f"结论：{result['status']}")
        print(f"Agent: {result['pass_count']} PASS / {result['warn_count']} WARN / {result['fail_count']} FAIL")
        print()
        for agent_name, r in sorted(result["agents"].items()):
            icon = {"PASS": "OK", "WARN": "WARN", "FAIL": "FAIL"}[r["verdict"]]
            print(f"  [{icon}] {r['agent']}")
            for i in r.get("issues", []):
                print(f"    - {i['detail']}")
        if result["conflicts"]:
            print("\n=== 交叉矛盾 ===")
            for c in result["conflicts"]:
                print(f"  [!] {c}")
        print()
        if result["all_issues"]:
            print("--- 汇总问题（可输入 post_writeback）---")
            for i in result["all_issues"]:
                print(f"  - {i}")
        print()
        if result["status"] == "PASS":
            print("下一步：post_writeback --audit PASS")
        elif result["status"] == "WARN":
            print("下一步：人工复核后 post_writeback --audit PASS|WARN")
        else:
            print("下一步：repair-feedback")

    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
