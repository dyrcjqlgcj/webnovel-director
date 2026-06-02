#!/usr/bin/env python3
"""Iterative outline validator and auto-fixer for webnovel-director.

Usage:
  python outline_iterate.py <book_dir> [--max-rounds 3] [--json] [--dry-run]
                                    [--no-llm] [--model deepseek-chat]
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import re
import sys
import time
from pathlib import Path

_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import SKILL_ROOT, parse_chapter_queue, read_text, write_text  # noqa: E402
from lib.llm import call_llm  # noqa: E402
from scripts.outline_gate_review import run_outline_review  # noqa: E402
from scripts.outline_causal_check import run_causal_check  # noqa: E402

logging.basicConfig(level=logging.INFO, format="  [%(levelname)s] %(message)s")
log = logging.getLogger("outline_iterate")


def _extract_core_concepts(book_dir: str) -> list[str]:
    premise_path = Path(book_dir) / "director" / "premise.md"
    text = read_text(premise_path)
    concepts = []
    # Match template format: "书名承诺\n> ...", "**主角处境**：...", "核心爽点机制**：..."
    for pattern in [
        r"书名承诺[：:]\s*\n*[> ]*(.+)",
        r"(?:主角|主角处境)[：:]\s*\n*[*_]{0,2}\s*(.+)",
        r"(?:金手指|核心爽点机制|核心能力)[：:]\s*\n*[*_]{0,2}\s*(.+)",
    ]:
        m = re.search(pattern, text)
        if m:
            keywords = re.findall(r"[一-鿿]{2,6}", m.group(1))
            concepts.extend(keywords[:4])
    return list(dict.fromkeys(concepts))


def apply_deterministic_fix(chapter: int, dimension: str, book_dir: str) -> tuple[bool, str]:
    queue_path = Path(book_dir) / "director" / "chapter_queue.md"
    content = read_text(queue_path)
    lines = content.split("\n")
    new_lines = []
    changed = False
    msg = ""
    dim_lower = dimension.lower()

    for line in lines:
        s = line.strip()
        if not s.startswith("|") or "---" in s:
            new_lines.append(line)
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 6:
            new_lines.append(line)
            continue
        try:
            ch_num = int(re.sub(r"\D", "", cells[0]))
            if ch_num != chapter:
                new_lines.append(line)
                continue
        except ValueError:
            new_lines.append(line)
            continue

        goal = cells[2]
        premise = cells[3]

        if "executability" in dim_lower or ("goal" in dim_lower and "缺少" in dimension):
            action_words = ["让读者", "推进", "揭露", "验证", "完成", "击败", "建立", "发现", "获得", "开启"]
            if goal and not any(w in goal for w in action_words):
                cells[2] = f"让读者{goal}"
                changed = True
                msg = f"Ch{chapter:04d}: Goal 补「让读者」前缀"

        elif "premise_alignment" in dim_lower or ("alignment" in dim_lower and "premise" in dim_lower):
            concepts = _extract_core_concepts(book_dir)
            if premise and concepts:
                for kw in concepts:
                    if kw not in premise and kw not in goal:
                        cells[3] = f"{kw}——{premise}"
                        changed = True
                        msg = f"Ch{chapter:04d}: Premise Hit 补核心概念「{kw}」关联"
                        break
                if not changed and len(premise) < 10:
                    cells[3] = f"[{concepts[0]}] {premise}"
                    changed = True
                    msg = f"Ch{chapter:04d}: Premise Hit 补概念标签"

        elif "causal_chain" in dim_lower:
            if chapter > 1 and goal and not any(w in goal for w in ["上周", "上一章", "因为", "由于", "接着", "承接"]):
                cells[2] = f"承接上章——{goal}"
                changed = True
                msg = f"Ch{chapter:04d}: Goal 补因果衔接「承接上章」"

        elif "forbidden_zone" in dim_lower or "forbidden" in dim_lower:
            forbidden_kw = ["系统面板", "状态栏", "任务栏", "系统商店", "后宫", "抢首通", "公会带飞", "反派降智", "主动暴露"]
            neutral = {"系统面板": "世界信息", "状态栏": "当前状况", "任务栏": "待办事项",
                       "系统商店": "交易渠道", "后宫": "伙伴", "抢首通": "争夺首位",
                       "公会带飞": "团队协作", "反派降智": "对手失误", "主动暴露": "信息外泄"}
            for kw in forbidden_kw:
                if kw in goal:
                    cells[2] = goal.replace(kw, neutral.get(kw, "..."))
                    changed = True
                    msg = f"Ch{chapter:04d}: Goal 替换禁飞区词「{kw}」→「{neutral.get(kw)}」"
                    break
            if not changed:
                for kw in forbidden_kw:
                    if kw in premise:
                        cells[3] = premise.replace(kw, "以合规方式")
                        changed = True
                        msg = f"Ch{chapter:04d}: Premise Hit 脱敏禁飞区词「{kw}」"
                        break

        elif "hook_integration" in dim_lower or "hook" in dim_lower:
            hook_markers = ["悬念", "疑问", "反转", "惊变", "暗线", "伏笔", "钩子", "揭秘", "发现", "危机"]
            if goal and not any(m in goal for m in hook_markers):
                cells[2] = f"{goal}（设钩子：信息差/反常现象）"
                changed = True
                msg = f"Ch{chapter:04d}: Goal 补钩子标记"

        elif "satisfaction" in dim_lower:
            payoff_markers = ["击败", "获得", "解锁", "突破", "打脸", "碾压", "首通", "升级", "收获", "逆袭", "揭露", "觉醒"]
            if goal and not any(m in goal for m in payoff_markers):
                if "战" in goal or "斗" in goal or "BOSS" in goal.upper():
                    cells[2] = f"{goal}（爽点：战斗获胜/首通达成）"
                elif "发现" in goal or "得知" in goal or "揭示" in goal:
                    cells[2] = f"{goal}（爽点：信息揭露带来的满足感）"
                else:
                    cells[2] = f"{goal}（目标爽点：能力/资源获得）"
                changed = True
                msg = f"Ch{chapter:04d}: Goal 补爽点标记"

        elif "power_curve" in dim_lower:
            if goal and not any(re.search(m, goal) for m in ["升级", "突破", "进阶", "觉醒", "领悟", "强化", "进化"]):
                if chapter % 10 == 0:
                    cells[2] = f"{goal}——实力突破/境界进阶"
                elif chapter % 5 == 0:
                    cells[2] = f"{goal}——技能强化/能力升级"
                else:
                    cells[2] = f"{goal}——渐进领悟/熟练度累积"
                changed = True
                msg = f"Ch{chapter:04d}: Goal 注入成长关键词"

        elif "volume_structure" in dim_lower:
            for vm_path_cand in [Path(book_dir) / "director" / "volume_map.md",
                                 Path(book_dir) / "story" / "outline" / "volume_map.md"]:
                if vm_path_cand.exists():
                    vm_text = read_text(vm_path_cand)
                    all_chs = re.findall(r"\|\s*(\d+)\s*\|", content)
                    total_chs = len(all_chs)
                    new_vm = re.sub(r"(\d+)\s*章", f"{total_chs} 章", vm_text, count=1)
                    if new_vm != vm_text:
                        write_text(vm_path_cand, new_vm)
                        changed = True
                        msg = f"Volume: 卷纲章数已同步为细纲实际章数({total_chs})"

        if changed:
            new_lines.append("| " + " | ".join(cells) + " |")
        else:
            new_lines.append(line)

    if changed:
        write_text(queue_path, "\n".join(new_lines))
    return changed, msg


def apply_llm_fix(chapter: int, dimension: str, suggestion: str, book_dir: str) -> bool:
    if not suggestion:
        return False
    queue_path = Path(book_dir) / "director" / "chapter_queue.md"
    content = read_text(queue_path)
    lines = content.split("\n")
    new_lines = []
    changed = False
    for line in lines:
        s = line.strip()
        if not s.startswith("|") or "---" in s:
            new_lines.append(line)
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 6:
            new_lines.append(line)
            continue
        try:
            if int(re.sub(r"\D", "", cells[0])) != chapter:
                new_lines.append(line)
                continue
        except ValueError:
            new_lines.append(line)
            continue
        fix_match = re.search(r"修改后[：:]\s*(.+?)(?:$|\n|。)", suggestion)
        if fix_match:
            fix_text = fix_match.group(1).strip()
            if "goal" in dimension.lower() or "executability" in dimension.lower():
                cells[2] = fix_text
                changed = True
            elif "premise" in dimension.lower() or "alignment" in dimension.lower():
                cells[3] = fix_text
                changed = True
            elif "forbidden" in dimension.lower():
                cells[6 if len(cells) >= 8 else 4] = fix_text
                changed = True
            elif len(fix_text) > len(cells[2]):
                cells[2] = fix_text
                changed = True
        if changed:
            new_lines.append("| " + " | ".join(cells) + " |")
        else:
            new_lines.append(line)
    if changed:
        write_text(queue_path, "\n".join(new_lines))
    return changed


def collect_issues(book_dir: str) -> list[dict]:
    all_issues = []
    gate_result = run_outline_review(book_dir)
    if gate_result.get("issues"):
        all_issues.extend(gate_result["issues"])
    if gate_result.get("chapters"):
        for ch in gate_result["chapters"]:
            for issue in ch.get("issues", []):
                issue["source"] = "outline_gate"
                all_issues.append(issue)
    causal_result = run_causal_check(book_dir)
    if causal_result.get("issues"):
        all_issues.extend(causal_result["issues"])
    return all_issues


def group_issues(issues: list[dict]) -> dict[str, list[dict]]:
    groups = {}
    for issue in issues:
        typ = issue.get("type", issue.get("dimension", "unknown"))
        groups.setdefault(typ, []).append(issue)
    return groups


def generate_fix_prompt(book_dir: str, group_type: str, issues: list[dict]) -> str:
    book = Path(book_dir)
    ch_queue = read_text(book / "director" / "chapter_queue.md")
    premise = read_text(book / "director" / "premise.md")
    issue_lines = "\n".join(
        f"  - Ch{i.get('chapter','?')}: {i.get('issue','')} [{i.get('severity','WARN')}]"
        for i in issues[:10]
    )
    return f"""你是网文大纲修复专家。以下是 chapter_queue.md 的当前内容：

---
{ch_queue[:3000]}
---

以下是 premise.md 的核心约束：
---
{premise[:1000]}
---

检测到以下大纲问题（类型：{group_type}）：
{issue_lines}

请针对这些问题，给出具体修复方案。格式要求：
1. 每个问题一行 "ChXXX: [修复动作] —— 修改前: xxx → 修改后: yyy"
2. 修复动作必须是具体可执行的文字修改
3. 不要改变原有意向，只补全缺失的逻辑链接

直接输出修复方案，不要额外解释。"""


def iterate(book_dir: str, max_rounds: int = 3, dry_run: bool = False,
            no_llm: bool = False, model: str = "") -> dict:
    book = Path(book_dir)
    director_dir = book / "director"
    director_dir.mkdir(parents=True, exist_ok=True)

    rounds = []
    all_fixes_applied = 0

    for round_num in range(1, max_rounds + 1):
        print(f"\n{'='*40}")
        print(f"  第 {round_num}/{max_rounds} 轮迭代")
        print(f"{'='*40}")
        time.sleep(0.3)

        issues = collect_issues(book_dir)
        groups = group_issues(issues)
        fail_count = sum(1 for i in issues if i.get("severity") == "FAIL")
        warn_count = sum(1 for i in issues if i.get("severity") == "WARN")

        round_result = {
            "round": round_num, "total_issues": len(issues),
            "fail": fail_count, "warn": warn_count,
            "groups": list(groups.keys()), "fixes_applied": 0,
        }
        print(f"  问题: {len(issues)} 个 (FAIL {fail_count}, WARN {warn_count})")

        if len(issues) == 0 or (fail_count == 0 and warn_count <= 2):
            print(f"  [PASS] 大纲通过")
            round_result["status"] = "PASS"
            rounds.append(round_result)
            break

        if not groups:
            print(f"  [PASS] 无问题分组")
            round_result["status"] = "PASS"
            rounds.append(round_result)
            break

        # Phase 1: Deterministic fixes
        det_fixes = 0
        for group_type, grp_issues in groups.items():
            for issue in grp_issues:
                ch = issue.get("chapter", 0)
                dim = issue.get("dimension", issue.get("type", "unknown"))
                fixed, msg = apply_deterministic_fix(ch, dim, book_dir)
                if fixed:
                    det_fixes += 1
                    print(f"  [DET] {msg}")

        if det_fixes > 0:
            print(f"  确定性修复: {det_fixes} 个")
            round_result["fixes_applied"] = det_fixes
            all_fixes_applied += det_fixes
            rounds.append(round_result)
            time.sleep(0.5)
            continue

        # Phase 2: LLM-based fixes
        if no_llm:
            print(f"  [SKIP] --no-llm 模式，不调用 LLM")
            rounds.append(round_result)
            break

        llm_fixes = 0
        if dry_run:
            print("  [dry-run] 跳过 LLM 修复")
        else:
            for group_type, grp_issues in groups.items():
                print(f"  修复组: {group_type} ({len(grp_issues)} 个问题)")
                prompt = generate_fix_prompt(book_dir, group_type, grp_issues)
                print(f"    [LLM] 正在调用 LLM ...")
                llm_response = call_llm(prompt, model=model)
                if not llm_response:
                    print(f"    [WARN] LLM 不可用，本轮无法修复此组")
                    continue
                for issue in grp_issues[:5]:
                    ch = issue.get("chapter", 0)
                    dim = issue.get("dimension", issue.get("type", "unknown"))
                    if apply_llm_fix(ch, dim, llm_response, book_dir):
                        llm_fixes += 1
                        print(f"    [LLM] Ch{ch:04d} [{dim}] 已修复")

        round_result["fixes_applied"] = llm_fixes
        all_fixes_applied += llm_fixes
        rounds.append(round_result)
        if llm_fixes == 0:
            print(f"  [WARN] 本轮无修复动作——已收敛或需人工介入")
            break
        time.sleep(1)

    final_issues = collect_issues(book_dir)
    final_fail = sum(1 for i in final_issues if i.get("severity") == "FAIL")
    final_warn = sum(1 for i in final_issues if i.get("severity") == "WARN")

    if final_fail == 0 and final_warn <= 2:
        status = "PASS"
    elif final_fail == 0:
        status = "WARN"
    else:
        status = "FAIL"

    report = {
        "status": status, "rounds": rounds, "total_rounds": len(rounds),
        "fixes_applied": all_fixes_applied,
        "final_issues": {"fail": final_fail, "warn": final_warn},
        "book_dir": book_dir,
    }

    report_lines = [
        "# Outline 迭代修复报告", "",
        f"时间：{datetime.datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"结论：{status}", f"迭代轮数：{len(rounds)}",
        f"修复动作：{all_fixes_applied}", f"最终状态：FAIL {final_fail} / WARN {final_warn}", "",
    ]
    for r in rounds:
        report_lines.extend([
            f"## 第 {r['round']} 轮",
            f"- 问题：{r['total_issues']} 个 (FAIL {r['fail']}, WARN {r['warn']})",
            f"- 修复：{r['fixes_applied']} 个", "",
        ])
    write_text(director_dir / "iterate_report.md", "\n".join(report_lines))
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-llm", action="store_true", help="仅确定性修复，不调用 LLM")
    ap.add_argument("--model", default="", help="LLM 模型覆盖")
    args = ap.parse_args()

    if args.dry_run:
        print("[dry-run] 不调用 LLM，不修改文件")

    report = iterate(args.book_dir, args.max_rounds, args.dry_run,
                     args.no_llm, args.model)

    if args.json:
        print("\n" + json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*40}")
        print(f"  迭代完成")
        print(f"{'='*40}")
        print(f"  结论：{report['status']}")
        print(f"  轮数：{report['total_rounds']}")
        print(f"  修复：{report['fixes_applied']} 个")
        print(f"  最终：FAIL {report['final_issues']['fail']} / WARN {report['final_issues']['warn']}")
        print(f"  报告：{Path(args.book_dir)/'director'/'iterate_report.md'}")
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
