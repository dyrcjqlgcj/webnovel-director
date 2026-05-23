#!/usr/bin/env python3
"""Concept validation gate for webnovel-director.

Usage:
  python concept_gate.py <concept_file.yaml>
  python concept_gate.py --inline "书名: xxx\n主角: xxx\n金手指: xxx"

Input: A YAML file or inline string with these fields:
  书名: (optional) tentative title
  梗概: (required) one-sentence summary, <50 chars
  金手指: (required) protagonist's unique ability/advantage
  世界观: (required) 2-3 sentences about the world
  对标: (optional) up to 2 comparable books
  字数: (optional) target word count
  平台: (optional) target platform, default 番茄
"""

from __future__ import annotations
import argparse, json, re, sys, yaml

WEIGHTS = {
    "protagonist_uniqueness": 25,
    "satisfaction_visibility": 25,
    "sustainability": 15,
    "market_fit": 15,
    "differentiation": 10,
    "finger_gradient": 10,
}

# Known failure patterns from 2026-05-23 testing
FAILURE_PATTERNS = [
    # Pattern, dimension, explanation
    (r"(更耐心|更聪明|更努力|更勤奋|更细心).{0,10}(观察|学习|思考)", "protagonist_uniqueness",
     "主角优势是'更X'型——这是人设，不是不可替代的机制优势"),
    (r"(所有人都能|每人都有|公开.{0,5}可以|大家都能)", "protagonist_uniqueness",
     "主角的优势没有排他性——别人也能做到"),
    (r"(开局.{0,5}无敌|SSS|顶级|满级|巅峰).{0,10}(能力|技能|装备|领地|资质)", "finger_gradient",
     "金手指一步登天——没有成长梯度"),
    (r"(秒杀|碾压|吊打).{0,15}(所有|一切|全局)", "finger_gradient",
     "爽点太早触顶——敌人全部弱于主角"),
    (r"(慢慢|逐渐|越来越).{0,5}(变强|升级|成长)", "satisfaction_visibility",
     "'慢慢变强'不是可视爽点——需要一个具体场景"),
]


def score_protagonist_uniqueness(concept: dict) -> tuple[int, list[str]]:
    gold = concept.get("金手指", "")
    summary = concept.get("梗概", "")
    combined = f"{gold}\n{summary}"
    issues = []
    score = 5
    # Check if the advantage is mechanism-level (not personality)
    mech_keywords = ["只有", "独占", "唯一", "免疫", "别人不能", "没人知道", "系统BUG", "隐藏", "未公开"]
    if any(kw in combined for kw in mech_keywords):
        score += 3
    # Check if advantage is personality-based (negative)
    personality_keywords = ["更耐心", "更聪明", "更努力", "更细心", "性格", "人好", "善良"]
    hits = [kw for kw in personality_keywords if kw in combined]
    if hits:
        score -= len(hits)
        issues.append(f"疑似人格型优势: {', '.join(hits)}（应改为机制型）")
    # Check exclusivity
    public_keywords = ["所有人都能", "每人都有", "公开的", "大家都能"]
    if any(kw in combined for kw in public_keywords):
        score -= 3
        issues.append("主角优势没有排他性——别人也能做到")
    # Floor/ceiling
    score = max(0, min(10, score))
    return score, issues


def score_satisfaction_visibility(concept: dict) -> tuple[int, list[str]]:
    gold = concept.get("金手指", "")
    summary = concept.get("梗概", "")
    combined = f"{gold}\n{summary}"
    issues = []
    score = 5
    # Check for visual satisfaction scenes
    visual_keywords = ["发现", "获得", "解锁", "开启", "第一个", "首次", "触发", "弹出"]
    if any(kw in combined for kw in visual_keywords):
        score += 2
    # Check for one-sentence spreadability
    if len(summary) <= 30:
        score += 1
    else:
        issues.append("梗概过长（>30字），不利于一句话传播")
    # Check if satisfaction is immediate vs delayed
    delay_keywords = ["30章后", "50章后", "中后期才", "渐渐"]
    if any(kw in combined for kw in delay_keywords):
        score -= 3
        issues.append("爽点太靠后——读者撑不到那个时候")
    score = max(0, min(10, score))
    return score, issues


def score_sustainability(concept: dict) -> tuple[int, list[str]]:
    world = concept.get("世界观", "")
    gold = concept.get("金手指", "")
    combined = f"{world}\n{gold}"
    issues = []
    score = 5
    # Check for tiered progression
    tier_keywords = ["层", "级", "阶段", "卷", "境界", "副本", "地图", "区域", "世界"]
    if any(kw in combined for kw in tier_keywords):
        score += 2
    # Check for expansion space
    expand_keywords = ["扩展", "扩张", "解锁新", "更高", "更深", "更远", "下一", "进阶"]
    if any(kw in combined for kw in expand_keywords):
        score += 1
    # Check for narrow world
    narrow_keywords = ["一间", "一个小", "一个房间", "永远在这", "没有其他"]
    if any(kw in combined for kw in narrow_keywords):
        score -= 3
        issues.append("世界观太窄——可能撑不起长篇")
    # Check for finite goal
    finite_keywords = ["找到", "杀死", "获得"]  # only if it's a SINGLE goal
    if re.search(r"(只要|只需|只需要).{0,10}(找到|杀死|获得)", combined):
        score -= 2
        issues.append("核心目标是单次事件——完成后没有内容了")
    score = max(0, min(10, score))
    return score, issues


def score_market_fit(concept: dict) -> tuple[int, list[str]]:
    platform = concept.get("平台", "番茄")
    competitors = concept.get("对标", "")
    issues = []
    score = 5
    if competitors:
        score += 2
    else:
        issues.append("没有提供对标书名——市场匹配度无法验证")
    # Platform-specific bonuses
    if platform == "番茄":
        fanqie_keywords = ["系统", "重生", "穿越", "游戏", "末世", "种田", "争霸", "都市"]
        summary = concept.get("梗概", "") + concept.get("金手指", "")
        if any(kw in summary for kw in fanqie_keywords):
            score += 1
    score = max(0, min(10, score))
    return score, issues


def score_differentiation(concept: dict) -> tuple[int, list[str]]:
    gold = concept.get("金手指", "")
    summary = concept.get("梗概", "")
    combined = f"{gold}\n{summary}"
    issues = []
    score = 5
    # Unique mechanism keywords
    unique_keywords = ["不一样", "不同", "不是", "却", "但是", "反而", "偏偏", "唯独"]
    if any(kw in combined for kw in unique_keywords):
        score += 1
    # Template danger
    template_keywords = ["穿越到异世界", "重生回到", "获得系统", "绑定系统", "开局签到"]
    hits = [kw for kw in template_keywords if kw in combined]
    if len(hits) >= 2:
        score -= 2
        issues.append(f"模板感重: {', '.join(hits)}（都是常见开局）")
    elif len(hits) == 1 and len(gold) < 50:
        score -= 1
    score = max(0, min(10, score))
    return score, issues


def score_finger_gradient(concept: dict) -> tuple[int, list[str]]:
    gold = concept.get("金手指", "")
    world = concept.get("世界观", "")
    combined = f"{gold}\n{world}"
    issues = []
    score = 5
    # Check for OP start
    op_keywords = ["开局就", "一开始就", "初始", "无敌", "SSS", "顶级", "满级", "最强"]
    if any(kw in combined for kw in op_keywords):
        score -= 3
        issues.append("金手指开局即巅峰——没有成长空间")
    # Check for growth gradient
    gradient_keywords = ["逐步", "升级", "进化", "觉醒", "解锁", "突破", "进阶", "蜕变"]
    if any(kw in combined for kw in gradient_keywords):
        score += 2
    # Check for limitation/cost
    cost_keywords = ["代价", "限制", "冷却", "消耗", "副作用", "反噬", "不能", "每次只能", "仅能"]
    if any(kw in combined for kw in cost_keywords):
        score += 2
    score = max(0, min(10, score))
    return score, issues


def run_failure_patterns(concept: dict) -> list[dict]:
    """Run regex-based failure pattern detection."""
    full_text = f"{concept.get('梗概','')}\n{concept.get('金手指','')}\n{concept.get('世界观','')}"
    results = []
    for pattern, dimension, explanation in FAILURE_PATTERNS:
        m = re.search(pattern, full_text)
        if m:
            results.append({
                "dimension": dimension,
                "match": m.group(0),
                "explanation": explanation,
            })
    return results


def check_concept(concept: dict) -> dict:
    """Full concept validation."""
    dimensions = {}
    dimensions["protagonist_uniqueness"] = score_protagonist_uniqueness(concept)
    dimensions["satisfaction_visibility"] = score_satisfaction_visibility(concept)
    dimensions["sustainability"] = score_sustainability(concept)
    dimensions["market_fit"] = score_market_fit(concept)
    dimensions["differentiation"] = score_differentiation(concept)
    dimensions["finger_gradient"] = score_finger_gradient(concept)

    total = 0
    details = {}
    all_issues = []
    for dim, (score, issues) in dimensions.items():
        weighted = score * WEIGHTS[dim] // 10
        total += weighted
        details[dim] = {"raw_score": score, "weighted": weighted, "weight": WEIGHTS[dim], "issues": issues}
        all_issues.extend([{"dimension": dim, "issue": i} for i in issues])

    failures = run_failure_patterns(concept)
    if failures:
        total -= len(failures) * 2
        total = max(0, total)

    if total >= 70:
        status = "PASS"
    elif total >= 50:
        status = "WARN"
    else:
        status = "FAIL"

    return {
        "status": status,
        "total_score": total,
        "max_score": 100,
        "dimensions": details,
        "failure_patterns": failures,
        "all_issues": all_issues + [{"dimension": f["dimension"], "issue": f["match"] + " → " + f["explanation"]} for f in failures],
        "next_action": {
            "PASS": "进入 premise-guard → 填写详细设定",
            "WARN": "标注风险后可继续，风险需写入 premise.md",
            "FAIL": "拒绝。修改概念后重试",
        }[status],
    }


def print_report(result: dict, concept: dict):
    status_icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[result["status"]]
    print(f"{status_icon} concept-gate: {result['status']} ({result['total_score']}/{result['max_score']})")
    print(f"   书名: {concept.get('书名','未定')}")
    print(f"   梗概: {concept.get('梗概','')}")
    print()

    dim_names = {
        "protagonist_uniqueness": "主角不可替代性",
        "satisfaction_visibility": "爽点可见性",
        "sustainability": "持续可写性",
        "market_fit": "市场匹配度",
        "differentiation": "差异化锚点",
        "finger_gradient": "金手指梯度",
    }
    print("  六维评测：")
    for dim, info in result["dimensions"].items():
        bar = "█" * info["raw_score"] + "░" * (10 - info["raw_score"])
        print(f"    {dim_names.get(dim, dim):10s} [{bar}] {info['raw_score']}/10 → {info['weighted']}分")
        for issue in info["issues"]:
            print(f"      ⚡ {issue}")

    if result["failure_patterns"]:
        print()
        print("  已知失败模式命中：")
        for fp in result["failure_patterns"]:
            print(f"    ❌ [{fp['dimension']}] {fp['match']}")
            print(f"       → {fp['explanation']}")

    print()
    if result["all_issues"]:
        print(f"  风险({len(result['all_issues'])}):")
        for i in result["all_issues"]:
            print(f"    - [{i['dimension']}] {i['issue']}")
    else:
        print("  无风险项")

    print()
    print(f"  下一步: {result['next_action']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("concept_file", nargs="?", help="YAML concept file")
    ap.add_argument("--inline", help="Inline YAML concept string")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()

    if args.inline:
        concept = yaml.safe_load(args.inline)
    elif args.concept_file:
        import pathlib
        concept = yaml.safe_load(pathlib.Path(args.concept_file).read_text(encoding="utf-8"))
    else:
        ap.print_help()
        return 1

    result = check_concept(concept)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result, concept)

    return {"PASS": 0, "WARN": 0, "FAIL": 1}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
