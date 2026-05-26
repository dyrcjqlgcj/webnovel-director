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
        last_audit["summary"] = audit_text[:300]

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
        "causal": [sys.executable, str(scripts / "outline_causal_check.py"), book],
        "iterate": [sys.executable, str(scripts / "outline_iterate.py"), book,
                    "--no-llm", "--max-rounds", "2"],
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
:root, [data-theme="dark"] {
  --bg: #0f1117; --card: #1a1d27; --border: #2a2d3a;
  --text: #e1e4ed; --muted: #6b7084; --accent: #6366f1;
  --pass: #22c55e; --warn: #eab308; --fail: #ef4444;
  --written: #3b82f6; --queue: #6b7280;
}
[data-theme="light"] {
  --bg: #f5f5f7; --card: #ffffff; --border: #e5e7eb;
  --text: #1f2937; --muted: #9ca3af; --accent: #4f46e5;
  --pass: #16a34a; --warn: #ca8a04; --fail: #dc2626;
  --written: #2563eb; --queue: #9ca3af;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text); min-height: 100vh; }
header { background: var(--card); border-bottom: 1px solid var(--border);
  padding: 16px 24px; display: flex; justify-content: space-between; align-items: center;
  position: sticky; top: 0; z-index: 10; }
header h1 { font-size: 20px; font-weight: 600; }
header .stats { display: flex; gap: 20px; font-size: 13px; color: var(--muted); }
header .stats strong { color: var(--text); }
main { max-width: 1600px; margin: 0 auto; padding: 24px 48px; display: grid;
  grid-template-columns: 1fr 320px; gap: 20px; }
.card { background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 20px; }
.card h2 { font-size: 14px; color: var(--muted); text-transform: uppercase;
  letter-spacing: 1px; margin-bottom: 12px; }
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.summary-item { text-align: center; padding: 12px; background: rgba(255,255,255,0.03);
  border-radius: 8px; }
.summary-item .value { font-size: 28px; font-weight: 700; }
.summary-item .label { font-size: 11px; color: var(--muted); margin-top: 4px; }
.pass-color { color: var(--pass); } .warn-color { color: var(--warn); }
.fail-color { color: var(--fail); } .written-color { color: var(--written); }

.progress-bar { height: 6px; background: var(--border); border-radius: 3px;
  margin: 16px 0; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); border-radius: 3px;
  transition: width 0.5s ease; }

table { width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }
th { text-align: left; padding: 8px 10px; color: var(--muted); font-weight: 500;
  border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; }
td { padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); }
td.ch { font-weight: 600; width: 50px; }
td.status { width: 80px; }
td.goal { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
td.goal:hover { white-space: normal; overflow: visible; background: var(--bg); position: relative; z-index: 1; }

.status-badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 600; }
.status-badge.PASS, .status-badge.WRITTEN { background: rgba(34,197,94,0.15); color: var(--pass); }
.status-badge.WARN { background: rgba(234,179,8,0.15); color: var(--warn); }
.status-badge.FAIL { background: rgba(239,68,68,0.15); color: var(--fail); }
.status-badge.QUEUE { background: rgba(107,114,128,0.15); color: var(--queue); }

.actions { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
.btn { padding: 10px 18px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--card); color: var(--text); cursor: pointer; font-size: 13px;
  font-weight: 500; transition: all 0.15s; }
.btn:hover { border-color: var(--accent); background: rgba(99,102,241,0.1); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn.primary:hover { opacity: 0.9; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

.hook-list { list-style: none; }
.hook-list li { padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.04);
  font-size: 12px; color: var(--muted); }

.output-panel { background: var(--bg); border-radius: 8px;
  padding: 12px; font-family: 'SF Mono', 'Consolas', monospace; font-size: 12px;
  min-height: 500px; overflow-y: auto; white-space: pre-wrap; }

.blockers { margin-top: 12px; }
.blocker-tag { display: inline-block; padding: 3px 8px; margin: 2px;
  background: rgba(239,68,68,0.12); color: var(--fail); border-radius: 4px; font-size: 11px; }

.spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border);
  border-top-color: var(--accent); border-radius: 50%; animation: spin 0.6s linear infinite; vertical-align: middle; margin-right: 6px; }
@keyframes spin { to { transform: rotate(360deg); } }

.refresh-time { font-size: 11px; color: var(--muted); margin-top: 8px; }

/* Modal */
.modal-overlay { display:none; position:fixed; top:0;left:0;right:0;bottom:0;
  background:rgba(0,0,0,0.6); z-index:100; justify-content:center;align-items:center; }
.modal-overlay.show { display:flex; }
.modal-box { background:var(--card); border:1px solid var(--border); border-radius:12px;
  padding:24px; max-width:600px; width:90%; max-height:80vh; overflow-y:auto; }
.modal-box h3 { font-size:16px; margin-bottom:8px; }
.modal-box .meta { font-size:12px; color:var(--muted); margin-bottom:16px; }
.modal-box .field { margin-bottom:12px; }
.modal-box .field-label { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:1px; }
.modal-box .field-value { font-size:13px; line-height:1.5; margin-top:4px; }
.modal-box .close-btn { float:right; background:none; border:none; color:var(--muted);
  font-size:20px; cursor:pointer; }
</style>
</head>
<body>
<header>
  <h1 id="project-title">载入中...</h1>
  <div class="stats">
    <select id="vol-selector" onchange="switchVolume()" style="background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:13px;margin-right:8px"></select>
    <span>进度 <strong id="ch-progress">-</strong></span>
    <span>字数 <strong id="ch-words">-</strong></span>
    <span>状态 <strong id="ch-status">-</strong></span>
    <button onclick="toggleTheme()" style="background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 10px;cursor:pointer;font-size:13px;margin-left:8px" title="切换明暗主题">🌓</button>
  </div>
</header>

<main>
  <div>
    <!-- Summary -->
    <div class="summary-grid card" style="grid-column:1/-1">
      <div class="summary-item"><div class="value" id="s-chapters">-</div><div class="label">已写章节</div></div>
      <div class="summary-item"><div class="value" id="s-words">-</div><div class="label">总字数</div></div>
      <div class="summary-item"><div class="value" id="s-pass">-</div><div class="label pass-color">已审查</div></div>
    </div>
    <div class="progress-bar"><div class="progress-fill" id="progress-fill" style="width:0%"></div></div>

    <!-- Chapter Table -->
    <div class="card">
      <h2>章节状态
        <select id="status-filter" onchange="render(STATE)" style="margin-left:12px;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:3px 8px;font-size:12px;">
          <option value="">全部状态</option>
          <option value="written">✅ 已写</option>
          <option value="pass">🟢 通过</option>
          <option value="warn">🟡 警告</option>
          <option value="fail">🔴 失败</option>
          <option value="queue">⬜ 待写</option>
        </select>
        <span style="font-size:11px;color:var(--muted);margin-left:8px;font-weight:400" id="auto-refresh-label"></span>
      </h2>
      <div style="max-height:600px;overflow-y:auto">
      <table id="chapter-table"><thead><tr>
        <th style="width:40px">#</th><th style="width:90px">标题</th><th style="width:55px">字数</th><th style="width:75px">修改</th><th style="width:55px">审查</th><th style="width:75px">时间</th><th style="width:140px">审查详情</th><th style="width:60px">状态</th><th style="width:44px"></th>
      </tr></thead><tbody></tbody></table>
      </div>
    </div>

    <!-- Actions -->
    <div class="card">
      <h2>操作</h2>
      <div class="actions">
        <button class="btn primary" onclick="doAction('doctor')">🔍 一键体检</button>
        <button class="btn" onclick="doAction('review')">📋 大纲审查</button>
        <button class="btn" onclick="doAction('causal')">🔗 逻辑验证</button>
        <button class="btn" onclick="doAction('iterate')">🔄 迭代修复</button>
        <button class="btn" onclick="exportTable()">📋 导出</button>
        <button class="btn" onclick="refresh()">🔃 刷新</button>
      </div>
    </div>
  </div>

  <!-- Sidebar -->
  <div>
    <div class="card">
      <h2>阻塞项</h2>
      <div class="blockers" id="blockers-list">-</div>
    </div>
    <div class="card" style="padding:12px">
      <div class="output-panel" id="output"></div>
      <div class="refresh-time" id="refresh-time"></div>
    </div>
  </div>
</main>

<!-- Chapter Detail Modal -->
<div class="modal-overlay" id="detail-modal" onclick="if(event.target===this)closeModal()">
  <div class="modal-box">
    <button class="close-btn" onclick="closeModal()">&times;</button>
    <h3 id="modal-title"></h3>
    <div class="meta" id="modal-meta"></div>
    <div class="field"><div class="field-label">章节目标 Goal</div><div class="field-value" id="modal-goal"></div><textarea id="modal-goal-edit" style="display:none;width:100%;min-height:60px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px;font-size:13px;resize:vertical"></textarea></div>
    <div class="field"><div class="field-label">命题兑现 Premise Must Hit</div><div class="field-value" id="modal-premise"></div><textarea id="modal-premise-edit" style="display:none;width:100%;min-height:60px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px;font-size:13px;resize:vertical"></textarea></div>
    <div class="field"><div class="field-label">禁飞区 Forbidden</div><div class="field-value" id="modal-forbidden"></div><textarea id="modal-forbidden-edit" style="display:none;width:100%;min-height:40px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px;font-size:13px;resize:vertical"></textarea></div>
    <div style="margin-top:16px;display:flex;gap:8px" id="modal-buttons">
      <button class="btn" id="modal-edit-btn" onclick="startEdit()">✏️ 编辑</button>
      <button class="btn primary" id="modal-save-btn" onclick="saveEdit()" style="display:none">💾 保存</button>
      <button class="btn" id="modal-cancel-btn" onclick="cancelEdit()" style="display:none">取消</button>
      <span style="font-size:11px;color:var(--muted);margin-left:8px;align-self:center" id="modal-save-status"></span>
    </div>
  </div>
</div>

<script>
const STATE = {};
let currentVolume = 0;

function normalizeStatus(s) {
  s = (s || '').toUpperCase();
  if (['WRITTEN','已写'].includes(s)) return 'written';
  if (['PASS','通过'].includes(s)) return 'pass';
  if (['WARN','警告'].includes(s)) return 'warn';
  if (['FAIL','失败'].includes(s)) return 'fail';
  if (['NEEDS_WRITING','NEEDS WRITING'].includes(s)) return 'queue';
  return 'queue'; // QUEUE / 待写 / 待写 / empty
}
function statusLabel(s) {
  const m = {written:'已写', pass:'通过', warn:'警告', fail:'失败', queue:'待写'};
  return m[normalizeStatus(s)] || '待写';
}

// Theme persistence
const savedTheme = localStorage.getItem('wd-theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

function toggleTheme() {
  const el = document.documentElement;
  const next = el.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  el.setAttribute('data-theme', next);
  localStorage.setItem('wd-theme', next);
}

async function refresh() {
  try {
    const r = await fetch('/api/state');
    const s = await r.json();
    Object.assign(STATE, s);
    render(s);
  } catch(e) { console.error(e); }
}

function render(s) {
  document.getElementById('project-title').textContent = s.title || '未命名项目';
  const totalBookChapters = (s.volumes||[]).reduce((sum, v) => sum + v.chapters, 0) || s.total_chapters_planned;
  // Progress: per-volume if selected, otherwise whole book
  let planned, written;
  if (currentVolume > 0) {
    const vol = (s.volumes||[]).find(v => v.start === currentVolume);
    if (vol) {
      planned = vol.chapters;
      written = (s.chapters||[]).filter(c => c.chapter >= vol.start && c.chapter <= vol.end && c.words > 0).length;
    }
  }
  if (!planned) { planned = totalBookChapters; written = s.total_chapters_written; }
  document.getElementById('ch-progress').textContent = written + '/' + planned + (currentVolume > 0 ? '' : ' (全)');
  document.getElementById('ch-words').textContent = (s.total_chars/10000).toFixed(1) + '万';
  const auditStatus = (s.last_audit || {}).status || '-';
  const auditLabels = {PASS:'通过', WARN:'警告', FAIL:'失败', NONE:'未审'};
  document.getElementById('ch-status').textContent = auditLabels[auditStatus] || auditStatus;

  // Volume selector
  const sel = document.getElementById('vol-selector');
  sel.innerHTML = '<option value="0">全部卷</option>' +
    (s.volumes||[]).map((v,i) =>
      `<option value="${v.start}" ${currentVolume===v.start?'selected':''}>第${v.label}卷 ${v.start}-${v.end}章 ${v.theme}</option>`
    ).join('');

  // Filter chapters by volume
  let chapters = s.chapters || [];
  if (currentVolume > 0) {
    const vol = (s.volumes||[]).find(v => v.start === currentVolume);
    if (vol) {
      chapters = chapters.filter(c => c.chapter >= vol.start && c.chapter <= vol.end);
    }
  }

  // Status filter
  const sf = document.getElementById('status-filter').value;
  if (sf) chapters = chapters.filter(c => normalizeStatus(c.status) === sf);

  // Summary
  document.getElementById('s-chapters').textContent = written;
  document.getElementById('s-words').textContent = (s.total_chars/10000).toFixed(1) + '万字';
  const passN = (s.chapters||[]).filter(c => c.review_verdict === 'PASS').length;
  const warnN = (s.chapters||[]).filter(c => c.review_verdict === 'WARN').length;
  const failN = (s.chapters||[]).filter(c => c.review_verdict === 'FAIL').length;
  const totalReviewed = passN + warnN + failN;
  document.getElementById('s-pass').innerHTML = totalReviewed + '<span style="font-size:11px;margin-left:4px"><span style="color:var(--pass)">' + passN + '</span>/<span style="color:var(--warn)">' + warnN + '</span>/<span style="color:var(--fail)">' + failN + '</span></span>';

  // Progress bar — use same planned/written from above
  const pct = planned > 0 ? Math.round(written / planned * 100) : 0;
  document.getElementById('progress-fill').style.width = pct + '%';

  // Chapter table
  const tbody = document.querySelector('#chapter-table tbody');
  tbody.innerHTML = chapters.slice(0, 50).map(c => {
    const ns = normalizeStatus(c.status);
    const cls = ns === 'written' ? 'PASS' : ns === 'warn' ? 'WARN' : ns === 'fail' ? 'FAIL' : 'QUEUE';
    const stLabel = statusLabel(c.status);
    const title = c.title || ('第' + String(c.chapter).padStart(3,'0') + '章');
    const w = c.words || 0;
    const wDisplay = w > 0 ? w.toString() : '-';
    const mTime = c.mtime || '-';
    const rvTime = c.reviewed_at || '';
    const rvVerdict = c.review_verdict || '';
    const rvIssues = c.review_issues || [];
    const issuesSummary = rvIssues.slice(0, 2).map(i => i.replace(/^\[.+\]\s*/, '').substring(0, 20)).join(', ') || '';
    const verdictColors = {PASS:'var(--pass)',WARN:'var(--warn)',FAIL:'var(--fail)'};
    const verdictStyle = rvVerdict ? `color:${verdictColors[rvVerdict]||'var(--muted)'};font-weight:600` : '';
    const verdictLabels = {PASS:'通过',WARN:'警告',FAIL:'失败'};
    return `<tr style="cursor:pointer" onclick="showDetail(${c.chapter})">
      <td class="ch">${c.chapter}</td>
      <td>${esc(title)}</td>
      <td style="font-variant-numeric:tabular-nums;text-align:right;padding-right:16px;font-size:12px;color:var(--muted)">${wDisplay}</td>
      <td style="font-size:11px;color:var(--muted);white-space:nowrap">${mTime}</td>
      <td style="font-size:12px;${verdictStyle}">${rvVerdict ? (verdictLabels[rvVerdict]||rvVerdict) : '-'}</td>
      <td style="font-size:11px;color:var(--muted);white-space:nowrap">${rvTime || '-'}</td>
      <td style="font-size:11px;color:var(--muted);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(rvIssues.join('; '))}">${issuesSummary || '-'}</td>
      <td class="status"><span class="status-badge ${cls}">${stLabel}</span></td>
      <td><button class="btn" style="padding:2px 6px;font-size:11px;width:36px" onclick="event.stopPropagation();doAction('review_ch_${c.chapter}')" title="审查第${c.chapter}章">审</button></td>
    </tr>`;
  }).join('');

  // Blockers
  const bl = document.getElementById('blockers-list');
  if ((s.blockers||[]).length > 0) {
    bl.innerHTML = s.blockers.map(b => `<span class="blocker-tag">⚠ ${esc(b)}</span>`).join('');
  } else {
    bl.innerHTML = '<span style="color:var(--pass);font-size:13px">✅ 无阻塞项</span>';
  }

  // Time
  document.getElementById('refresh-time').textContent = '更新 ' + new Date().toLocaleTimeString();
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function switchVolume() {
  currentVolume = parseInt(document.getElementById('vol-selector').value) || 0;
  render(STATE);
}

function closeModal() { document.getElementById('detail-modal').classList.remove('show'); }

let editingChapter = 0;

function showDetail(chNum) {
  const ch = (STATE.chapters||[]).find(c => c.chapter === chNum);
  if (!ch) return;
  editingChapter = chNum;
  document.getElementById('modal-title').textContent = '第' + ch.chapter + '章 ' + (ch.title || '');
  document.getElementById('modal-meta').textContent =
    '状态: ' + statusLabel(ch.status) + ' | 字数: ' + ((ch.words||0)/1000).toFixed(1) + 'k' +
    (ch.reviewed_at ? ' | 最后修改: ' + ch.reviewed_at : '');
  renderReadOnly(ch);
  document.getElementById('detail-modal').classList.add('show');
}

function renderReadOnly(ch) {
  document.getElementById('modal-goal').style.display = 'block'; document.getElementById('modal-goal-edit').style.display = 'none';
  document.getElementById('modal-premise').style.display = 'block'; document.getElementById('modal-premise-edit').style.display = 'none';
  document.getElementById('modal-forbidden').style.display = 'block'; document.getElementById('modal-forbidden-edit').style.display = 'none';
  document.getElementById('modal-goal').textContent = ch.goal || '未设定';
  document.getElementById('modal-premise').textContent = ch.premise_hit || '未设定';
  document.getElementById('modal-forbidden').textContent = ch.forbidden || '无';
  document.getElementById('modal-edit-btn').style.display = 'inline-block';
  document.getElementById('modal-save-btn').style.display = 'none'; document.getElementById('modal-cancel-btn').style.display = 'none';
  document.getElementById('modal-save-status').textContent = '';
}

function startEdit() {
  const ch = (STATE.chapters||[]).find(c => c.chapter === editingChapter);
  if (!ch) return;
  document.getElementById('modal-goal').style.display = 'none'; document.getElementById('modal-goal-edit').style.display = 'block';
  document.getElementById('modal-goal-edit').value = ch.goal || '';
  document.getElementById('modal-premise').style.display = 'none'; document.getElementById('modal-premise-edit').style.display = 'block';
  document.getElementById('modal-premise-edit').value = ch.premise_hit || '';
  document.getElementById('modal-forbidden').style.display = 'none'; document.getElementById('modal-forbidden-edit').style.display = 'block';
  document.getElementById('modal-forbidden-edit').value = ch.forbidden || '';
  document.getElementById('modal-edit-btn').style.display = 'none';
  document.getElementById('modal-save-btn').style.display = 'inline-block'; document.getElementById('modal-cancel-btn').style.display = 'inline-block';
}

function cancelEdit() {
  const ch = (STATE.chapters||[]).find(c => c.chapter === editingChapter);
  if (ch) renderReadOnly(ch);
}

async function saveEdit() {
  const goal = document.getElementById('modal-goal-edit').value;
  const premise = document.getElementById('modal-premise-edit').value;
  const forbidden = document.getElementById('modal-forbidden-edit').value;
  const statusEl = document.getElementById('modal-save-status');
  statusEl.textContent = '保存中...';
  try {
    const r = await fetch('/api/save_chapter', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({chapter: editingChapter, goal, premise_hit: premise, forbidden})
    });
    const d = await r.json();
    if (d.success) {
      const ch = (STATE.chapters||[]).find(c => c.chapter === editingChapter);
      if (ch) { ch.goal = goal; ch.premise_hit = premise; ch.forbidden = forbidden; }
      renderReadOnly(ch || {});
      refresh();
      statusEl.textContent = '✅ 已保存';
      setTimeout(() => { statusEl.textContent = ''; }, 2000);
    } else {
      statusEl.textContent = '❌ ' + (d.error || '失败');
    }
  } catch(e) {
    statusEl.textContent = '❌ ' + e.message;
  }
}

function exportTable() {
  const chapters = STATE.chapters || [];
  const rows = [['章','标题','字数','Goal','Premise Hit','状态']];
  for (const c of chapters.slice(0, 80)) {
    if (currentVolume > 0) {
      const vol = (STATE.volumes||[]).find(v => v.start === currentVolume);
      if (vol && (c.chapter < vol.start || c.chapter > vol.end)) continue;
    }
    rows.push([c.chapter, c.title||'', ((c.words||0)/1000).toFixed(1)+'k', (c.goal||'').substring(0,50), (c.premise_hit||'').substring(0,50), statusLabel(c.status)]);
  }
  const text = rows.map(r => r.join('\t')).join('\n');
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target;
    const orig = btn.textContent;
    btn.textContent = '✅ 已复制';
    setTimeout(() => btn.textContent = orig, 1500);
  });
}

async function doAction(action) {
  const btn = event.target;
  const orig = btn.textContent;
  btn.disabled = true;
  btn.style.width = btn.offsetWidth + 'px';
  btn.innerHTML = '<span class="spinner"></span>';

  const out = document.getElementById('output');
  out.textContent = '执行中...';

  try {
    const r = await fetch('/api/action/' + action);
    const d = await r.json();
    out.textContent = (d.output || d.error || 'Done.');

    // Instant update: refresh the table row for review actions
    if (action.startsWith('review_ch_')) {
      const chNum = action.replace('review_ch_', '');
      const statusMatch = (d.output || '').match(/结论[：:]\s*(PASS|WARN|FAIL)/);
      if (statusMatch) {
        const ch = (STATE.chapters||[]).find(c => c.chapter === parseInt(chNum));
        if (ch) {
          ch.reviewed_at = new Date().toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
          ch.review_verdict = statusMatch[1];
          // Extract review issues from output
          const issues = [];
          const lines = (d.output || '').split('\n');
          for (const line of lines) {
            const m = line.match(/(?:WARN|FAIL)\s+\[(.+?)\]\s*(?:—|:)?\s*(.+)/);
            if (m) issues.push('[' + m[1] + '] ' + m[2].trim());
          }
          ch.review_issues = issues;
        }
        render(STATE);
      }
    }

    if (action.startsWith('review_ch_')) {
      // Already handled by instant update above, skip refresh
    } else if (d.success) {
      setTimeout(refresh, 2000);
    }
  } catch(e) {
    out.textContent = 'Error: ' + e.message;
  }
  btn.disabled = false;
  btn.textContent = orig;
  btn.style.width = '';
}

// Auto-refresh every 30 seconds
let refreshCountdown = 30;
setInterval(() => {
  refreshCountdown--;
  if (refreshCountdown <= 0) {
    refresh();
    refreshCountdown = 30;
  }
  document.getElementById('auto-refresh-label').textContent = refreshCountdown + 's 自动刷新';
}, 1000);

refresh();
</script>
</body>
</html>"""


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

        if path == "/api/save_chapter":
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
