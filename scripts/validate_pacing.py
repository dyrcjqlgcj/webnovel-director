#!/usr/bin/env python3
"""Validate chapter_queue pacing against volume_map.

Usage:
  python validate_pacing.py <book_dir> [--json]

Checks:
  1. Each boss layer's first-clear chapter in queue vs volume range
  2. Protagonist first-clear timing (too early = pace violation)
  3. Chapter count per volume vs queue coverage
"""

from __future__ import annotations
from pathlib import Path
import argparse, json, re, sys


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="ignore") if p.exists() else ""


def parse_volumes(text: str) -> list[dict]:
    vols = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if not re.match(r"^[一二三四五六七八九十\d]+$", cells[0]):
            continue
        rm = re.search(r"(\d+)\s*[-–—]\s*(\d+)", cells[1])
        if not rm:
            continue
        start, end = int(rm.group(1)), int(rm.group(2))
        # Extract boss layers from cells[2]
        boss_layers = []
        boss_col = cells[2] if len(cells) > 2 else ""
        for n in re.findall(r"(\d+)", boss_col):
            boss_layers.append(int(n))
        vols.append({
            "label": cells[0], "start": start, "end": end,
            "boss_layers": boss_layers,
            "theme": cells[4].strip() if len(cells) > 4 else "",
        })
    return vols


def parse_first_clears(text: str) -> list[dict]:
    """Parse the 首通归属 table from volume_map."""
    clears = []
    in_table = False
    for line in text.splitlines():
        s = line.strip()
        if "首通归属" in s or "首通者" in s:
            in_table = True
            continue
        if not in_table or not s.startswith("|") or "---" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue
        layer_match = re.search(r"第\s*(\d+)\s*层", cells[0])
        if not layer_match:
            continue
        layer = int(layer_match.group(1))
        first_clear = cells[1].strip() if len(cells) > 1 else ""
        # Determine if protagonist (沈拓) or Feng Zheng (冯铮)
        is_protagonist = "沈拓" in first_clear
        is_fengzheng = "冯铮" in first_clear
        clears.append({
            "layer": layer,
            "first_clear": first_clear,
            "is_protagonist": is_protagonist,
            "is_fengzheng": is_fengzheng,
        })
    return clears


def parse_chapter_queue(path: Path) -> list[dict]:
    rows = []
    for line in read(path).splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "Chapter" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 6:
            continue
        n = re.sub(r"\D", "", cells[0])
        if not n.isdigit():
            continue
        rows.append({
            "chapter": int(n),
            "title": cells[1],
            "goal": cells[2],
            "premise_hit": cells[3],
            "forbidden": cells[4],
        })
    return rows


def parse_progress_targets(text: str) -> list[dict]:
    """Parse 进度目标 table from volume_map.md."""
    targets = []
    in_table = False
    for line in text.splitlines():
        s = line.strip()
        if "进度目标" in s:
            in_table = True
            continue
        if not in_table or not s.startswith("|") or "---" in s:
            if in_table and not s.startswith("|"):
                in_table = False
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue
        layer_match = re.search(r"第\s*(\d+)\s*层", cells[0])
        if not layer_match and "逃亡" not in cells[0]:
            continue
        layer = int(layer_match.group(1)) if layer_match else 99
        ch_match = re.search(r"Ch\s*(\d+)", cells[1])
        if not ch_match:
            continue
        targets.append({
            "layer": layer,
            "chapter": int(ch_match.group(1)),
            "event": cells[2].strip() if len(cells) > 2 else "",
        })
    return targets


def find_protagonist_clears_in_queue(chapters: list[dict]) -> list[dict]:
    """Find chapters where protagonist GETS a first clear (not just observes one)."""
    clears = []
    for ch in chapters:
        combined = f"{ch['title']} {ch['goal']}"
        # Must have both 首通 AND explicit protagonist signal
        if "首通" not in combined:
            continue
        # Exclude Blood Flag / Feng Zheng first clears
        if "冯铮" in combined and "首通" in combined:
            if "沈拓" not in combined and "主角" not in combined:
                continue  # Blood Flag's clear, not protagonist's
        # Must explicitly say protagonist got it (not just weekly/replay)
        if "不是首通" in combined or "周首通保底" in combined:
            continue  # Weekly clear, not first clear
        protag_signal = ("沈拓首通" in combined or "主角首通" in combined or
                        "沈拓拿下" in combined or "沈拓.*首通" in combined or
                        "沈拓的第一个" in combined or "史上首通.*沈拓" in combined or
                        "沈拓.*史上首通" in combined)
        protag_signal_re = re.search(r"沈拓.{0,5}(首通|拿下)", combined) or re.search(r"(首通|拿下).{0,5}沈拓", combined)
        if not protag_signal and not protag_signal_re:
            continue
        layer_match = re.search(r"第\s*(\d+)\s*层", combined)
        if layer_match:
            clears.append({"chapter": ch["chapter"], "layer": int(layer_match.group(1))})
    return clears


def find_boss_layer_chapters(chapters: list[dict], layer: int) -> list[int]:
    """Find chapters that mention a specific boss layer."""
    chs = []
    for ch in chapters:
        combined = f"{ch['title']} {ch['goal']}"
        if f"第{layer}层" in combined or f"第 {layer} 层" in combined:
            chs.append(ch["chapter"])
    return chs


def validate(book_dir: str) -> dict:
    book = Path(book_dir)

    # Find volume_map
    vm_paths = [book / "director" / "volume_map.md",
                book / "story" / "outline" / "volume_map.md"]
    vm_path = next((p for p in vm_paths if p.exists()), None)
    cq_path = book / "director" / "chapter_queue.md"

    if not vm_path:
        return {"status": "FAIL", "issues": [{"severity": "FAIL", "type": "pacing",
                "issue": "volume_map.md 不存在"}]}
    if not cq_path.exists():
        return {"status": "FAIL", "issues": [{"severity": "FAIL", "type": "pacing",
                "issue": "chapter_queue.md 不存在"}]}

    vm_text = read(vm_path)
    volumes = parse_volumes(vm_text)
    first_clears = parse_first_clears(vm_text)
    chapters = parse_chapter_queue(cq_path)
    queue_chs = len(chapters)
    queue_max_layer = 0
    for ch in chapters:
        combined = f"{ch['title']} {ch['goal']}"
        for layer in re.findall(r"通过第\s*(\d+)\s*层|到达第\s*(\d+)\s*层|拿下第\s*(\d+)\s*层|第\s*(\d+)\s*层.*首通|速通第\s*(\d+)\s*层|过第\s*(\d+)\s*层", combined):
            for g in layer:
                if g:
                    queue_max_layer = max(queue_max_layer, int(g))

    issues = []

    # ── Check 1: Protagonist first-clear timing ──
    if first_clears:
        protag_clears = [c for c in first_clears if c["is_protagonist"]]
        if protag_clears:
            first_protag_clear = protag_clears[0]
            first_protag_layer = first_protag_clear["layer"]

            # Find which volume this layer belongs to
            for vol in volumes:
                if first_protag_layer in vol["boss_layers"]:
                    min_chapter = vol["start"]
                    max_chapter = vol["end"]
                    break
            else:
                # Fallback: find by proximity
                min_chapter = 999
                for vol in volumes:
                    if vol["boss_layers"] and min(vol["boss_layers"]) <= first_protag_layer <= max(vol["boss_layers"]):
                        min_chapter = vol["start"]
                        break

            # Check if any chapter in queue claims a protagonist first clear too early
            queue_clears = find_protagonist_clears_in_queue(chapters)
            for qc in queue_clears:
                if qc["chapter"] < min_chapter:
                    issues.append({"severity": "FAIL", "type": "pacing_too_fast",
                        "issue": f"细纲 Ch{qc['chapter']} 中主角在第{qc['layer']}层首通，"
                                 f"但卷纲设定主角首通从第{first_protag_layer}层开始（卷{vol['label']}，Ch{min_chapter}起）。"
                                 f"细纲进度过快——主角在 Ch{qc['chapter']} 不应该拿到首通"})

    # ── Check 2: Boss layer chapter coverage ──
    for vol in volumes:
        for layer in vol.get("boss_layers", []):
            layer_chs = find_boss_layer_chapters(chapters, layer)
            if not layer_chs:
                continue
            for ch_num in layer_chs:
                if ch_num < vol["start"]:
                    issues.append({"severity": "WARN", "type": "pacing_fast",
                        "issue": f"第{layer}层在细纲 Ch{ch_num} 出现，"
                                 f"但卷纲设该层在第{vol['label']}卷（Ch{vol['start']}-{vol['end']}）——可能过快"})
                elif ch_num > vol["end"]:
                    issues.append({"severity": "WARN", "type": "pacing_slow",
                        "issue": f"第{layer}层在细纲 Ch{ch_num} 出现，"
                                 f"但卷纲设该层在第{vol['label']}卷（Ch{vol['start']}-{vol['end']}）——可能过慢"})

    # ── Check 3: Progress targets (hard check from volume_map) ──
    targets = parse_progress_targets(vm_text)
    if targets:
        for t in targets:
            layer_chs = find_boss_layer_chapters(chapters, t["layer"])
            if not layer_chs:
                continue
            earliest_ch = min(layer_chs)
            latest_ch = max(layer_chs)
            # Check if the layer appears before its target chapter
            if earliest_ch < t["chapter"] - 5:  # Allow 5-chapter margin
                issues.append({"severity": "FAIL", "type": "pacing_too_fast",
                    "issue": f"第{t['layer']}层在细纲 Ch{earliest_ch} 出现，"
                             f"但进度目标设为 Ch{t['chapter']}——进度过快"})
            elif latest_ch > t["chapter"] + 10:  # Allow 10-chapter margin for later
                issues.append({"severity": "WARN", "type": "pacing_slow",
                    "issue": f"第{t['layer']}层在细纲 Ch{latest_ch} 才出现，"
                             f"但进度目标设为 Ch{t['chapter']}——进度可能偏慢"})

    status = "FAIL" if any(i["severity"] == "FAIL" for i in issues) else (
        "WARN" if issues else "PASS")

    return {
        "status": status,
        "volumes": len(volumes),
        "queue_chapters": queue_chs,
        "total_vol_chapters": sum(v["end"] - v["start"] + 1 for v in volumes),
        "queue_max_layer": queue_max_layer,
        "first_clears": first_clears,
        "progress_targets": targets,
        "protagonist_clears_in_queue": find_protagonist_clears_in_queue(chapters),
        "issues": issues,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = validate(args.book_dir)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"=== 进度验证报告 ===")
        print(f"卷数: {result['volumes']}，细纲章数: {result['queue_chapters']}")
        print(f"细纲最大层数: {result['queue_max_layer']}")
        print(f"结论: {result['status']}")
        if result["first_clears"]:
            parts = []
            for c in result["first_clears"][:6]:
                parts.append("第{}层->{}".format(c["layer"], c["first_clear"]))
            print("首通归属: " + ", ".join(parts))
        if result["protagonist_clears_in_queue"]:
            parts = []
            for c in result["protagonist_clears_in_queue"]:
                parts.append("Ch{}({}层)".format(c["chapter"], c["layer"]))
            print("细纲中主角首通: " + ", ".join(parts))
        if not result["issues"]:
            print("[PASS] 细纲进度与卷纲一致")
        for i in result["issues"]:
            icon = "[FAIL]" if i["severity"] == "FAIL" else "[WARN]"
            print(f"  {icon} {i['issue']}")

    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
