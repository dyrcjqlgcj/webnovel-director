#!/usr/bin/env python3
"""Migrate an inkos-style project to full webnovel-director structure.

Usage:
  python migrate_project.py <book_dir> [--json] [--dry-run]

Detects inkos project markers (truth/, chapters/, book.json, story/, etc.),
runs sync + premise extraction, creates missing director/ scaffolding,
and prints a structured migration report.
"""
from __future__ import annotations
from pathlib import Path
import argparse, datetime, json, re, subprocess, sys

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent
TEMPLATE_DIR = SKILL_ROOT / "templates"

# ----------------------------------------------------------------
# detection
# ----------------------------------------------------------------

INKOS_MARKERS = [
    "chapters",           # inkos CHAPTERS dir
    "story",              # inkos story/ dir
    "truth",              # shared truth/ dir
    "book.json",          # classic inkos metadata
    "inkos.json",         # newer inkos metadata
    "inkos.yaml",         # YAML variant
    "story/current_focus.md",
    "story/author_intent.md",
    "story/book_rules.md",
]


def detect_inkos(book_dir: Path) -> dict[str, object]:
    """Check which inkos features exist in book_dir.

    Returns a dict with found/absent marker lists and an overall confidence
    score (0-100).
    """
    found: list[str] = []
    absent: list[str] = []
    for marker in INKOS_MARKERS:
        if (book_dir / marker).exists():
            found.append(marker)
        else:
            absent.append(marker)
    # confidence: each found marker ~ points; chapters counts double
    score = sum(2 if m == "chapters" else 1 for m in found)
    confidence = min(100, score * 12)
    return {
        "is_inkos": len(found) >= 2,
        "confidence": confidence,
        "found": found,
        "absent": absent,
    }


def detect_director(book_dir: Path) -> dict[str, object]:
    """Check which webnovel-director files already exist."""
    required = [
        "director/premise.md",
        "director/director_state.json5",
        "director/chapter_queue.md",
        "director/last_audit.md",
        "director/audit_log.md",
        "truth/current_state.md",
        "truth/resource_ledger.md",
        "truth/particle_ledger.md",
        "truth/pending_hooks.md",
    ]
    found = []
    missing = []
    for rel in required:
        if (book_dir / rel).exists():
            found.append(rel)
        else:
            missing.append(rel)
    return {"found": found, "missing": missing}


# ----------------------------------------------------------------
# migration steps
# ----------------------------------------------------------------

def run_sync(book_dir: Path) -> tuple[int, str, str]:
    """Run sync_inkos_state.py --write."""
    cp = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "sync_inkos_state.py"),
         str(book_dir), "--write", "--json"],
        capture_output=True, text=True,
    )
    return cp.returncode, cp.stdout.strip(), cp.stderr.strip()


def run_premise(book_dir: Path) -> tuple[int, str, str]:
    """Run extract_premise.py to generate director/premise.md."""
    out = str(book_dir / "director" / "premise.md")
    cp = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "extract_premise.py"),
         str(book_dir), "--out", out, "--json"],
        capture_output=True, text=True,
    )
    return cp.returncode, cp.stdout.strip(), cp.stderr.strip()


def ensure_director_files(book_dir: Path) -> list[str]:
    """Create any still-missing director/ scaffolding from templates."""
    created: list[str] = []
    templates = {
        "director/last_audit.md": "last_audit.md",
        "director/audit_log.md": "audit_log.md",
    }
    # chapter_queue needs a bit more care — create from template if missing
    if not (book_dir / "director" / "chapter_queue.md").exists():
        templates["director/chapter_queue.md"] = "chapter_queue.md"

    for rel, tmpl_name in templates.items():
        dst = book_dir / rel
        if dst.exists():
            continue
        src = TEMPLATE_DIR / tmpl_name
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        created.append(rel)
    return created


# ----------------------------------------------------------------
# report
# ----------------------------------------------------------------

def build_report(book_dir: Path, inkos_detect: dict, director_detect: dict,
                 sync_ok: bool, premise_ok: bool, created: list[str],
                 errors: list[str]) -> dict:
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    total_steps = 3  # detect + sync + premise
    done = (1 if inkos_detect["is_inkos"] else 0) + (1 if sync_ok else 0) + (1 if premise_ok else 0)
    status = "PASS" if done == total_steps and not errors else ("WARN" if done >= 1 else "FAIL")
    return {
        "status": status,
        "book": str(book_dir),
        "inkos": inkos_detect,
        "director_before": director_detect,
        "steps": {
            "sync_inkos_state": "OK" if sync_ok else "FAIL",
            "extract_premise": "OK" if premise_ok else "FAIL",
            "scaffolding_created": created,
        },
        "errors": errors,
        "completedAt": now,
    }


# ----------------------------------------------------------------
# main
# ----------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="inkos → webnovel-director 一键迁移",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python migrate_project.py ~/workspace/我的书
  python migrate_project.py ~/workspace/我的书 --json
  python migrate_project.py ~/workspace/我的书 --dry-run
""")
    ap.add_argument("book_dir", help="inkos 项目目录")
    ap.add_argument("--json", action="store_true", help="JSON 格式输出")
    ap.add_argument("--dry-run", action="store_true", help="仅检测不写入")
    args = ap.parse_args()

    book = Path(args.book_dir).resolve()
    errors: list[str] = []

    if not book.exists():
        if args.json:
            print(json.dumps({"status": "FAIL", "error": f"目录不存在: {book}"},
                             ensure_ascii=False, indent=2))
        else:
            print(f"结论：FAIL — 目录不存在: {book}")
        return 1

    # ---- Phase 1: Detect ----
    inkos = detect_inkos(book)
    director_before = detect_director(book)

    if not inkos["is_inkos"]:
        errors.append("未检测到 inkos 项目特征（需至少 2 个特征标记）")
        report = build_report(book, inkos, director_before, False, False, [], errors)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print("结论：FAIL")
            print(f"依据：book={book}; inkos_markers_found={inkos['found']}")
            print(f"检测到的标记：{inkos['found']}")
            print(f"缺失的标记：{inkos['absent']}")
            print("建议：确认目录是否为 inkos 项目，或使用 init_project.py 新建")
        return 1

    # ---- Phase 2: Sync state (--write) ----
    sync_ok = False
    sync_out = ""
    if not args.dry_run:
        rc, sync_out, sync_err = run_sync(book)
        sync_ok = (rc == 0)
        if not sync_ok:
            errors.append(f"sync_inkos_state.py 失败: {sync_err or sync_out[:200]}")

    # ---- Phase 3: Extract premise ----
    premise_ok = False
    premise_out = ""
    if not args.dry_run:
        rc, premise_out, premise_err = run_premise(book)
        premise_ok = (rc == 0)
        if not premise_ok:
            errors.append(f"extract_premise.py 失败: {premise_err or premise_out[:200]}")

    # ---- Phase 4: Ensure scaffolding ----
    created: list[str] = [] if args.dry_run else ensure_director_files(book)

    # ---- Phase 5: Final detection (post-migration) ----
    director_after = detect_director(book) if not args.dry_run else director_before

    report = build_report(book, inkos, director_before, sync_ok, premise_ok, created, errors)

    if args.json:
        report["director_after"] = director_after
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"结论：{report['status']}")
        print(f"依据：book={book}")
        print(f"inkos 特征：置信度 {inkos['confidence']}%")
        print(f"  找到：{', '.join(inkos['found']) or '无'}")
        print(f"  缺失：{', '.join(inkos['absent']) or '无'}")
        print()
        print(f"迁移前 director 文件：已存在 {len(director_before['found'])} / 缺失 {len(director_before['missing'])}")
        if director_before['missing']:
            for m in director_before['missing']:
                print(f"  - 缺失: {m}")
        print()
        if args.dry_run:
            print("模式：dry-run（未执行任何写入操作）")
        else:
            print(f"Phase 2 - sync_inkos_state: {'[OK]' if sync_ok else '[FAIL]'}")
            print(f"Phase 3 - extract_premise: {'[OK]' if premise_ok else '[FAIL]'}")
            if created:
                print(f"Phase 4 - 补充创建：{', '.join(created)}")
            print()
            print(f"迁移后 director 文件：已存在 {len(director_after['found'])} / 缺失 {len(director_after.get('missing', []) or [])}")
            if director_after.get('missing'):
                for m in director_after['missing']:
                    print(f"  - 仍缺失: {m}")
        print()
        print("建议：")
        print("  1. 人工审 director/premise.md 并填写命题三要素")
        print("  2. 运行 outline_gate_review.py 验证")
        print("  3. review_chapter.py 逐章过审一致性")
        if director_after and director_after.get('missing'):
            print("  4. 补全仍缺失的文件")

    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
