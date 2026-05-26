#!/usr/bin/env python3
"""Multi-book project manager for webnovel-director.

Usage:
  python project_manager.py list [--json]
  python project_manager.py doctor <name> [--json]
  python project_manager.py switch <name>
  python project_manager.py new <dir> --title "书名" [--force]

list    List all webnovel-director projects under the workspace.
doctor  Run director_doctor.py on the named project.
switch  Set the named project as the active project.
new     Quick-initialize a new book via init_project.py.
"""
from __future__ import annotations
from pathlib import Path
import argparse, json, re, subprocess, sys

WORKSPACE = Path.home() / ".openclaw" / "workspace"
ACTIVE_FILE = WORKSPACE / ".active_project"
SCRIPTS_DIR = Path(__file__).resolve().parent

# ----------------------------------------------------------------
# helpers
# ----------------------------------------------------------------

def find_projects() -> list[Path]:
    """Walk WORKSPACE and find dirs containing director/director_state.json5."""
    projects: list[Path] = []
    if not WORKSPACE.exists():
        return projects
    for d in WORKSPACE.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        state = d / "director" / "director_state.json5"
        if state.exists():
            projects.append(d)
    return sorted(projects, key=lambda p: p.name.lower())


def parse_json5_state(path: Path) -> dict[str, object]:
    """Minimal JSON5-like parser: extract top-level key: value pairs."""
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    out: dict[str, object] = {}
    for key in ["bookId", "title", "status", "activeVolume", "currentChapter",
                "canWrite", "lastAuditStatus", "updatedAt"]:
        m = re.search(rf'\b{key}\s*:\s*([^,\n}}]+)', text)
        if m:
            raw = m.group(1).strip().strip('"\'')
            if raw in {"true", "false"}:
                out[key] = raw == "true"
            elif re.match(r"^\d+$", raw):
                out[key] = int(raw)
            else:
                out[key] = raw
    blk = re.search(r"\bblockers\s*:\s*\[([^\]]*)\]", text, re.S)
    if blk:
        out["blockers"] = [b.strip().strip('"\'') for b in blk.group(1).split(",") if b.strip()]
    return out


def find_project_by_name(name: str) -> Path | None:
    """Look up a project by its directory name (case-insensitive)."""
    lower = name.lower()
    for p in find_projects():
        if p.name.lower() == lower:
            return p
    return None


def get_active_project() -> str | None:
    """Read the active project name from .active_project."""
    if ACTIVE_FILE.exists():
        return ACTIVE_FILE.read_text(encoding="utf-8").strip()
    return None


def run_script(script_name: str, *args: str) -> subprocess.CompletedProcess:
    """Run a peer script from the same scripts/ directory."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


# ----------------------------------------------------------------
# subcommand handlers
# ----------------------------------------------------------------

def cmd_list(json_output: bool = False) -> int:
    """List all detected webnovel-director projects."""
    projects = find_projects()
    active = get_active_project()

    results = []
    for p in projects:
        state = parse_json5_state(p / "director" / "director_state.json5")
        results.append({
            "name": p.name,
            "path": str(p),
            "active": p.name == active,
            "title": state.get("title", ""),
            "status": state.get("status", ""),
            "currentChapter": state.get("currentChapter", 0),
            "canWrite": state.get("canWrite", False),
            "updatedAt": state.get("updatedAt", ""),
        })

    if json_output:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif not projects:
        print("结论：PASS（无项目）")
        print("工作区：", WORKSPACE)
        print("问题：暂无 webnovel-director 项目")
        print("建议：运行 `project_manager.py new <dir> --title \"书名\"` 创建新项目")
    else:
        print(f"结论：PASS（共 {len(projects)} 个项目）")
        print(f"工作区：{WORKSPACE}")
        for r in results:
            marker = " *" if r["active"] else "  "
            cw = "Y" if r["canWrite"] else "N"
            ch = r["currentChapter"]
            print(f"{marker} {r['name']:30s} Ch{ch:04d}  canWrite={cw}  {r['title']}")
        if not active and results:
            print("建议：未设置活跃项目，运行 `project_manager.py switch <name>`")

    return 1 if not projects else 0


def cmd_doctor(name: str, json_output: bool = False) -> int:
    """Run director_doctor.py on the named project."""
    proj = find_project_by_name(name)
    if not proj:
        if json_output:
            print(json.dumps({"status": "FAIL", "error": f"未找到项目: {name}"},
                             ensure_ascii=False, indent=2))
        else:
            print(f"结论：FAIL")
            print(f"问题：未找到项目 '{name}'")
            print(f"可用项目：{[p.name for p in find_projects()]}")
        return 1

    args = ["--json"] if json_output else []
    cp = run_script("director_doctor.py", str(proj), *args)
    sys.stdout.write(cp.stdout)
    if cp.stderr:
        sys.stderr.write(cp.stderr)
    return cp.returncode


def cmd_switch(name: str) -> int:
    """Set the named project as active."""
    proj = find_project_by_name(name)
    if not proj:
        print(f"结论：FAIL")
        print(f"问题：未找到项目 '{name}'")
        available = [p.name for p in find_projects()]
        if available:
            print(f"可用项目：{available}")
        return 1

    ACTIVE_FILE.write_text(proj.name, encoding="utf-8")
    print(f"结论：PASS")
    print(f"活跃项目已切换为：{proj.name}")
    print(f"路径：{proj}")
    return 0


def cmd_new(directory: str, title: str, force: bool = False) -> int:
    """Quick-initialize a new book via init_project.py."""
    book_dir = WORKSPACE / directory
    if book_dir.exists() and list(book_dir.iterdir()) and not force:
        print(f"结论：FAIL")
        print(f"问题：目录 '{book_dir}' 已存在且非空")
        print(f"建议：使用 --force 强制覆盖，或指定不同的目录名")
        return 1

    script_args = [str(book_dir), "--title", title]
    if force:
        script_args.append("--force")

    cp = run_script("init_project.py", *script_args)
    sys.stdout.write(cp.stdout)
    if cp.stderr:
        sys.stderr.write(cp.stderr)

    if cp.returncode == 0:
        # Auto-switch to the new project
        ACTIVE_FILE.write_text(directory, encoding="utf-8")
        print(f"活跃项目已自动切换为：{directory}")

    return cp.returncode


# ----------------------------------------------------------------
# main
# ----------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="webnovel-director 多书项目管理器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python project_manager.py list
  python project_manager.py doctor 我的书
  python project_manager.py switch 我的书
  python project_manager.py new 新书 --title "末日之塔"
  python project_manager.py new 新书 --title "末日之塔" --force
""")

    sub = ap.add_subparsers(dest="command", help="子命令")

    # list
    p_list = sub.add_parser("list", help="列出所有项目")
    p_list.add_argument("--json", action="store_true", help="JSON 输出")

    # doctor
    p_doctor = sub.add_parser("doctor", help="对项目运行健康检查")
    p_doctor.add_argument("name", help="项目名（目录名）")
    p_doctor.add_argument("--json", action="store_true", help="JSON 输出")

    # switch
    p_switch = sub.add_parser("switch", help="切换活跃项目")
    p_switch.add_argument("name", help="项目名（目录名）")

    # new
    p_new = sub.add_parser("new", help="快速初始化新书")
    p_new.add_argument("dir", help="项目目录名（将在 workspace 下创建）")
    p_new.add_argument("--title", required=True, help="书名")
    p_new.add_argument("--force", action="store_true", help="强制覆盖已有目录")

    args = ap.parse_args()

    if args.command == "list":
        return cmd_list(args.json)
    elif args.command == "doctor":
        return cmd_doctor(args.name, args.json)
    elif args.command == "switch":
        return cmd_switch(args.name)
    elif args.command == "new":
        return cmd_new(args.dir, args.title, args.force)
    else:
        ap.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
