#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""细纲自动扩展工具。

从卷纲+已写章节+人物矩阵推演新的细纲条目，写入 chapter_queue。

规则:
  - 始终保持当前章之前至少有 5 章细纲储备
  - 每次最多生成 10 章新细纲
  - 生成内容必须通过禁飞区+命题检查
  - 状态标记为 QUEUE

用法:
  python extend_outline.py <book_dir>                   # 仅检查储备状态
  python extend_outline.py <book_dir> --generate 5      # 生成5章新细纲
  python extend_outline.py <book_dir> --auto            # 自动: 储备<5章则补齐到+5章
"""

from __future__ import annotations
import argparse, json, os, re, sys, urllib.request
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="ignore") if p.exists() else ""

def write_text(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

def parse_queue(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 8 or not cells[0].isdigit():
            continue
        rows.append({
            "ch": int(cells[0]), "title": cells[1], "goal": cells[2],
            "premise": cells[3], "scenes": cells[4], "words": cells[5],
            "forbidden": cells[6], "status": cells[7],
        })
    return rows

def format_queue_row(row: dict) -> str:
    return f"| {row['ch']} | {row['title']} | {row['goal']} | {row['premise']} | {row['scenes']} | {row['words']} | {row['forbidden']} | {row['status']} |"

def check_reserve(book_dir: Path) -> dict:
    """检查细纲储备状态。返回 {current_ch, last_outline, reserve, need_more}"""
    state_path = book_dir / "director" / "director_state.json5"
    qp = book_dir / "director" / "chapter_queue.md"

    state_text = read_text(state_path)
    m = re.search(r"currentChapter\s*:\s*(\d+)", state_text)
    current_ch = int(m.group(1)) if m else 0

    if not qp.exists():
        return {"current_ch": current_ch, "last_outline": 0, "reserve": 0, "need_more": True}

    queue = parse_queue(read_text(qp))
    if not queue:
        return {"current_ch": current_ch, "last_outline": 0, "reserve": 0, "need_more": True}

    last_outline = max(r["ch"] for r in queue)
    # Reserve = how many chapters of outline exist beyond current position
    reserve = max(0, last_outline - current_ch)
    need_more = reserve < 5
    return {
        "current_ch": current_ch, "last_outline": last_outline,
        "reserve": reserve, "need_more": need_more,
    }

def get_volume_context(book_dir: Path, current_ch: int) -> str:
    """获取当前卷的结构上下文。"""
    vm_path = book_dir / "director" / "volume_map.md"
    if not vm_path.exists():
        vm_path = book_dir / "story" / "outline" / "volume_map.md"
    if not vm_path.exists():
        return ""
    text = read_text(vm_path)
    # Extract current volume info
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and "---" not in s and re.match(r"\|\s*[一二三四五六]+\s*\|", s):
            lines.append(s)
        if re.match(r"\|\s*\d+\s*[-–]\s*\d+\s*\|", s):
            m2 = re.search(r"(\d+)\s*[-–]\s*(\d+)", s)
            if m2 and int(m2.group(1)) <= current_ch <= int(m2.group(2)):
                lines.append(s)
    return "\n".join(lines[-10:])

def get_recent_chapters(book_dir: Path, current_ch: int, count: int = 5) -> str:
    """获取最近N章正文摘要。"""
    ch_dir = book_dir / "正文"
    if not ch_dir.exists():
        return ""
    summaries = []
    for ch in range(max(1, current_ch - count + 1), current_ch + 1):
        candidates = list(ch_dir.glob(f"第{ch:02d}章*.md")) + list(ch_dir.glob(f"第0{ch}章*.md"))
        if not candidates:
            continue
        text = read_text(candidates[0])
        # Extract first and last 200 chars as summary
        start = text.strip()[:200].replace("\n", " ")
        end = text.strip()[-200:].replace("\n", " ") if len(text.strip()) > 200 else ""
        summaries.append(f"第{ch}章: {start}...")
    return "\n".join(summaries)

def build_generation_prompt(book_dir: Path, current_ch: int, count: int) -> str:
    """构建 LLM 细纲生成提示词。"""
    premise = read_text(book_dir / "director" / "premise.md")
    vol_ctx = get_volume_context(book_dir, current_ch)
    recent = get_recent_chapters(book_dir, current_ch)
    char_matrix = read_text(book_dir / "story" / "character_matrix.md")

    # Get existing queue entries for pattern matching
    qp = book_dir / "director" / "chapter_queue.md"
    existing_queue = ""
    if qp.exists():
        existing = parse_queue(read_text(qp))
        recent_entries = [r for r in existing if r["ch"] <= current_ch][-5:]
        existing_queue = "\n".join(
            f"第{r['ch']}章 {r['title']}: Goal={r['goal'][:50]}, MustHit={r['premise'][:50]}"
            for r in recent_entries
        )

    prompt = f"""你是长篇网文《逃离轮回》的细纲规划师。请生成接下来 {count} 章的细纲。

## 小说命题与禁飞区
{premise[:2000]}

## 当前卷纲
{vol_ctx[:1000]}

## 最近已写章节摘要
{recent[:2000]}

## 已写章节的细纲参考
{existing_queue[:1000]}

## 人物矩阵
{char_matrix[:1000]}

## 要求
1. 生成第 {current_ch + 1} 到第 {current_ch + count} 章的细纲
2. 每章包含: 章节标题、Goal（本章目标）、Premise Must Hit（必须兑现的命题元素）、Forbidden（本章禁飞区）
3. 章节需承接上一章的结尾（第 {current_ch} 章）
4. 严格避免触犯禁飞区
5. 每章目标清晰具体，可分步执行
6. 输出格式（纯文本，每行一个JSON对象）:

{{"ch": {current_ch + 1}, "title": "标题", "goal": "本章目标描述", "premise": "必须兑现的命题", "forbidden": ""}}
{{"ch": {current_ch + 2}, "title": "标题", "goal": "本章目标描述", "premise": "必须兑现的命题", "forbidden": ""}}
...

只输出 JSON 行，不要其他内容。"""
    return prompt

def call_llm(prompt: str) -> str:
    """调用 LLM API。"""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    if not api_key:
        return ""
    url = f"{base_url}/chat/completions"
    data = json.dumps({
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7, "max_tokens": 4096,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  LLM 调用失败: {e}")
        return ""

def append_to_queue(book_dir: Path, new_rows: list[dict]):
    """追加新细纲到 chapter_queue。"""
    qp = book_dir / "director" / "chapter_queue.md"
    existing = read_text(qp)
    # Remove trailing whitespace and add new rows
    existing = existing.rstrip() + "\n"
    for row in new_rows:
        row["scenes"] = row.get("scenes", "")
        row["words"] = row.get("words", "0")
        row["status"] = "QUEUE"
        existing += format_queue_row(row) + "\n"
    write_text(qp, existing)

def generate(book_dir: Path, count: int) -> list[dict]:
    """生成细纲并写入。"""
    reserve = check_reserve(book_dir)
    current_ch = reserve["current_ch"]
    if current_ch == 0:
        print("错误: 未找到 currentChapter")
        return []

    actual_count = min(count, 10)
    print(f"当前进度: 第{current_ch}章, 细纲储备: {reserve['reserve']}章")
    print(f"生成目标: +{actual_count}章")

    prompt = build_generation_prompt(book_dir, current_ch, actual_count)
    print("调用 LLM 生成细纲...")
    response = call_llm(prompt)

    if not response:
        print("LLM 未返回结果")
        return []

    # Parse JSON lines
    new_rows = []
    for line in response.strip().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            if "ch" in obj and "title" in obj:
                new_rows.append({
                    "ch": obj["ch"], "title": obj["title"],
                    "goal": obj.get("goal", ""), "premise": obj.get("premise", ""),
                    "forbidden": obj.get("forbidden", ""),
                })
                print(f"  生成: 第{obj['ch']}章 {obj['title']}")
        except json.JSONDecodeError:
            continue

    if new_rows:
        append_to_queue(book_dir, new_rows)
        print(f"\n已生成 {len(new_rows)} 章细纲并写入 chapter_queue")
        
        # Run outline-gate review on the new entries
        print("运行 outline-gate 审查...")
        import subprocess
        scripts = str(SCRIPTS_DIR)
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(scripts, "outline_gate_review.py"), str(book_dir), "--json"],
                capture_output=True, timeout=60,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
            )
            output = result.stdout.decode("utf-8", errors="replace")
            if "FAIL" in output[:500]:
                print(f"  WARN: outline-gate 检测到 FAIL — 请人工复核后修改")
            elif "WARN" in output[:500]:
                print(f"  INFO: outline-gate WARN — 可接受，建议检查")
            else:
                print(f"  PASS: outline-gate 审查通过")
        except Exception as e:
            print(f"  WARN: outline-gate 无法运行 ({e})")
    return new_rows

def main() -> int:
    ap = argparse.ArgumentParser(description="细纲自动扩展工具")
    ap.add_argument("book_dir", help="项目目录")
    ap.add_argument("--generate", type=int, help="生成N章新细纲")
    ap.add_argument("--auto", action="store_true", help="自动补齐到+5章储备")
    args = ap.parse_args()

    book_dir = Path(args.book_dir).resolve()
    if not (book_dir / "director").exists():
        print("不是有效的 webnovel-director 项目")
        return 1

    if args.generate:
        generate(book_dir, args.generate)
        return 0

    if args.auto:
        reserve = check_reserve(book_dir)
        print(f"第{reserve['current_ch']}章 | 细纲储备: {reserve['reserve']}章 | 至第{reserve['last_outline']}章")
        if reserve["need_more"]:
            needed = 5 - reserve["reserve"]
            print(f"储备不足, 自动生成 {needed} 章")
            generate(book_dir, needed)
        else:
            print("储备充足, 无需生成")
        return 0

    # Default: just check
    reserve = check_reserve(book_dir)
    print(f"当前: 第{reserve['current_ch']}章 | 细纲至: 第{reserve['last_outline']}章 | 储备: {reserve['reserve']}章")
    print("状态: " + ("需要扩展" if reserve['need_more'] else "充足"))
    return 0 if not reserve['need_more'] else 1

if __name__ == "__main__":
    raise SystemExit(main())
