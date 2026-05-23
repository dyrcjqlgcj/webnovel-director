#!/usr/bin/env python3
"""Outline causal-logic validator for webnovel-director.

Checks beyond the 6-dimension outline-gate review:
  1. Causal chain: every event has a cause and a consequence
  2. Satisfaction density: no >5 chapter gaps without payoff
  3. Character arc: each character has start→change→climax→end state
  4. Power curve: no flat zones (no progress) and no jump zones (too fast)

Usage:
  python outline_causal_check.py <book_dir> [--json] [--write-report]
"""

from __future__ import annotations
import argparse, datetime, json, re, sys
from pathlib import Path


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="ignore") if p.exists() else ""


def split_cell(row: str) -> list[str]:
    return [c.strip().replace("<br>", "\n") for c in row.strip().strip("|").split("|")]


# ── Parse volume map ──

def parse_volume_map(path: Path) -> list[dict]:
    """Parse director/volume_map.md or story/outline/volume_map.md."""
    vols = []
    text = read(path)
    # Match patterns like "第一卷：xxx" or "### 第一卷：xxx"
    vol_pattern = re.compile(r"第([一二三四五六七八九十\d]+)卷[：:]\s*(.+)", re.MULTILINE)
    for m in vol_pattern.finditer(text):
        vol_num = m.group(1)
        vol_name = m.group(2).strip()
        # Try to extract chapter count and word count
        ch_match = re.search(r"(\d+)\s*章", vol_name)
        word_match = re.search(r"(\d+)\s*万字", vol_name)
        vols.append({
            "volume": vol_num,
            "name": vol_name,
            "chapters": int(ch_match.group(1)) if ch_match else 0,
            "words": int(word_match.group(1)) if word_match else 0,
        })
    return vols


def parse_chapter_queue(path: Path) -> list[dict]:
    """Parse chapter_queue.md table."""
    rows = []
    for line in read(path).splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "Chapter" in s:
            continue
        cells = split_cell(s)
        if len(cells) < 6:
            continue
        n_raw = re.sub(r"\D", "", cells[0])
        if not n_raw:
            continue
        rows.append({
            "chapter": int(n_raw),
            "title": cells[1],
            "goal": cells[2],
            "premise_hit": cells[3],
            "forbidden": cells[4],
            "status": cells[5],
        })
    return rows


# ── Causal chain analysis ──

def check_causal_chain(chapters: list[dict]) -> list[dict]:
    """Check that every chapter's goal logically connects to surrounding chapters."""
    issues = []
    action_causes = ["因为", "由于", "上文", "上一章", "之前", "接到", "得知", "发现"]
    action_effects = ["导致", "触发", "引出", "引起", "使得", "从而", "因此", "打开", "开启", "推动"]

    for i, ch in enumerate(chapters):
        goal = ch.get("goal", "")
        # First chapter: check it establishes something
        if i == 0 and goal:
            if not any(kw in goal for kw in ["醒来", "发现", "进入", "收到", "穿越", "重生", "绑定", "激活"]):
                issues.append({"chapter": ch["chapter"], "severity": "WARN",
                    "type": "causal_chain",
                    "issue": "首章goal未包含开局动作词（醒来/发现/进入/穿越...），可能缺乏启动事件"})
        # Middle chapters: check cause and effect
        if i > 0 and goal:
            prev_goal = chapters[i-1].get("goal", "")
            combined = f"{prev_goal}\n{goal}"
            has_cause = any(kw in goal for kw in action_causes)
            has_effect_end = any(kw in goal for kw in action_effects)
            if not has_cause and not has_effect_end:
                # Check if there's any keyword overlap with previous chapter
                prev_keywords = set(re.findall(r"[\u4e00-\u9fff]{3,}", prev_goal))
                curr_keywords = set(re.findall(r"[\u4e00-\u9fff]{3,}", goal))
                overlap = prev_keywords & curr_keywords
                if not overlap:
                    issues.append({"chapter": ch["chapter"], "severity": "WARN",
                        "type": "causal_chain",
                        "issue": f"与前一章goal无因果衔接——前后章可能断裂"})

    # Check for "orphan" hook setups (mentioning something in chapter N but never resolving)
    return issues


# ── Satisfaction density ──

def check_satisfaction_density(chapters: list[dict]) -> list[dict]:
    """Ensure no >5 consecutive chapters without a satisfaction/payoff event."""
    issues = []
    payoff_keywords = ["击败", "获得", "解锁", "突破", "打脸", "打脸", "碾压", "首通", "升级",
                       "收获", "打脸", "逆袭", "爽", "复仇", "揭露", "震惊", "觉醒"]

    last_payoff = 0
    for i, ch in enumerate(chapters):
        goal = ch.get("goal", "")
        premise = ch.get("premise_hit", "")
        combined = f"{goal} {premise}"
        if any(kw in combined for kw in payoff_keywords):
            gap = i - last_payoff
            if gap > 5:
                issues.append({"chapter": ch["chapter"], "severity": "WARN",
                    "type": "satisfaction_density",
                    "issue": f"距上次爽点已{gap}章——建议在Ch{ch['chapter']-1}或本章增加爽点"})
            last_payoff = i

    return issues


# ── Character arc check ──

def check_character_arcs(chapters: list[dict], book_dir: Path) -> list[dict]:
    """Check that major characters appear and evolve across the story."""
    issues = []
    # Try to find character files
    chars_dir = book_dir / "设定" / "角色"
    if not chars_dir.exists():
        chars_dir = book_dir / "story" / "characters"
    if not chars_dir.exists():
        return issues

    char_files = list(chars_dir.glob("*.md"))
    if not char_files:
        return issues

    for cf in char_files:
        char_name = cf.stem
        # Count appearances across chapters
        appearances = []
        for ch in chapters:
            combined = f"{ch.get('goal','')} {ch.get('title','')} {ch.get('premise_hit','')}"
            if char_name in combined:
                appearances.append(ch["chapter"])

        if len(appearances) < 2:
            # Only warn if this is a major character (not a one-off NPC)
            char_text = read(cf)
            if "主要" in char_text or "核心" in char_text or "女主" in char_text or "男" in char_text[:5]:
                issues.append({"chapter": 0, "severity": "WARN",
                    "type": "character_arc",
                    "issue": f"核心角色「{char_name}」在全书中出现次数<2——角色弧线可能断裂"})

        if appearances and len(appearances) >= 3:
            # Check for clustering (all appearances in one small range = flat arc)
            span = max(appearances) - min(appearances)
            if span < len(chapters) * 0.15 and len(chapters) > 20:
                issues.append({"chapter": 0, "severity": "WARN",
                    "type": "character_arc",
                    "issue": f"角色「{char_name}」出现集中在{min(appearances)}-{max(appearances)}章（跨度{span}章），中后期缺席"})

    return issues


# ── Power curve check ──

def check_power_curve(chapters: list[dict]) -> list[dict]:
    """Check power progression: no flat zones (no growth) and no jump zones (too fast)."""
    issues = []
    power_keywords = ["升级", "突破", "进阶", "觉醒", "解锁", "获得.*能力", "获得.*技能", "领悟",
                      "升到", "达到", "踏入", "晋升", "强化", "进化"]

    growth_points = []
    for i, ch in enumerate(chapters):
        goal = ch.get("goal", "")
        premise = ch.get("premise_hit", "")
        combined = f"{goal} {premise}"
        if any(re.search(kw, combined) for kw in power_keywords):
            growth_points.append(ch["chapter"])

    if not growth_points:
        return issues  # Can't analyze without power growth events

    # Check for flat zones (>8 chapters without growth)
    prev = 0
    for gp in growth_points:
        gap = gp - prev
        if gap > 8 and prev > 0:
            issues.append({"chapter": prev, "severity": "WARN",
                "type": "power_curve",
                "issue": f"Ch{prev}到Ch{gp}之间已有{gap}章无力量成长事件——可能进入平淡期"})
        prev = gp

    # Check for jump zones (back-to-back growth in consecutive chapters)
    jump_count = 0
    for i in range(1, len(growth_points)):
        if growth_points[i] - growth_points[i-1] <= 2:
            jump_count += 1
    if jump_count >= 3:
        issues.append({"chapter": 0, "severity": "WARN",
            "type": "power_curve",
            "issue": "力量成长事件过于密集——可能造成升级过快、爽点透支"})

    return issues


# ── Volume structure check ──

def check_volume_structure(volumes: list[dict], chapters: list[dict]) -> list[dict]:
    """Check volume-level structure: each volume has a climax and state change."""
    issues = []
    total_chs = sum(v.get("chapters", 0) for v in volumes)
    if total_chs == 0:
        return issues

    expected_total = len(chapters)
    if expected_total > 0 and abs(total_chs - expected_total) > expected_total * 0.2:
        issues.append({"chapter": 0, "severity": "WARN",
            "type": "volume_structure",
            "issue": f"卷纲总章数({total_chs})与细纲章数({expected_total})偏差>20%——卷纲和细纲不同步"})

    return issues


# ── Main ──

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-report", action="store_true")
    args = ap.parse_args()
    book = Path(args.book_dir).resolve()

    # Find files (support both director/ and story/outline/ paths)
    vol_map_paths = [book / "director" / "volume_map.md", book / "story" / "outline" / "volume_map.md"]
    ch_queue_paths = [book / "director" / "chapter_queue.md", book / "story" / "outline" / "chapter_queue.md"]

    vol_map_path = next((p for p in vol_map_paths if p.exists()), None)
    ch_queue_path = next((p for p in ch_queue_paths if p.exists()), None)

    if not ch_queue_path:
        print("FAIL: 找不到 chapter_queue.md")
        return 1

    volumes = parse_volume_map(vol_map_path) if vol_map_path else []
    chapters = parse_chapter_queue(ch_queue_path)

    if not chapters:
        print("FAIL: chapter_queue 为空")
        return 1

    all_issues = []
    all_issues.extend(check_causal_chain(chapters))
    all_issues.extend(check_satisfaction_density(chapters))
    all_issues.extend(check_character_arcs(chapters, book))
    all_issues.extend(check_power_curve(chapters))
    if volumes:
        all_issues.extend(check_volume_structure(volumes, chapters))

    fail_count = sum(1 for i in all_issues if i["severity"] == "FAIL")
    warn_count = sum(1 for i in all_issues if i["severity"] == "WARN")
    status = "FAIL" if fail_count > 0 else ("WARN" if warn_count > 0 else "PASS")

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    if args.json:
        result = {"status": status, "total_chapters": len(chapters), "volumes": len(volumes),
                  "fail": fail_count, "warn": warn_count, "issues": all_issues}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"=== 大纲逻辑验证报告 ===")
        print(f"时间：{now}")
        print(f"项目：{book}")
        print(f"结论：{status} (FAIL {fail_count} / WARN {warn_count})")
        print(f"卷数：{len(volumes)}，总章数：{len(chapters)}")
        print()
        if not all_issues:
            print("OK 无逻辑问题")
        for i in all_issues:
            icon = "[FAIL]" if i["severity"] == "FAIL" else "[WARN]"
            ch = f"Ch{i['chapter']:04d}" if i.get("chapter") else "all"
            print(f"  {icon} [{i['type']}] {ch} — {i['issue']}")
        print()
        print(f"下一步：{'可进入 execution-dispatch' if status == 'PASS' else '修复大纲逻辑问题'}")

    if args.write_report:
        report_dir = book / "director"
        report_dir.mkdir(parents=True, exist_ok=True)
        lines = [f"# 大纲逻辑验证", f"", f"时间：{now}", f"结论：{status}", f"",
                 f"## 摘要", f"| 指标 | 值 |", f"|---|---|",
                 f"| 卷数 | {len(volumes)} |", f"| 总章数 | {len(chapters)} |",
                 f"| FAIL | {fail_count} |", f"| WARN | {warn_count} |", f""]
        if all_issues:
            lines.append("## 问题")
            for i in all_issues:
                lines.append(f"- **{i['severity']}** [{i['type']}] {i.get('chapter','all')} — {i['issue']}")
        else:
            lines.append("OK 无逻辑问题")
        (report_dir / "outline_logic_review.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"\n报告已写入：{report_dir / 'outline_logic_review.md'}")

    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
