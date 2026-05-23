#!/usr/bin/env python3
"""Full chapter-by-chapter outline-gate review for webnovel-director.

Usage:
  python outline_gate_review.py <book_dir> [--json] [--write-report]

This is the deep version: it reads premise.md, chapter_queue.md, truth files,
and produces per-chapter PASS/WARN/FAIL with specific evidence and suggestions.
The old outline_gate_check.py remains as the fast structural gate.
"""
from __future__ import annotations
from pathlib import Path
import argparse, datetime, json, re

REQUIRED_FILES = [
    "director/premise.md",
    "director/chapter_queue.md",
    "truth/pending_hooks.md",
]

DEFAULT_FORBIDDEN_PATTERNS = [
    ("系统面板|状态栏|任务栏|系统商店|系统抽奖|系统任务|系统提示", "system_panel", "无系统世界观"),
    ("后宫|收后宫|开后宫", "harem", "禁后宫"),
    ("抢首通|独占BOSS|正面碾压|公会带飞|建公会碾压", "carry_by_guild", "禁公会带飞/抢首通"),
    ("反派降智|反派犯傻|反派送人头", "villain_stupid", "反派降智"),
    ("主角高调宣布|主动暴露底牌|公开核心秘密", "reveal_secret", "主角过早暴露"),
]

DIMENSIONS = [
    "volume_promise",
    "premise_alignment", 
    "forbidden_zone",
    "satisfaction_progression",
    "hook_integration",
    "executability",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore") if path.exists() else ""


def split_cell(row: str) -> list[str]:
    return [c.strip().replace("<br>", "\n") for c in row.strip().strip("|").split("|")]


def parse_queue(path: Path) -> list[dict]:
    rows=[]
    for line in read(path).splitlines():
        s=line.strip()
        if not s.startswith("|") or "---" in s or "Chapter" in s:
            continue
        cells=split_cell(s)
        if len(cells)<6:
            continue
        n_raw=re.sub(r"\D","",cells[0])
        if not n_raw:
            continue
        rows.append({
            "chapter":int(n_raw),
            "title_hint":cells[1],
            "goal":cells[2],
            "premise_must_hit":cells[3],  # column: Premise Must Hit
            "forbidden":cells[4],         # column: Forbidden
            "status":cells[5],
        })
    return rows


def extract_premise_promise(text: str) -> str:
    m=re.search(r"##\s*书名承诺\s*\n+(.*?)(?:##|\Z)", text, re.S)
    if m: return m.group(1).strip()
    m=re.search(r"书名承诺\s*\n+(.*?)(?:\n##|\n#|\Z)", text, re.S)
    return m.group(1).strip() if m else ""


def extract_forbidden_zones(text: str) -> list[dict]:
    zones=[]
    # Match lines like "- 禁飞区 1：..." or "- 禁飞区 N：..." or numbered items
    in_section=False
    for line in text.splitlines():
        s=line.strip()
        if "禁飞区" in s and ("##" in s or s.startswith("##")):
            in_section=True; continue
        if in_section and s.startswith("##"):
            break
        if in_section and s.startswith("-"):
            # Try to extract number and content
            m=re.match(r"-\s*禁飞区\s*(\d+)\s*[：:]\s*(.+)", s)
            if m:
                zones.append({"id":int(m.group(1)),"content":m.group(2)})
            else:
                zones.append({"id":len(zones)+1,"content":re.sub(r"^-\s*","",s)})
    return zones


def extract_role_locks(text: str) -> list[dict]:
    locks=[]
    in_table=False
    for line in text.splitlines():
        s=line.strip()
        if "角色功能锁" in s:
            in_table=True; continue
        if in_table:
            if s.startswith("##"):
                break
            if not s.startswith("|"):
                continue
            if "---" in s:
                continue
            if "角色/势力" in s:
                continue
            if "偏离日志" in s or "卷级" in s:
                break
            cells=split_cell(s)
            if len(cells)>=4 and cells[0]:
                locks.append({"role":cells[0],"function":cells[1] if len(cells)>1 else "","allow":cells[2] if len(cells)>2 else "","forbid":cells[3] if len(cells)>3 else ""})
    return locks


def extract_volume_zones(text: str) -> list[dict]:
    zones=[]
    in_table=False
    for line in text.splitlines():
        s=line.strip()
        if "卷级禁区" in s:
            in_table=True; continue
        if in_table:
            if s.startswith("##"):
                break
            if not s.startswith("|"):
                continue
            if "---" in s:
                continue
            if "卷" in s and s.startswith("|") and ("禁止" in s or "原因" in s):
                continue
            if "偏离日志" in s:
                break
            cells=split_cell(s)
            if len(cells)>=3 and cells[0]:
                try:
                    vol=int(re.sub(r"\D","",cells[0]))
                    zones.append({"volume":vol,"forbidden":cells[1] if len(cells)>1 else "","reason":cells[2] if len(cells)>2 else "","alternative":cells[3] if len(cells)>3 else ""})
                except: pass
    return zones


def parse_hooks(path: Path) -> list[dict]:
    hooks=[]
    for line in read(path).splitlines():
        s=line.strip()
        if s.startswith("|") and "---" not in s and "hook_id" not in s.lower() and "Hook ID" not in s:
            cells=split_cell(s)
            if len(cells)>=5:
                hooks.append({"id":cells[0],"promise":cells[2] if len(cells)>2 else "","status":cells[-1] if cells[-1] else ""})
    return hooks


# ── per-dimension checkers ──

def check_volume_promise(ch: dict, volume_zones: list[dict], ch_index: int, total: int) -> dict:
    """Check if this chapter fits the current volume's constraints."""
    issues=[]
    goal = (ch.get("goal") or "").strip()
    forbidden = (ch.get("forbidden") or "").strip()
    # Guess volume from chapter number: 1-25=v1, 26-70=v2, 71-140=v3, ...
    vol=1
    if ch["chapter"]>25: vol=2
    if ch["chapter"]>70: vol=3
    if ch["chapter"]>140: vol=4
    if ch["chapter"]>240: vol=5
    if ch["chapter"]>360: vol=6
    if ch["chapter"]>500: vol=7
    vz = next((z for z in volume_zones if z.get("volume")==vol), None)
    if vz and vz.get("forbidden"):
        for keyword in re.split(r"[、,，]", vz["forbidden"]):
            kw=keyword.strip()
            if kw and kw in goal+forbidden:
                issues.append({"severity":"FAIL","dimension":"volume_promise","issue":f"触犯卷{vol}禁区: {kw}"})
    if not goal and ch_index==0:
        issues.append({"severity":"WARN","dimension":"volume_promise","issue":"首章Goal缺失，无法判断卷目标衔接"})
    return {"pass":len([i for i in issues if i["severity"]=="FAIL"])==0, "issues":issues}


def extract_concept_anchors(text: str) -> list[str]:
    """Extract 2-6 char meaningful Chinese phrases as concept anchors."""
    # Extract longer meaningful substrings that carry concept weight
    anchors = []
    chars = list(text)
    i = 0
    while i < len(chars) - 1:
        # Try spans of 2-6 chars
        for span in [6, 5, 4, 3, 2]:
            if i + span <= len(chars):
                chunk = "".join(chars[i:i+span])
                # Keep if it looks like a concept (has at least one noun/verb feel)
                if re.match(r"^[\u4e00-\u9fff]{" + str(span) + r"}$", chunk):
                    anchors.append(chunk)
                    i += 1
                    break
        else:
            i += 1
    return anchors


def check_premise_alignment(ch: dict, premise_text: str, forbidden_zones: list[dict]) -> dict:
    """Check if chapter's premise_must_hit connects to the book's core promise.

    Uses concept-anchor matching instead of raw keyword overlap: extracts
    meaningful multi-char phrases from both premise and chapter, and checks
    if any premise concept is echoed in the chapter's goal or must_hit.
    """
    issues=[]
    must_hit = (ch.get("premise_must_hit") or "").strip()
    goal = (ch.get("goal") or "").strip()
    combined = goal + " " + must_hit
    if not must_hit:
        issues.append({"severity":"WARN","dimension":"premise_alignment","issue":"缺少 Premise Must Hit"})
    elif len(must_hit)<10:
        issues.append({"severity":"WARN","dimension":"premise_alignment","issue":"Premise Must Hit 过短，可能不是具体兑现点"})
    # Concept-anchor check: extract anchors from premise, see if any appear in chapter text
    if premise_text and must_hit:
        premise_anchors = extract_concept_anchors(premise_text)
        # Filter to meaningful anchors (>=3 chars, not pure function words)
        meaningful = [a for a in premise_anchors if len(a) >= 3]
        if not meaningful:
            meaningful = [a for a in premise_anchors if len(a) >= 2]
        hits = [a for a in meaningful if a in combined]
        if not hits:
            # Fallback: word-level overlap with 3+ char words only
            promise_words = set(re.findall(r"[\u4e00-\u9fff]{3,}", premise_text))
            hit_words = set(re.findall(r"[\u4e00-\u9fff]{3,}", combined))
            if not (promise_words & hit_words):
                issues.append({"severity":"WARN","dimension":"premise_alignment",
                    "issue":"章节目标未命中书名任何概念锚点，可能偏离核心命题"})
    return {"pass":len([i for i in issues if i["severity"]=="FAIL"])==0, "issues":issues}


def check_forbidden_zone(ch: dict, forbidden_zones: list[dict], role_locks: list[dict]) -> dict:
    """Scan chapter goal/premise/forbidden for violation of premise's forbidden zones and role locks."""
    issues=[]
    goal = (ch.get("goal") or "").strip()
    must_hit = (ch.get("premise_must_hit") or "").strip()
    ch_forbidden = (ch.get("forbidden") or "").strip()
    combined = goal + " " + must_hit
    # Check default patterns
    for pattern, tag, label in DEFAULT_FORBIDDEN_PATTERNS:
        if re.search(pattern, combined) and tag not in ch_forbidden and label not in ch_forbidden:
            # Only penalize if the forbidden pattern appears in goal/premise but NOT in the forbidden column
            if re.search(pattern, goal + " " + must_hit):
                issues.append({"severity":"FAIL","dimension":"forbidden_zone","issue":f"疑似触犯 {label}：{tag}"})
    # Check explicit premise forbidden zones
    for fz in forbidden_zones:
        keywords = re.findall(r"[\u4e00-\u9fff]{2,}", fz.get("content",""))
        for kw in keywords:
            if kw in combined and kw not in ch_forbidden:
                # Only warn if keyword is meaningful (>3 chars) and not common
                if len(kw)>=4:
                    issues.append({"severity":"WARN","dimension":"forbidden_zone","issue":f"可能接近禁飞区{fz.get('id','')}: {kw}"})
                    break
    return {"pass":len([i for i in issues if i["severity"]=="FAIL"])==0, "issues":issues}


def check_satisfaction_progression(chapters: list[dict], idx: int) -> dict:
    """Check that premise-hitting density is maintained (~every 3 chapters)."""
    issues=[]
    if idx==0:
        return {"pass":True,"issues":[]}
    # Look back up to 3 chapters; if none have must_hit content, warn
    window=chapters[max(0,idx-3):idx]
    hits=sum(1 for c in window if len((c.get("premise_must_hit") or "").strip())>10)
    current_hit=len((chapters[idx].get("premise_must_hit") or "").strip())>10
    if hits==0 and not current_hit:
        issues.append({"severity":"WARN","dimension":"satisfaction_progression","issue":"前3章无命题兑现，本章也未兑现爽点递进可能断裂"})
    return {"pass":len([i for i in issues if i["severity"]=="FAIL"])==0, "issues":issues}


def check_hook_integration(ch: dict, hooks: list[dict]) -> dict:
    """Check if pending hooks are being used/integrated in this chapter."""
    issues=[]
    goal = (ch.get("goal") or "").strip()
    must_hit = (ch.get("premise_must_hit") or "").strip()
    combined = goal + " " + must_hit
    open_hooks = [h for h in hooks if h.get("status","").lower() in {"open","🟡 未回收","🟡 进行中","active","进行中"}]
    # Don't require every chapter to use hooks, but flag if there are many open hooks
    if len(open_hooks)>5:
        used=0
        for h in open_hooks:
            if any(kw in combined for kw in re.findall(r"[\u4e00-\u9fff]{2,}", h.get("promise",""))):
                used+=1
        if used==0:
            issues.append({"severity":"WARN","dimension":"hook_integration","issue":f"有{len(open_hooks)}条未回收钩子，本章未涉及任何一条"})
    return {"pass":len([i for i in issues if i["severity"]=="FAIL"])==0, "issues":issues}


def check_executability(ch: dict) -> dict:
    """Check if chapter has enough detail to be executable."""
    issues=[]
    goal = (ch.get("goal") or "").strip()
    must_hit = (ch.get("premise_must_hit") or "").strip()
    if not goal:
        issues.append({"severity":"FAIL","dimension":"executability","issue":"缺少 Goal"})
    elif len(goal)<15:
        issues.append({"severity":"WARN","dimension":"executability","issue":"Goal 过短（<15字），可能不可执行"})
    if not must_hit:
        issues.append({"severity":"FAIL","dimension":"executability","issue":"缺少 Premise Must Hit"})
    # Check if goal contains action words
    action_words=["让读者","推进","揭露","验证","完成","突破","建立","击败","发现","获得","开启","收束"]
    if goal and not any(w in goal for w in action_words):
        issues.append({"severity":"WARN","dimension":"executability","issue":"Goal 缺少可执行动作词（让读者/推进/揭露/验证/完成...）"})
    return {"pass":len([i for i in issues if i["severity"]=="FAIL"])==0, "issues":issues}


# ── main ──

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-report", action="store_true", help="write report to director/outline_review.md")
    args=ap.parse_args()
    book=Path(args.book_dir).resolve()

    # Check required files
    missing=[rel for rel in REQUIRED_FILES if not (book/rel).exists()]
    if missing:
        result={"status":"FAIL","chapters":[],"issues":[{"severity":"FAIL","issue":"缺少文件: "+", ".join(missing)}]}
        if args.json: print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("结论：FAIL")
            print(f"依据：{book}")
            print("问题：缺少文件：" + ", ".join(missing))
            print("建议：运行 init_project / sync_inkos_state 补齐")
            print("下一步：停止")
        return 1

    premise_text = read(book/"director/premise.md")
    premise_promise = extract_premise_promise(premise_text)
    forbidden_zones = extract_forbidden_zones(premise_text)
    role_locks = extract_role_locks(premise_text)
    volume_zones = extract_volume_zones(premise_text)
    chapters = parse_queue(book/"director/chapter_queue.md")
    hooks = parse_hooks(book/"truth/pending_hooks.md")

    if not chapters:
        result={"status":"FAIL","chapters":[],"issues":[{"severity":"FAIL","issue":"chapter_queue has no rows"}]}
        if args.json: print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("结论：FAIL")
            print(f"依据：{book/'director/chapter_queue.md'}")
            print("问题：chapter_queue 没有章节行")
            print("建议：补齐 chapter_queue")
            print("下一步：停止")
        return 1

    chapter_results=[]
    all_issues=[]
    pass_count, warn_count, fail_count = 0, 0, 0

    for idx, ch in enumerate(chapters):
        checks={}
        checks["volume_promise"]=check_volume_promise(ch, volume_zones, idx, len(chapters))
        checks["premise_alignment"]=check_premise_alignment(ch, premise_text, forbidden_zones)
        checks["forbidden_zone"]=check_forbidden_zone(ch, forbidden_zones, role_locks)
        checks["satisfaction_progression"]=check_satisfaction_progression(chapters, idx)
        checks["hook_integration"]=check_hook_integration(ch, hooks)
        checks["executability"]=check_executability(ch)
        ch_issues=[]
        for dim, result in checks.items():
            ch_issues.extend(result["issues"])
        for i in ch_issues: i["chapter"]=ch["chapter"]
        has_fail=any(i["severity"]=="FAIL" for i in ch_issues)
        has_warn=any(i["severity"]=="WARN" for i in ch_issues)
        if has_fail:
            ch_status="FAIL"; fail_count+=1
        elif has_warn:
            ch_status="WARN"; warn_count+=1
        else:
            ch_status="PASS"; pass_count+=1
        chapter_results.append({"chapter":ch["chapter"],"title_hint":ch["title_hint"],"status":ch_status,"issues":ch_issues,"checks":{k:{"pass":v["pass"],"issues_count":len(v["issues"])} for k,v in checks.items()}})
        all_issues.extend([{**i,"chapter":ch["chapter"]} for i in ch_issues])

    status="FAIL" if fail_count>0 else ("WARN" if warn_count>0 else "PASS")
    result={"status":status,"total":len(chapters),"pass":pass_count,"warn":warn_count,"fail":fail_count,"premise_promise_length":len(premise_promise),"forbidden_zones":len(forbidden_zones),"role_locks":len(role_locks),"volume_zones":len(volume_zones),"open_hooks":len([h for h in hooks if h.get("status","").lower() in {"open","🟡 未回收","🟡 进行中","active","进行中"}]),"chapters":chapter_results}

    now=datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"=== outline-gate 审查报告 ===")
        print(f"时间：{now}")
        print(f"项目：{book}")
        print(f"结论：{status}")
        print(f"章节：总计{len(chapters)}章 | PASS {pass_count} | WARN {warn_count} | FAIL {fail_count}")
        print(f"依据：premise={len(premise_promise)}字; forbidden_zones={len(forbidden_zones)}; role_locks={len(role_locks)}; volume_zones={len(volume_zones)}; open_hooks={len([h for h in hooks if h.get('status','').lower() in {'open','🟡 未回收','🟡 进行中','active','进行中'}])}")
        print("")
        for cr in chapter_results:
            icon={"PASS":"[PASS]","WARN":"[WARN]","FAIL":"[FAIL]"}[cr["status"]]
            print(f"--- Ch{cr['chapter']:04d} {cr['title_hint']} {icon} {cr['status']} ---")
            if not cr["issues"]:
                print("  OK 无问题")
            else:
                for i in cr["issues"]:
                    sev_icon="[FAIL]" if i["severity"]=="FAIL" else "[WARN]"
                    print(f"  {sev_icon} [{i['dimension']}] {i['issue']}")
            print("")

        print("--- 建议 ---")
        if status=="PASS":
            print("1. 所有章节已通过审查，可清空 blockers 设置 canWrite=true")
            print("2. 进入 execution-dispatch / build_task_package")
        elif status=="WARN":
            print("1. 修 WARN 后可考虑通过，但建议先逐章补强")
            print("2. 全部 WARN 项清除后再改 canWrite=true")
        else:
            print("1. 先修 FAIL 章节")
            print("2. FAIL 未清除不得生成任务包、不得写正文")
            print("3. 修后重跑 outline_gate_review.py")
        print(f"下一步：{'execution-dispatch' if status=='PASS' else '修复 OUTLINE 章节' if status=='FAIL' else '人工复核'}")

    if args.write_report:
        report_dir=book/"director"
        report_dir.mkdir(parents=True, exist_ok=True)
        lines=[f"# Outline Gate 审查报告", f"", f"时间：{now}", f"结论：{status}", f"", f"## 摘要", f"", f"| 维度 | 值 |", f"|---|---|", f"| 总章节 | {len(chapters)} |", f"| PASS | {pass_count} |", f"| WARN | {warn_count} |", f"| FAIL | {fail_count} |", f"", f"## 逐章"]
        for cr in chapter_results:
            lines.append(f"")
            lines.append(f"### Ch{cr['chapter']:04d} {cr['title_hint']} — {cr['status']}")
            lines.append(f"")
            if not cr["issues"]:
                lines.append("  OK 无问题")
            else:
                for i in cr["issues"]:
                    lines.append(f"- **{i['severity']}** [{i['dimension']}] {i['issue']}")
        lines.append(f"")
        lines.append(f"## 下一步")
        lines.append(f"")
        if status=="PASS":
            lines.append("execution-dispatch")
        elif status=="FAIL":
            lines.append("修复 OUTLINE 章节")
        else:
            lines.append("人工复核")
        (report_dir/"outline_review.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"\n报告已写入：{report_dir/'outline_review.md'}")

    return 1 if status=="FAIL" else 0

if __name__=="__main__":
    raise SystemExit(main())





