#!/usr/bin/env python3
"""Build a chapter task package for webnovel-director execution-dispatch.

Usage:
  python build_task_package.py <book_dir> --chapter 12 [--out task.yaml] [--with-cover]

Reads director_state, premise, chapter_queue, last_audit and truth files, then
emits a YAML-like task package. This script is deliberately conservative: if
canWrite=false, blockers exist, or the chapter is not PASS/READY in queue, it
fails instead of producing a write prompt.
"""
from __future__ import annotations
from pathlib import Path
import argparse, ast, datetime, json, re, sys

REQUIRED = [
    "director/premise.md",
    "director/director_state.json5",
    "director/chapter_queue.md",
    "director/last_audit.md",
    "truth/current_state.md",
    "truth/resource_ledger.md",
    "truth/particle_ledger.md",
    "truth/pending_hooks.md",
]
READY_STATUSES = {"pass", "ready", "待写", "通过", "可写", "queued", "done"}
BLOCKED_STATUSES = {"fail", "blocked", "stop", "未通过", "阻塞", "修复"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def strip_json5(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"([,{]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def load_state(path: Path) -> dict:
    text = read_text(path)
    try:
        return json.loads(strip_json5(text))
    except Exception:
        # Tiny fallback for simple JSON5-like files.
        data = {}
        for key in ["bookId", "title", "status", "executor", "canWrite", "activeVolume", "currentChapter"]:
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
            try:
                data["blockers"] = ast.literal_eval(bm.group(1).replace("'", '"'))
            except Exception:
                data["blockers"] = [bm.group(1)]
        return data


def split_cell(row: str) -> list[str]:
    row = row.strip().strip("|")
    return [c.strip().replace("<br>", "\n") for c in row.split("|")]


def parse_chapter_queue(path: Path) -> list[dict]:
    rows = []
    for line in read_text(path).splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "Chapter" in s:
            continue
        cells = split_cell(s)
        if len(cells) < 6:
            continue
        ch_raw = re.sub(r"\D", "", cells[0])
        if not ch_raw:
            continue
        rows.append({
            "chapter": int(ch_raw),
            "title_hint": cells[1],
            "goal": cells[2],
            "premise_must_hit": cells[3],
            "forbidden": cells[4],
            "status": cells[5],
        })
    return rows


def listify(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"[；;、，,\n]+", text)
    return [p.strip(" -") for p in parts if p.strip(" -")]


def yaml_quote(s: str) -> str:
    return json.dumps(s or "", ensure_ascii=False)


def yaml_list(items: list[str], indent: int = 2) -> str:
    pad = " " * indent
    if not items:
        return f"{pad}- \"\""
    return "\n".join(f"{pad}- {yaml_quote(i)}" for i in items)


def excerpt_file(path: Path, max_chars: int = 900) -> str:
    if not path.exists():
        return ""
    text = read_text(path).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...<truncated>"


def extract_cover_prompt(premise_path: Path) -> str:
    """Extract title, core concept, and emotional tone from premise.md and
    generate a ~200-char Chinese cover-art prompt suitable for image generation.

    The prompt includes: book title, author placeholder, genre hints, visual
    description (composition, colour palette, focal elements), and mood.
    Returns an empty string if premise.md is missing or unparseable.
    """
    if not premise_path.exists():
        return ""
    text = premise_path.read_text(encoding="utf-8-sig", errors="ignore")
    # ── Extract structured fields ──────────────────────────────────
    title = ""
    promise = ""
    situation = ""
    mechanism = ""
    forbidden_raw = ""

    # Book title: first heading or {{TITLE}} template (strip "- Premise" suffix)
    tm = re.search(r"^#\s+(.+)", text, re.M)
    if tm:
        title = tm.group(1).strip()
        # Strip common premise.md heading suffixes
        title = re.sub(r"\s*[-–—]\s*[Pp]remise\s*$", "", title).strip()
        title = re.sub(r"\s*[-–—]\s*[命命]题\s*$", "", title).strip()
    if not title or "{{" in title:
        tm2 = re.search(r'title\s*:\s*"?([^"\n]+)"?', text)
        if tm2:
            title = tm2.group(1).strip()
    if not title or "{{" in title:
        title = ""  # will use placeholder

    # Promise line: the one-sentence core hook
    pm = re.search(r"书名承诺[\s\S]*?>\s*(.+)", text)
    if not pm:
        pm = re.search(r"一句话说明[\s\S]*?>\s*(.+)", text)
    if pm:
        promise = pm.group(1).strip()

    # Situation & core mechanism from 命题三要素
    sit_m = re.search(r"主角处境[：:]\s*(.+)", text)
    if sit_m:
        situation = sit_m.group(1).strip()
    mech_m = re.search(r"核心爽点机制[：:]\s*(.+)", text)
    if mech_m:
        mechanism = mech_m.group(1).strip()

    # Forbidden zones signal tone
    fz_match = re.search(r"禁飞区[\s\S]*?角色功能锁", text)
    if fz_match:
        forbidden_raw = fz_match.group(0)

    # ── Infer emotional tone ───────────────────────────────────────
    tone_keywords = [
        ("热血", ["热血", "战斗", "争霸", "无敌", "升级", "逆袭"]),
        ("悬疑", ["悬疑", "谜团", "诡异", "秘密", "调查", "解密"]),
        ("虐恋", ["虐恋", "虐心", "错过", "误会", "追妻", "火葬场"]),
        ("甜宠", ["甜宠", "甜蜜", "宠溺", "温暖", "治愈", "温柔"]),
        ("末世", ["末世", "末日", "丧尸", "废土", "生存"]),
        ("权谋", ["权谋", "权斗", "宫斗", "朝堂", "计谋"]),
        ("仙侠", ["仙侠", "修仙", "修真", "飞升", "宗门", "天道"]),
        ("科幻", ["科幻", "星际", "AI", "机甲", "未来"]),
        ("都市", ["都市", "现代", "总裁", "职场", "日常"]),
    ]
    combined = promise + situation + mechanism + forbidden_raw
    detected_tones = [t for t, kws in tone_keywords if any(kw in combined for kw in kws)]
    tone = detected_tones[0] if detected_tones else "玄幻"

    # ── Build visual mood cue ──────────────────────────────────────
    mood_map = {
        "热血": "史诗感、强光影对比、金色与暗红色调",
        "悬疑": "暗调、蓝紫色冷光、阴影与迷雾",
        "虐恋": "柔焦、冷暖对比、雨夜或雪天",
        "甜宠": "暖色调、柔和光晕、樱花或晨曦",
        "末世": "灰暗废土、残阳、废墟与新生对比",
        "权谋": "庄重、深红色帷幔、对称构图",
        "仙侠": "云雾飘渺、青蓝水墨、剑光与灵兽",
        "科幻": "赛博朋克霓虹、金属质感、全息投影",
        "都市": "现代都市夜景、玻璃幕墙、街灯光晕",
        "玄幻": "奇幻光影、异世界元素、古风或魔幻色调",
    }
    mood = mood_map.get(tone, mood_map["玄幻"])

    # ── Assemble prompt (~200 chars) ────────────────────────────────
    book_name = title if title else "《未命名》"
    core_concept = promise if promise else (mechanism or situation or "宏大世界观下的冒险")
    if len(core_concept) > 60:
        core_concept = core_concept[:57] + "..."

    prompt = (
        f"中文网络小说封面，书名《{book_name}》作者[作者名]，"
        f"题材{tone}，核心概念：{core_concept}。"
        f"视觉风格：{mood}。"
        f"构图要求：竖版9:16，书名置于上方居中，醒目大字，"
        f"下方为核心场景插画，底部留白处放置作者署名。"
        f"整体精致，有出版级品质感。"
    )

    # Trim to ~220 chars max
    if len(prompt) > 220:
        prompt = prompt[:217] + "..."

    return prompt.strip()


def status_ok(status: str) -> bool:
    s = status.strip().lower()
    return any(x in s for x in READY_STATUSES) and not any(x in s for x in BLOCKED_STATUSES)


def fail(reason: str, evidence: str, suggestions: list[str], json_mode: bool = False) -> int:
    if json_mode:
        print(json.dumps({"status":"FAIL", "reason":reason, "evidence":evidence, "suggestions":suggestions}, ensure_ascii=False, indent=2))
    else:
        print("结论：FAIL")
        print(f"依据：{evidence}")
        print(f"问题：{reason}")
        print("建议：")
        for i, s in enumerate(suggestions[:3], 1):
            print(f"{i}. {s}")
        print("下一步：停止")
    return 1


def build_package(book: Path, chapter: int, row: dict, state: dict, cover_prompt: str = "") -> str:
    files = {rel: book / rel for rel in REQUIRED}
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    read_files = REQUIRED
    update_files = [
        "director/director_state.json5",
        "director/last_audit.md",
        "director/audit_log.md",
        "director/chapter_queue.md",
        "truth/current_state.md",
        "truth/resource_ledger.md",
        "truth/particle_ledger.md",
        "truth/pending_hooks.md",
    ]
    premise_hits = listify(row["premise_must_hit"])
    forbidden = listify(row["forbidden"])
    if not forbidden:
        forbidden = ["不得触犯 director/premise.md 与 director/forbidden_zones.md 中的禁飞区"]
    state_before = [
        "写前必须读取并遵守 truth/current_state.md",
        "写前必须核对 resource_ledger / particle_ledger / pending_hooks",
        f"director_state.currentChapter={state.get('currentChapter', '')}",
        f"director_state.activeVolume={state.get('activeVolume', '')}",
    ]
    beats = [
        {
            "goal": row["goal"] or "围绕本章目标建立场景推进",
            "conflict": "从 chapter_queue 目标中拆出直接阻碍；不得用无因果事故替代冲突",
            "turn": "本章中段必须产生状态变化、认知变化或资源变化",
            "hook": "章末钩子必须承接本章变化，并写入 pending_hooks 或 current_state",
        }
    ]
    lines = []
    lines.append(f"chapter: {chapter:04d}")
    lines.append(f"title_hint: {yaml_quote(row['title_hint'])}")
    lines.append(f"book_id: {yaml_quote(str(state.get('bookId', '')))}")
    lines.append(f"book_title: {yaml_quote(str(state.get('title', '')))}")
    lines.append(f"executor: {yaml_quote(str(state.get('executor', 'inkos')))}")
    lines.append(f"generated_at: {yaml_quote(now)}")
    lines.append(f"chapter_goal: {yaml_quote(row['goal'])}")
    lines.append("premise_must_hit:")
    lines.append(yaml_list(premise_hits))
    lines.append("forbidden:")
    lines.append(yaml_list(forbidden))
    lines.append("state_before:")
    lines.append(yaml_list(state_before))
    lines.append("beats:")
    for b in beats:
        lines.append(f"  - goal: {yaml_quote(b['goal'])}")
        lines.append(f"    conflict: {yaml_quote(b['conflict'])}")
        lines.append(f"    turn: {yaml_quote(b['turn'])}")
        lines.append(f"    hook: {yaml_quote(b['hook'])}")
    lines.append("continuity:")
    lines.append("  read_files:")
    lines.append(yaml_list(read_files, 4))
    lines.append("  update_files:")
    lines.append(yaml_list(update_files, 4))
    lines.append('audit_after: "level_1"')
    lines.append("director_context:")
    for rel in ["director/premise.md", "director/last_audit.md", "truth/current_state.md", "truth/pending_hooks.md"]:
        lines.append(f"  {rel.replace('/', '_').replace('.', '_')}: |-")
        ex = excerpt_file(book / rel)
        if not ex:
            lines.append("    ")
        else:
            for line in ex.splitlines():
                lines.append("    " + line)
    lines.append("post_write_required:")
    lines.append('  - "运行 chapter-review Level 1"')
    lines.append('  - "PASS 才能推进 currentChapter"')
    lines.append('  - "WARN/FAIL 必须写入 director/last_audit.md 与 director/audit_log.md"')
    lines.append('  - "更新 truth files，不得只输出正文"')
    if cover_prompt:
        lines.append(f"cover_prompt: {yaml_quote(cover_prompt)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--chapter", type=int)
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--with-cover", action="store_true",
                    help="Extract premise.md → generate cover_prompt field in package")
    args = ap.parse_args()
    book = Path(args.book_dir).resolve()

    missing = [rel for rel in REQUIRED if not (book / rel).exists()]
    if missing:
        return fail("缺少 director/truth 必需文件：" + ", ".join(missing), str(book), ["先运行 project-init/init_project.py", "补齐 premise 与 truth files", "再进入 execution-dispatch"], args.json)

    state = load_state(book / "director/director_state.json5")
    blockers = state.get("blockers") or []
    if isinstance(blockers, str):
        blockers = [blockers]
    if not state.get("canWrite", False):
        return fail("director_state.canWrite=false", "director/director_state.json5", ["先通过 outline-gate", "清空 blockers", "更新 canWrite=true 后再派发"], args.json)
    if blockers:
        return fail("存在未清除 blockers：" + ", ".join(map(str, blockers)), "director/director_state.json5", ["进入 repair-feedback", "修复后更新 last_audit", "清空 blockers 再派发"], args.json)

    chapter = args.chapter or int(state.get("currentChapter", 0)) + 1
    queue = parse_chapter_queue(book / "director/chapter_queue.md")
    row = next((r for r in queue if r["chapter"] == chapter), None)
    if not row:
        return fail(f"chapter_queue 中没有第 {chapter:04d} 章", "director/chapter_queue.md", ["先用 outline-gate 生成/审查该章细纲", "写入 chapter_queue", "状态必须为 PASS/READY/待写"], args.json)
    if not status_ok(row["status"]):
        return fail(f"第 {chapter:04d} 章状态不可写：{row['status']}", "director/chapter_queue.md", ["修复该章细纲", "将状态改为 PASS/READY/待写", "再生成任务包"], args.json)
    if not row["goal"] or not row["premise_must_hit"]:
        return fail(f"第 {chapter:04d} 章缺少 Goal 或 Premise Must Hit", "director/chapter_queue.md", ["补齐章节目标", "补齐本章必须兑现的命题元素", "重新过 outline-gate"], args.json)

    cover_prompt = ""
    if args.with_cover:
        premise_path = book / "director" / "premise.md"
        cover_prompt = extract_cover_prompt(premise_path)
        if not cover_prompt:
            print("警告：无法从 premise.md 提取封面 prompt（文件缺失或格式不完整）", file=sys.stderr)
    package = build_package(book, chapter, row, state, cover_prompt)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(package, encoding="utf-8")
        print("结论：PASS")
        print(f"依据：chapter_queue 第 {chapter:04d} 章；director_state.canWrite=true；blockers=0")
        print("问题：暂无")
        print("建议：1. 将任务包交给 inkos/执行器；2. 写后运行 chapter-review Level 1；3. 回写 director/truth")
        print(f"下一步：调用执行器，任务包={out}")
    else:
        print(package)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
