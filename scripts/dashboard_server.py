#!/usr/bin/env python3
"""webnovel-director Dashboard Server.

Usage:
  python dashboard_server.py <book_dir> [--port 8765] [--no-open]

Single-file HTTP server. Reads the project state and renders an interactive
dashboard with chapter status, progress tracking, and one-click actions.
"""

from __future__ import annotations
import argparse, datetime, json, os, re, subprocess, sys, time, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ── ANSI color codes ──
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
MAGENTA = '\033[95m'
BOLD = '\033[1m'
DIM = '\033[2m'
RESET = '\033[0m'

SCRIPTS_DIR = Path(__file__).resolve().parent


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="ignore") if p.exists() else ""


def parse_json5(text: str) -> dict:
    """Minimal JSON5 parser for director_state."""
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"([,{]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def parse_chapter_queue(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "Chapter" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) >= 6:
            n = re.sub(r"\D", "", cells[0])
            if n.isdigit():
                rows.append({
                    "chapter": int(n),
                    "title": cells[1],
                    "goal": cells[2],
                    "premise_hit": cells[3],
                    "forbidden": cells[4],
                    "status": cells[5].upper() if cells[5].upper() in ("PASS", "WARN", "FAIL", "WRITTEN", "待写", "QUEUE") else cells[5],
                })
    return rows


def strip_markdown(text: str) -> str:
    """Strip markdown formatting, keep only body text."""
    # Remove headers (# ...)
    text = re.sub(r"^#{1,6}\s+.+$", "", text, flags=re.MULTILINE)
    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Remove all whitespace (blank lines, spaces, newlines)
    text = re.sub(r"\s+", "", text)
    return text


def count_words(book_dir: Path) -> int:
    """Count body text characters (no markdown formatting)."""
    total = 0
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                total += len(strip_markdown(read(f)))
    return total


def parse_volumes(book_dir: Path) -> list[dict]:
    """Parse volume structure from volume_map.md."""
    for vm_path in [book_dir / "director" / "volume_map.md",
                    book_dir / "story" / "outline" / "volume_map.md"]:
        if not vm_path.exists():
            continue
        text = read(vm_path)
        vols = []
        # Match volume table rows: | 一 | 1-80 | ... |
        for line in text.splitlines():
            s = line.strip()
            if not s.startswith("|") or "---" in s:
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) < 3:
                continue
            # Skip header rows and non-volume rows
            if cells[0] in ("卷", "章节", "Chapter", "") or not cells[0]:
                continue
            # Only match rows where first cell is a Chinese number or digit followed by "卷"
            if not re.match(r"^[一二三四五六七八九十\d]+$", cells[0]):
                continue
            vol_label = cells[0]
            ch_range = cells[1] if len(cells) > 1 else ""
            # Parse chapter range like "1-75"
            rm = re.search(r"(\d+)\s*[-–—]\s*(\d+)", ch_range)
            if rm:
                start, end = int(rm.group(1)), int(rm.group(2))
                vols.append({
                    "label": vol_label.strip(),
                    "start": start, "end": end,
                    "chapters": end - start + 1,
                    "theme": cells[4].strip() if len(cells) > 4 else "",
                })
        return vols
    return []


def get_project_state(book_dir: Path) -> dict:
    """Build complete project state for the dashboard."""
    state_file = (book_dir / "director" / "director_state.json5")
    state = parse_json5(read(state_file))

    queue = parse_chapter_queue(read(book_dir / "director" / "chapter_queue.md"))

    # Chapter files
    chapter_files = []
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                chapter_files.append(f)

    total_chars = count_words(book_dir)

    # Per-chapter word counts + review timestamps
    chapter_words = {}
    chapter_mtime = {}
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                m = re.match(r"第0*(\d+)章", f.name)
                if m:
                    ch_num = int(m.group(1))
                    chapter_words[ch_num] = len(strip_markdown(read(f)))
                    chapter_mtime[ch_num] = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%m-%d %H:%M")

    # Load review history (from both dashboard and main session reviews)
    review_history = {}
    rh_path = book_dir / "director" / ".review_history.json"
    if rh_path.exists():
        try:
            review_history = json.loads(read(rh_path))
        except json.JSONDecodeError:
            pass

    for ch in queue:
        ch["words"] = chapter_words.get(ch["chapter"], 0)
        ch["mtime"] = chapter_mtime.get(ch["chapter"], "")
        rh = review_history.get(str(ch["chapter"]), {})
        ch["reviewed_at"] = rh.get("time", "")
        ch["review_verdict"] = rh.get("verdict", "")
        ch["review_issues"] = rh.get("issues", [])

    # Audit status from last_audit.md
    last_audit = {}
    audit_path = book_dir / "director" / "last_audit.md"
    if audit_path.exists():
        audit_text = read(audit_path)
        last_audit["status"] = "PASS" if "PASS" in audit_text else (
            "WARN" if "WARN" in audit_text else (
                "FAIL" if "FAIL" in audit_text else "NONE"))
        # Strip markdown formatting for display
        clean = re.sub(r"^#{1,6}\s+.+$", "", audit_text[:500], flags=re.MULTILINE)
        clean = re.sub(r"```[\s\S]*?```", "", clean)
        clean = re.sub(r"`([^`]+)`", r"\1", clean)
        clean = re.sub(r"^[-*_]{3,}\s*$", "", clean, flags=re.MULTILINE)
        last_audit["summary"] = clean.strip()[:200]

    # Foreshadowing from truth/pending_hooks.md
    hooks = []
    hooks_path = book_dir / "truth" / "pending_hooks.md"
    if hooks_path.exists():
        hook_text = read(hooks_path)
        # Try table format: | H001 | ...
        for line in hook_text.splitlines():
            s = line.strip()
            if s.startswith("| H") or s.startswith("|H"):
                cells = [c.strip() for c in s.strip("|").split("|")]
                if len(cells) >= 3:
                    hooks.append(f"{cells[0]}: {cells[1]} [{cells[3] if len(cells)>3 else '?'}]")
            elif s.startswith("-"):
                hooks.append(s.strip("- ").strip())

    # Premise summary
    premise_text = read(book_dir / "director" / "premise.md")
    premise_summary = ""
    m = re.search(r"书名承诺[：:]\s*(.+)", premise_text)
    if m:
        premise_summary = m.group(1).strip()

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
        "volumes": parse_volumes(book_dir),
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
    }

    if action.startswith("review_ch_"):
        ch = action.replace("review_ch_", "")
        # Find the actual chapter text file
        ch_file = None
        for ch_dir_name in ("正文", "chapters"):
            ch_dir = book_dir / ch_dir_name
            if ch_dir.exists():
                candidates = sorted(ch_dir.glob(f"第*{ch.zfill(3)}*章*.md")) + sorted(ch_dir.glob(f"第*{ch}*章*.md"))
                if not candidates:
                    candidates = sorted(ch_dir.glob(f"第0*{ch}章*.md"))
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
        output = (stdout + stderr)[:2000]

        # review_chapter.py handles its own history write with issues — don't overwrite

        return {
            "success": result.returncode in (0, 1),
            "returncode": result.returncode,
            "output": output,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Action timed out (60s)"}
    except Exception as e:
        return {"error": str(e)}


# ── HTML Template ──

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>网文导演仪表盘</title>
<style>
:root { --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #e6edf3; --muted: #8b949e; --accent: #3b82f6; --pass: #22c55e; --warn: #eab308; --fail: #ef4444; }
[data-theme="light"] { --bg: #f6f8fa; --card: #ffffff; --border: #d0d7de; --text: #1f2328; --muted: #656d76; --accent: #0969da; --pass: #1a7f37; --warn: #9a6700; --fail: #cf222e; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
  background: var(--bg); color: var(--text); min-height: 100vh; line-height: 1.5; }

/* Header */
#header { background: var(--card); border-bottom: 1px solid var(--border);
  padding: 12px 24px; display: flex; align-items: center; gap: 14px;
  position: sticky; top: 0; z-index: 20; }
#header h1 { font-size: 18px; font-weight: 700; }
#header .status-block { padding: 4px 14px; border-radius: 6px; font-size: 12px;
  font-weight: 600; white-space: nowrap; }
#header .spacer { flex: 1; }
#header .head-stat { font-size: 12px; color: var(--muted); }
#header .head-stat b { color: var(--text); }

/* Layout */
#main { max-width: 1400px; margin: 0 auto; padding: 20px 24px;
  display: grid; grid-template-columns: 1fr 300px; gap: 20px; }

/* Cards */
.card { background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px; }
.card h2 { font-size: 13px; color: var(--muted); letter-spacing: 0.5px;
  margin-bottom: 12px; font-weight: 600; }

/* Action bar */
#action-bar { display: flex; gap: 10px; margin-bottom: 16px; align-items: center; }
.btn { padding: 8px 16px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--card); color: var(--text); cursor: pointer; font-size: 13px;
  font-weight: 500; transition: opacity 0.15s; }
.btn:hover { opacity: 0.85; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Table */
#table-wrap { max-height: calc(100vh - 150px); overflow-y: auto; border-radius: 6px; }
#chapter-table { width: 100%; border-collapse: collapse; font-size: 13px; }
#chapter-table th { text-align: left; padding: 8px 12px; color: var(--muted);
  font-weight: 500; border-bottom: 2px solid var(--border); font-size: 11px;
  letter-spacing: 0.5px; position: sticky; top: 0; background: var(--card); z-index: 1; }
#chapter-table td { padding: 7px 12px; border-bottom: 1px solid rgba(255,255,255,0.04); }
#chapter-table tbody tr { cursor: pointer; transition: background 0.1s; }
#chapter-table tbody tr:hover { background: rgba(255,255,255,0.03); }
#chapter-table .ch-col { font-weight: 600; width: 50px; }
#chapter-table .words-col { text-align: right; font-variant-numeric: tabular-nums;
  font-size: 12px; color: var(--muted); width: 70px; }
#chapter-table .score-col { text-align: center; font-weight: 700; width: 55px; }
#chapter-table .time-col { width: 75px; font-size: 11px; color: var(--muted); white-space: nowrap; }
#chapter-table .status-col { width: 65px; }
#chapter-table .review-col { width: 44px; text-align: center; }

/* Filter row */
.filter-row { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.filter-row select { background: var(--card); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px; padding: 4px 8px; font-size: 12px; }

/* Sidebar */
#sidebar { display: flex; flex-direction: column; gap: 16px; }
.progress-bg { height: 6px; background: var(--border); border-radius: 3px;
  margin: 8px 0 12px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); border-radius: 3px;
  transition: width 0.5s ease; }
.stat-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }
.stat-row .val { font-weight: 600; }
.audit-entry { font-size: 12px; padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
.audit-entry .time { color: var(--muted); font-size: 11px; }
.blocker-item { padding: 3px 0; font-size: 12px; color: var(--fail); }

/* Output panel */
#output { background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 10px; font-family: 'SF Mono', 'Consolas', 'Courier New', monospace;
  font-size: 12px; height: 500px; overflow-y: auto; white-space: pre-wrap;
  margin-top: 16px; color: var(--muted); }

/* Modal */
#modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.7); z-index: 100; justify-content: center; align-items: center; }
#modal-overlay.show { display: flex; }
#modal-box { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
  padding: 24px; max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto; }
#modal-box h3 { font-size: 16px; margin-bottom: 6px; }
#modal-box .meta { font-size: 12px; color: var(--muted); margin-bottom: 16px; }
#modal-box .field { margin-bottom: 12px; }
#modal-box .field-label { font-size: 11px; color: var(--muted); letter-spacing: 0.5px;
  margin-bottom: 4px; font-weight: 500; }
#modal-box .field-value { font-size: 13px; line-height: 1.5; }
#modal-box .close-btn { float: right; background: none; border: none; color: var(--muted);
  font-size: 22px; cursor: pointer; line-height: 1; }
#modal-box textarea { width: 100%; min-height: 60px; background: var(--bg);
  color: var(--text); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px; font-size: 13px; resize: vertical; font-family: inherit; }

/* Misc */
.spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border);
  border-top-color: var(--accent); border-radius: 50%; animation: spin 0.6s linear infinite;
  vertical-align: middle; margin-right: 6px; }
@keyframes spin { to { transform: rotate(360deg); } }
.refresh-indicator { font-size: 11px; color: var(--muted); white-space: nowrap; }
</style>
</head>
<body>

<header id="header">
  <h1 id="h-title">载入中...</h1>
  <div class="status-block" id="h-status" style="background:rgba(107,114,128,0.15)">--</div>
  <div class="spacer"></div>
  <div class="header-progress">
    <div class="progress-bg" style="height:4px;width:180px"><div class="progress-fill" id="header-progress" style="width:0%"></div></div>
    <span style="font-size:11px;color:var(--muted);margin-left:8px;white-space:nowrap" id="header-progress-text">-</span>
  </div>
  <div class="header-stats">
    <span class="header-stat-item">&#9888; <b id="h-warn">0</b></span>
    <span class="header-stat-item">&#10060; <b id="h-fail">0</b></span>
    <span class="header-stat-item">&#128221; <b id="h-canwrite">-</b></span>
  </div>
  <span class="refresh-indicator" style="margin-left: 10px" id="refresh-hint"></span>
  <button onclick="toggleTheme()" style="margin-left:10px;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 10px;cursor:pointer;font-size:13px" title="切换主题">&#9788;</button>
</header>

<div id="main">
  <div>
    <!-- Action bar -->
    <div id="action-bar">
      <button class="btn primary" onclick="doAction('doctor')">一键体检</button>
      <button class="btn" onclick="doAction('review')">大纲审查</button>
      <button class="btn" onclick="refresh()">刷新</button>
      <span style="flex:1"></span>
      <button class="btn" onclick="exportTable()" style="font-size:12px">导出</button>
    </div>

    <!-- Chapter table -->
    <div class="card" style="padding:12px">
      <div class="filter-row">
        <h2 style="margin:0;flex:1">章节状态</h2>
        <select id="vol-select" onchange="switchVolume()"></select>
        <select id="status-filter" onchange="applyFilter()">
          <option value="">全部</option>
          <option value="written">已写</option>
          <option value="pass">通过</option>
          <option value="warn">警告</option>
          <option value="fail">失败</option>
          <option value="queue">待写</option>
        </select>
      </div>
      <div id="table-wrap">
        <table id="chapter-table">
          <thead><tr>
            <th class="ch-col">#</th>
            <th>标题</th>
            <th class="words-col">字数</th>
            <th class="score-col">评分</th>
            <th class="time-col">修改</th>
            <th class="status-col">审查</th>
            <th class="time-col">时间</th>
            <th class="review-col"></th>
          </tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </div>

  </div>

  <!-- Sidebar -->
  <div id="sidebar">
    <div class="card">
      <h2>审查统计</h2>
      <div class="stat-row"><span>PASS</span><span class="val" style="color:var(--pass)" id="sb-pass">0</span></div>
      <div class="stat-row"><span>WARN</span><span class="val" style="color:var(--warn)" id="sb-warn">0</span></div>
      <div class="stat-row"><span>FAIL</span><span class="val" style="color:var(--fail)" id="sb-fail">0</span></div>
      <div class="stat-row"><span>待审</span><span class="val" id="sb-pending">0</span></div>
    </div>

    <div class="card">
      <h2>最近审计</h2>
      <div id="sb-audit"><span style="color:var(--muted);font-size:12px">--</span></div>
    </div>

    <div id="output">-- 就绪 --</div>
  </div>
</div>

<!-- Chapter Detail Modal -->
<div id="modal-overlay" onclick="if(event.target===this)closeModal()">
  <div id="modal-box">
    <button class="close-btn" onclick="closeModal()">&times;</button>
    <h3 id="modal-title"></h3>
    <div class="meta" id="modal-meta"></div>
    <div class="field">
      <div class="field-label">章节目标 Goal</div>
      <div class="field-value" id="modal-goal"></div>
      <textarea id="modal-goal-edit" style="display:none"></textarea>
    </div>
    <div class="field">
      <div class="field-label">命题兑现 Must Hit</div>
      <div class="field-value" id="modal-premise"></div>
      <textarea id="modal-premise-edit" style="display:none"></textarea>
    </div>
    <div class="field">
      <div class="field-label">禁飞区 Forbidden</div>
      <div class="field-value" id="modal-forbidden"></div>
      <textarea id="modal-forbidden-edit" style="display:none"></textarea>
    </div>
    <div style="margin-top: 16px; display: flex; gap: 8px; align-items: center;">
      <button class="btn" id="modal-edit-btn" onclick="startEdit()">编辑</button>
      <button class="btn primary" id="modal-save-btn" onclick="saveEdit()" style="display:none">保存</button>
      <button class="btn" id="modal-cancel-btn" onclick="cancelEdit()" style="display:none">取消</button>
      <span style="font-size: 11px; color: var(--muted);" id="modal-save-status"></span>
    </div>
  </div>
</div>

<script>
const STATE = {};
let currentVolume = 0;
let countdown = 30;
let editingChapter = 0;

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function toggleTheme() {
  var t = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('theme', t);
}
(function() {
  var t = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', t);
})();

function calcScore(c) {
  // No score for unreviewed chapters
  if (!c.review_verdict) return {grade:'', color:'#6b7280'};
  let s = 0;
  if (c.words > 0) s++;
  if (c.goal && c.goal.length > 3 && c.goal !== '未设定') s++;
  if (c.premise_hit && c.premise_hit.length > 3 && c.premise_hit !== '未设定') s++;
  if (c.review_verdict === 'PASS') s += 2;
  else if (c.review_verdict === 'WARN') s++;
  if (s >= 5) return {grade:'A', color:'#22c55e'};
  if (s >= 4) return {grade:'B', color:'#10b981'};
  if (s >= 3) return {grade:'C', color:'#eab308'};
  if (s >= 2) return {grade:'D', color:'#f97316'};
  return {grade:'', color:'#6b7280'};
}

function renderTable(chapters) {
  return chapters.map(c => {
    const sc = calcScore(c);
    const title = c.title || ('第' + c.chapter + '章');
    const words = (c.words || 0);
    const mtime = c.mtime || '-';
    const rvVerdict = c.review_verdict || '';
    const rvTime = c.reviewed_at || '-';
    const verdictColors = {PASS:'#22c55e',WARN:'#eab308',FAIL:'#ef4444'};
    const vLabel = {PASS:'通过',WARN:'警告',FAIL:'失败'};
    return `<tr onclick="showDetail(${c.chapter})">
      <td class="ch-col">${c.chapter}</td>
      <td>${esc(title)}</td>
      <td class="words-col">${words || '-'}</td>
      <td class="score-col" style="color:${sc.color}">${sc.grade}</td>
      <td style="font-size:11px;color:var(--muted);white-space:nowrap">${mtime}</td>
      <td style="font-size:12px;font-weight:600;color:${verdictColors[rvVerdict]||'var(--muted)'}">${rvVerdict ? (vLabel[rvVerdict]||rvVerdict) : (words > 0 ? '已写' : '-')}</td>
      <td style="font-size:11px;color:var(--muted);white-space:nowrap">${rvTime}</td>
      <td class="review-col"><button onclick="event.stopPropagation();doAction('review_ch_${c.chapter}')" style="padding:3px 8px;font-size:11px;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:4px;cursor:pointer">审</button></td>
    </tr>`;
  }).join('');
}

function render(data) {
  Object.assign(STATE, data);
  const s = STATE;

  // Header
  document.getElementById('h-title').textContent = s.title || '未命名项目';

  const la = s.last_audit || {};
  const ast = la.status || 'NONE';
  const stColors = {PASS: 'rgba(34,197,94,0.18)', WARN: 'rgba(234,179,8,0.18)',
                    FAIL: 'rgba(239,68,68,0.18)', NONE: 'rgba(107,114,128,0.12)'};
  const stText = {PASS: '#22c55e', WARN: '#eab308', FAIL: '#ef4444', NONE: '#8b949e'};
  const stLabels = {PASS: '审计通过', WARN: '审计警告', FAIL: '审计失败', NONE: '未审计'};
  const hSt = document.getElementById('h-status');
  hSt.textContent = stLabels[ast] || ast;
  hSt.style.background = stColors[ast] || stColors.NONE;
  hSt.style.color = stText[ast] || stText.NONE;

  // Volume selector
  const totalBookCh = (s.volumes || []).reduce(function(sum, v) { return sum + v.chapters; }, 0) || s.total_chapters_planned;
  document.getElementById('vol-select').innerHTML = '<option value="0">全部卷</option>' +
    (s.volumes || []).map(function(v) {
      return '<option value="' + v.start + '" ' + (currentVolume === v.start ? 'selected' : '') + '>第' + v.label + '卷 ' + v.start + '-' + v.end + '章 ' + (v.theme || '') + '</option>';
    }).join('');

  // Filter chapters
  var chapters = s.chapters || [];
  if (currentVolume > 0) {
    var vol = (s.volumes || []).find(function(v) { return v.start === currentVolume; });
    if (vol) chapters = chapters.filter(function(c) { return c.chapter >= vol.start && c.chapter <= vol.end; });
  }
  var sf = document.getElementById('status-filter').value;
  if (sf) {
    chapters = chapters.filter(function(c) {
      var ns = (c.status || '').toUpperCase();
      if (sf === 'written') return c.words > 0 && !c.review_verdict;
      if (sf === 'pass') return c.review_verdict === 'PASS';
      if (sf === 'warn') return c.review_verdict === 'WARN';
      if (sf === 'fail') return c.review_verdict === 'FAIL';
      if (sf === 'queue') return !c.words || (c.words === 0 && !c.review_verdict);
      return true;
    });
  }

  // Chapter table
  document.querySelector('#chapter-table tbody').innerHTML = renderTable(chapters.slice(0, 60));

  // Header progress bar
  var planned = totalBookCh, written = s.total_chapters_written;
  if (currentVolume > 0) {
    var cv = (s.volumes || []).find(function(v) { return v.start === currentVolume; });
    if (cv) { planned = cv.chapters; written = chapters.filter(function(c) { return c.words > 0; }).length; }
  }
  var pct = planned > 0 ? Math.round(written / planned * 100) : 0;
  document.getElementById('header-progress').style.width = pct + '%';
  document.getElementById('header-progress-text').textContent = '已写' + written + '章/共' + planned + '章 (' + pct + '%) ' + ((s.total_chars || 0) / 10000).toFixed(1) + '万字';

  // Sidebar: review stats
  var allCh = s.chapters || [];
  document.getElementById('sb-pass').textContent = allCh.filter(function(c) { return c.review_verdict === 'PASS'; }).length;
  document.getElementById('sb-warn').textContent = allCh.filter(function(c) { return c.review_verdict === 'WARN'; }).length;
  document.getElementById('sb-fail').textContent = allCh.filter(function(c) { return c.review_verdict === 'FAIL'; }).length;
  document.getElementById('sb-pending').textContent = allCh.filter(function(c) { return c.words > 0 && !c.review_verdict; }).length;

  // Header stats
  document.getElementById('h-warn').textContent = allCh.filter(function(c) { return c.review_verdict === 'WARN'; }).length;
  document.getElementById('h-fail').textContent = allCh.filter(function(c) { return c.review_verdict === 'FAIL'; }).length;
  var nextCh = s.current_chapter || allCh.filter(function(c){return c.words>0}).length;
  document.getElementById('h-canwrite').textContent = s.can_write ? ('下一章 ' + (nextCh + 1)) : '锁定';

  // Sidebar: recent audits
  var audDiv = document.getElementById('sb-audit');
  var html = '';
  // Show last_audit first
  if (la.status && la.status !== 'NONE') {
    var vc = {PASS: '#22c55e', WARN: '#eab308', FAIL: '#ef4444'};
    html += '<div style="font-size:13px;font-weight:600;color:' + (vc[la.status] || 'var(--muted)') + ';margin-bottom:4px">' + (la.status === 'PASS' ? '审计通过' : la.status === 'WARN' ? '审计警告' : '审计失败') + '</div>';
    if (la.summary) {
      html += '<div style="font-size:11px;color:var(--muted);margin-bottom:8px;line-height:1.4">' + esc(la.summary.substring(0, 120)) + '</div>';
    }
  }
  // Show latest chapter reviews
  var reviewed = allCh.filter(function(c) { return c.reviewed_at; }).sort(function(a, b) {
    return (b.reviewed_at || '').localeCompare(a.reviewed_at || '');
  }).slice(0, 5);
  if (reviewed.length > 0) {
    html += reviewed.map(function(c) {
      var vc = {PASS: '#22c55e', WARN: '#eab308', FAIL: '#ef4444'};
      return '<div style="font-size:11px;padding:1px 0"><span style="color:' + (vc[c.review_verdict] || 'var(--muted)') + '">' + (c.review_verdict || '?') + '</span> Ch' + c.chapter + ' <span style="color:var(--muted)">' + (c.reviewed_at || '') + '</span></div>';
    }).join('');
  }
  audDiv.innerHTML = html || '<span style="color:var(--muted);font-size:12px">暂无</span>';

  // Sidebar: blockers
  var bl = document.getElementById('sb-blockers');
  if (bl) {
  if ((s.blockers || []).length > 0) {
    bl.innerHTML = s.blockers.map(function(b) { return '<div class="blocker-item">' + esc(b) + '</div>'; }).join('');
  } else {
    bl.innerHTML = '<span style="color:var(--pass);font-size:12px">无阻塞项</span>';
  }
  }

  // Refresh indicator
  document.getElementById('refresh-hint').textContent = countdown + 's 刷新';
}

// Actions
async function refresh() {
  try {
    const r = await fetch('/api/state');
    render(await r.json());
  } catch(e) { console.error(e); }
}

async function doAction(action) {
  const out = document.getElementById('output');
  out.textContent = '执行中...';

  try {
    const r = await fetch('/api/action/' + action);
    const d = await r.json();
    out.textContent = d.output || d.error || '完成';

    if (action.startsWith('review_ch_')) {
      const chNum = parseInt(action.replace('review_ch_', ''));
      const m = (d.output || '').match(/结论[：:]\s*(PASS|WARN|FAIL)/);
      if (m) {
        const ch = (STATE.chapters || []).find(c => c.chapter === chNum);
        if (ch) {
          const now = new Date();
          ch.reviewed_at = (now.getMonth()+1).toString().padStart(2,'0') + '-' +
                           now.getDate().toString().padStart(2,'0') + ' ' +
                           now.getHours().toString().padStart(2,'0') + ':' +
                           now.getMinutes().toString().padStart(2,'0') + ':' +
                           now.getSeconds().toString().padStart(2,'0');
          ch.review_verdict = m[1];
          const issues = [];
          for (const line of (d.output || '').split('\n')) {
            const im = line.match(/(?:WARN|FAIL)\s+\[(.+?)\]\s*(?:—|:)?\s*(.+)/);
            if (im) issues.push('[' + im[1] + '] ' + im[2].trim());
          }
          ch.review_issues = issues;
          // Persist to server
          fetch('/api/save_review', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              chapter: chNum,
              verdict: m[1],
              time: ch.reviewed_at,
              issues: issues
            })
          }).catch(function(){});
        }
        render(STATE);
      }
    } else if (d.success) {
      setTimeout(refresh, 2000);
    }
  } catch(e) {
    out.textContent = '错误: ' + e.message;
  }
}

function switchVolume() {
  currentVolume = parseInt(document.getElementById('vol-select').value) || 0;
  applyFilter();
}

function applyFilter() { render(STATE); }

// Modal
function showDetail(chNum) {
  const ch = (STATE.chapters || []).find(c => c.chapter === chNum);
  if (!ch) return;
  editingChapter = chNum;
  document.getElementById('modal-title').textContent = '第' + ch.chapter + '章 ' + (ch.title || '');
  document.getElementById('modal-meta').textContent =
    '字数: ' + ((ch.words || 0) / 1000).toFixed(1) + 'k' +
    ' | 审查: ' + (ch.review_verdict || '未审') +
    (ch.reviewed_at ? ' | ' + ch.reviewed_at : '');
  renderReadOnly(ch);
  document.getElementById('modal-overlay').classList.add('show');
}

function closeModal() { document.getElementById('modal-overlay').classList.remove('show'); }

function renderReadOnly(ch) {
  document.getElementById('modal-goal').style.display = 'block';
  document.getElementById('modal-goal-edit').style.display = 'none';
  document.getElementById('modal-premise').style.display = 'block';
  document.getElementById('modal-premise-edit').style.display = 'none';
  document.getElementById('modal-forbidden').style.display = 'block';
  document.getElementById('modal-forbidden-edit').style.display = 'none';
  document.getElementById('modal-goal').textContent = ch.goal || '未设定';
  document.getElementById('modal-premise').textContent = ch.premise_hit || '未设定';
  document.getElementById('modal-forbidden').textContent = ch.forbidden || '无';
  document.getElementById('modal-edit-btn').style.display = 'inline-block';
  document.getElementById('modal-save-btn').style.display = 'none';
  document.getElementById('modal-cancel-btn').style.display = 'none';
  document.getElementById('modal-save-status').textContent = '';
}

function startEdit() {
  const ch = (STATE.chapters || []).find(c => c.chapter === editingChapter);
  if (!ch) return;
  document.getElementById('modal-goal').style.display = 'none';
  document.getElementById('modal-goal-edit').style.display = 'block';
  document.getElementById('modal-goal-edit').value = ch.goal || '';
  document.getElementById('modal-premise').style.display = 'none';
  document.getElementById('modal-premise-edit').style.display = 'block';
  document.getElementById('modal-premise-edit').value = ch.premise_hit || '';
  document.getElementById('modal-forbidden').style.display = 'none';
  document.getElementById('modal-forbidden-edit').style.display = 'block';
  document.getElementById('modal-forbidden-edit').value = ch.forbidden || '';
  document.getElementById('modal-edit-btn').style.display = 'none';
  document.getElementById('modal-save-btn').style.display = 'inline-block';
  document.getElementById('modal-cancel-btn').style.display = 'inline-block';
}

function cancelEdit() {
  const ch = (STATE.chapters || []).find(c => c.chapter === editingChapter);
  if (ch) renderReadOnly(ch);
}

async function saveEdit() {
  const goal = document.getElementById('modal-goal-edit').value;
  const premise = document.getElementById('modal-premise-edit').value;
  const forbidden = document.getElementById('modal-forbidden-edit').value;
  const st = document.getElementById('modal-save-status');
  st.textContent = '保存中...';
  try {
    const r = await fetch('/api/save_chapter', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({chapter: editingChapter, goal, premise_hit: premise, forbidden})
    });
    const d = await r.json();
    if (d.success) {
      const ch = (STATE.chapters || []).find(c => c.chapter === editingChapter);
      if (ch) { ch.goal = goal; ch.premise_hit = premise; ch.forbidden = forbidden; }
      renderReadOnly(ch || {});
      refresh();
      st.textContent = '已保存';
      setTimeout(function() { st.textContent = ''; }, 2000);
    } else {
      st.textContent = '失败: ' + (d.error || '');
    }
  } catch(e) {
    st.textContent = '错误: ' + e.message;
  }
}

function exportTable() {
  var chapters = (STATE.chapters || []).filter(function(c) {
    if (currentVolume > 0) {
      var vol = (STATE.volumes || []).find(function(v) { return v.start === currentVolume; });
      if (vol && (c.chapter < vol.start || c.chapter > vol.end)) return false;
    }
    return true;
  });
  var rows = [['章','标题','字数','Goal','Premise Hit','状态']];
  for (var i = 0; i < chapters.length && i < 80; i++) {
    var c = chapters[i];
    rows.push([c.chapter, c.title||'', ((c.words||0)/1000).toFixed(1)+'k',
               (c.goal||'').substring(0,50), (c.premise_hit||'').substring(0,50),
               c.status||'QUEUE']);
  }
  var text = rows.map(function(r) { return r.join('\t'); }).join('\n');
  navigator.clipboard.writeText(text).catch(function() {});
}

// Countdown tick
setInterval(function() {
  countdown--;
  if (countdown <= 0) countdown = 30;
  var el = document.getElementById('refresh-hint');
  if (el) el.textContent = countdown + 's 刷新';
}, 1000);

// Init on DOMContentLoaded (not direct call)
async function init() {
  try {
    const r = await fetch('/api/state');
    const data = await r.json();
    countdown = 30;
    render(data);
    setInterval(async function() {
      try {
        countdown = 30;
        const r2 = await fetch('/api/state');
        render(await r2.json());
      } catch(e) { console.error(e); }
    }, 30000);
  } catch(e) { console.error(e); }
}
document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>"""


def save_review_history(book_dir: Path, data: dict) -> dict:
    """Save chapter review result to .review_history.json"""
    rh_path = book_dir / "director" / ".review_history.json"
    rh = {}
    if rh_path.exists():
        try:
            rh = json.loads(read(rh_path))
        except json.JSONDecodeError:
            pass
    ch = str(data.get("chapter", ""))
    rh[ch] = {
        "time": data.get("time", ""),
        "verdict": data.get("verdict", ""),
        "issues": data.get("issues", []),
    }
    rh_path.write_text(json.dumps(rh, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True}


def save_chapter_queue(book_dir: Path, data: dict) -> dict:
    """Update a single chapter's row in chapter_queue.md."""
    cq_path = book_dir / "director" / "chapter_queue.md"
    if not cq_path.exists():
        return {"success": False, "error": "chapter_queue.md 不存在"}

    ch_num = data.get("chapter")
    goal = data.get("goal", "")
    premise_hit = data.get("premise_hit", "")
    forbidden = data.get("forbidden", "")

    content = read(cq_path)
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
        # Update this row
        cells[2] = goal
        cells[3] = premise_hit
        cells[4] = forbidden
        new_lines.append("| " + " | ".join(cells) + " |")
        found = True

    if not found:
        return {"success": False, "error": f"未找到第{ch_num}章"}

    cq_path.write_text("\n".join(new_lines), encoding="utf-8")
    return {"success": True, "chapter": ch_num}

class DashboardHandler(BaseHTTPRequestHandler):
    book_dir: Path = None  # Set by the server

    def log_message(self, format, *args):
        pass  # Quiet

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_html()
        elif path == "/api/state":
            self._serve_json(get_project_state(self.book_dir))
        elif path.startswith("/api/action/"):
            action = path.split("/")[-1]
            self._serve_json(run_action(self.book_dir, action))
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/save_review":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                result = save_review_history(self.book_dir, data)
                self._serve_json(result)
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})
        elif path == "/api/save_chapter":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                result = save_chapter_queue(self.book_dir, data)
                self._serve_json(result)
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})
        else:
            self.send_error(404)

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

    def _serve_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def parse_audit_log(audit_log_path: Path) -> list[dict]:
    """Parse audit_log.md table rows into a list of dicts."""
    if not audit_log_path.exists():
        return []
    text = read(audit_log_path)
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "Time" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) >= 5:
            rows.append({
                "time": cells[0],
                "module": cells[1],
                "object": cells[2],
                "result": cells[3].upper(),
                "summary": cells[4],
                "next": cells[5] if len(cells) > 5 else "",
            })
    return rows


def run_cli_mode(args) -> int:
    """Render a colored terminal dashboard panel."""
    # Ensure UTF-8 output on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    book_dir = Path(args.book_dir).resolve() if args.book_dir else None

    # Try auto-detect
    if not book_dir:
        cwd = Path.cwd()
        if (cwd / "director" / "director_state.json5").exists():
            book_dir = cwd
        else:
            print(f"{RED}用法: python dashboard_server.py <book_dir> --mode cli{RESET}")
            return 1

    if not (book_dir / "director" / "director_state.json5").exists():
        print(f"{RED}错误: {book_dir} 中未找到 director/director_state.json5{RESET}")
        return 1

    refresh_interval = args.refresh or 0

    while True:
        # Clear screen
        os.system("cls" if os.name == "nt" else "clear")

        state = get_project_state(book_dir)
        audit_log_path = book_dir / "director" / "audit_log.md"
        audit_entries = parse_audit_log(audit_log_path)

        # Audit status block
        audit_status = (state.get("last_audit") or {}).get("status", "NONE")
        status_color = {"PASS": GREEN, "WARN": YELLOW, "FAIL": RED}.get(audit_status, RESET)
        status_icon = {"PASS": f"{GREEN}[OK]{RESET}", "WARN": f"{YELLOW}[!!]{RESET}",
                       "FAIL": f"{RED}[XX]{RESET}", "NONE": f"{DIM}[--]{RESET}"}.get(audit_status, "[--]")
        status_block = {"PASS": "████", "WARN": "▓▓▓▓", "FAIL": "░░░░", "NONE": "····"}.get(audit_status, "····")

        # ═══ Top: Project header ═══
        title = state.get("title", book_dir.name)
        print(f"{BOLD}{CYAN}╔{'═' * 58}╗{RESET}")
        print(f"{BOLD}{CYAN}║{RESET} {BOLD}项目:{RESET} 《{title}》")
        print(f"{BOLD}{CYAN}║{RESET} {BOLD}状态:{RESET} {status_icon} {status_color}{audit_status} {status_color}{status_block}{RESET}")
        if state.get("premise_summary"):
            prem_line = state["premise_summary"][:48]
            print(f"{BOLD}{CYAN}║{RESET} {BOLD}命题:{RESET} {DIM}{prem_line}{RESET}")
        blockers = state.get("blockers", [])
        if blockers:
            print(f"{BOLD}{CYAN}║{RESET} {BOLD}阻塞:{RESET} {RED}{len(blockers)} 项{RESET}  {', '.join(blockers[:2])}")
        print(f"{BOLD}{CYAN}╚{'═' * 58}╝{RESET}")

        # ═══ Middle: Chapter progress ═══
        print(f"\n{CYAN}📊 章节进度{RESET}")
        total = state.get("total_chapters_planned", 0)
        written = state.get("total_chapters_written", 0)
        ratio = written / max(total, 1)
        bar_width = 40
        filled = int(bar_width * ratio)
        bar = "█" * filled + "░" * (bar_width - filled)
        pct_bar = f"{bar} {written}/{total} ({ratio * 100:.1f}%)"
        print(f"  {pct_bar}")

        # Word count + review stats
        total_chars = state.get("total_chars", 0)
        chapters_list = state.get("chapters", [])
        pass_n = sum(1 for c in chapters_list if c.get("review_verdict") == "PASS")
        warn_n = sum(1 for c in chapters_list if c.get("review_verdict") == "WARN")
        fail_n = sum(1 for c in chapters_list if c.get("review_verdict") == "FAIL")
        total_reviewed = pass_n + warn_n + fail_n
        print(f"  总字数: {total_chars / 10000:.1f}万字 | 已审查: {total_reviewed}章 "
              f"({GREEN}{pass_n}P{RESET} {YELLOW}{warn_n}W{RESET} {RED}{fail_n}F{RESET})")

        # Chapter status breakdown (quick grid)
        if chapters_list:
            cols = 10
            ch_status_grid = []
            for ch in chapters_list:
                ch_status_grid.append(ch)
            # Print a compact status line
            status_chars = []
            for ch in chapters_list[:80]:
                s = (ch.get("status") or "").upper()
                if s in ("PASS", "WRITTEN"):
                    status_chars.append(f"{GREEN}●{RESET}")
                elif s == "WARN":
                    status_chars.append(f"{YELLOW}●{RESET}")
                elif s == "FAIL":
                    status_chars.append(f"{RED}●{RESET}")
                else:
                    status_chars.append(f"{DIM}○{RESET}")
            # Layout in rows of 20
            row_width = 20
            for row_start in range(0, min(len(status_chars), 80), row_width):
                row_chars = status_chars[row_start:row_start + row_width]
                ch_start = row_start + 1
                ch_end = min(row_start + row_width, len(status_chars))
                print(f"  ch{ch_start:02d}-{ch_end:02d}: {''.join(row_chars)}")

        # ═══ Bottom: Last 5 audit records ═══
        print(f"\n{CYAN}📋 最近审计记录 (共 {len(audit_entries)} 条){RESET}")
        if audit_entries:
            recent = audit_entries[-5:]
            # Header
            print(f"  {DIM}{'时间':<20} {'模块':<16} {'对象':<14} {'结果':<6} {'摘要'}{RESET}")
            for entry in recent:
                result_color = {"PASS": GREEN, "WARN": YELLOW, "FAIL": RED}.get(entry["result"], RESET)
                time_str = entry["time"][:19]
                module_str = entry["module"][:15]
                obj_str = entry["object"][:13]
                summary_str = entry["summary"][:40]
                print(f"  {DIM}{time_str:<20}{RESET} {module_str:<16} {obj_str:<14} "
                      f"{result_color}{entry['result']:<6}{RESET} {summary_str}")
        else:
            print(f"  {DIM}(暂无审计记录){RESET}")

        # ═══ Footer ═══
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if refresh_interval > 0:
            print(f"\n{DIM}  刷新间隔: {refresh_interval}s | 更新时间: {now_str} | Ctrl+C 退出{RESET}")
            try:
                time.sleep(refresh_interval)
            except KeyboardInterrupt:
                print(f"\n{RESET}  已停止")
                return 0
        else:
            print(f"\n{DIM}  更新时间: {now_str}{RESET}")
            return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="webnovel-director Dashboard")
    ap.add_argument("book_dir", nargs="?", help="小说项目路径")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--mode", choices=["server", "cli"], default="server",
                    help="运行模式: server (Web仪表盘) 或 cli (终端面板)")
    ap.add_argument("--refresh", "-r", type=int, default=0, metavar="N",
                    help="CLI模式自动刷新间隔(秒), 0=单次输出")
    args = ap.parse_args()

    if args.mode == "cli":
        return run_cli_mode(args)

    # ── Server mode ──
    if not args.book_dir:
        # Try to find a project in current dir
        cwd = Path.cwd()
        if (cwd / "director" / "director_state.json5").exists():
            args.book_dir = str(cwd)
        else:
            print("用法: python dashboard_server.py <book_dir> [--port 8765]")
            print("  或: python dashboard_server.py <book_dir> --mode cli [--refresh N]")
            print("或在含有 director/director_state.json5 的项目目录下运行")
            return 1

    book_dir = Path(args.book_dir).resolve()
    if not (book_dir / "director" / "director_state.json5").exists():
        print(f"错误: {book_dir} 中未找到 director/director_state.json5")
        print("请先运行 init_project.py 初始化项目")
        return 1

    DashboardHandler.book_dir = book_dir
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
