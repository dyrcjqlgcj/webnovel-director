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
import threading
import uuid
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import (  # noqa: E402
    SKILL_ROOT,
    _detect_queue_columns,
    count_body_chars,
    parse_chapter_queue,
    parse_json5,
    parse_volume_core_events,
    parse_volume_map,
    read_text,
    rebuild_volume_events_section,
    replace_events_in_section,
    split_table_cells,
    strip_markdown,
    write_chapter_queue,
    write_text,
    _find_volume_section,
)
from lib.llm import call_llm  # noqa: E402

SCRIPTS_DIR = SKILL_ROOT / "scripts"
TEMPLATE_DIR = SKILL_ROOT / "dashboard" / "templates"
STATIC_DIR = SKILL_ROOT / "dashboard" / "static"

# Cache for static file contents
_static_cache: dict[str, bytes] = {}

# Cache for project state (30s TTL to match frontend auto-refresh)
_state_cache: dict[str, tuple[float, dict]] = {}
_STATE_CACHE_TTL = 30  # seconds

# Async job tracking for write_flow
_write_jobs: dict[str, dict] = {}
_write_jobs_lock = threading.Lock()

# Async job tracking for batch_write
_batch_jobs: dict[str, dict] = {}
_batch_jobs_lock = threading.Lock()

# Scanner knowledge cache for scan_concepts endpoint
_scanner_context: str | None = None
_scanner_context_lock = threading.Lock()


def _load_scanner_context() -> str:
    """Lazily load all scanner reference docs into a single cached string."""
    global _scanner_context
    if _scanner_context is not None:
        return _scanner_context
    with _scanner_context_lock:
        if _scanner_context is not None:
            return _scanner_context
        parts = []
        scanner_dir = SKILL_ROOT / "subsystems" / "scanner"
        for fname in ["guide.md"]:
            fp = scanner_dir / fname
            if fp.exists():
                parts.append(read_text(fp))
        refs_dir = scanner_dir / "references"
        if refs_dir.exists():
            for fp in sorted(refs_dir.glob("*.md")):
                parts.append(f"---\n# {fp.name}\n")
                parts.append(read_text(fp))
        _scanner_context = "\n\n".join(parts)
        return _scanner_context


def _get_platform_context(platform: str) -> str:
    """Extract platform-specific guidance from scanner reference docs."""
    ctx = _load_scanner_context()
    # Extract key platform sections
    platform_keywords = {
        "番茄": ["番茄", "fanqie"],
        "起点": ["起点", "qidian"],
        "七猫": ["七猫"],
        "晋江": ["晋江"],
        "知乎盐选": ["知乎", "盐选", "盐言"],
    }
    keywords = platform_keywords.get(platform, [platform])
    lines = ctx.split("\n")
    relevant = []
    capture = False
    for line in lines:
        for kw in keywords:
            if kw in line and (line.strip().startswith("##") or line.strip().startswith("###")):
                capture = True
                break
        if capture and line.strip().startswith("##") and all(kw not in line for kw in keywords):
            capture = False
        if capture:
            relevant.append(line)
    if not relevant:
        # Return first 3000 chars as fallback
        return ctx[:3000]
    return "\n".join(relevant[:200])


def run_scan_concepts(platform: str, genre_preference: str = "") -> dict:
    """Generate market-scan concept candidates for a platform via LLM."""
    platform_ctx = _get_platform_context(platform)
    genre_hint = f"聚焦{genre_preference}题材。" if genre_preference else ""

    prompt = f"""你是一位专注于{platform}平台的网文市场分析师。以下是平台市场数据和读者画像：

{platform_ctx}

---
任务：为{platform}平台生成4个差异化的网文选题方案。{genre_hint}

每个方案必须包含：
1. 书名：符合{platform}命名规律，吸引眼球
2. 梗概：一句话（≤50字），说清核心看点和情绪钩子
3. 金手指：主角的独特能力/优势，必须是机制型（不是人格型）
4. 世界观：2-3句话描述故事世界背景
5. 题材标签：2-4个标签
6. 市场理由：为什么这个选题适合{platform}的读者（引用平台数据支撑）
7. 信心度：1-100

要求：
- 4个方案要有差异：不同题材、不同金手指类型、不同情绪走向
- 每个方案都必须是可执行的，不是纯概念
- 梗概要能一句话传播，读者3秒内能理解卖点
- 金手指要有成长梯度和排他性，不能开局即巅峰

严格按照以下JSON数组格式输出，不要输出任何其他内容：
[
  {{
    "title": "...",
    "summary": "...",
    "ability": "...",
    "world": "...",
    "genre_tags": ["...", "..."],
    "market_rationale": "...",
    "confidence": 85
  }}
]"""

    try:
        response = call_llm(prompt, temperature=0.85, max_tokens=2500, timeout=90)
        if not response:
            return {"success": False, "error": "LLM调用失败，请检查API密钥是否配置", "candidates": []}

        # Try to extract JSON array from response
        json_match = re.search(r"\[[\s\S]*\]", response.strip())
        if json_match:
            candidates = json.loads(json_match.group(0))
        else:
            candidates = json.loads(response.strip())

        if not isinstance(candidates, list):
            return {"success": False, "error": "LLM返回格式不正确", "candidates": []}

        return {"success": True, "candidates": candidates, "platform": platform}
    except json.JSONDecodeError:
        return {"success": False, "error": "LLM返回格式解析失败，请重试", "candidates": []}
    except Exception as e:
        return {"success": False, "error": str(e), "candidates": []}


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
    for ch_dir_name in ("正文", "chapters", "story/chapters"):
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
    for ch_dir_name in ("正文", "chapters", "story/chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                chapter_files.append(f)

    total_chars = count_body_chars(book_dir)
    chapter_words = count_chapter_words_detail(book_dir)

    # Chapter mtimes
    chapter_mtime = {}
    for ch_dir_name in ("正文", "chapters", "story/chapters"):
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

    # Track chapter file numbers and titles
    chapter_file_nums = set()
    chapter_titles_from_files: dict[int, str] = {}
    for ch_dir_name in ("正文", "chapters", "story/chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                m = re.match(r"第0*(\d+)章", f.name)
                if m:
                    ch_num = int(m.group(1))
                    chapter_file_nums.add(ch_num)
                    # Extract title from filename: "第011章-硫雾压境.md" → "硫雾压境"
                    rest = f.name[m.end():]
                    title = rest.lstrip("-_. ").replace(".md", "").strip()
                    if title:
                        chapter_titles_from_files[ch_num] = title

    for ch in queue:
        ch["title"] = ch.get("title_hint", "") or chapter_titles_from_files.get(ch["chapter"], "")
        ch["words"] = chapter_words.get(ch["chapter"], 0)
        ch["mtime"] = chapter_mtime.get(ch["chapter"], "")
        # Override status: if chapter has prose file, it's "written" regardless of queue status
        if ch["words"] > 0 and ch["chapter"] in chapter_file_nums:
            ch["status"] = "written"
        rh = review_history.get(str(ch["chapter"]), {})
        ch["reviewed_at"] = rh.get("time", "")
        ch["review_verdict"] = rh.get("verdict", "")
        ch["review_issues"] = rh.get("issues", [])

    # Merge in chapters from files not already in the queue
    queued_chapters = {ch["chapter"] for ch in queue}
    for ch_num in sorted(chapter_file_nums):
        if ch_num not in queued_chapters:
            title = chapter_titles_from_files.get(ch_num, f"第{ch_num:03d}章")
            queue.append({
                "chapter": ch_num,
                "title_hint": title,
                "title": title,
                "goal": "",
                "premise_must_hit": "",
                "forbidden": "",
                "status": "written",
                "words": chapter_words.get(ch_num, 0),
                "mtime": chapter_mtime.get(ch_num, ""),
                "reviewed_at": "",
                "review_verdict": "",
                "review_issues": [],
            })
    queue.sort(key=lambda ch: ch["chapter"])

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


def _get_state_cached(book_dir: Path) -> dict:
    """Return cached project state if fresh, otherwise recompute and cache."""
    import time
    key = str(book_dir.resolve())
    now = time.time()
    if key in _state_cache:
        ts, data = _state_cache[key]
        if now - ts < _STATE_CACHE_TTL:
            return data
    data = get_project_state(book_dir)
    _state_cache[key] = (now, data)
    # Prune old entries (keep max 10)
    if len(_state_cache) > 10:
        oldest = sorted(_state_cache.items(), key=lambda x: x[1][0])[:-10]
        for k, _ in oldest:
            _state_cache.pop(k, None)
    return data


def _spawn_script(cmd: list[Path | str], timeout: int = 60) -> dict:
    """Run a Python script via subprocess and return structured result."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONLEGACYWINDOWSSTDIO": "utf-8"}
    try:
        result = subprocess.run([str(x) for x in cmd], capture_output=True, timeout=timeout, env=env)
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "output": (stdout + stderr)[:2000],
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Action timed out ({timeout}s)"}
    except Exception as e:
        return {"error": str(e)}


def _find_chapter_file(book_dir: Path, chapter: str) -> str | None:
    """Find a chapter prose file by chapter number."""
    for ch_dir_name in ("正文", "chapters", "story/chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for pat in [f"第*{chapter.zfill(3)}*章*.md", f"第*{chapter}*章*.md", f"第0*{chapter}章*.md"]:
                candidates = sorted(ch_dir.glob(pat))
                if candidates:
                    return str(candidates[0])
    return None


def _do_write_flow(book_dir: Path, chapter: int) -> dict:
    """Execute the full write flow: build -> write -> review -> writeback -> check queue -> extend."""
    step_results: list[dict] = []
    book = str(book_dir)
    python = sys.executable
    scripts = SCRIPTS_DIR
    ch_str = str(chapter)

    def _add_step(name: str, result: dict) -> None:
        step_results.append({
            "step": name,
            "success": result.get("success", False),
            "output": result.get("output", result.get("error", ""))[:500],
        })

    # Step a: build task package
    result = _spawn_script(
        [python, str(scripts / "build_task_package.py"), book, "--chapter", ch_str],
        timeout=120)
    _add_step("build", result)
    if not result.get("success"):
        return {"success": False, "chapter": chapter, "step_results": step_results,
                "queue_remaining": -1, "queue_extended": False,
                "error": "构建任务包失败: " + result.get("error", result.get("output", "未知错误"))}

    # Step b: write chapter
    result = _spawn_script(
        [python, str(scripts / "write_chapter.py"), book, "--chapter", ch_str],
        timeout=300)
    _add_step("write", result)
    if not result.get("success"):
        return {"success": False, "chapter": chapter, "step_results": step_results,
                "queue_remaining": -1, "queue_extended": False,
                "error": "写章失败: " + result.get("error", result.get("output", "未知错误"))}

    # Step c: review chapter (find the chapter file first)
    ch_file = _find_chapter_file(book_dir, ch_str)
    review_cmd = [python, str(scripts / "review_chapter.py"), book, "--chapter", ch_str]
    if ch_file:
        review_cmd.extend(["--text", ch_file])
    result = _spawn_script(review_cmd, timeout=120)
    _add_step("review", result)
    if not result.get("success"):
        return {"success": False, "chapter": chapter, "step_results": step_results,
                "queue_remaining": -1, "queue_extended": False,
                "error": "审查失败: " + result.get("error", result.get("output", "未知错误"))}

    # Step d: post writeback (always PASS for auto flow)
    result = _spawn_script(
        [python, str(scripts / "post_writeback.py"), book,
         "--chapter", ch_str, "--audit", "PASS", "--summary", "", "--write", "--json"],
        timeout=120)
    _add_step("writeback", result)

    # Step e: check queue remaining (count chapters with status "待写")
    queue_path = book_dir / "director" / "chapter_queue.md"
    queue_remaining = 0
    if queue_path.exists():
        queue = parse_chapter_queue(queue_path)
        pending_statuses = {"待写", "NEEDS_WRITING", "NEEDS WRITING"}
        queue_remaining = sum(
            1 for c in queue
            if (c.get("status", "") or "").upper().replace(" ", "_") in
               {s.upper().replace(" ", "_") for s in pending_statuses}
        )

    # Step f: extend outline if < 5 chapters remaining
    queue_extended = False
    if queue_remaining < 5:
        ext_result = _spawn_script(
            [python, str(scripts / "generate_outline_queue.py"), book,
             "--chapters", "5", "--llm"],
            timeout=180)
        _add_step("extend_outline", ext_result)
        queue_extended = ext_result.get("success", False)

    return {
        "success": True,
        "chapter": chapter,
        "step_results": step_results,
        "queue_remaining": queue_remaining,
        "queue_extended": queue_extended,
    }


# Provider presets — loaded from config.yaml at startup
_provider_presets: list[dict] = []


def _load_presets() -> list[dict]:
    """Load provider presets from config.yaml."""
    try:
        import yaml
        cfg_path = SKILL_ROOT / "config.yaml"
        if cfg_path.exists():
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            return cfg.get("provider_presets", [])
    except Exception:
        pass
    return []


def _try_verify_at(base_url: str, api_key: str) -> dict | None:
    """Try to verify a key at a given base_url. Returns result dict or None."""
    import urllib.request as ur
    # Normalize base_url: strip trailing slash, ensure /v1 if it's chat-compatible
    url = base_url.rstrip("/")
    models_url = f"{url}/models"
    try:
        req = ur.Request(models_url, headers={"Authorization": f"Bearer {api_key}"})
        with ur.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                data = json.loads(resp.read())
                models_raw = data.get("data", [])
                models = []
                for m in models_raw:
                    mid = (m.get("id") or "").strip()
                    if mid and isinstance(mid, str):
                        models.append(mid)
                # Keep chat/completion models at top
                preferred = [m for m in models if "chat" in m.lower() or "reasoner" in m.lower() or "instruct" in m.lower()]
                others = [m for m in models if m not in preferred]
                models = preferred + others
                return {"models": models[:30], "base_url": base_url}
    except ur.HTTPError as e:
        return None
    except Exception:
        return None


def _verify_api_key(api_key: str, base_url: str = "", _provider_hint: str = "") -> dict:
    """Verify an API key at a custom base_url, or auto-detect across presets.

    If base_url is given, verify only at that URL.
    Otherwise, try all preset providers in order.
    """
    import urllib.request as ur

    if base_url:
        result = _try_verify_at(base_url, api_key)
        if result:
            return {
                "success": True,
                "message": "API Key 有效",
                "provider": "custom",
                "label": base_url.rstrip("/"),
                "base_url": base_url,
                "models": result["models"],
            }
        # Try one more: some APIs use a different models path
        try:
            url = base_url.rstrip("/")
            req = ur.Request(f"{url}/v1/models", headers={"Authorization": f"Bearer {api_key}"})
            with ur.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read())
                    models = []
                    for m in data.get("data", []):
                        mid = (m.get("id") or "").strip()
                        if mid:
                            models.append(mid)
                    return {
                        "success": True,
                        "message": "API Key 有效",
                        "provider": "custom",
                        "label": base_url.rstrip("/"),
                        "base_url": base_url,
                        "models": models[:30],
                    }
        except Exception:
            pass
        return {"success": False, "error": "自定义端点验证失败，请检查 base_url 和 API Key"}

    # Auto-detect across presets
    presets = _load_presets()
    if not presets:
        presets = [{"id": "deepseek", "label": "DeepSeek", "base_url": "https://api.deepseek.com/v1"}]

    errors = []
    for p in presets:
        pid = p.get("id", "")
        plabel = p.get("label", pid)
        pbase = p.get("base_url", "")
        if not pbase or pid == "custom":
            continue
        result = _try_verify_at(pbase, api_key)
        if result:
            return {
                "success": True,
                "message": f"{plabel} API Key 有效",
                "provider": pid,
                "label": plabel,
                "base_url": pbase,
                "models": result["models"],
            }
        errors.append(f"{plabel}: 401/error")

    return {"success": False, "error": "Key 无效，所有厂商均返回 401", "details": errors}


def _start_batch_write(book_dir: Path, chapter_start: int, count: int) -> str:
    """Start a batch write job. Returns job_id for polling."""
    job_id = uuid.uuid4().hex[:12]
    with _batch_jobs_lock:
        _batch_jobs[job_id] = {
            "status": "running",
            "job_id": job_id,
            "chapter_start": chapter_start,
            "count": count,
            "completed": 0,
            "failed": 0,
            "current_chapter": chapter_start,
            "results": [],
            "started_at": datetime.datetime.now().isoformat(),
        }

    def _bg_batch():
        for i in range(count):
            ch = chapter_start + i
            with _batch_jobs_lock:
                _batch_jobs[job_id]["current_chapter"] = ch
            result = _do_write_flow(book_dir, ch)
            with _batch_jobs_lock:
                _batch_jobs[job_id]["results"].append({
                    "chapter": ch,
                    "success": result.get("success", False),
                    "step_results": result.get("step_results", []),
                    "queue_remaining": result.get("queue_remaining", -1),
                    "queue_extended": result.get("queue_extended", False),
                    "error": result.get("error", ""),
                })
                if result.get("success"):
                    _batch_jobs[job_id]["completed"] += 1
                else:
                    _batch_jobs[job_id]["failed"] += 1

        with _batch_jobs_lock:
            _batch_jobs[job_id]["status"] = "done"
            _batch_jobs[job_id]["finished_at"] = datetime.datetime.now().isoformat()

        # Clean up old jobs
        with _batch_jobs_lock:
            keys = list(_batch_jobs.keys())
            if len(keys) > 20:
                for old_key in keys[:-20]:
                    _batch_jobs.pop(old_key, None)

    threading.Thread(target=_bg_batch, daemon=True).start()
    return job_id


def _run_parallel_review(book_dir: Path, vol_str: str) -> dict:
    """Run review_parallel.py for all written chapters in a volume."""
    try:
        vol_num = int(vol_str)
    except ValueError:
        return {"success": False, "error": f"无效卷号: {vol_str}"}

    volumes = parse_volume_map(book_dir / "director" / "volume_map.md")
    target_vol = None
    for v in volumes:
        if v["volume"] == vol_num:
            target_vol = v
            break
    if not target_vol:
        return {"success": False, "error": f"未找到第{vol_num}卷"}

    # Find written chapters in this volume
    chapter_files = []
    for ch_dir_name in ("正文", "chapters", "story/chapters"):
        ch_dir = book_dir / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                m = re.match(r"第0*(\d+)章", f.name)
                if m:
                    ch_num = int(m.group(1))
                    if target_vol["start"] <= ch_num <= target_vol["end"]:
                        chapter_files.append((ch_num, str(f)))

    if not chapter_files:
        return {"success": False, "error": f"第{vol_num}卷内没有已写章节"}

    results = []
    passed = 0
    failed = 0
    for ch_num, ch_file in sorted(chapter_files):
        # Step 1: build task package (required by review_parallel, but may fail for already-written chapters)
        build_result = _spawn_script(
            [sys.executable, str(SCRIPTS_DIR / "build_task_package.py"), str(book_dir),
             "--chapter", str(ch_num)],
            timeout=60)

        # Step 2: run review — use review_parallel if build succeeded, otherwise fall back to review_chapter
        if build_result.get("success"):
            r = _spawn_script(
                [sys.executable, str(SCRIPTS_DIR / "review_parallel.py"), str(book_dir),
                 "--chapter", str(ch_num), "--text", ch_file, "--json"],
                timeout=180)
        else:
            # Fallback: review_chapter.py only needs --text, no task package required
            r = _spawn_script(
                [sys.executable, str(SCRIPTS_DIR / "review_chapter.py"), str(book_dir),
                 "--chapter", str(ch_num), "--text", ch_file],
                timeout=120)
        verdict = "?"
        if r.get("output"):
            # Try JSON parse first (--json flag)
            try:
                parsed = json.loads(r["output"])
                verdict = parsed.get("status", "?")
            except json.JSONDecodeError:
                m = re.search(r"结论[：:]\s*(PASS|WARN|FAIL)", r["output"])
                if m:
                    verdict = m.group(1)
        results.append({"chapter": ch_num, "verdict": verdict, "success": r.get("success", False)})
        if verdict == "PASS":
            passed += 1
        else:
            failed += 1

    return {
        "success": True,
        "volume": vol_num,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
        "output": "\n".join(
            f"Ch{r['chapter']:03d}: {r['verdict']}" for r in results
        ),
    }


def run_action(book_dir: Path, action: str) -> dict:
    """Execute a director script action."""
    book = str(book_dir)
    scripts = SCRIPTS_DIR

    if action.startswith("review_ch_"):
        ch = action.replace("review_ch_", "")
        ch_file = None
        for ch_dir_name in ("正文", "chapters", "story/chapters"):
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
        return _spawn_script(cmd)

    if action.startswith("generate_queue_"):
        parts = action.replace("generate_queue_", "").split("_")
        chapters = parts[0]
        from_index = len(parts) > 1 and parts[1] == "1"
        cmd = [sys.executable, str(scripts / "generate_outline_queue.py"), book, "--chapters", chapters]
        if from_index:
            cmd.append("--from-index")
        return _spawn_script(cmd)

    if action.startswith("build_ch_"):
        ch = action.replace("build_ch_", "")
        cmd = [sys.executable, str(scripts / "build_task_package.py"), book, "--chapter", ch]
        return _spawn_script(cmd)

    if action.startswith("write_chapter_"):
        ch = action.replace("write_chapter_", "")
        cmd = [sys.executable, str(scripts / "write_chapter.py"), book, "--chapter", ch]
        return _spawn_script(cmd)

    return {"error": f"Unknown action: {action}"}


def run_concept_gate(data: dict) -> dict:
    """Run concept_gate.py with inline YAML data."""
    import tempfile, yaml
    yaml_text = "\n".join(f"{k}: \"{v}\"" for k, v in data.items() if v)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(yaml_text)
        tmp_path = f.name
    try:
        result = _spawn_script([sys.executable, str(SCRIPTS_DIR / "concept_gate.py"), tmp_path, "--json"])
        if result.get("output"):
            try:
                parsed = json.loads(result["output"])
                return {"success": True, "data": parsed}
            except json.JSONDecodeError:
                return result
        return result
    finally:
        try: os.unlink(tmp_path)
        except: pass


def run_init_project(books_root: Path, data: dict) -> dict:
    """Run init_project.py to create a new book project."""
    title = data.get("title", "").strip()
    if not title:
        return {"success": False, "error": "书名不能为空"}
    book_id = data.get("book_id", "").strip() or None
    book_dir = books_root / title
    cmd = [sys.executable, str(SCRIPTS_DIR / "init_project.py"), str(book_dir), "--title", title]
    if book_id:
        cmd.extend(["--book-id", book_id])
    result = _spawn_script(cmd)
    if result.get("success"):
        result["book_path"] = str(book_dir)
        result["book_key"] = str(book_dir)
        result["title"] = title
    return result


def run_post_writeback(book_dir: Path, body: str) -> dict:
    """Run post_writeback.py."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"success": False, "error": "无效 JSON"}
    chapter = data.get("chapter", 0)
    audit = data.get("audit", "PASS")
    summary = data.get("summary", "")
    cmd = [sys.executable, str(SCRIPTS_DIR / "post_writeback.py"), str(book_dir),
           "--chapter", str(chapter), "--audit", audit, "--summary", summary, "--write", "--json"]
    return _spawn_script(cmd)


def save_chapter_queue_row(book_dir: Path, data: dict) -> dict:
    """Update a single chapter's row in chapter_queue.md. Column-aware."""
    cq_path = book_dir / "director" / "chapter_queue.md"
    if not cq_path.exists():
        return {"success": False, "error": "chapter_queue.md 不存在"}

    ch_num = data.get("chapter")
    if ch_num is None:
        return {"success": False, "error": "缺少 chapter 参数"}
    goal = data.get("goal", "")
    premise_hit = data.get("premise_hit", "")
    forbidden = data.get("forbidden", "")

    content = read_text(cq_path)
    lines = content.split("\n")

    # Detect column layout from header
    col_map = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("|") and "---" not in s:
            if i + 1 < len(lines) and "---" in lines[i + 1]:
                col_map = _detect_queue_columns(split_table_cells(s))
                break
    if col_map is None:
        col_map = _detect_queue_columns([])  # fallback to 6-column

    new_lines = []
    found = False

    for line in lines:
        s = line.strip()
        if not s.startswith("|") or "---" in s:
            new_lines.append(line)
            continue
        cells = split_table_cells(s)
        n = re.sub(r"\D", "", cells[col_map["chapter"]])
        if not n.isdigit() or int(n) != ch_num:
            new_lines.append(line)
            continue
        if col_map.get("goal", -1) >= 0:
            cells[col_map["goal"]] = goal
        if col_map.get("premise_must_hit", -1) >= 0:
            cells[col_map["premise_must_hit"]] = premise_hit
        if col_map.get("forbidden", -1) >= 0:
            cells[col_map["forbidden"]] = forbidden
        new_lines.append("| " + " | ".join(cells) + " |")
        found = True

    if not found:
        return {"success": False, "error": f"未找到第{ch_num}章"}

    write_text(cq_path, "\n".join(new_lines))
    return {"success": True, "chapter": ch_num}


def scan_books(books_root: Path) -> list[dict]:
    """Scan for book projects (directories containing director/director_state.json5)."""
    books = []
    if not books_root or not books_root.exists():
        return books
    for entry in sorted(books_root.iterdir()):
        if not entry.is_dir():
            continue
        state_file = entry / "director" / "director_state.json5"
        if state_file.exists():
            state = parse_json5(read_text(state_file))
            books.append({"key": str(entry), "title": state.get("title", entry.name), "path": str(entry)})
    return books


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
    books_root: Path = None
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
        raw = json.dumps(data, ensure_ascii=True, indent=2)
        self._serve(200, "application/json; charset=utf-8", raw.encode("utf-8"))

    def _resolve_book(self, qs) -> Path | None:
        key = qs.get("book", [None])[0]
        if key:
            candidate = Path(key)
            if (candidate / "director" / "director_state.json5").exists():
                return candidate
            return None
        if self.books_root:
            books = scan_books(self.books_root)
            if books:
                return Path(books[0]["path"])
        return self.book_dir

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._serve(200, "text/html; charset=utf-8",
                        self.html_template.encode("utf-8"))

        elif path.startswith("/static/"):
            filename = path.replace("/static/", "", 1)
            content = _load_static(filename)
            ext = os.path.splitext(filename)[1]
            mime = MIME_TYPES.get(ext, "application/octet-stream")
            self._serve(200, mime, content)

        elif path == "/api/books":
            self._serve_json(scan_books(self.books_root) if self.books_root else [])

        elif path == "/api/state":
            target = self._resolve_book(qs)
            if target:
                self._serve_json(_get_state_cached(target))
            else:
                self._serve_json({"error": "未找到书籍项目", "title": "无项目"})

        elif path == "/api/provider_presets":
            presets = _load_presets()
            self._serve_json({"presets": presets})

        elif path == "/api/outline/full":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"error": "未找到书籍项目"})
                return
            vm_path = target / "director" / "volume_map.md"
            cq_path = target / "director" / "chapter_queue.md"
            volumes_raw = parse_volume_map(vm_path) if vm_path.exists() else []
            volumes = parse_volume_map(vm_path, include_events=True) if vm_path.exists() else []
            # Detect active volume
            state_path = target / "director" / "director_state.json5"
            active_vol = 1
            if state_path.exists():
                state = parse_json5(read_text(state_path))
                active_vol = state.get("activeVolume", 1)
            # Mark active volume
            for v in volumes:
                v["is_active"] = v["volume"] == active_vol
            # Chapters
            chapters = parse_chapter_queue(cq_path) if cq_path.exists() else []
            # Merge mtime and title from chapter files
            for ch in chapters:
                for ch_dir_name in ("正文", "chapters", "story/chapters"):
                    ch_dir = target / ch_dir_name
                    if ch_dir.exists():
                        for pat in [f"第*{str(ch['chapter']).zfill(3)}*章*.md",
                                    f"第*{str(ch['chapter'])}*章*.md",
                                    f"第0*{str(ch['chapter'])}章*.md"]:
                            candidates = sorted(ch_dir.glob(pat))
                            if candidates:
                                f = candidates[0]
                                ch["mtime"] = datetime.datetime.fromtimestamp(
                                    f.stat().st_mtime).strftime("%m-%d %H:%M")
                                # Extract title from filename
                                rest = f.name.split("章", 1)[-1] if "章" in f.name else ""
                                title = rest.lstrip("-_. ").replace(".md", "").strip()
                                if title and not ch.get("title_hint"):
                                    ch["title_hint"] = title
                                break
                if "mtime" not in ch:
                    ch["mtime"] = ""
                # Map chapter to volume
                for v in volumes_raw:
                    if v["start"] <= ch["chapter"] <= v["end"]:
                        ch["volume_num"] = v["volume"]
                        break
            self._serve_json({
                "volumes": volumes,
                "active_volume": active_vol,
                "chapters": chapters,
                "total_chapters_planned": sum(v["chapters"] for v in volumes_raw),
            })

        elif path == "/api/chapter_content":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return
            ch_str = qs.get("chapter", [None])[0]
            if not ch_str:
                self._serve_json({"success": False, "error": "缺少 chapter 参数"})
                return
            ch_file = _find_chapter_file(target, ch_str)
            if not ch_file:
                self._serve_json({"success": False, "error": f"未找到第{ch_str}章的正文文件"})
                return
            content = read_text(Path(ch_file))
            body = content
            title_match = re.match(r"^#\s*(.+)", body)
            title = title_match.group(1) if title_match else f"第{ch_str}章"
            if title_match:
                body = body[title_match.end():].lstrip()
            char_count = len(strip_markdown(body))
            para_count = len([p for p in body.split("\n\n") if p.strip()])
            self._serve_json({
                "success": True,
                "chapter": int(ch_str),
                "title": title,
                "content": content,
                "body": body,
                "char_count": char_count,
                "para_count": para_count,
                "file": str(Path(ch_file).relative_to(target)),
            })

        elif path == "/api/file":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return
            rel_path = qs.get("path", [""])[0]
            if not rel_path or ".." in rel_path:
                self._serve_json({"success": False, "error": "无效路径"})
                return
            file_path = (target / rel_path).resolve()
            if not str(file_path).startswith(str(target.resolve())):
                self._serve_json({"success": False, "error": "路径越界"})
                return
            if not file_path.exists():
                self._serve_json({"success": False, "error": "文件不存在"})
                return
            self._serve_json({"success": True, "content": read_text(file_path), "path": rel_path})

        elif path == "/api/write_flow":
            # Job polling: GET /api/write_flow?job=<job_id>
            job_id = qs.get("job", [None])[0]
            if job_id:
                with _write_jobs_lock:
                    job = _write_jobs.get(job_id)
                if job:
                    self._serve_json(job)
                else:
                    self._serve_json({"status": "not_found", "error": "任务不存在"})
                return

            # Start new write flow: GET /api/write_flow?book=...&chapter=N
            chapter_str = qs.get("chapter", [None])[0]
            if not chapter_str:
                self._serve_json({"success": False, "error": "缺少 chapter 参数"})
                return
            try:
                chapter = int(chapter_str)
            except ValueError:
                self._serve_json({"success": False, "error": "chapter 必须是数字"})
                return
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return

            job_id = uuid.uuid4().hex[:12]
            with _write_jobs_lock:
                _write_jobs[job_id] = {
                    "status": "running",
                    "job_id": job_id,
                    "chapter": chapter,
                    "step_results": [],
                    "queue_remaining": -1,
                    "queue_extended": False,
                    "started_at": datetime.datetime.now().isoformat(),
                }

            def _bg_run():
                try:
                    result = _do_write_flow(target, chapter)
                    with _write_jobs_lock:
                        _write_jobs[job_id].update(result)
                        _write_jobs[job_id]["status"] = "done" if result.get("success") else "error"
                        _write_jobs[job_id]["finished_at"] = datetime.datetime.now().isoformat()
                except Exception as e:
                    with _write_jobs_lock:
                        _write_jobs[job_id]["status"] = "error"
                        _write_jobs[job_id]["error"] = str(e)
                        _write_jobs[job_id]["finished_at"] = datetime.datetime.now().isoformat()

                # Clean up old jobs (keep latest 20)
                with _write_jobs_lock:
                    keys = list(_write_jobs.keys())
                    if len(keys) > 20:
                        for old_key in keys[:-20]:
                            _write_jobs.pop(old_key, None)

            threading.Thread(target=_bg_run, daemon=True).start()
            self._serve_json({"job_id": job_id, "status": "started", "chapter": chapter})

        elif path == "/api/batch_write":
            # Job polling: GET /api/batch_write?job=<job_id>
            job_id = qs.get("job", [None])[0]
            if job_id:
                with _batch_jobs_lock:
                    job = _batch_jobs.get(job_id)
                if job:
                    self._serve_json(job)
                else:
                    self._serve_json({"status": "not_found", "error": "任务不存在"})
                return
            self._serve_json({"success": False, "error": "batch_write 需要 POST 启动或 GET ?job= 轮询"})
            return

        elif path.startswith("/api/action/"):
            action = path.split("/")[-1]
            target = self._resolve_book(qs)
            if target:
                action_map = {
                    "doctor": [sys.executable, str(SCRIPTS_DIR / "director_doctor.py"), target],
                    "review": [sys.executable, str(SCRIPTS_DIR / "outline_gate_review.py"), target],
                    "causal": [sys.executable, str(SCRIPTS_DIR / "outline_causal_check.py"), target],
                    "iterate": [sys.executable, str(SCRIPTS_DIR / "outline_iterate.py"), target, "--no-llm", "--max-rounds", "2"],
                }
                if action in action_map:
                    self._serve_json(_spawn_script(action_map[action]))
                elif action.startswith("review_parallel_"):
                    vol_str = action.replace("review_parallel_", "")
                    result = _run_parallel_review(target, vol_str)
                    self._serve_json(result)
                elif action.startswith("repair_"):
                    ch_str = action.replace("repair_", "")
                    result = _spawn_script(
                        [sys.executable, str(SCRIPTS_DIR / "repair_plan.py"), str(target),
                         "--chapter", ch_str], timeout=120)
                    self._serve_json(result)
                else:
                    self._serve_json(run_action(target, action))
            else:
                self._serve_json({"error": "未找到书籍项目"})

        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/save_chapter":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                result = save_chapter_queue_row(target, data)
                self._serve_json(result)
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})

        elif path == "/api/concept_gate":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                result = run_concept_gate(data)
                self._serve_json(result)
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})

        elif path == "/api/scan_concepts":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                platform = data.get("platform", "番茄")
                genre_pref = data.get("genre_preference", "")
                result = run_scan_concepts(platform, genre_pref)
                self._serve_json(result)
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})

        elif path == "/api/init_project":
            target_root = self.books_root or (SKILL_ROOT / "books")
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                result = run_init_project(target_root, data)
                self._serve_json(result)
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})

        elif path == "/api/file":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                rel_path = data.get("path", "")
                if not rel_path or ".." in rel_path:
                    self._serve_json({"success": False, "error": "无效路径"})
                    return
                file_path = (target / rel_path).resolve()
                if not str(file_path).startswith(str(target.resolve())):
                    self._serve_json({"success": False, "error": "路径越界"})
                    return
                if not file_path.exists():
                    self._serve_json({"success": False, "error": "文件不存在"})
                    return
                write_text(file_path, data.get("content", ""))
                self._serve_json({"success": True})
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})

        elif path == "/api/outline/save_event":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                volume_num = data.get("volume", 1)
                events = data.get("events", [])
                vm_path = target / "director" / "volume_map.md"
                if not vm_path.exists():
                    self._serve_json({"success": False, "error": "volume_map.md 不存在"})
                    return
                full_text = read_text(vm_path)
                section = _find_volume_section(full_text, volume_num)
                if not section:
                    self._serve_json({"success": False, "error": f"未找到第{volume_num}卷详情"})
                    return
                new_section = replace_events_in_section(section, events, volume_num)
                new_full = full_text.replace(section, new_section)
                write_text(vm_path, new_full)
                self._serve_json({"success": True, "volume": volume_num})
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})

        elif path == "/api/outline/add_event":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                volume_num = data.get("volume", 1)
                new_event = data.get("event", {})
                vm_path = target / "director" / "volume_map.md"
                if not vm_path.exists():
                    self._serve_json({"success": False, "error": "volume_map.md 不存在"})
                    return
                full_text = read_text(vm_path)
                # Find the section, parse existing events, append new one, rebuild
                section = _find_volume_section(full_text, volume_num)
                if not section:
                    self._serve_json({"success": False, "error": f"未找到第{volume_num}卷详情"})
                    return
                existing = parse_volume_core_events(section, volume_num)
                existing.append({
                    "range_start": new_event.get("range_start", 1),
                    "range_end": new_event.get("range_end", 1),
                    "label": new_event.get("label", "新事件块"),
                    "status": new_event.get("status", "planned"),
                    "events": new_event.get("events", []),
                })
                new_section = replace_events_in_section(section, existing, volume_num)
                new_full = full_text.replace(section, new_section)
                write_text(vm_path, new_full)
                self._serve_json({"success": True, "volume": volume_num})
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})

        elif path == "/api/generate_queue":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return
            chapters = qs.get("chapters", ["20"])[0]
            from_index = qs.get("from_index", ["0"])[0] == "1"
            result = run_action(target, f"generate_queue_{chapters}_{'1' if from_index else '0'}")
            self._serve_json(result)

        elif path == "/api/write_chapter":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return
            chapter = qs.get("chapter", ["0"])[0]
            result = run_action(target, f"write_chapter_{chapter}")
            self._serve_json(result)

        elif path == "/api/review_chapter_post":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return
            chapter = qs.get("chapter", ["0"])[0]
            result = run_action(target, f"review_ch_{chapter}")
            self._serve_json(result)

        elif path == "/api/post_writeback":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            result = run_post_writeback(target, body)
            self._serve_json(result)

        elif path == "/api/verify_key":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                api_key = (data.get("api_key", "") or "").strip()
                base_url = (data.get("base_url", "") or "").strip()
                if not api_key:
                    self._serve_json({"success": False, "error": "API Key 不能为空"})
                    return
                result = _verify_api_key(api_key, base_url=base_url)
                self._serve_json(result)
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})

        elif path == "/api/save_key":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                api_key = (data.get("api_key", "") or "").strip()
                provider = data.get("provider", "custom")
                model = data.get("model", "")
                base_url = (data.get("base_url", "") or "").strip()
                if not api_key:
                    self._serve_json({"success": False, "error": "API Key 不能为空"})
                    return

                config_local = SKILL_ROOT / "config.local.yaml"
                try:
                    import yaml
                    existing: dict = {}
                    if config_local.exists():
                        existing = yaml.safe_load(config_local.read_text(encoding="utf-8")) or {}
                except Exception:
                    existing = {}

                existing.setdefault("api_keys", {})
                existing["api_keys"][provider] = {"key": api_key}
                if base_url:
                    existing["api_keys"][provider]["base_url"] = base_url
                if model:
                    existing["api_keys"][provider]["default_model"] = model

                # Also save to providers section for llm.py compatibility
                existing.setdefault("providers", {})
                existing["providers"].setdefault(provider, {})
                existing["providers"][provider]["base_url"] = base_url or f"https://api.{provider}.com/v1"
                if model:
                    existing["providers"][provider]["default_model"] = model

                import yaml
                config_local.write_text(yaml.dump(existing, allow_unicode=True, default_flow_style=False),
                                        encoding="utf-8")
                # Inject for current process
                if provider == "deepseek":
                    os.environ["DEEPSEEK_API_KEY"] = api_key
                elif base_url:
                    os.environ[f"{provider.upper()}_API_KEY"] = api_key
                    os.environ[f"{provider.upper()}_BASE_URL"] = base_url
                self._serve_json({"success": True, "message": f"已保存到 {config_local.name}", "provider": provider, "model": model or "默认"})
            except Exception as e:
                self._serve_json({"success": False, "error": f"保存失败: {str(e)}"})

        elif path == "/api/batch_write":
            target = self._resolve_book(qs)
            if not target:
                self._serve_json({"success": False, "error": "未找到书籍项目"})
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                chapter_start = data.get("chapter_start", 0)
                count = data.get("count", 1)
                if not chapter_start or count < 1:
                    self._serve_json({"success": False, "error": "chapter_start 和 count 参数不正确"})
                    return
                job_id = _start_batch_write(target, chapter_start, count)
                self._serve_json({"job_id": job_id, "status": "started", "chapter_start": chapter_start, "count": count})
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)})

        else:
            self.send_error(404)


def main() -> int:
    ap = argparse.ArgumentParser(description="webnovel-director Dashboard")
    ap.add_argument("book_dir", nargs="?", help="小说项目路径（单书模式）")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--books-root", type=str, default=None,
                    help="多书根目录（默认 <项目根>/books）")
    args = ap.parse_args()

    books_root = None
    if args.books_root:
        books_root = Path(args.books_root).resolve()
    else:
        default_root = SKILL_ROOT / "books"
        if default_root.exists():
            books_root = default_root

    if books_root:
        books = scan_books(books_root)
        if books:
            args.book_dir = books[0]["path"]
            print(f"  扫描到 {len(books)} 本书:")
            for b in books:
                print(f"    {b['title']}")

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
    DashboardHandler.books_root = books_root
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
