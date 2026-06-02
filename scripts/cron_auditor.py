#!/usr/bin/env python3
"""Gateway cron task auditor for webnovel-director.

Usage:
  python cron_auditor.py --check <book_dir>
  python cron_auditor.py --check <book_dir> --json

Scans director_state.json5 for cron configuration and produces a colour-coded
audit report.  Verifies:
  1. cron jobId is set and plausible
  2. The cron prompt mentions director gate files (canWrite, blockers, etc.)
  3. Recent run activity (last 24 h) is indicated in state or logs
"""

from __future__ import annotations
import argparse, datetime, json, re, sys
from pathlib import Path

# ── ANSI colour helpers ──────────────────────────────────────────────

class Ansi:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"


def _c(colour: str, text: str) -> str:
    """Wrap text in ANSI colour + reset."""
    return f"{colour}{text}{Ansi.RESET}"


def ok(text: str) -> str:
    return _c(Ansi.GREEN, f"✓ {text}")


def warn(text: str) -> str:
    return _c(Ansi.YELLOW, f"⚠ {text}")


def fail(text: str) -> str:
    return _c(Ansi.RED, f"✗ {text}")


def info(text: str) -> str:
    return _c(Ansi.CYAN, f"ℹ {text}")


def bold(text: str) -> str:
    return _c(Ansi.BOLD, text)


def dim(text: str) -> str:
    return _c(Ansi.DIM, text)


# ── JSON5 lite parser ────────────────────────────────────────────────

def strip_json5(text: str) -> str:
    """Crude JSON5 → JSON for well-behaved director_state files."""
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"([,{]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def load_director_state(book_dir: Path) -> dict:
    """Load director_state.json5, returning empty dict on failure."""
    state_path = book_dir / "director" / "director_state.json5"
    if not state_path.exists():
        return {}
    text = state_path.read_text(encoding="utf-8-sig", errors="ignore")
    try:
        return json.loads(strip_json5(text))
    except Exception:
        # Best-effort regex fallback
        data: dict = {}
        for key in ("bookId", "title", "canWrite", "lastRun",
                    "currentChapter", "activeVolume", "status"):
            m = re.search(rf'\b{key}\s*:\s*([^,\n}}]+)', text)
            if m:
                raw = m.group(1).strip().strip('"\'')
                if raw in {"true", "false"}:
                    data[key] = raw == "true"
                elif raw.isdigit():
                    data[key] = int(raw)
                else:
                    data[key] = raw
        # Extract cron block
        cron_block = re.search(r'\bcron\s*:\s*(\{[^}]*\})', text, re.S)
        if cron_block:
            cron_data: dict = {}
            for ck in ("enabled", "jobId", "schedule", "lastRun"):
                cm = re.search(rf'\b{ck}\s*:\s*([^,\n}}]+)', cron_block.group(1))
                if cm:
                    val = cm.group(1).strip().strip('"\'')
                    if val in {"true", "false"}:
                        cron_data[ck] = val == "true"
                    else:
                        cron_data[ck] = val
            data["cron"] = cron_data
        # Extract blockers
        bm = re.search(r"\bblockers\s*:\s*(\[[^\]]*\])", text, re.S)
        if bm:
            try:
                import ast
                data["blockers"] = ast.literal_eval(bm.group(1).replace("'", '"'))
            except Exception:
                data["blockers"] = [bm.group(1)]
        return data


# ── Check helpers ────────────────────────────────────────────────────

def check_cron_job_id(state: dict) -> tuple[bool, str, str]:
    """Verify cron.jobId is set and looks valid."""
    cron = state.get("cron", {})
    if not cron:
        return False, fail("cron 块缺失"), "director_state.json5 中无 cron 配置块"

    enabled = cron.get("enabled", False)
    job_id = cron.get("jobId", "")

    if not enabled:
        return True, warn("cron.enabled=false — 自动写作未开启"), ""

    if not job_id or not str(job_id).strip():
        return False, fail("cron.jobId 为空 — 无有效 cron 任务 ID"), "需设置 jobId 并启用 cron"

    return True, ok(f"cron.jobId={job_id}"), ""


def check_gate_bypass(state: dict) -> tuple[bool, str, str]:
    """Check that the cron setup doesn't bypass director gate."""
    issues = []
    cron = state.get("cron", {})

    # canWrite must be true when cron is enabled
    if cron.get("enabled"):
        if not state.get("canWrite"):
            issues.append(fail("canWrite=false 但 cron 已启用 — 闸门绕过风险"))

    # blockers must be empty
    blockers = state.get("blockers", [])
    if isinstance(blockers, str):
        blockers = [blockers] if blockers else []
    if blockers:
        issues.append(fail(f"blockers 非空 ({len(blockers)}项) — cron 写前闸门失效"))

    if issues:
        return False, "\n  ".join(issues), "清空 blockers 并确保 canWrite=true 后 cron 才安全"

    return True, ok("闸门通过 — canWrite=true, blockers=0"), ""


def check_recent_activity(state: dict) -> tuple[bool, str, str]:
    """Check last run activity in the last 24 hours."""
    cron = state.get("cron", {})
    last_run = cron.get("lastRun", "")

    now = datetime.datetime.now().astimezone()
    cutoff = now - datetime.timedelta(hours=24)

    if not last_run or not str(last_run).strip():
        return False, warn("cron.lastRun 为空 — 无最近运行记录"), "cron 可能未实际触发；运行 openclaw cron list 确认"

    try:
        # Try ISO 8601 parsing
        ts = last_run
        if isinstance(ts, str):
            ts = ts.replace("Z", "+00:00")
            run_dt = datetime.datetime.fromisoformat(ts)
        else:
            run_dt = datetime.datetime.fromtimestamp(float(ts), tz=datetime.timezone.utc)
    except (ValueError, TypeError, OSError):
        return False, warn(f"cron.lastRun 无法解析: {last_run}"), "请用 ISO 8601 格式或 Unix 时间戳"

    delta = now - run_dt
    hours_ago = delta.total_seconds() / 3600

    if run_dt >= cutoff:
        return True, ok(f"最近运行: {hours_ago:.1f} 小时前 ({run_dt.isoformat(timespec='minutes')})"), ""
    else:
        return False, warn(f"最近运行: {hours_ago:.0f} 小时前 — 超过 24h"), "cron 调度可能已停；运行 openclaw cron list 确认状态"


def check_cron_prompt_quality(book_dir: Path) -> tuple[bool, str, str]:
    """Lightweight check: does a cron prompt exist and mention gate terms?"""
    # Check common locations for stored cron prompts
    candidates = [
        book_dir / "director" / "cron_prompt.txt",
        book_dir / "director" / "cron_prompt.md",
        book_dir / "cron" / "prompt.txt",
    ]
    prompt_path = None
    for p in candidates:
        if p.exists():
            prompt_path = p
            break

    if prompt_path is None:
        return False, warn("未找到 cron prompt 文件"), "建议在 director/ 下保存 cron_prompt.txt 以供审计"

    prompt = prompt_path.read_text(encoding="utf-8-sig", errors="ignore")

    # Check for required gate mentions
    gate_terms = ["canWrite", "blockers", "director/premise.md", "chapter_queue"]
    found = [t for t in gate_terms if t.lower() in prompt.lower()]
    missing = [t for t in gate_terms if t.lower() not in prompt.lower()]

    if missing:
        return False, fail(f"cron prompt 缺少闸门关键词: {', '.join(missing)}"), \
               "cron prompt 须包含 canWrite/blockers/director/premise.md/chapter_queue"
    return True, ok(f"cron prompt 包含所有闸门关键词 ({', '.join(found)})"), ""


def extract_schedule_hint(state: dict) -> str:
    """Extract readable schedule from state."""
    cron = state.get("cron", {})
    schedule = cron.get("schedule", "")
    if not schedule or not str(schedule).strip():
        return dim("（未设置 schedule）")
    return f"schedule={schedule}"


# ── Main reporter ────────────────────────────────────────────────────

def run_audit(book_dir: Path, json_mode: bool = False) -> int:
    state_path = book_dir / "director" / "director_state.json5"
    if not state_path.exists():
        if json_mode:
            print(json.dumps({"status": "FAIL", "reason": "director_state.json5 不存在"},
                             ensure_ascii=False, indent=2))
        else:
            print(fail("director_state.json5 不存在 — 请先 init_project"))
        return 1

    state = load_director_state(book_dir)
    if not state:
        if json_mode:
            print(json.dumps({"status": "FAIL", "reason": "director_state.json5 无法解析"},
                             ensure_ascii=False, indent=2))
        else:
            print(fail("director_state.json5 无法解析"))
        return 1

    cron = state.get("cron", {})
    checks = [
        ("Cron Job ID 有效性", check_cron_job_id(state)),
        ("闸门绕过检测",     check_gate_bypass(state)),
        ("24h 运行记录",      check_recent_activity(state)),
        ("Cron Prompt 审计",  check_cron_prompt_quality(book_dir)),
    ]

    passes = sum(1 for _, (ok_flag, _, _) in checks if ok_flag)
    total = len(checks)

    if json_mode:
        items = []
        for name, (ok_flag, msg, suggestion) in checks:
            # Strip ANSI for JSON
            clean = re.sub(r"\033\[[0-9;]*m", "", msg)
            items.append({"check": name, "pass": ok_flag, "message": clean, "suggestion": suggestion})
        result = {
            "status": "PASS" if passes == total else ("WARN" if passes >= total - 1 else "FAIL"),
            "book": str(book_dir),
            "title": state.get("title", ""),
            "cron_enabled": cron.get("enabled", False),
            "cron_jobId": cron.get("jobId", ""),
            "schedule": cron.get("schedule", ""),
            "passes": passes,
            "total": total,
            "checks": items,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if passes == total else 1

    # ── Colour terminal report ──────────────────────────────────────
    title = state.get("title", book_dir.name)
    book_id = state.get("bookId", "—")

    print()
    print(bold("╔══════════════════════════════════════════════════════╗"))
    print(bold("║") + bold("  webnovel-director · Cron 审计报告").center(50) + bold("║"))
    print(bold("╠══════════════════════════════════════════════════════╣"))
    print(bold("║ ") + f"项目: {title}" + " " * max(1, 39 - len(f"项目: {title}")) + bold("║"))
    print(bold("║ ") + f"ID: {book_id}" + " " * max(1, 42 - len(f"ID: {book_id}")) + bold("║"))
    cron_enabled_str = ok("已启用") if cron.get("enabled") else dim("未启用")
    print(bold("║ ") + f"cron: {cron_enabled_str}  {extract_schedule_hint(state)}" + " " * max(1, 6) + bold("║"))
    print(bold("╠══════════════════════════════════════════════════════╣"))

    failures_count = 0
    for name, (ok_flag, msg, suggestion) in checks:
        status_icon = ok(name) if ok_flag else name
        lines = msg.split("\n")
        print(bold("║ ") + f"{status_icon}".ljust(46) + bold("║"))
        for line in lines[1:]:
            print(bold("║   ") + f"{line}".ljust(44) + bold("║"))
        if suggestion and not ok_flag:
            print(bold("║   ") + dim(f"→ {suggestion}")[:46].ljust(44) + bold("║"))
        if not ok_flag:
            failures_count += 1

    print(bold("╠══════════════════════════════════════════════════════╣"))

    # Summary
    if failures_count == 0:
        summary = ok(f"全部通过 ({passes}/{total})")
    elif failures_count <= 1:
        summary = warn(f"{failures_count} 项需关注 ({passes}/{total})")
    else:
        summary = fail(f"{failures_count} 项失败 ({passes}/{total})")

    print(bold("║ ") + summary.ljust(46) + bold("║"))
    print(bold("╚══════════════════════════════════════════════════════╝"))
    print()

    # ── Actionable next steps ───────────────────────────────────────
    print(bold("下一步操作："))
    print(f"  1. 运行 {info('openclaw cron list')} 确认 Gateway 中 cron 任务状态")
    if not cron.get("jobId"):
        print(f"  2. {warn('设置 director_state.json5 中 cron.jobId')}")
    if not cron.get("schedule"):
        print(f"  3. {warn('设置 cron.schedule（cron 表达式）')}")
    print()

    return 0 if failures_count == 0 else 1


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description="Audit webnovel-director cron integration")
    ap.add_argument("--check", dest="book_dir", required=True,
                    help="Book directory containing director/director_state.json5")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()
    return run_audit(Path(args.book_dir).resolve(), args.json)


if __name__ == "__main__":
    raise SystemExit(main())
