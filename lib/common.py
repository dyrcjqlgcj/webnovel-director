"""Shared utilities for webnovel-director scripts.

All scripts should import from here instead of copy-pasting helpers.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("wd.common")

# ── Path constants ──────────────────────────────────────────────

SKILL_ROOT = Path(__file__).resolve().parent.parent

DIRECTOR_PREMISE = "director/premise.md"
DIRECTOR_STATE = "director/director_state.json5"
DIRECTOR_QUEUE = "director/chapter_queue.md"
DIRECTOR_LAST_AUDIT = "director/last_audit.md"
DIRECTOR_AUDIT_LOG = "director/audit_log.md"
DIRECTOR_OUTLINE_REVIEW = "director/outline_review.md"
DIRECTOR_VOLUME_MAP = "director/volume_map.md"

TRUTH_CURRENT_STATE = "truth/current_state.md"
TRUTH_RESOURCE_LEDGER = "truth/resource_ledger.md"
TRUTH_PARTICLE_LEDGER = "truth/particle_ledger.md"
TRUTH_PENDING_HOOKS = "truth/pending_hooks.md"
TRUTH_RELATIONSHIP_GRAPH = "truth/relationship_graph.yaml"

STORY_VOLUME_MAP = "story/outline/volume_map.md"

REQUIRED_FILES = [
    DIRECTOR_PREMISE, DIRECTOR_STATE, DIRECTOR_QUEUE,
    DIRECTOR_LAST_AUDIT, DIRECTOR_AUDIT_LOG,
    TRUTH_CURRENT_STATE, TRUTH_RESOURCE_LEDGER,
    TRUTH_PARTICLE_LEDGER, TRUTH_PENDING_HOOKS,
]

READY_STATUSES = {"pass", "ready", "待写", "通过", "可写", "queued", "done", "written"}
BLOCKED_STATUSES = {"fail", "blocked", "stop", "未通过", "阻塞", "修复"}

# ── File I/O ───────────────────────────────────────────────────

def read_text(path: str | Path) -> str:
    """Read a file with utf-8-sig encoding, ignoring errors."""
    p = Path(path) if isinstance(path, str) else path
    return p.read_text(encoding="utf-8-sig", errors="ignore") if p.exists() else ""


def write_text(path: str | Path, content: str):
    """Write content to a file, creating parent directories."""
    p = Path(path) if isinstance(path, str) else path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# ── Markdown table parsing ─────────────────────────────────────

def split_table_cells(row: str) -> list[str]:
    """Split a markdown table row into cells (no leading/trailing pipe)."""
    return [c.strip().replace("<br>", "\n") for c in row.strip().strip("|").split("|")]


def parse_chapter_queue(text_or_path: str | Path) -> list[dict]:
    """Parse chapter_queue.md into a list of chapter dicts.

    Each dict: chapter, title_hint, goal, premise_must_hit, forbidden, status
    """
    text = read_text(text_or_path) if "|" not in str(text_or_path)[:100] else str(text_or_path)
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "Chapter" in s:
            continue
        cells = split_table_cells(s)
        if len(cells) < 6:
            continue
        n_raw = re.sub(r"\D", "", cells[0])
        if not n_raw or not n_raw.isdigit():
            continue
        rows.append({
            "chapter": int(n_raw),
            "title_hint": cells[1],
            "goal": cells[2],
            "premise_must_hit": cells[3],
            "forbidden": cells[4],
            "status": cells[5],
        })
    return rows


def write_chapter_queue(path: str | Path, rows: list[dict]):
    """Write chapter rows back to a markdown table file."""
    header = (
        "| Chapter | 标题提示 | Goal | Premise Must Hit | Forbidden | Status |\n"
        "|---------|----------|------|------------------|-----------|--------|"
    )
    body = "\n".join(
        f"| {r['chapter']:04d} | {r.get('title_hint', '')} | "
        f"{r.get('goal', '')} | {r.get('premise_must_hit', '')} | "
        f"{r.get('forbidden', '')} | {r.get('status', '')} |"
        for r in rows
    )
    write_text(path, f"{header}\n{body}\n")


def parse_volume_map(text_or_path: str | Path | None) -> list[dict]:
    """Parse volume_map.md table into [{volume, start, end, theme}] sorted by volume."""
    if text_or_path is None:
        return []
    text = read_text(text_or_path) if isinstance(text_or_path, (str, Path)) and not str(text_or_path).startswith("|") else str(text_or_path)
    vols = []
    cn_nums = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    in_table = False

    for line in text.splitlines():
        s = line.strip()
        if not in_table:
            if "卷" in s and s.startswith("|"):
                in_table = True
            continue
        if not s.startswith("|") or "---" in s:
            continue
        if "偏离日志" in s or "卷级禁区" in s:
            break
        cells = split_table_cells(s)
        if len(cells) < 3:
            continue
        vol_name = cells[0].strip()
        if not vol_name:
            continue
        m = re.search(r"([\d一二三四五六七八九十]+)", vol_name)
        if not m:
            continue
        vol_num = cn_nums.get(m.group(1))
        if vol_num is None:
            try:
                vol_num = int(m.group(1))
            except ValueError:
                continue
        range_str = cells[1].strip() if len(cells) > 1 else ""
        rm = re.search(r"(\d+)\s*[-–—]\s*(\d+)", range_str)
        if rm:
            start, end = int(rm.group(1)), int(rm.group(2))
        else:
            ch_m = re.search(r"(\d+)\s*章", range_str)
            if ch_m:
                end = int(ch_m.group(1))
                start = (vols[-1]["end"] + 1) if vols else 1
            else:
                continue
        theme = cells[4].strip() if len(cells) > 4 else ""
        vols.append({"volume": vol_num, "start": start, "end": end, "chapters": end - start + 1, "theme": theme})
    return sorted(vols, key=lambda v: v["volume"])


def chapter_to_volume(ch_num: int, volume_ranges: list[dict]) -> int | None:
    """Map a chapter number to its volume using parsed volume_map ranges."""
    for vr in volume_ranges:
        if vr["start"] <= ch_num <= vr["end"]:
            return vr["volume"]
    return None


def parse_hooks(text_or_path: str | Path) -> list[dict]:
    """Parse pending_hooks.md table into [{id, promise, status, ...}]."""
    text = read_text(text_or_path) if isinstance(text_or_path, (str, Path)) else str(text_or_path)
    hooks = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and "---" not in s and "hook_id" not in s.lower() and "Hook ID" not in s:
            cells = split_table_cells(s)
            if len(cells) >= 5:
                hooks.append({
                    "id": cells[0],
                    "promise": cells[2] if len(cells) > 2 else "",
                    "priority": cells[3] if len(cells) > 3 else "",
                    "status": cells[-1] if cells[-1] else "",
                })
    return hooks


# ── JSON5 parsing ──────────────────────────────────────────────

def strip_json5(text: str) -> str:
    """Minimal JSON5 → JSON converter."""
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"([,{]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def parse_json5(text: str) -> dict:
    """Parse a JSON5 string, returning {} on failure."""
    try:
        return json.loads(strip_json5(text))
    except (json.JSONDecodeError, ValueError):
        return {}


def load_json5_file(path: str | Path) -> dict:
    """Read and parse a JSON5 file."""
    return parse_json5(read_text(path))


def load_director_state(book_dir: str | Path) -> dict:
    """Load director_state.json5, with regex fallback for broken files."""
    book = Path(book_dir)
    path = book / DIRECTOR_STATE
    text = read_text(path)
    data = parse_json5(text)
    if data:
        return data

    # Fallback: regex extraction
    data = {}
    for key in ["bookId", "title", "status", "executor", "canWrite", "activeVolume", "currentChapter", "updatedAt"]:
        m = re.search(rf"\b{key}\s*:\s*([^,\n}}]+)", text)
        if m:
            raw = m.group(1).strip().strip('"\'')
            if raw in {"true", "false"}:
                data[key] = raw == "true"
            elif raw.isdigit():
                data[key] = int(raw)
            else:
                data[key] = raw
    bm = re.search(r"\bblockers\s*:\s*(\[[^\]]*\])", text, re.S)
    if bm:
        import ast
        try:
            data["blockers"] = ast.literal_eval(bm.group(1).replace("'", '"'))
        except (ValueError, SyntaxError):
            data["blockers"] = [bm.group(1)]
    return data


# ── Premise parsing ────────────────────────────────────────────

def extract_premise_promise(text: str) -> str:
    """Extract the core promise text from premise.md."""
    m = re.search(r"##\s*书名承诺\s*\n+(.*?)(?:##|\Z)", text, re.S)
    if m:
        return m.group(1).strip()
    m = re.search(r"书名承诺\s*\n+(.*?)(?:\n##|\n#|\Z)", text, re.S)
    return m.group(1).strip() if m else ""


def extract_forbidden_zones(text: str) -> list[dict]:
    """Extract forbidden zone entries from premise.md."""
    zones = []
    in_section = False
    for line in text.splitlines():
        s = line.strip()
        if "禁飞区" in s and ("##" in s or s.startswith("##")):
            in_section = True
            continue
        if in_section and s.startswith("##"):
            break
        if in_section and s.startswith("-"):
            m = re.match(r"-\s*禁飞区\s*(\d+)\s*[：:]\s*(.+)", s)
            if m:
                zones.append({"id": int(m.group(1)), "content": m.group(2)})
            else:
                zones.append({"id": len(zones) + 1, "content": re.sub(r"^-\s*", "", s)})
    return zones


def extract_role_locks(text: str) -> list[dict]:
    """Extract role function locks from premise.md table."""
    locks = []
    in_table = False
    for line in text.splitlines():
        s = line.strip()
        if "角色功能锁" in s:
            in_table = True
            continue
        if not in_table:
            continue
        if s.startswith("##") or "偏离日志" in s or "卷级" in s:
            break
        if not s.startswith("|") or "---" in s or "角色/势力" in s:
            continue
        cells = split_table_cells(s)
        if len(cells) >= 4 and cells[0]:
            locks.append({
                "role": cells[0],
                "function": cells[1] if len(cells) > 1 else "",
                "allow": cells[2] if len(cells) > 2 else "",
                "forbid": cells[3] if len(cells) > 3 else "",
            })
    return locks


def extract_volume_zones(text: str) -> list[dict]:
    """Extract volume-level forbidden zones from premise.md."""
    zones = []
    in_table = False
    for line in text.splitlines():
        s = line.strip()
        if "卷级禁区" in s:
            in_table = True
            continue
        if not in_table:
            continue
        if s.startswith("##") or "偏离日志" in s:
            break
        if not s.startswith("|") or "---" in s:
            continue
        if "禁止" in s or "原因" in s:
            continue
        cells = split_table_cells(s)
        if len(cells) >= 3 and cells[0]:
            try:
                vol = int(re.sub(r"\D", "", cells[0]))
                zones.append({
                    "volume": vol,
                    "forbidden": cells[1] if len(cells) > 1 else "",
                    "reason": cells[2] if len(cells) > 2 else "",
                    "alternative": cells[3] if len(cells) > 3 else "",
                })
            except ValueError:
                pass
    return zones


# ── Word / character counting ──────────────────────────────────

def strip_markdown(text: str) -> str:
    """Remove markdown formatting, keeping only body text."""
    text = re.sub(r"^#{1,6}\s+.+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", "", text)
    return text


def count_body_chars(book_dir: str | Path) -> int:
    """Count body text characters (no markdown) across all chapters."""
    book = Path(book_dir)
    total = 0
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                total += len(strip_markdown(read_text(f)))
    return total


def count_chapter_words(book_dir: str | Path) -> dict[int, int]:
    """Return {chapter_num: char_count} for all chapter files."""
    book = Path(book_dir)
    counts = {}
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                m = re.match(r"第0*(\d+)章", f.name)
                if m:
                    counts[int(m.group(1))] = len(strip_markdown(read_text(f)))
    return counts


# ── Text utilities ─────────────────────────────────────────────

def listify(text: str) -> list[str]:
    """Split text by any common delimiter into a list of non-empty items."""
    text = (text or "").strip()
    if not text:
        return []
    return [p.strip(" -") for p in re.split(r"[；;、，,\n]+", text) if p.strip(" -")]


def excerpt_file(path: str | Path, max_chars: int = 900) -> str:
    """Read a file, truncating to max_chars with a marker."""
    if not Path(path).exists():
        return ""
    text = read_text(path).strip()
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "\n...<truncated>"


def slugify(s: str) -> str:
    """Create a filesystem-safe slug from a title string."""
    s = re.sub(r"\s+", "-", s.strip().lower())
    s = re.sub(r"[^\w\-一-鿿]", "", s)
    return s or "book"


def latest_chapter(book_dir: str | Path) -> int:
    """Find the highest chapter number from chapter files."""
    book = Path(book_dir)
    best = 0
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book / ch_dir_name
        if ch_dir.exists():
            for f in ch_dir.glob("*.*"):
                m = re.match(r"^.*?0*(\d+)章", f.name) or re.match(r"^(\d{4})_", f.name)
                if m:
                    best = max(best, int(m.group(1)))
    return best


def status_ok(status: str) -> bool:
    """Check if a chapter status is ready for writing."""
    s = status.strip().lower()
    return any(x in s for x in READY_STATUSES) and not any(x in s for x in BLOCKED_STATUSES)


def now_iso() -> str:
    """Return current time as ISO string."""
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def find_volume_map(book_dir: str | Path) -> Path | None:
    """Find volume_map.md at any known location in the book directory."""
    book = Path(book_dir)
    candidates = [book / DIRECTOR_VOLUME_MAP, book / STORY_VOLUME_MAP]
    return next((p for p in candidates if p.exists()), None)


def resolve_project(title: str | None = None, book_id: str | None = None) -> dict:
    """Build minimal project metadata."""
    return {
        "title": title or "未命名",
        "book_id": book_id or slugify(title or "book"),
        "updated_at": now_iso(),
    }
