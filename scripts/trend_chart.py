#!/usr/bin/env python3
"""ASCII terminal trend charts for webnovel-director projects.

Usage:
  python trend_chart.py <book_dir> [--last N] [--all]

Reads audit_log.md and chapter files to produce three ASCII line charts:
  1. 字数趋势 — word count per chapter
  2. 审查分趋势 — review score (PASS=3, WARN=2, FAIL=1)
  3. 偏离度趋势 — deviation estimate based on audit summaries

No matplotlib or external dependencies required — pure Unicode box-drawing.
"""
from __future__ import annotations
from pathlib import Path
import argparse, re, sys

# ── ASCII chart engine ──


def _draw_line(grid: list[list[str]], x1: int, y1: int, x2: int, y2: int):
    """Bresenham line algorithm on a char grid."""
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx - dy
    h = len(grid)
    w = len(grid[0]) if h > 0 else 0

    while True:
        if 0 <= y1 < h and 0 <= x1 < w:
            # Pick best box-drawing character later; for now just mark
            if grid[y1][x1] == " ":
                grid[y1][x1] = "·"
        if x1 == x2 and y1 == y2:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x1 += sx
        if e2 < dx:
            err += dx
            y1 += sy


def _render_chart(grid: list[list[str]], y_min: float, y_max: float, height: int,
                  x_labels: list[tuple[int, str]], title: str, y_label: str,
                  mean_line: float | None = None) -> str:
    """Render a 2D char grid into a string with axes."""
    width = len(grid[0]) if grid else 0
    lines = []

    # Title
    lines.append(f"  {title}")

    # Y-axis + data rows
    for row_idx in range(height):
        row = grid[row_idx]
        # Y label every few rows
        val = y_max - (row_idx / max(height - 1, 1)) * (y_max - y_min)
        if row_idx % max(1, height // 8) == 0:
            y_str = f"{val:>7.0f} " if val >= 100 else f"{val:>7.1f} "
        else:
            y_str = " " * 8
        lines.append(y_str + "┤" + "".join(row))

    # X-axis baseline
    lines.append(" " * 8 + "└" + "─" * width)

    # Mean line indicator
    if mean_line is not None:
        mean_y = height - 1 - int((mean_line - y_min) / max(y_max - y_min, 0.001) * (height - 1))
        mean_y = max(0, min(height - 1, mean_y))
        lines.append(f"  ══ 均值: {mean_line:.1f} {y_label}")

    # X-axis labels
    label_row = " " * 8 + " "
    for x_pos, label in x_labels:
        # Place label at x position
        start = x_pos - len(label) // 2
        start = max(0, start)
        while len(label_row) < 8 + start + len(label):
            label_row += " "
        label_row = label_row[:8 + start] + label + label_row[8 + start + len(label):]
    lines.append(label_row)

    return "\n".join(lines)


def ascii_line_chart(data_points: list[tuple[str, float]], title: str = "",
                     y_label: str = "", width: int = 60, height: int = 14) -> str:
    """Render an ASCII line chart from (x_label, value) data points.

    Returns a multi-line string with Unicode box-drawing axes.
    """
    if not data_points:
        return f"  {title}\n  (无数据)"

    values = [v for _, v in data_points]
    labels = [l for l, _ in data_points]

    min_val = min(values)
    max_val = max(values)
    if max_val == min_val:
        max_val = min_val + 1.0
    # Add 10% padding
    padding = (max_val - min_val) * 0.1 or 1.0
    y_min = max(0, min_val - padding)
    y_max = max_val + padding

    # Create grid
    grid = [[" " for _ in range(width)] for _ in range(height)]

    # Map data points to grid coordinates
    n = len(data_points)
    points = []
    for i in range(n):
        if n == 1:
            px = width // 2
        else:
            px = int(i / (n - 1) * (width - 1))
        py = height - 1 - int((values[i] - y_min) / max(y_max - y_min, 0.001) * (height - 1))
        py = max(0, min(height - 1, py))
        points.append((px, py))

    # Draw markers
    for px, py in points:
        if 0 <= py < height and 0 <= px < width:
            grid[py][px] = "●"

    # Draw connecting lines
    for i in range(n - 1):
        _draw_line(grid, points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])

    # Compute mean
    mean_val = sum(values) / len(values)

    # X-axis labels: show every few points
    step = max(1, n // 12)
    x_label_pairs = []
    for i in range(n):
        if n == 1:
            px = width // 2
        else:
            px = int(i / (n - 1) * (width - 1))
        if i % step == 0 or i == n - 1:
            lbl = labels[i][:5] if labels[i] else str(i + 1)
            x_label_pairs.append((px, lbl))

    return _render_chart(grid, y_min, y_max, height, x_label_pairs,
                         title, y_label, mean_val)


# ── Data extraction ──


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="ignore") if p.exists() else ""


def strip_markdown(text: str) -> str:
    """Strip markdown formatting, keep only body text."""
    text = re.sub(r"^#{1,6}\s+.+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", "", text)
    return text


def count_chapter_words(book_dir: Path) -> dict[int, int]:
    """Return {chapter_number: word_count} for all chapter files."""
    counts = {}
    for ch_dir_name in ("正文", "chapters"):
        ch_dir = book_dir / ch_dir_name
        if not ch_dir.exists():
            continue
        for f in sorted(ch_dir.glob("*.md")):
            m = re.match(r"第0*(\d+)章", f.name)
            if m:
                ch_num = int(m.group(1))
                counts[ch_num] = len(strip_markdown(read(f)))
    return counts


def parse_audit_log(audit_log_path: Path) -> list[dict]:
    """Parse audit_log.md table rows."""
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


def parse_chapter_queue(book_dir: Path) -> dict[int, dict]:
    """Return {chapter_number: {title, status, ...}} from chapter_queue.md."""
    result = {}
    cq_path = book_dir / "director" / "chapter_queue.md"
    if not cq_path.exists():
        return result
    text = read(cq_path)
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "Chapter" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) >= 6:
            n = re.sub(r"\D", "", cells[0])
            if n.isdigit():
                result[int(n)] = {
                    "title": cells[1],
                    "goal": cells[2],
                    "premise_hit": cells[3],
                    "forbidden": cells[4],
                    "status": cells[5].upper(),
                }
    return result


def extract_review_scores(audit_entries: list[dict]) -> dict[int, float]:
    """Extract review scores from audit log entries.

    Maps PASS→3, WARN→2, FAIL→1. Groups by chapter number extracted from object field.
    """
    scores: dict[int, list[float]] = {}
    score_map = {"PASS": 3.0, "WARN": 2.0, "FAIL": 1.0}

    for entry in audit_entries:
        # Try to extract chapter number from object field (e.g. "第12章", "Ch 12")
        m = re.search(r"第\s*0*(\d+)\s*章", entry["object"])
        if not m:
            m = re.search(r"[Cc][Hh]?\s*0*(\d+)", entry["object"])
        if not m:
            continue
        ch_num = int(m.group(1))
        sc = score_map.get(entry["result"])
        if sc is not None:
            if ch_num not in scores:
                scores[ch_num] = []
            scores[ch_num].append(sc)

    # Average per chapter
    return {ch: sum(vals) / len(vals) for ch, vals in scores.items()}


def estimate_deviation(audit_entries: list[dict]) -> dict[int, float]:
    """Estimate premise deviation from audit summaries.

    Simple heuristic: count deviation-related keywords in summary text.
    Score 0=on-track, 100=severe deviation.
    """
    dev_keywords = [
        "偏离", "背离", "命题", "禁飞区", "触犯", "禁止", "违背",
        "偏离命题", "方向错误", "主线", "书名承诺", "forbidden",
        "相反", "矛盾", "不一致", "漂移", "偏题",
    ]
    dev: dict[int, list[float]] = {}

    for entry in audit_entries:
        m = re.search(r"第\s*0*(\d+)\s*章", entry["object"])
        if not m:
            m = re.search(r"[Cc][Hh]?\s*0*(\d+)", entry["object"])
        if not m:
            continue
        ch_num = int(m.group(1))
        summary = entry.get("summary", "").lower()
        hits = sum(1 for kw in dev_keywords if kw.lower() in summary)
        # Score: 0-100, each keyword hit adds 15, max 100
        d_score = min(100, hits * 15 + (10 if entry.get("result", "") == "FAIL" else 0)
                      + (5 if entry.get("result", "") == "WARN" else 0))

        if ch_num not in dev:
            dev[ch_num] = []
        dev[ch_num].append(d_score)

    return {ch: max(vals) for ch, vals in dev.items()}  # Take worst


# ── main ──


def main() -> int:
    # Ensure UTF-8 output on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="ASCII终端趋势图")
    ap.add_argument("book_dir", help="小说项目路径")
    ap.add_argument("--last", type=int, default=30, metavar="N",
                    help="最近N章（默认30）")
    ap.add_argument("--all", action="store_true",
                    help="显示全部章节（覆盖 --last）")
    args = ap.parse_args()

    book_dir = Path(args.book_dir).resolve()
    if not (book_dir / "director").exists():
        print(f"错误: {book_dir} 中未找到 director/ 目录")
        return 1

    # Gather data
    word_counts = count_chapter_words(book_dir)
    audit_log_path = book_dir / "director" / "audit_log.md"
    audit_entries = parse_audit_log(audit_log_path)
    review_scores = extract_review_scores(audit_entries)
    deviations = estimate_deviation(audit_entries)
    chapter_queue = parse_chapter_queue(book_dir)

    # Determine chapter range
    all_chapters = sorted(set(list(word_counts.keys()) + list(review_scores.keys())
                               + list(deviations.keys())))
    if not all_chapters:
        print("未找到任何章节数据。请先确保有章节文件和审计记录。")
        return 1

    if args.all:
        chapter_range = all_chapters
    else:
        # Take last N chapters (by chapter number)
        chapter_range = sorted(all_chapters)[-args.last:]

    # Build chart data
    word_data = []
    score_data = []
    dev_data = []

    for ch in chapter_range:
        label = f"ch{ch}"
        wc = word_counts.get(ch, 0)
        if wc > 0:
            word_data.append((label, wc))

        sc = review_scores.get(ch)
        if sc is not None:
            score_data.append((label, sc))
        elif ch in chapter_queue and chapter_queue[ch].get("status") in ("PASS", "WARN", "FAIL"):
            sq = {"PASS": 3.0, "WARN": 2.0, "FAIL": 1.0}
            score_data.append((label, sq.get(chapter_queue[ch]["status"], 0)))

        dv = deviations.get(ch, 0)
        dev_data.append((label, dv))

    # Render charts
    print()
    print("═" * 72)
    print(f"  📈 webnovel-director 趋势图 — {book_dir.name}")
    print(f"  范围: 第{chapter_range[0]}-{chapter_range[-1]}章 ({len(chapter_range)}章)")
    print("═" * 72)

    print()
    chart1 = ascii_line_chart(word_data, title="📖 字数趋势（实写字数）", y_label="字", width=62, height=12)
    print(chart1)

    print()
    chart2 = ascii_line_chart(score_data, title="📊 审查分趋势（PASS=3 WARN=2 FAIL=1）", y_label="分", width=62, height=10)
    print(chart2)

    print()
    chart3 = ascii_line_chart(dev_data, title="📉 偏离度趋势（越高越偏离命题）", y_label="%", width=62, height=10)
    print(chart3)

    # Summary stats
    print()
    print("═" * 72)
    if word_data:
        avg_words = sum(v for _, v in word_data) / len(word_data)
        max_words = max(v for _, v in word_data)
        min_words = min(v for _, v in word_data)
        print(f"  字数: 均 {avg_words:.0f}字 | 最高 {max_words:.0f}字 | 最低 {min_words:.0f}字 | 共 {sum(v for _, v in word_data)}字")
    if score_data:
        avg_score = sum(v for _, v in score_data) / len(score_data)
        pass_n = sum(1 for _, v in score_data if v >= 3)
        warn_n = sum(1 for _, v in score_data if 2 <= v < 3)
        fail_n = sum(1 for _, v in score_data if v < 2)
        print(f"  审查: 均分 {avg_score:.1f} | PASS {pass_n} | WARN {warn_n} | FAIL {fail_n}")
    if dev_data:
        avg_dev = sum(v for _, v in dev_data) / len(dev_data)
        high_dev = sum(1 for _, v in dev_data if v > 30)
        print(f"  偏离: 均 {avg_dev:.0f}% | 高偏离(>30%) {high_dev}章")
    print("═" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
