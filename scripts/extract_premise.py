#!/usr/bin/env python3
"""Extract premise draft from existing story files.

Usage:
  python extract_premise.py <book_dir> [--out premise.md] [--json]

Reads story/outline/volume_map.md, story/author_intent.md, story/book_rules.md,
story/outline/story_frame.md (if present), and produces a draft director/premise.md.

This is a FIRST DRAFT generator. Human review is mandatory before using it as
the director's truth source.
"""
from __future__ import annotations
from pathlib import Path
import sys
_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import read_text
import argparse, datetime, json, re


def extract_section(text: str, heading: str) -> str:
    """Extract content under a markdown heading."""
    pat = rf"##\s*{re.escape(heading)}.*?\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pat, text, re.S)
    if m:
        return m.group(1).strip()
    # Try bullet-level
    pat2 = rf"\*?\*?{re.escape(heading)}[\*:：\s]*\n(.*?)(?=\n\*?\*|\Z)"
    m2 = re.search(pat2, text, re.S)
    return m2.group(1).strip() if m2 else ""


def extract_list_items(text: str) -> list[str]:
    """Extract items from a bullet/table/list."""
    items = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("-") or s.startswith("*") or s.startswith("❌"):
            item = re.sub(r"^[-*❌]\s*", "", s).strip()
            if item:
                items.append(item)
        elif re.match(r"^\d+\.", s):
            item = re.sub(r"^\d+\.\s*", "", s).strip()
            if item:
                items.append(item)
    return items


def extract_table_rows(text: str) -> list[dict]:
    rows = []
    headers = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and "---" in s:
            headers = [h.strip() for h in s.strip("|").split("|")]
            continue
        if "---" in s:
            continue
        if s.startswith("|") and headers:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= len(headers):
                row = {}
                for i, h in enumerate(headers):
                    if i < len(cells):
                        row[h] = cells[i]
                if any(v for v in row.values()):
                    rows.append(row)
    return rows


def build_premise(book_dir: Path, meta: dict) -> str:
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    title = meta.get("title") or book_dir.name

    # Read source files
    intent_text = read_text(book_dir / "story" / "author_intent.md")
    rules_text = read_text(book_dir / "story" / "book_rules.md")
    volume_text = read_text(book_dir / "story" / "outline" / "volume_map.md")
    frame_text = read_text(book_dir / "story" / "outline" / "story_frame.md")

    # 书名承诺
    one_liner = extract_section(intent_text, "一句话") or ""
    if not one_liner:
        # Try to build from core sell points
        sells = extract_list_items(extract_section(intent_text, "核心卖点") or "")
        one_liner = "; ".join(sells[:3]) if sells else title

    # 禁飞区
    forbidden_items = extract_list_items(extract_section(intent_text, "禁止") or "")
    if not forbidden_items:
        # Check book_rules
        rules_forbid = extract_list_items(extract_section(rules_text, "世界观硬规则") or "")
        forbidden_items = [r for r in rules_forbid if any(w in r for w in ["不能", "禁止", "不可", "无"])]
    if not forbidden_items:
        forbidden_items = ["待填写：本书禁止的套路方向"]

    # 卷级禁区
    vol_zones = []
    for line in volume_text.splitlines():
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*[^|]+\s*\|\s*[^|]+\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            vol_name = m.group(1).strip()
            theme = m.group(2).strip()
            vol_zones.append(f"| {vol_name} | 待填写 | {theme} | 待填写 |")

    # 角色功能锁
    role_table = extract_table_rows(extract_section(intent_text, "角色") or "")

    lines = []
    lines.append(f"# {title} - Premise")
    lines.append("")
    lines.append("## 书名承诺")
    lines.append("")
    lines.append(f"> {one_liner}")
    lines.append("")
    lines.append("## 命题三要素")
    lines.append("")
    lines.append("1. **主角处境**：待填写——从 author_intent.md 提取的建议见下文")
    lines.append("2. **核心爽点机制**：待填写")
    lines.append("3. **长线代价 / 反噬 / 更大问题**：待填写")
    lines.append("")

    # Source material hints
    sells = extract_list_items(extract_section(intent_text, "核心卖点") or "")
    if sells:
        lines.append("> 从 author_intent.md 核心卖点中提取到的线索：")
        for s in sells[:5]:
            lines.append(f"> - {s}")
        lines.append("")

    lines.append("## 禁飞区")
    lines.append("")
    for i, f in enumerate(forbidden_items[:8], 1):
        lines.append(f"- 禁飞区 {i}：{f}")
    lines.append("")

    lines.append("## 角色功能锁")
    lines.append("")
    lines.append("| 角色/势力 | 叙事功能 | 允许做什么 | 禁止越界 |")
    lines.append("|---|---|---|---|")
    if role_table:
        for r in role_table[:12]:
            name = r.get("名称") or r.get("角色") or r.get("姓名") or ""
            role = r.get("定位") or r.get("类型") or r.get("身份") or ""
            lines.append(f"| {name} | {role} | 待填写 | 待填写 |")
    else:
        lines.append("| 主角 | 核心机制执行者 | 待填写 | 待填写 |")
        lines.append("| 对手 | 压力与误判来源 | 待填写 | 待填写 |")
        lines.append("| 盟友 | 情报/代价/镜像 | 待填写 | 待填写 |")
    lines.append("")

    lines.append("## 卷级禁区")
    lines.append("")
    lines.append("| 卷 | 禁止方向 | 原因 | 替代爽点 |")
    lines.append("|---|---|---|---|")
    if vol_zones:
        for vz in vol_zones:
            lines.append(vz)
    else:
        lines.append("| 1 | 待填写 | 待填写 | 待填写 |")
    lines.append("")

    lines.append("## 偏离日志")
    lines.append("")
    lines.append("| 日期 | 对象 | 判定 | 原因 | 处理 |")
    lines.append("|---|---|---|---|---|")
    lines.append(f"| {now[:10]} | 由 extract_premise.py 自动生成 | WARN | 需人工复核和填写命题三要素 | 待填写 |")

    lines.append("")
    lines.append("---")
    lines.append(f"> ⚠️ 本文件由 `scripts/extract_premise.py` 从现有 story 文件自动生成初稿。")
    lines.append("> 必须人工填写命题三要素、角色功能锁、卷级禁区后，再由 `outline_gate_review.py` 审查。")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    book = Path(args.book_dir).resolve()

    missing = []
    for rel in ["story/author_intent.md", "story/book_rules.md", "story/outline/volume_map.md"]:
        if not (book / rel).exists():
            missing.append(rel)

    meta = {}
    bj = book / "book.json"
    if bj.exists():
        try:
            meta = json.loads(read_text(bj))
        except Exception:
            pass

    premise = build_premise(book, meta)
    sources_count = 3 - len(missing)
    issues = [{"severity": "WARN", "issue": f"missing {m}"} for m in missing]

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(premise, encoding="utf-8")

    result = {"status": "WARN" if issues else "PASS", "sources_found": sources_count, "issues": issues, "output": args.out}

    if args.json:
        result["premise_length"] = len(premise)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("结论：" + ("WARN" if missing else "PASS"))
        print(f"依据：book={book}; sources_found={sources_count}")
        print("问题：" + ("暂无" if not issues else "; ".join(i["issue"] for i in issues)))
        print("建议：1. 人工填写命题三要素；2. 补全角色功能锁；3. outline_gate_review 审查后再使用")
        print("下一步：人工复核，进入 outline-gate")
        if args.out:
            print(f"\n初稿已写入：{args.out}")
        if not args.out:
            print("\n--- 初稿预览 ---")
            # Print without emoji that break GBK
            safe = premise[:3000].replace('❌','[X]').replace('⚠','[!]')
            print(safe)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
