#!/usr/bin/env python3
"""Import scan results into concept_gate for validation.

Usage:
  python concept_gate_import.py --from scan_result.json
  python concept_gate_import.py --from scan_result.json --run

Accepts JSON from story-short-scan / story-long-scan outputs and converts
to concept_gate.py --inline YAML format.  With --run, passes the inline
string directly to concept_gate.py for scoring.

Input JSON can use either flat keys or nested structures:
  {"书名":"xxx", "梗概":"xxx", "金手指":"xxx", "世界观":"xxx", ...}
  {"title":"xxx", "summary":"xxx", "golden_finger":"xxx", ...}
  [{"书名":"xxx", ...}, ...]   (batch — first PASS used, or all printed)
"""

from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
from typing import Any

# Canonical concept_gate fields
REQUIRED_FIELDS = ["梗概", "金手指", "世界观"]

# Mapping from English / alternative keys to canonical Chinese keys
KEY_MAP = {
    "title": "书名",
    "name": "书名",
    "book_title": "书名",
    "book_name": "书名",
    "summary": "梗概",
    "premise": "梗概",
    "synopsis": "梗概",
    "blurb": "梗概",
    "description": "梗概",
    "golden_finger": "金手指",
    "cheat": "金手指",
    "ability": "金手指",
    "power": "金手指",
    "protagonist_ability": "金手指",
    "world": "世界观",
    "world_setting": "世界观",
    "world_building": "世界观",
    "setting": "世界观",
    "platform": "平台",
    "target_platform": "平台",
    "competitor": "对标",
    "benchmark": "对标",
    "reference": "对标",
    "references": "对标",
    "word_count": "字数",
    "target_words": "字数",
    "total_words": "字数",
}


def normalize_concept(raw: dict) -> dict:
    """Convert raw JSON dict into canonical concept_gate field names."""
    concept: dict[str, Any] = {}
    # Direct Chinese keys first
    for key in ["书名", "梗概", "金手指", "世界观", "平台", "对标", "字数"]:
        if key in raw and raw[key]:
            concept[key] = raw[key]
    # English / alt keys as fallback
    for src, dst in KEY_MAP.items():
        if dst not in concept and src in raw and raw[src]:
            concept[dst] = raw[src]
    # Attempt nested extraction from common scan-output shapes
    for nested_key in ("concept", "book", "novel", "item", "data", "result"):
        if nested_key in raw and isinstance(raw[nested_key], dict):
            inner = raw[nested_key]
            for key in ["书名", "梗概", "金手指", "世界观", "平台", "对标", "字数"]:
                if key not in concept and key in inner and inner[key]:
                    concept[key] = inner[key]
    return concept


def concept_to_inline_yaml(concept: dict) -> str:
    """Render a concept dict as YAML inline string for concept_gate.py --inline."""
    parts = []
    for key in ["书名", "梗概", "金手指", "世界观", "平台", "对标", "字数"]:
        if key in concept:
            val = concept[key]
            # Escape newlines and special YAML chars minimally
            if isinstance(val, str) and ("\n" in val or ":" in val[1:]):
                val = val.replace('"', '\\"')
                parts.append(f'{key}: "{val}"')
            else:
                parts.append(f"{key}: {val}")
    return "\n".join(parts)


def load_json(path: str) -> Any:
    """Load JSON file, handling UTF-8 with or without BOM."""
    text = Path(path).read_text(encoding="utf-8-sig")
    return json.loads(text)


def find_concept_gate_script() -> Path:
    """Locate concept_gate.py relative to this script or in same directory."""
    here = Path(__file__).resolve().parent
    gate = here / "concept_gate.py"
    if gate.exists():
        return gate
    return here / "concept_gate.py"  # let subprocess fail with clear message


def run_concept_gate(inline: str, gate_path: Path) -> int:
    """Execute concept_gate.py --inline and stream output."""
    cmd = [sys.executable, str(gate_path), "--inline", inline]
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def print_inline_preview(concept: dict, inline: str):
    """Print a human-friendly preview of what will be sent to concept_gate."""
    print("=" * 60)
    print("concept_gate_import — 直通预览")
    print("=" * 60)
    for key in ["书名", "梗概", "金手指", "世界观", "平台", "对标", "字数"]:
        if key in concept:
            val = concept[key]
            if isinstance(val, str) and len(val) > 80:
                val = val[:77] + "..."
            print(f"  {key}: {val}")
    print("-" * 60)
    print("  → concept_gate --inline 参数：")
    print(f"  {inline}")
    print("=" * 60)


def main() -> int:
    # Ensure UTF-8 output on Windows
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description="Import scan JSON → concept_gate validation")
    ap.add_argument("--from", dest="from_file", required=True,
                    help="JSON file from story-short-scan / story-long-scan")
    ap.add_argument("--run", action="store_true",
                    help="Directly invoke concept_gate.py after import")
    args = ap.parse_args()

    data = load_json(args.from_file)

    # Normalise to list of concept dicts
    items: list[dict] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Single book dict (possibly nested under a "books"/"results" key)
        if any(k in data for k in ("书名", "梗概", "title", "summary")):
            items = [data]
        else:
            for candidate_key in ("books", "results", "items", "novels", "entries"):
                if candidate_key in data and isinstance(data[candidate_key], list):
                    items = data[candidate_key]
                    break
            if not items:
                items = [data]

    if not items:
        print("错误：JSON 未包含可解析的书本条目", file=sys.stderr)
        return 1

    concepts = [normalize_concept(item) for item in items]
    valid = [c for c in concepts if all(c.get(f) for f in REQUIRED_FIELDS)]

    if not valid:
        print("错误：所有条目都缺少必填字段（梗概/金手指/世界观）", file=sys.stderr)
        print("可解析的条目：")
        for i, c in enumerate(concepts):
            missing = [f for f in REQUIRED_FIELDS if not c.get(f)]
            title = c.get("书名", f"条目{i+1}")
            print(f"  {i+1}. {title} — 缺少: {', '.join(missing)}")
        return 1

    gate_path = find_concept_gate_script()
    if not gate_path.exists():
        print(f"错误：找不到 concept_gate.py（期望路径: {gate_path}）", file=sys.stderr)
        return 1

    # If --run, run each valid concept through the gate
    if args.run:
        for i, concept in enumerate(valid):
            if len(valid) > 1:
                print(f"\n{'▼' * 30} 条目 {i+1}/{len(valid)} — {concept.get('书名','未命名')} {'▼' * 30}")
            inline = concept_to_inline_yaml(concept)
            rc = run_concept_gate(inline, gate_path)
            if rc != 0:
                print(f"\n⚠ concept_gate 退出码 {rc}", file=sys.stderr)
        return 0
    else:
        # Preview only
        for i, concept in enumerate(valid):
            inline = concept_to_inline_yaml(concept)
            if i > 0:
                print()
            print_inline_preview(concept, inline)
        print()
        print(f"[OK] 共 {len(valid)} 个有效概念。加 --run 直接调用 concept_gate.py 验证。")
        print(f"  手动运行：python concept_gate.py --inline \"{concept_to_inline_yaml(valid[0])}\"")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
