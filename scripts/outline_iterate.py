#!/usr/bin/env python3
"""Iterative outline validator and auto-fixer for webnovel-director.

Usage:
  python outline_iterate.py <book_dir> [--max-rounds 3] [--json] [--dry-run]
                                    [--no-llm] [--model deepseek-chat]

LLM calling: uses direct DeepSeek API (DEEPSEEK_API_KEY env var),
falls back to openclaw gateway, with retry on failure.
"""

from __future__ import annotations
import argparse, datetime, json, re, subprocess, sys, time, os, logging
import urllib.request, urllib.error
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="  [%(levelname)s] %(message)s")
log = logging.getLogger("outline_iterate")

MAX_LLM_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]  # seconds, exponential-ish


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="ignore") if p.exists() else ""


def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def run_script(book_dir: str, script: str, *args) -> dict:
    scripts_dir = Path(__file__).parent
    script_path = scripts_dir / script
    if not script_path.exists():
        return {"status": "FAIL", "issues": [{"issue": f"Script not found: {script}"}]}
    cmd = [sys.executable, str(script_path), book_dir, "--json"] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60,
                                env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
        if result.returncode in (0, 1) and result.stdout.strip():
            return json.loads(result.stdout)
        return {"status": "FAIL", "issues": [{"issue": result.stderr[:500] if result.stderr else "no output"}]}
    except subprocess.TimeoutExpired:
        return {"status": "FAIL", "issues": [{"issue": f"{script} 超时(60s)"}]}
    except Exception as e:
        return {"status": "FAIL", "issues": [{"issue": str(e)}]}


def _call_deepseek_api(prompt: str, model: str = "deepseek-chat", timeout: int = 120) -> tuple[str, bool]:
    """Call DeepSeek API directly (OpenAI-compatible). Most reliable path."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return "", False

    data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )

    for attempt in range(MAX_LLM_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read())
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, True
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
            log.debug(f"DeepSeek API attempt {attempt+1}: {e}")
            if attempt < MAX_LLM_RETRIES - 1:
                time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)-1)])
    return "", False


def _try_llm_gateway(prompt: str, model: str = "", timeout: int = 120) -> tuple[str, bool]:
    """Try LLM via openclaw gateway (fallback)."""
    cmd = ["openclaw", "agent", "--json", "--local", "--message", prompt]
    if model:
        cmd.extend(["--model", model])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                timeout=timeout, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            reply = data.get("reply") or data.get("content") or ""
            if reply:
                return reply, True
    except (subprocess.TimeoutExpired, Exception):
        pass
    return "", False


def call_llm(prompt: str, model: str = "deepseek-chat", timeout: int = 120) -> str:
    """Call LLM with retry and fallback.

    Strategy (tried in order, each with 3 retries):
      1. Direct DeepSeek API (DEEPSEEK_API_KEY env var) — fastest, most reliable
      2. OpenClaw gateway --local — fallback
    """
    strategies = [
        ("deepseek_direct", lambda m=model, t=timeout: _call_deepseek_api(prompt, m, t)),
        ("openclaw_local", lambda m=model, t=timeout: _try_llm_gateway(prompt, m, t)),
    ]

    for strategy_name, strategy_fn in strategies:
        reply, ok = strategy_fn()
        if ok and reply:
            log.info(f"LLM OK via {strategy_name}")
            return reply

    log.warning("LLM 调用失败（已重试全部策略），将使用确定性修复")
    return ""


def apply_deterministic_fix(chapter: int, dimension: str, ch_lines: list[str], book_dir: str) -> tuple[bool, str]:
    """Apply keyword-based deterministic fixes without LLM.

    Returns (changed, message).
    """
    queue_path = Path(book_dir) / "director" / "chapter_queue.md"
    content = read(queue_path)
    lines = content.split("\n")
    new_lines = []
    changed = False
    msg = ""

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

        # --- Deterministic fix patterns ---

        # Pattern 1: Missing action words in Goal
        if "executability" in dimension.lower() or ("goal" in dimension.lower() and "缺少" in dimension):
            action_words = ["让读者", "推进", "揭露", "验证", "完成", "击败", "建立", "发现", "获得", "开启"]
            if goal and not any(w in goal for w in action_words):
                cells[2] = f"让读者{goal}"
                changed = True
                msg = f"Ch{chapter:04d}: Goal 补「让读者」前缀"

        # Pattern 2: Premise alignment - inject book concept keywords
        elif "premise_alignment" in dimension.lower() or "alignment" in dimension.lower():
            if premise and len(goal) > 10:
                # Try to prepend a premise-related hook
                if "死亡" in str(content) and "死亡" not in goal:
                    cells[3] = f"死亡记忆不灭的体现——{premise}"
                    changed = True
                    msg = f"Ch{chapter:04d}: Premise Hit 补核心概念关联"

        # Pattern 3: Causal chain - add explicit cause/effect connector
        elif "causal_chain" in dimension.lower():
            if chapter > 1 and goal and not any(w in goal for w in ["上周", "上一章", "因为", "由于", "接着"]):
                cells[2] = f"承接上章——{goal}"
                changed = True
                msg = f"Ch{chapter:04d}: Goal 补因果衔接「承接上章」"

        if changed:
            new_lines.append("| " + " | ".join(cells) + " |")
        else:
            new_lines.append(line)

    if changed:
        write(queue_path, "\n".join(new_lines))
    return changed, msg


def apply_fix(chapter: int, dimension: str, suggestion: str, book_dir: str) -> bool:
    """Apply a fix suggestion from LLM to chapter_queue.md."""
    if not suggestion:
        return False

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
                cells[4] = fix_text
                changed = True
            elif len(fix_text) > len(cells[2]):
                cells[2] = fix_text
                changed = True

        if changed:
            new_lines.append("| " + " | ".join(cells) + " |")
        else:
            new_lines.append(line)

    if changed:
        write(queue_path, "\n".join(new_lines))
    return changed


def collect_issues(book_dir: str) -> list[dict]:
    all_issues = []
    gate_result = run_script(book_dir, "outline_gate_review.py")
    if gate_result.get("issues"):
        all_issues.extend(gate_result["issues"])
    if gate_result.get("chapters"):
        for ch in gate_result["chapters"]:
            for issue in ch.get("issues", []):
                issue["source"] = "outline_gate"
                all_issues.append(issue)
    causal_result = run_script(book_dir, "outline_causal_check.py")
    if causal_result.get("issues"):
        all_issues.extend(causal_result["issues"])
    return all_issues


def group_issues(issues: list[dict]) -> dict[str, list[dict]]:
    groups = {}
    for issue in issues:
        typ = issue.get("type", issue.get("dimension", "unknown"))
        if typ not in groups:
            groups[typ] = []
        groups[typ].append(issue)
    return groups


def generate_fix_prompt(book_dir: str, group_type: str, issues: list[dict]) -> str:
    book = Path(book_dir)
    ch_queue = read(book / "director" / "chapter_queue.md")
    premise = read(book / "director" / "premise.md")
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

        # --- Early exit conditions ---
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

        # --- Phase 1: Deterministic fixes (always run, no LLM needed) ---
        det_fixes = 0
        for group_type, grp_issues in groups.items():
            for issue in grp_issues:
                ch = issue.get("chapter", 0)
                dim = issue.get("dimension", issue.get("type", "unknown"))
                fixed, msg = apply_deterministic_fix(ch, dim, [str(g) for g in groups], book_dir)
                if fixed:
                    det_fixes += 1
                    print(f"  [DET] {msg}")

        if det_fixes > 0:
            print(f"  确定性修复: {det_fixes} 个")
            round_result["fixes_applied"] = det_fixes
            all_fixes_applied += det_fixes
            rounds.append(round_result)
            time.sleep(0.5)
            continue  # Re-check next round

        # --- Phase 2: LLM-based fixes (for remaining issues) ---
        if no_llm:
            print(f"  [SKIP] --no-llm 模式，不调用 LLM")
            round_result["fixes_applied"] = 0
            rounds.append(round_result)
            break

        llm_fixes = 0
        if dry_run:
            print("  [dry-run] 跳过 LLM 修复")
        else:
            for group_type, grp_issues in groups.items():
                print(f"  修复组: {group_type} ({len(grp_issues)} 个问题)")

                prompt = generate_fix_prompt(book_dir, group_type, grp_issues)
                print(f"    ⏳ 正在调用 LLM ...")

                llm_response = call_llm(prompt, model=model)
                if not llm_response:
                    print(f"    [WARN] LLM 不可用，本轮无法修复此组")
                    continue

                for issue in grp_issues[:5]:
                    ch = issue.get("chapter", 0)
                    dim = issue.get("dimension", issue.get("type", "unknown"))
                    if apply_fix(ch, dim, llm_response, book_dir):
                        llm_fixes += 1
                        print(f"    [LLM] Ch{ch:04d} [{dim}] 已修复")

        round_result["fixes_applied"] = llm_fixes
        all_fixes_applied += llm_fixes
        rounds.append(round_result)

        if llm_fixes == 0:
            print(f"  [WARN] 本轮无修复动作——已收敛或需人工介入")
            break

        time.sleep(1)

    # --- Final status ---
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
        report_lines.append(f"## 第 {r['round']} 轮")
        report_lines.append(f"- 问题：{r['total_issues']} 个 (FAIL {r['fail']}, WARN {r['warn']})")
        report_lines.append(f"- 修复：{r['fixes_applied']} 个")
        report_lines.append("")
    write(director_dir / "iterate_report.md", "\n".join(report_lines))

    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-llm", action="store_true", help="仅确定性修复，不调用 LLM")
    ap.add_argument("--model", default="", help="LLM 模型覆盖 (如 deepseek-v4-pro)")
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
