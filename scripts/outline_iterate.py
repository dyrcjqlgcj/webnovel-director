#!/usr/bin/env python3
"""Iterative outline validator and auto-fixer for webnovel-director.

Usage:
  python outline_iterate.py <book_dir> [--max-rounds 3] [--json] [--dry-run]

Workflow:
  1. Run outline_gate_review.py + outline_causal_check.py
  2. Collect all WARN/FAIL issues
  3. Group by type, generate fix prompts
  4. Call LLM via openclaw agent for reasoning-required fixes
  5. Apply deterministic fixes directly
  6. Re-run checks
  7. Loop until: all PASS, max rounds reached, or no progress

Output: director/iterate_report.md + updated outline files
"""

from __future__ import annotations
import argparse, datetime, json, re, subprocess, sys, time
from pathlib import Path


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="ignore") if p.exists() else ""


def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def run_script(book_dir: str, script: str, *args) -> dict:
    """Run a director Python script and return JSON result."""
    scripts_dir = Path(__file__).parent
    script_path = scripts_dir / script
    if not script_path.exists():
        return {"status": "FAIL", "issues": [{"issue": f"Script not found: {script}"}]}
    cmd = [sys.executable, str(script_path), book_dir, "--json"] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60,
                                env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
        if result.returncode == 0 or result.returncode == 1:
            return json.loads(result.stdout) if result.stdout.strip() else {"status": "PASS", "issues": []}
        return {"status": "FAIL", "issues": [{"issue": result.stderr[:500]}]}
    except Exception as e:
        return {"status": "FAIL", "issues": [{"issue": str(e)}]}


def call_llm(prompt: str, max_tokens: int = 2000) -> str:
    """Call LLM via openclaw agent --local for reasoning."""
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--local", "--json", "--message", prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            return data.get("reply", data.get("content", ""))
        return ""
    except Exception as e:
        return f"[LLM调用失败: {e}]"


def collect_issues(book_dir: str) -> list[dict]:
    """Run both check scripts and collect all issues."""
    all_issues = []

    # Run outline_gate_review (6-dimension)
    gate_result = run_script(book_dir, "outline_gate_review.py")
    if gate_result.get("issues"):
        all_issues.extend(gate_result["issues"])
    if gate_result.get("chapters"):
        for ch in gate_result["chapters"]:
            for issue in ch.get("issues", []):
                issue["source"] = "outline_gate"
                all_issues.append(issue)

    # Run outline_causal_check (logic)
    causal_result = run_script(book_dir, "outline_causal_check.py")
    if causal_result.get("issues"):
        all_issues.extend(causal_result["issues"])

    return all_issues


def group_issues(issues: list[dict]) -> dict[str, list[dict]]:
    """Group issues by type for batch fixing."""
    groups = {}
    for issue in issues:
        typ = issue.get("type", issue.get("dimension", "unknown"))
        if typ not in groups:
            groups[typ] = []
        groups[typ].append(issue)
    return groups


def generate_fix_prompt(book_dir: str, group_type: str, issues: list[dict]) -> str:
    """Generate an LLM fix prompt for a group of issues."""
    book = Path(book_dir)
    ch_queue = read(book / "director" / "chapter_queue.md")
    premise = read(book / "director" / "premise.md")

    issue_lines = "\n".join(
        f"  - Ch{i.get('chapter','?')}: {i.get('issue','')} [{i.get('severity','WARN')}]"
        for i in issues[:10]
    )

    return f"""你是网文大纲修复专家。以下是 director/chapter_queue.md 的当前内容：

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
1. 对每个问题，输出 "ChXXX: [修复动作] —— 修改前: xxx → 修改后: yyy"
2. 修复动作必须是具体可执行的文字修改
3. 不要改变原有意向，只补全缺失的逻辑链接
4. 如果某章 Goal 缺失，给出一个具体的 Goal

直接输出修复方案，不要额外解释。"""


def apply_fix(chapter: int, dimension: str, suggestion: str, book_dir: str) -> bool:
    """Apply a fix suggestion to chapter_queue.md. Returns True if applied."""
    queue_path = Path(book_dir) / "director" / "chapter_queue.md"
    content = read(queue_path)
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
            ch_num = int(re.sub(r"\D", "", cells[0]))
            if ch_num != chapter:
                new_lines.append(line)
                continue
        except:
            new_lines.append(line)
            continue

        # Try to extract fix content from suggestion
        # Pattern: "修改前: xxx → 修改后: yyy" or "ChXXX: [fix]"
        fix_match = re.search(r"修改后[：:]\s*(.+?)(?:$|\n)", suggestion)
        if fix_match:
            fix_text = fix_match.group(1).strip()

            # Determine which column to fix
            if "goal" in dimension.lower() or "executability" in dimension.lower():
                cells[2] = fix_text
                changed = True
            elif "premise" in dimension.lower() or "alignment" in dimension.lower():
                cells[3] = fix_text
                changed = True
            elif "forbidden" in dimension.lower():
                cells[4] = fix_text
                changed = True
            else:
                # Default: try to improve goal
                if len(fix_text) > len(cells[2]):
                    cells[2] = fix_text
                    changed = True

        if changed:
            new_lines.append("| " + " | ".join(cells) + " |")
        else:
            new_lines.append(line)

    if changed:
        write(queue_path, "\n".join(new_lines))
    return changed


def iterate(book_dir: str, max_rounds: int = 3, dry_run: bool = False) -> dict:
    """Main iteration loop."""
    book = Path(book_dir)
    director_dir = book / "director"
    director_dir.mkdir(parents=True, exist_ok=True)

    rounds = []
    all_fixes_applied = 0

    for round_num in range(1, max_rounds + 1):
        print(f"\n=== 第 {round_num} 轮迭代 ===")
        time.sleep(0.5)

        issues = collect_issues(book_dir)
        groups = group_issues(issues)

        fail_count = sum(1 for i in issues if i.get("severity") == "FAIL")
        warn_count = sum(1 for i in issues if i.get("severity") == "WARN")

        round_result = {
            "round": round_num,
            "total_issues": len(issues),
            "fail": fail_count,
            "warn": warn_count,
            "groups": list(groups.keys()),
            "fixes_applied": 0,
        }

        print(f"  问题: {len(issues)} 个 (FAIL {fail_count}, WARN {warn_count})")

        if len(issues) == 0 or (fail_count == 0 and warn_count <= 2):
            print(f"  ✅ 通过！")
            round_result["status"] = "PASS"
            rounds.append(round_result)
            break

        if not groups:
            print(f"  ✅ 无问题分组")
            round_result["status"] = "PASS"
            rounds.append(round_result)
            break

        # Process each group
        round_fixes = 0
        for group_type, grp_issues in groups.items():
            print(f"  修复组: {group_type} ({len(grp_issues)} 个问题)")

            if dry_run:
                print(f"    [dry-run] 跳过修复")
                continue

            # Generate fix prompt
            prompt = generate_fix_prompt(book_dir, group_type, group_issues)

            # Call LLM for reasoning
            llm_response = call_llm(prompt, max_tokens=3000)
            if not llm_response or llm_response.startswith("[LLM"):
                print(f"    ⚠ LLM 调用失败，跳过")
                continue

            # Parse and apply fixes
            for issue in grp_issues[:5]:  # Max 5 fixes per group per round
                ch = issue.get("chapter", 0)
                dim = issue.get("dimension", issue.get("type", "unknown"))
                if apply_fix(ch, dim, llm_response, book_dir):
                    round_fixes += 1
                    print(f"    ✅ Ch{ch:04d} [{dim}] 已修复")

        time.sleep(1)  # Brief pause between rounds
        round_result["fixes_applied"] = round_fixes
        all_fixes_applied += round_fixes
        rounds.append(round_result)

        if round_fixes == 0:
            print(f"  ⚠ 本轮无修复动作——可能已收敛或需要人工介入")
            break

    # Final status
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
        "status": status,
        "rounds": rounds,
        "total_rounds": len(rounds),
        "fixes_applied": all_fixes_applied,
        "final_issues": {"fail": final_fail, "warn": final_warn},
        "book_dir": book_dir,
    }

    # Write iterate report
    report_text = ["# Outline 迭代修复报告", "",
                   f"时间：{datetime.datetime.now().astimezone().isoformat(timespec='seconds')}",
                   f"结论：{status}",
                   f"迭代轮数：{len(rounds)}",
                   f"修复动作：{all_fixes_applied}",
                   f"最终状态：FAIL {final_fail} / WARN {final_warn}", ""]
    for r in rounds:
        report_text.append(f"## 第 {r['round']} 轮")
        report_text.append(f"- 问题：{r['total_issues']} 个 (FAIL {r['fail']}, WARN {r['warn']})")
        report_text.append(f"- 修复：{r['fixes_applied']} 个")
        report_text.append("")
    write(director_dir / "iterate_report.md", "\n".join(report_text))

    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        print("[dry-run 模式] 不实际调用 LLM 或修改文件")

    report = iterate(args.book_dir, args.max_rounds, args.dry_run)

    if args.json:
        print("\n" + json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"\n=== 迭代完成 ===")
        print(f"结论：{report['status']}")
        print(f"轮数：{report['total_rounds']}")
        print(f"修复：{report['fixes_applied']} 个")
        print(f"最终：FAIL {report['final_issues']['fail']} / WARN {report['final_issues']['warn']}")

    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())

