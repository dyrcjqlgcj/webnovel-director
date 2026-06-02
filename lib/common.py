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


_QUEUE_COLUMN_ALIASES = {
    "chapter":    ["ch", "chapter", "章", "章节", "#"],
    "title_hint": ["标题提示", "标题", "title hint", "title_hint", "title", "章名"],
    "goal":       ["goal", "目标", "本章目标", "chapter goal"],
    "premise_must_hit": ["premise must hit", "命题兑现", "premise", "premise_hit", "爽点"],
    "scenes":     ["scenes", "场景", "场景设计"],
    "words":      ["words", "字数", "预估字数", "word count", "target words"],
    "forbidden":  ["forbidden", "禁飞区", "禁止", "禁止项"],
    "status":     ["status", "状态", "审查状态"],
}


def _detect_queue_columns(header_cells: list[str]) -> dict[str, int]:
    """Build a name→index map from a header row of chapter_queue columns.

    Falls back to 6-column default if no recognizable header is found.
    """
    col_map: dict[str, int] = {}
    for i, cell in enumerate(header_cells):
        name = cell.strip().lower()
        for key, aliases in _QUEUE_COLUMN_ALIASES.items():
            if name in aliases:
                col_map[key] = i
                break
    if not col_map or "chapter" not in col_map:
        # Fallback: 6-column format
        return {"chapter": 0, "title_hint": 1, "goal": 2,
                "premise_must_hit": 3, "forbidden": 4, "status": 5,
                "scenes": -1, "words": -1}
    col_map.setdefault("title_hint", -1)
    col_map.setdefault("goal", -1)
    col_map.setdefault("premise_must_hit", -1)
    col_map.setdefault("scenes", -1)
    col_map.setdefault("words", -1)
    col_map.setdefault("forbidden", -1)
    col_map.setdefault("status", -1)
    return col_map


def _safe_cell(cells: list[str], col_map: dict[str, int], key: str) -> str:
    """Get a cell value by column name, returning '' if the column is missing."""
    idx = col_map.get(key, -1)
    if idx < 0 or idx >= len(cells):
        return ""
    return cells[idx]


def parse_chapter_queue(text_or_path: str | Path) -> list[dict]:
    """Parse chapter_queue.md into a list of chapter dicts.

    Uses header-aware column detection to support both 6-column and
    8-column formats.  Each dict contains: chapter, title_hint, goal,
    premise_must_hit, forbidden, status, plus optionally scenes and words.
    """
    text = read_text(text_or_path) if "|" not in str(text_or_path)[:100] else str(text_or_path)
    lines = text.splitlines()

    # Detect columns from the header row (row before the separator line)
    col_map = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("|") and not "---" in s:
            cells = split_table_cells(s)
            # Check if next line is a separator
            if i + 1 < len(lines) and "---" in lines[i + 1]:
                col_map = _detect_queue_columns(cells)
                break

    if col_map is None:
        col_map = _detect_queue_columns([])  # use default

    rows = []
    for line in lines:
        s = line.strip()
        if not s.startswith("|") or "---" in s:
            continue
        cells = split_table_cells(s)
        n_raw = re.sub(r"\D", "", _safe_cell(cells, col_map, "chapter"))
        if not n_raw or not n_raw.isdigit():
            continue
        row = {
            "chapter": int(n_raw),
            "title_hint": _safe_cell(cells, col_map, "title_hint"),
            "goal": _safe_cell(cells, col_map, "goal"),
            "premise_must_hit": _safe_cell(cells, col_map, "premise_must_hit"),
            "forbidden": _safe_cell(cells, col_map, "forbidden"),
            "status": _safe_cell(cells, col_map, "status"),
        }
        if col_map.get("scenes", -1) >= 0:
            row["scenes"] = _safe_cell(cells, col_map, "scenes")
        if col_map.get("words", -1) >= 0:
            row["words_target"] = _safe_cell(cells, col_map, "words")
        rows.append(row)
    return rows


def write_chapter_queue(path: str | Path, rows: list[dict]):
    """Write chapter rows back to a markdown table file (8-column format)."""
    header = (
        "| Ch | 标题提示 | Goal | Premise Must Hit | Scenes | Words | Forbidden | Status |\n"
        "|---:|----------|------|------------------|--------|-------|-----------|--------|"
    )
    body = "\n".join(
        f"| {r['chapter']:04d} | {r.get('title_hint', '')} | "
        f"{r.get('goal', '')} | {r.get('premise_must_hit', '')} | "
        f"{r.get('scenes', '')} | {r.get('words_target', '')} | "
        f"{r.get('forbidden', '')} | {r.get('status', '')} |"
        for r in rows
    )
    write_text(path, f"{header}\n{body}\n")


def parse_volume_map(text_or_path: str | Path | None,
                     include_events: bool = False) -> list[dict]:
    """Parse volume_map.md table into [{volume, start, end, theme}] sorted by volume.

    If include_events is True, each volume dict also contains a 'core_events' key
    with structured event blocks parsed from the volume detail sections."""
    text = (read_text(text_or_path) if isinstance(text_or_path, (str, Path))
            and not str(text_or_path).startswith("|") else str(text_or_path or ""))
    if not text:
        return []
    vols = []
    cn_nums = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    in_table = False
    vol_nums_seen = []

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
        vol_nums_seen.append(vol_num)
        vols.append({"volume": vol_num, "start": start, "end": end,
                     "chapters": end - start + 1, "theme": theme})

    if include_events and vols:
        for i, vol in enumerate(vols):
            # Find the detail section for this volume and extract events
            section_text = _find_volume_section(text, vol["volume"])
            if section_text:
                vol["core_events"] = parse_volume_core_events(section_text, vol["volume"])
            else:
                vol["core_events"] = []

    return sorted(vols, key=lambda v: v["volume"])


def _find_volume_section(text: str, volume_num: int) -> str:
    """Extract the detail section for a specific volume from volume_map.md.

    Looks for patterns like '## 第一卷详情' or '## 第1卷' after the main table."""
    cn_labels = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七"}
    cn_label = cn_labels.get(volume_num, str(volume_num))
    # Try multiple heading patterns
    patterns = [
        rf"##\s*第[一二三四五六七\d]+\s*卷[：:\s]",
        rf"###\s*第[一二三四五六七\d]+\s*卷",
        rf"\*\*第[一二三四五六七\d]+\s*卷[：:]",
    ]
    for pattern in patterns:
        # Find all volume section starts
        starts = list(re.finditer(pattern, text))
        for i, m in enumerate(starts):
            sec_start = m.start()
            sec_end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
            section_text = text[sec_start:sec_end]
            # Check if this section mentions our volume
            if (f"第{volume_num}" in section_text[:40] or
                f"第{cn_label}" in section_text[:40] or
                (volume_num == 1 and "第一卷" in section_text[:40])):
                return section_text
    # Fallback: return empty
    return ""


def parse_volume_core_events(section_text: str, volume_num: int) -> list[dict]:
    """Extract structured core event blocks from a volume detail section.

    Handles patterns like:
      **Ch1-10：降生与觉醒** ✅
      - Ch1：全员穿越，主角降临C级格
      - Ch2：第一次侦察——发现邻格隐藏矿脉

    Returns [{range_start, range_end, label, events: [{ch, desc}], status}]
    """
    events = []
    current_block = None

    for line in section_text.splitlines():
        s = line.strip()
        # Match event block header:
        # Format 1: **Ch1-10：label** ✅  or **1-10章：label**
        # Format 2: **1-10章：label**
        m = re.match(r"\*\*(?:Ch\.?)?\s*(\d+)\s*[-–—]\s*(\d+)\s*(?:章)?[：:]\s*(.+?)\*\*(.*)", s)
        if not m:
            # Also match without trailing **: **1-10章：label**
            m = re.match(r"\*\*(\d+)\s*[-–—]\s*(\d+)\s*章[：:]\s*(.+?)\*\*$", s)
        if m:
            if current_block:
                events.append(current_block)
            range_start = int(m.group(1))
            range_end = int(m.group(2))
            label = m.group(3).strip()
            trailer = m.group(4).strip() if m.lastindex and m.lastindex >= 4 else ""
            status = "planned"
            if "✅" in trailer:
                status = "done"
            elif "⏳" in trailer:
                status = "in_progress"
            current_block = {
                "range_start": range_start, "range_end": range_end,
                "label": label, "status": status,
                "events": [],
            }
            continue
        # Match event bullet:
        # Format 1: - Ch1：description
        # Format 2: - 第1章：description
        # Format 3: - 1-5章：description (range description)
        m_ch = re.match(r"[-•]\s*(?:Ch\.?\s*)?(\d+)[：:]\s*(.+)", s)
        m_di = re.match(r"[-•]\s*第\s*(\d+)\s*章[：:]\s*(.+)", s)
        if (m_ch or m_di) and current_block:
            m2 = m_ch or m_di
            ch = int(m2.group(1))
            desc = m2.group(2).strip()
            current_block["events"].append({"ch": ch, "desc": desc})
            continue
        # Match range bullet: - 1-5章：description or - 1-5：description
        m_range = re.match(r"[-•]\s*(\d+)\s*[-–—]\s*(\d+)\s*(?:章)?[：:]\s*(.+)", s)
        if m_range and current_block:
            ch_start = int(m_range.group(1))
            desc = m_range.group(3).strip()
            current_block["events"].append({"ch": ch_start, "desc": desc})
            continue

    if current_block:
        events.append(current_block)

    # If no structured events found, try the "**核心事件**：" bullet-list format
    # (used by volumes 2-7): "- 61-75章：魔晶矿脉发现——描述"
    if not events:
        in_core_events = False
        for line in section_text.splitlines():
            s = line.strip()
            if "核心事件" in s and s.startswith("**"):
                in_core_events = True
                continue
            if in_core_events:
                m = re.match(r"[-•]\s*(\d+)\s*[-–—]\s*(\d+)\s*章[：:]\s*(.+)", s)
                if m:
                    label = m.group(3).strip()
                    # Split on —— or ： to get label vs description
                    desc_parts = re.split(r"[——：:]", label, maxsplit=1)
                    events.append({
                        "range_start": int(m.group(1)),
                        "range_end": int(m.group(2)),
                        "label": desc_parts[0].strip(),
                        "status": "planned",
                        "events": [{"ch": 0, "desc": desc_parts[1].strip() if len(desc_parts) > 1 else label}],
                    })
                    continue
                # Check if we've moved past the core events section
                if s.startswith("**") and "核心事件" not in s:
                    in_core_events = False
                elif s.startswith("##") or s.startswith("---"):
                    in_core_events = False

    # If still no events, try numbered chapter bullets as last resort
    # Look for any numbered chapters listed as bullets
    if not events:
        ch_events = []
        for line in section_text.splitlines():
            s = line.strip()
            m = re.match(r"[-•]\s*Ch\.?\s*(\d+)[：:]\s*(.+)", s)
            if m:
                ch_events.append({"ch": int(m.group(1)), "desc": m.group(2).strip()})
        if ch_events:
            events.append({
                "range_start": ch_events[0]["ch"],
                "range_end": ch_events[-1]["ch"],
                "label": f"第{volume_num}卷核心事件",
                "status": "planned",
                "events": ch_events,
            })

    return events


def rebuild_volume_events_section(events: list[dict], volume_num: int) -> str:
    """Rebuild ONLY the core events block within a volume section in volume_map.md format.

    Used to replace just the events portion without touching the rest of the section."""
    status_icons = {"done": "✅", "in_progress": "⏳", "planned": "○"}
    lines = []
    for ev in events:
        icon = status_icons.get(ev.get("status", "planned"), "○")
        label = ev.get("label", "")
        lines.append(f"**Ch{ev['range_start']}-{ev['range_end']}：{label}** {icon}")
        for e in ev.get("events", []):
            if e.get("ch", 0) > 0:
                lines.append(f"- Ch{e['ch']}：{e['desc']}")
            else:
                lines.append(f"- {e['desc']}")
        lines.append("")
    return "\n".join(lines)


def replace_events_in_section(section_text: str, events: list[dict], volume_num: int) -> str:
    """Replace core events within a volume section, preserving all other content.

    Handles both Volume 1 format (**ChX-Y：label** blocks) and
    Volumes 2-7 format (**核心事件**： bullet list)."""
    new_events_block = rebuild_volume_events_section(events, volume_num)

    # Find the region covering all event blocks: from the first **X-Y章：label**
    # to after the last event bullet, handling blank lines between blocks
    first_ev = re.search(r"\*\*(?:Ch\.?\s*)?\d+\s*[-–—]\s*\d+(?:章)?[：:]", section_text)
    if first_ev:
        # Find the end: last bullet line that belongs to any event block
        # Search for pattern: **X-Y章：label** or - bullet line, then find the last one
        ev_lines = list(re.finditer(
            r"\*\*(?:Ch\.?\s*)?\d+\s*[-–—]\s*\d+(?:章)?[：:].+?\*\*|^[-•]\s*(?:第\s*\d+\s*章|\d+(?:[-–—]\d+)?(?:章)?)[：:]",
            section_text, re.MULTILINE))
        if ev_lines:
            start = first_ev.start()
            end = ev_lines[-1].end()
            # Extend end to include any trailing newline
            while end < len(section_text) and section_text[end] in '\n\r':
                end += 1
            return section_text[:start] + new_events_block.strip() + "\n\n" + section_text[end:].lstrip()

    # Try Volumes 2-7 format: find **核心事件**： section
    core_ev_pattern = re.compile(r"\*\*核心事件\*\*[：:][^\n]*\n((?:[-•][^\n]*\n?)*)", re.MULTILINE)
    m = core_ev_pattern.search(section_text)
    if m:
        return section_text[:m.start()] + new_events_block.strip() + "\n\n" + section_text[m.end():].lstrip()

    # Fallback: append to end of section
    return section_text.rstrip() + "\n\n" + new_events_block.strip() + "\n"


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
    for ch_dir_name in ("正文", "chapters", "story/chapters"):
        ch_dir = book / ch_dir_name
        if ch_dir.exists():
            for f in sorted(ch_dir.glob("*.md")):
                total += len(strip_markdown(read_text(f)))
    return total


def count_chapter_words(book_dir: str | Path) -> dict[int, int]:
    """Return {chapter_num: char_count} for all chapter files."""
    book = Path(book_dir)
    counts = {}
    for ch_dir_name in ("正文", "chapters", "story/chapters"):
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
    for ch_dir_name in ("正文", "chapters", "story/chapters"):
        ch_dir = book / ch_dir_name
        if ch_dir.exists():
            for f in ch_dir.glob("*.md"):
                m = re.match(r"第0*(\d+)章", f.name)
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
