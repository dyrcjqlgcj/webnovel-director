#!/usr/bin/env python3
"""webnovel-director Dashboard Server.

Usage:
  python dashboard_server.py <book_dir> [--port 8765] [--no-open]

Single-file HTTP server. Reads project state and renders an interactive
dashboard with chapter status, progress tracking, and one-click actions.
HTML/CSS/JS are served from dashboard/templates/ and dashboard/static/.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import (  # noqa: E402
    SKILL_ROOT,
    count_body_chars,
    parse_chapter_queue,
    parse_json5,
    parse_volume_map,
    read_text,
    strip_markdown,
    write_text,
)

SCRIPTS_DIR = SKILL_ROOT / "scripts"
TEMPLATE_DIR = SKILL_ROOT / "dashboard" / "templates"
STATIC_DIR = SKILL_ROOT / "dashboard" / "static"

# Cache for static file contents
_static_cache: dict[str, bytes] = {}


def _load_html() -> str:
    return read_text(TEMPLATE_DIR / "index.html")


def _load_static(filename: str) -> bytes:
    if filename not in _static_cache:
        fpath = STATIC_DIR / filename
        if fpath.exists():
            _static_cache[filename] = fpath.read_bytes()
        else:
            _static_cache[filename] = b""
    return _static_cache[filename]


def count_chapter_words_detail(book_dir: Path) -> dict[int, int]:
    counts = {}
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                m = re.match(r"第0*(\d+)章", f.name)
                if m:
                    counts[int(m.group(1))] = len(strip_markdown(read_text(f)))
    return counts


def get_project_state(book_dir: Path) -> dict:
    """Build complete project state for the dashboard."""
    state_file = book_dir / "director" / "director_state.json5"
    state = {}
    if state_file.exists():
        state = parse_json5(read_text(state_file))

    queue = parse_chapter_queue(book_dir / "director" / "chapter_queue.md")

    chapter_files = []
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                chapter_files.append(f)

    total_chars = count_body_chars(book_dir)
    chapter_words = count_chapter_words_detail(book_dir)

    # Chapter mtimes
    chapter_mtime = {}
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                m = re.match(r"第0*(\d+)章", f.name)
                if m:
                    ch_num = int(m.group(1))
                    chapter_mtime[ch_num] = datetime.datetime.fromtimestamp(
                        f.stat().st_mtime).strftime("%m-%d %H:%M")

    # Review history
    review_history = {}
    rh_path = book_dir / "director" / ".review_history.json"
    if rh_path.exists():
        try:
            review_history = json.loads(read_text(rh_path))
        except json.JSONDecodeError:
            pass

    for ch in queue:
        ch["words"] = chapter_words.get(ch["chapter"], 0)
        ch["mtime"] = chapter_mtime.get(ch["chapter"], "")
        rh = review_history.get(str(ch["chapter"]), {})
        ch["reviewed_at"] = rh.get("time", "")
        ch["review_verdict"] = rh.get("verdict", "")
        ch["review_issues"] = rh.get("issues", [])

    # Audit status
    last_audit = {}
    audit_path = book_dir / "director" / "last_audit.md"
    if audit_path.exists():
        audit_text = read_text(audit_path)
        last_audit["status"] = "PASS" if "PASS" in audit_text else (
            "WARN" if "WARN" in audit_text else ("FAIL" if "FAIL" in audit_text else "NONE"))
        last_audit["summary"] = audit_text[:300]

    # Hooks
    hooks = []
    hooks_path = book_dir / "truth" / "pending_hooks.md"
    if hooks_path.exists():
        hook_text = read_text(hooks_path)
        for line in hook_text.splitlines():
            s = line.strip()
            if s.startswith("| H") or s.startswith("|H"):
                cells = [c.strip() for c in s.strip("|").split("|")]
                if len(cells) >= 3:
                    hooks.append(f"{cells[0]}: {cells[1]} [{cells[3] if len(cells)>3 else '?'}]")
            elif s.startswith("-"):
                hooks.append(s.strip("- ").strip())

    # Premise summary
    premise_text = read_text(book_dir / "director" / "premise.md")
    premise_summary = ""
    m = re.search(r"书名承诺[：:]\s*(.+)", premise_text)
    if m:
        premise_summary = m.group(1).strip()

    # Volumes
    volumes = []
    for vm_path_cand in [book_dir / "director" / "volume_map.md",
                          book_dir / "story" / "outline" / "volume_map.md"]:
        if vm_path_cand.exists():
            volumes = parse_volume_map(vm_path_cand)
            break

    return {
        "title": state.get("title", book_dir.name),
        "book_id": state.get("bookId", ""),
        "status": state.get("status", "unknown"),
        "active_volume": state.get("activeVolume", 1),
        "current_chapter": state.get("currentChapter", 0),
        "can_write": state.get("canWrite", False),
        "blockers": state.get("blockers", []),
        "total_chars": total_chars,
        "total_chapters_written": len(chapter_files),
        "total_chapters_planned": len(queue),
        "premise_summary": premise_summary,
        "last_audit": last_audit,
        "chapters": queue,
        "chapter_files": [f.name for f in chapter_files],
        "volumes": volumes,
        "hooks": hooks[:20],
        "hooks_total": len(hooks),
        "updated_at": state.get("updatedAt", ""),
    }


def run_action(book_dir: Path, action: str) -> dict:
    """Execute a director script action."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    book = str(book_dir)
    scripts = SCRIPTS_DIR

    actions = {
        "doctor": [sys.executable, str(scripts / "director_doctor.py"), book],
        "review": [sys.executable, str(scripts / "outline_gate_review.py"), book],
        "causal": [sys.executable, str(scripts / "outline_causal_check.py"), book],
        "iterate": [sys.executable, str(scripts / "outline_iterate.py"), book,
                    "--no-llm", "--max-rounds", "2"],
    }

    if action.startswith("review_ch_"):
        ch = action.replace("review_ch_", "")
        ch_file = None
        for ch_dir_name in ("正文", "chapters"):
            ch_dir = book_dir / ch_dir_name
            if ch_dir.exists():
                for pat in [f"第*{ch.zfill(3)}*章*.md", f"第*{ch}*章*.md", f"第0*{ch}章*.md"]:
                    candidates = sorted(ch_dir.glob(pat))
                    if candidates:
                        ch_file = str(candidates[0])
                        break
        cmd = [sys.executable, str(scripts / "review_chapter.py"), book, "--chapter", ch]
        if ch_file:
            cmd.extend(["--text", ch_file])
        actions["review_chapter"] = cmd
        action = "review_chapter"

    if action not in actions:
        return {"error": f"Unknown action: {action}"}

    try:
        result = subprocess.run(actions[action], capture_output=True, timeout=60, env=env)
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        return {
            "success": result.returncode in (0, 1),
            "returncode": result.returncode,
            "output": (stdout + stderr)[:2000],
        }
    except subprocess.TimeoutExpired:
        return {"error": "Action timed out (60s)"}
    except Exception as e:
        return {"error": str(e)}


def save_chapter_queue_row(book_dir: Path, data: dict) -> dict:
    """Update a single chapter's row in chapter_queue.md."""
    cq_path = book_dir / "director" / "chapter_queue.md"
    if not cq_path.exists():
        return {"success": False, "error": "chapter_queue.md 不存在"}

    ch_num = data.get("chapter")
    goal = data.get("goal", "")
    premise_hit = data.get("premise_hit", "")
    forbidden = data.get("forbidden", "")

    content = read_text(cq_path)
    lines = content.split("\n")
    new_lines = []
    found = False

    for line in lines:
        s = line.strip()
        if not s.startswith("|") or "---" in s or "Chapter" in s:
            new_lines.append(line)
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 6:
            new_lines.append(line)
            continue
        n = re.sub(r"\D", "", cells[0])
        if not n.isdigit() or int(n) != ch_num:
            new_lines.append(line)
            continue
        cells[2] = goal
        cells[3] = premise_hit
        cells[4] = forbidden
        new_lines.append("| " + " | ".join(cells) + " |")
        found = True

    if not found:
        return {"success": False, "error": f"未找到第{ch_num}章"}

    write_text(cq_path, "\n".join(new_lines))
    return {"success": True, "chapter": ch_num}


MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


class DashboardHandler(BaseHTTPRequestHandler):
    book_dir: Path = None
    html_template: str = ""

    def log_message(self, format, *args):
        pass

    def _serve(self, code: int, content_type: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _serve_json(self, data):
        self._serve(200, "application/json; charset=utf-8",
                    json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve(200, "text/html; charset=utf-8",
                        self.html_template.encode("utf-8"))

        elif path.startswith("/static/"):
            filename = path.replace("/static/", "", 1)
            content = _load_static(filename)
            ext = os.path.splitext(filename)[1]
            mime = MIME_TYPES.get(ext, "application/octet-stream")
            self._serve(200, mime, content)

        elif path == "/api/state":
            self._serve_json(get_project_state(self.book_dir))

        elif path.startswith("/api/action/"):
            action = path.split("/")[-1]
            self._serve_json(run_action(self.book_dir, action))

        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/save_chapter":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                result = save_chapter_queue_row(self.book_dir, data)
                self._serve_json(result)
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})
        else:
            self.send_error(404)


def main() -> int:
    ap = argparse.ArgumentParser(description="webnovel-director Dashboard")
    ap.add_argument("book_dir", nargs="?", help="小说项目路径")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    if not args.book_dir:
        cwd = Path.cwd()
        if (cwd / "director" / "director_state.json5").exists():
            args.book_dir = str(cwd)
        else:
            print("用法: python dashboard_server.py <book_dir> [--port 8765]")
            print("或在含有 director/director_state.json5 的项目目录下运行")
            return 1

    book_dir = Path(args.book_dir).resolve()
    if not (book_dir / "director" / "director_state.json5").exists():
        print(f"错误: {book_dir} 中未找到 director/director_state.json5")
        print("请先运行 init_project.py 初始化项目")
        return 1

    DashboardHandler.book_dir = book_dir
    DashboardHandler.html_template = _load_html()

    server = HTTPServer(("127.0.0.1", args.port), DashboardHandler)

    url = f"http://127.0.0.1:{args.port}"
    print(f"  webnovel-director Dashboard")
    print(f"  项目: {get_project_state(book_dir)['title']}")
    print(f"  地址: {url}")
    print(f"  按 Ctrl+C 停止")

    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
