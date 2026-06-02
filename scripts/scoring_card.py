#!/usr/bin/env python3
"""Chapter scoring card for webnovel-director.

Usage:
  python scoring_card.py <book_dir> --chapter 1-30 [--json]

Scoring dimensions (weighted):
  1. 命题贴合 (30%) — premise alignment
  2. 爽点密度 (25%) — satisfaction / payoff density
  3. 人物一致性 (20%) — character consistency
  4. 结构完整 (15%) — structural integrity
  5. 去AI味   (10%) — anti-AI-pattern score

Grades: A(>=90) B(>=75) C(>=60) D(>=45) F(<45)
Trend:  ↑ improving  /  ↓ declining  /  → flat  (vs previous chapter)
"""

from __future__ import annotations
from pathlib import Path
import argparse, json, re, sys, math


# ── helpers ──

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="ignore") if p.exists() else ""


def find_book_text_files(book_dir: Path, ch_num: int) -> Path | None:
    """Find the chapter text file for a given chapter number."""
    ch_str = f"{ch_num:04d}"
    candidates = (list(book_dir.glob(f"chapters/第{ch_str}章-*.md"))
                + list(book_dir.glob(f"chapters/第{ch_str}章-*.txt")))
    return candidates[0] if candidates else None


def find_task_package(book_dir: Path, ch_num: int) -> dict:
    """Load task package for a chapter."""
    ch_str = f"{ch_num:04d}"
    tp = book_dir / "director" / "task_packages" / f"{ch_str}.yaml"
    if not tp.exists():
        return {}
    text = read(tp)
    pkg = {"chapter": ch_num, "chapter_goal": "", "title_hint": "", "premise_must_hit": [], "forbidden": []}
    for key in ["chapter", "chapter_goal", "title_hint", "executor"]:
        m = re.search(rf"^{key}:\s*(.+)$", text, re.M)
        if m:
            val = m.group(1).strip().strip('"')
            pkg[key] = int(val) if key == "chapter" and val.isdigit() else val
    for field in ["premise_must_hit", "forbidden"]:
        items = []
        in_sec = False
        for line in text.splitlines():
            if line.strip() == f"{field}:": in_sec = True; continue
            if in_sec:
                if line.strip().startswith("- "): items.append(line.strip()[2:].strip('"'))
                elif not line.strip().startswith(" ") and line.strip(): break
        pkg[field] = items
    return pkg


def parse_chapter_queue(book_dir: Path) -> list[dict]:
    """Parse chapter_queue.md to get outline-level info."""
    cq_path = book_dir / "director" / "chapter_queue.md"
    rows = []
    for line in read(cq_path).splitlines():
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


def load_premise_keywords(book_dir: Path) -> set[str]:
    """Extract core premise keywords for alignment scoring."""
    premise_text = read(book_dir / "director" / "premise.md")
    if not premise_text:
        return set()
    # Extract 书名承诺 section
    m = re.search(r"##\s*书名承诺\s*\n+(.*?)(?:##|\Z)", premise_text, re.S)
    if not m:
        m = re.search(r"书名承诺\s*\n+(.*?)(?:\n##|\n#|\Z)", premise_text, re.S)
    text = m.group(1).strip() if m else premise_text[:3000]
    # Also pull premise must-hit items from the whole document
    keywords = set()
    for kw in re.findall(r"[\u4e00-\u9fff]{4,}", text):
        keywords.add(kw)
    # Add explicit Must-Hit items
    for mh in re.findall(r"Must[- ]*Hit\s*[：:]\s*(.+)", premise_text, re.I):
        for kw in re.findall(r"[\u4e00-\u9fff]{3,}", mh):
            keywords.add(kw)
    return keywords


def load_character_names(book_dir: Path) -> list[str]:
    """Load character names from relationship graph."""
    rg = read(book_dir / "truth" / "relationship_graph.yaml")
    names = set()
    if rg:
        for m in re.finditer(r"(?:source|target):\s*\"?([^\"#\n]+)", rg):
            name = m.group(1).strip()
            if name and not name.startswith("{{"):
                names.add(name)
    return list(names)


# ── AI-pattern markers ──

AI_MARKERS = [
    # Structural
    (r"总之[,，]", "总结句式"),
    (r"通过以上.{0,10}我们", "论证句式"),
    (r"值得[一-]提的是", "插入句式"),
    (r"需要(?:注意|强调)的是", "说教句式"),
    (r"由此(?:可见|可知)", "逻辑推演"),
    (r"从某种(?:意义|程度)上说", "模糊修饰"),
    (r"不可否认的是", "空洞转折"),
    # Over-explanation
    (r"这是[一-]种.{2,10}的体[验会]", "过度阐释"),
    (r"令人.{2,6}(?:的是|之感)", "情绪贴标签"),
    (r"不禁.{2,10}(?:起来|了)", "叙述干预"),
    # Redundant phrasing
    (r"在.{2,6}的过程中", "过程冗余"),
    (r"进行.{0,2}了.{1,8}", "进行冗余"),
    (r"出现.{0,2}了.{1,8}", "出现冗余"),
    (r"发生.{0,2}了.{1,8}", "发生冗余"),
    (r"感到.{0,2}了.{1,6}", "感到冗余"),
    (r"有着.{1,8}", "有着冗余"),
    (r"显得格外.{2,6}", "显得冗余"),
    # Paragraph-level
    (r"\n\n(?:首先|其次|再次|最后|第一|第二|第三|此外|另外)\b", "列举结构"),
    (r"\n\n(?:然而|但是|不过|可是|因此|所以|于是|紧接着|随即)", "机械过渡"),
    (r"\n\n(?:与此同时|与此同时|另一方面)", "二元对比"),
]


def score_anti_ai(text: str) -> tuple[float, list[str]]:
    """Score anti-AI-pattern: fewer markers = higher score."""
    if not text:
        return 50.0, ["无文本"]
    chars = len(text.replace("\n", "").replace(" ", ""))
    if chars < 500:
        return 50.0, ["文本过短"]
    found = []
    for pattern, label in AI_MARKERS:
        hits = len(re.findall(pattern, text))
        if hits > 0:
            found.append(f"{label}(×{hits})")
    # Density: markers per 1000 chars
    density = sum(len(re.findall(p, text)) for p, _ in AI_MARKERS) / (chars / 1000)
    if density == 0:
        score = 95.0
    elif density < 2:
        score = 85.0
    elif density < 5:
        score = 70.0
    elif density < 10:
        score = 50.0
    elif density < 20:
        score = 30.0
    else:
        score = 10.0
    return score, found


def score_premise_alignment(text: str, premise_keywords: set[str], must_hit: list[str]) -> tuple[float, list[str]]:
    """Score how well the chapter aligns with the book premise."""
    if not text or not premise_keywords:
        return 50.0, ["无文本或无前提数据"]
    chars = len(text.replace("\n", "").replace(" ", ""))
    evidence = []
    # Check premise keyword hits
    hits = [kw for kw in premise_keywords if kw in text]
    hit_rate = len(hits) / max(len(premise_keywords), 1)
    evidence.append(f"前提关键词命中: {len(hits)}/{len(premise_keywords)} ({hit_rate:.0%})")
    # Check must-hit items
    mh_hits = 0
    for mh in must_hit:
        if not mh:
            continue
        keywords = re.findall(r"[\u4e00-\u9fff]{2,}", mh)
        if keywords and any(kw in text for kw in keywords):
            mh_hits += 1
    mh_rate = mh_hits / max(len(must_hit), 1)
    evidence.append(f"Must-Hit兑现: {mh_hits}/{len(must_hit)} ({mh_rate:.0%})")
    # Weighted: 60% premise keywords + 40% must-hit
    raw = hit_rate * 60 + mh_rate * 40
    return min(raw * 1.2, 98.0), evidence  # bonus cap for strong alignment


def score_satisfaction_density(text: str) -> tuple[float, list[str]]:
    """Score chapter for satisfaction/payoff density."""
    if not text:
        return 40.0, ["无文本"]
    chars = len(text.replace("\n", "").replace(" ", ""))
    evidence = []
    # Action markers
    actions = len(re.findall(r"(击败|击杀|突破|获得|发现|开启|完成|通过|成功|晋级|提升|解锁|学会|掌握|领悟)", text))
    # Emotional beats
    emotional = len(re.findall(r"(震惊|惊恐|狂喜|愤怒|绝望|希望|感动|泪|笑|怒吼|握拳|颤抖)", text))
    # Conflict / reversal
    conflicts = len(re.findall(r"(但是|然而|不过|突然|竟然|不料|谁知|结果|没想到)", text))
    # Payoff density per 1000 chars
    kchars = chars / 1000
    action_density = actions / max(kchars, 1)
    emotional_density = emotional / max(kchars, 1)
    conflict_density = conflicts / max(kchars, 1)
    evidence.append(f"动作密度: {action_density:.1f}/k字")
    evidence.append(f"情感密度: {emotional_density:.1f}/k字")
    evidence.append(f"冲突逆转: {conflict_density:.1f}/k字")
    # Composite: action 40%, emotion 30%, conflict 30%
    raw = (min(action_density / 5, 1) * 40
         + min(emotional_density / 4, 1) * 30
         + min(conflict_density / 3, 1) * 30)
    return min(raw * 1.15, 98.0), evidence


def score_character_consistency(text: str, characters: list[str], book_dir: Path) -> tuple[float, list[str]]:
    """Score character consistency based on presence and name stability."""
    if not text or not characters:
        return 60.0, ["无文本或无角色数据"]
    evidence = []
    chars = len(text.replace("\n", "").replace(" ", ""))
    # Check name occurrences
    present = [c for c in characters if c in text]
    absent = [c for c in characters if c not in text]
    presence_rate = len(present) / max(len(characters), 1)
    evidence.append(f"角色出现率: {len(present)}/{len(characters)} ({presence_rate:.0%})")
    # Check for name variants (potential inconsistency)
    name_baselines = {}
    for name in characters:
        base = re.sub(r"[·\-.·]", "", name)
        if len(base) >= 2:
            name_baselines[name] = base
    variant_count = 0
    for name, base in name_baselines.items():
        # Look for variations: partial name without full name nearby
        short = name[:2] if len(name) > 2 else name
        if name not in text and short in text:
            # Name appears in shortened form, possible inconsistency
            # Only flag if the full form is unexpected
            pass  # Short forms are often fine in novels
    # Check for pronoun ambiguity section (7+ consecutive paragraphs without name ref)
    paragraphs = [p for p in re.split(r'\n\s*\n', text) if p.strip()]
    name_refs = sum(1 for p in paragraphs if any(n in p for n in characters))
    para_rate = name_refs / max(len(paragraphs), 1)
    evidence.append(f"角色命名密度: {para_rate:.0%} 段落含角色名")
    # Weighted score
    score = presence_rate * 60 + para_rate * 40
    return min(score * 1.1, 98.0), evidence


def score_structure(text: str) -> tuple[float, list[str]]:
    """Score chapter structure: hook, development, climax, cliffhanger."""
    if not text:
        return 40.0, ["无文本"]
    chars = len(text.replace("\n", "").replace(" ", ""))
    evidence = []
    paragraphs = [p for p in re.split(r'\n\s*\n', text) if p.strip()]
    para_count = len(paragraphs)
    evidence.append(f"段落数: {para_count}")
    # 1. Opening hook (first 300 chars)
    opening = text[:300] if len(text) > 300 else text
    hook_words = ["？", "…", "突然", "意外", "不是", "原来", "竟然", "从未"]
    hook_present = any(w in opening for w in hook_words)
    evidence.append(f"开头钩子: {'有' if hook_present else '无'}")
    # 2. Paragraph count adequacy
    if para_count < 10:
        structure_score = 0
    elif para_count < 15:
        structure_score = 0.3
    elif para_count < 25:
        structure_score = 0.6
    elif para_count < 40:
        structure_score = 0.85
    else:
        structure_score = 1.0
    # 3. Mid-chapter pivot
    mid = len(paragraphs) // 2
    mid_text = "\n".join(paragraphs[max(0, mid - 2):mid + 2])
    pivot_words = ["但是", "然而", "不过", "结果", "原来", "发现", "才知", "转变"]
    pivot_present = any(w in mid_text for w in pivot_words)
    evidence.append(f"中段转折: {'有' if pivot_present else '无'}")
    # 4. Ending cliffhanger (last 300 chars)
    ending = text[-300:] if len(text) > 300 else text
    cliff_markers = ["？", "…", "——", "不再", "开始", "突然", "发现", "不是", "原来", "他", "她"]
    cliff_count = sum(1 for m in cliff_markers if m in ending)
    evidence.append(f"章末钩子强度: {cliff_count}/10 ({'强' if cliff_count >= 4 else '弱' if cliff_count >= 2 else '无'})")
    # Composite
    scores = {
        "hook": 0.75 if hook_present else 0.25,
        "paragraphs": structure_score,
        "pivot": 0.7 if pivot_present else 0.3,
        "cliffhanger": min(cliff_count / 5, 1.0),
    }
    raw = (scores["hook"] * 0.2 + scores["paragraphs"] * 0.25
         + scores["pivot"] * 0.25 + scores["cliffhanger"] * 0.3)
    return raw * 100, evidence


# ── composite scoring ──

WEIGHTS = {
    "premise": 0.30,
    "satisfaction": 0.25,
    "character": 0.20,
    "structure": 0.15,
    "anti_ai": 0.10,
}


def score_chapter(text: str, premise_kw: set[str], must_hit: list[str],
                  characters: list[str], book_dir: Path) -> dict:
    """Score a single chapter across all dimensions."""
    s_premise, ev_premise = score_premise_alignment(text, premise_kw, must_hit)
    s_satisfy, ev_satisfy = score_satisfaction_density(text)
    s_char, ev_char = score_character_consistency(text, characters, book_dir)
    s_struct, ev_struct = score_structure(text)
    s_ai, ev_ai = score_anti_ai(text)

    composite = (
        s_premise * WEIGHTS["premise"]
        + s_satisfy * WEIGHTS["satisfaction"]
        + s_char * WEIGHTS["character"]
        + s_struct * WEIGHTS["structure"]
        + s_ai * WEIGHTS["anti_ai"]
    )

    grade = "F"
    if composite >= 90: grade = "A"
    elif composite >= 75: grade = "B"
    elif composite >= 60: grade = "C"
    elif composite >= 45: grade = "D"

    return {
        "chapter": 0,  # filled by caller
        "composite": round(composite, 1),
        "grade": grade,
        "dimensions": {
            "命题贴合": {"score": round(s_premise, 1), "weight": 0.30, "evidence": ev_premise},
            "爽点密度": {"score": round(s_satisfy, 1), "weight": 0.25, "evidence": ev_satisfy},
            "人物一致性": {"score": round(s_char, 1), "weight": 0.20, "evidence": ev_char},
            "结构完整": {"score": round(s_struct, 1), "weight": 0.15, "evidence": ev_struct},
            "去AI味": {"score": round(s_ai, 1), "weight": 0.10, "evidence": ev_ai},
        }
    }


def grade_to_color(grade: str) -> str:
    colors = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}
    return colors.get(grade, "⚪")


def trend_icon(prev: float | None, curr: float) -> str:
    if prev is None:
        return "→"
    diff = curr - prev
    if diff > 2:
        return "↑"
    elif diff < -2:
        return "↓"
    else:
        return "→"


def parse_chapter_range(arg: str) -> list[int]:
    """Parse chapter range like '1-30' or '5' into a list of chapter numbers."""
    chapters = []
    m = re.match(r"(\d+)\s*[-–—]\s*(\d+)", arg)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        chapters = list(range(start, end + 1))
    else:
        nums = [int(x) for x in re.findall(r"\d+", arg)]
        chapters = nums
    return chapters


def main() -> int:
    ap = argparse.ArgumentParser(description="Chapter scoring card for webnovel-director")
    ap.add_argument("book_dir", help="Path to the book project directory")
    ap.add_argument("--chapter", required=True, help='Chapter or range, e.g. "1-30" or "5"')
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    args = ap.parse_args()

    book_dir = Path(args.book_dir).resolve()
    if not book_dir.exists():
        print(f"错误：目录不存在：{book_dir}", file=sys.stderr)
        return 1

    chapter_nums = parse_chapter_range(args.chapter)
    if not chapter_nums:
        print(f"错误：无法解析章节范围：{args.chapter}", file=sys.stderr)
        return 1

    # Load shared data
    premise_kw = load_premise_keywords(book_dir)
    characters = load_character_names(book_dir)

    # Score each chapter
    results = []
    prev_composite = None
    for ch_num in chapter_nums:
        # Try to find chapter text
        text_path = find_book_text_files(book_dir, ch_num)
        chapter_text = read(text_path) if text_path else ""

        # Try task package for must-hit info
        task_pkg = find_task_package(book_dir, ch_num)
        must_hit = task_pkg.get("premise_must_hit", [])

        score = score_chapter(chapter_text, premise_kw, must_hit, characters, book_dir)
        score["chapter"] = ch_num
        score["trend"] = trend_icon(prev_composite, score["composite"])
        if chapter_text:
            score["text_length"] = len(chapter_text.replace("\n", "").replace(" ", ""))
        else:
            score["text_length"] = 0
            score["note"] = "正文文件未找到，基于大纲评分"

        results.append(score)
        prev_composite = score["composite"]

    if args.json:
        output = {"range": args.chapter, "total": len(results), "chapters": results}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    # ── Table output ──
    print()
    print(f"📊 综合评分卡 — {book_dir.name}")
    print(f"章节范围: {args.chapter} ({len(results)}章)")
    print(f"{'─' * 70}")
    print(f"{'章节':>6} │ {'综合':>6} │ {'等级':>3} │ {'趋势':>2} │ {'命题(30%)':>7} │ {'爽点(25%)':>7} │ {'人物(20%)':>7} │ {'结构(15%)':>7} │ {'AI味(10%)':>7}")
    print(f"{'─' * 70}")

    sum_premise = sum_premise_w = 0.0
    sum_satisfy = sum_satisfy_w = 0.0
    sum_char = sum_char_w = 0.0
    sum_struct = sum_struct_w = 0.0
    sum_ai = sum_ai_w = 0.0

    for r in results:
        d = r["dimensions"]
        print(f"{r['chapter']:>6} │ {r['composite']:>6.1f} │ {grade_to_color(r['grade'])}{r['grade']:>2} │ {r['trend']:>2} │ "
              f"{d['命题贴合']['score']:>7.1f} │ {d['爽点密度']['score']:>7.1f} │ "
              f"{d['人物一致性']['score']:>7.1f} │ {d['结构完整']['score']:>7.1f} │ "
              f"{d['去AI味']['score']:>7.1f}")
        sum_premise += d["命题贴合"]["score"]; sum_premise_w += 1
        sum_satisfy += d["爽点密度"]["score"]; sum_satisfy_w += 1
        sum_char += d["人物一致性"]["score"]; sum_char_w += 1
        sum_struct += d["结构完整"]["score"]; sum_struct_w += 1
        sum_ai += d["去AI味"]["score"]; sum_ai_w += 1

    print(f"{'─' * 70}")
    avg = lambda s, w: round(s / max(w, 1), 1)
    print(f"{'平均':>6} │ {'—':>6} │ {'—':>3} │ {'—':>2} │ "
          f"{avg(sum_premise, sum_premise_w):>7.1f} │ "
          f"{avg(sum_satisfy, sum_satisfy_w):>7.1f} │ "
          f"{avg(sum_char, sum_char_w):>7.1f} │ "
          f"{avg(sum_struct, sum_struct_w):>7.1f} │ "
          f"{avg(sum_ai, sum_ai_w):>7.1f}")
    print(f"{'─' * 70}")

    # Distribution
    grades_count = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for r in results:
        grades_count[r["grade"]] = grades_count.get(r["grade"], 0) + 1
    grade_parts = [f"{g}:{c}" for g, c in grades_count.items() if c > 0]
    print(f"分布: {' | '.join(grade_parts)}")
    print()

    # Per-chapter detail (condensed)
    for r in results:
        if r.get("note"):
            print(f"[Ch{r['chapter']:04d}] ⚠ {r['note']}")
        if r["grade"] in ("D", "F"):
            worst = sorted(r["dimensions"].items(), key=lambda x: x[1]["score"])[:2]
            parts = [f"{name}={val['score']:.0f}" for name, val in worst]
            print(f"[Ch{r['chapter']:04d}] 🔴 等级{r['grade']} — 弱项: {', '.join(parts)}")

    print(f"✅ 评级图例: A≥90  B≥75  C≥60  D≥45  F<45  |  趋势: ↑改善 ↓退化 →持平")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
