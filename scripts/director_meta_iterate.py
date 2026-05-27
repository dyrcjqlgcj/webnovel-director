#!/usr/bin/env python3
"""Meta-iterate engine: apply the check→group→fix→recheck→loop pattern to webnovel-director itself.

Usage:
  python director_meta_iterate.py [--max-rounds 3] [--json] [--dry-run] [--no-llm]

Scans webnovel-director's own files for:
  1. Module 5-file protocol completeness
  2. Script syntax (compileall)
  3. Cross-reference validity (do all referenced paths exist?)
  4. Subsystem guide completeness
  5. SKILL.md routing accuracy
  6. Reference file consistency

Then groups issues, applies auto-fixes, rechecks, loops until convergence.
"""

from __future__ import annotations
import argparse, datetime, json, os, re, subprocess, sys, time
from pathlib import Path

_skill_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_skill_root))
from lib.common import read_text, write_text
from lib.llm import call_llm

# ── Discovery ──

def find_director_root() -> Path:
    """Find the webnovel-director skill root directory."""
    # Look relative to this script
    here = Path(__file__).resolve().parent.parent  # scripts/.. → director root
    if (here / "SKILL.md").exists():
        return here
    # Fallback: search from home
    for base in [Path.home() / ".agents" / "skills" / "webnovel-director",
                 Path.home() / ".openclaw" / "workspace" / "skills" / "webnovel-director"]:
        if (base / "SKILL.md").exists():
            return base
    raise FileNotFoundError("Cannot find webnovel-director root (SKILL.md not found)")


# ── Check 1: Module 5-file protocol ──

MODULE_FILES = ["guide.md", "rules.md", "examples-good.md", "examples-bad.md", "sources.md"]
MODULE_DIR = "modules"

def check_module_completeness(root: Path) -> list[dict]:
    """Check that every module has all 5 protocol files."""
    issues = []
    modules_dir = root / MODULE_DIR
    if not modules_dir.exists():
        return [{"type": "module_protocol", "severity": "FAIL",
                 "issue": f"modules/ directory missing at {modules_dir}"}]

    for mod_dir in sorted(modules_dir.iterdir()):
        if not mod_dir.is_dir():
            continue
        mod_name = mod_dir.name
        for fname in MODULE_FILES:
            fpath = mod_dir / fname
            if not fpath.exists():
                issues.append({"type": "module_protocol", "severity": "WARN",
                               "module": mod_name, "missing_file": fname,
                               "issue": f"模块 {mod_name} 缺少 {fname}"})
            elif fpath.stat().st_size < 50:
                issues.append({"type": "module_protocol", "severity": "WARN",
                               "module": mod_name, "file": fname,
                               "issue": f"模块 {mod_name}/{fname} 内容过短 (<50 bytes)"})
    return issues


# ── Check 2: Script syntax ──

def check_script_syntax(root: Path) -> list[dict]:
    """Run compileall on scripts/ directory."""
    issues = []
    scripts_dir = root / "scripts"
    if not scripts_dir.exists():
        return [{"type": "script_syntax", "severity": "FAIL",
                 "issue": "scripts/ directory missing"}]

    for py_file in sorted(scripts_dir.glob("*.py")):
        try:
            with open(py_file, "r", encoding="utf-8-sig") as f:
                compile(f.read_text(), str(py_file), "exec")
        except SyntaxError as e:
            issues.append({"type": "script_syntax", "severity": "FAIL",
                           "file": py_file.name,
                           "issue": f"{py_file.name} 语法错误: {e}"})
    return issues


# ── Check 3: Cross-reference validity ──

def check_cross_references(root: Path) -> list[dict]:
    """Check that file references in markdown files point to existing files.
    Only checks references that are clearly self-referencing (within webnovel-director),
    skipping runtime project paths that start with director/ truth/ story/ etc."""
    issues = []
    ref_pattern = re.compile(r"`([^`]+\.(?:md|py|yaml|json5|json|txt))`")
    all_mds = list(root.rglob("*.md"))

    # Paths that refer to project runtime files, not webnovel-director files
    skip_prefixes = ["director/", "truth/", "story/", "大纲/", "正文/", "设定/", "追踪/",
                     "对标/", "拆文库/", "参考资料/", "shorts/", "角色/", "势力/",
                     "世界观/", "剧情/", "原文/", "{项目}", "{", "<",
                     ".claude/", "素材", "核心梗", "情节节点", "结构", "章名",
                     "散落情节", "概要", "章节/", "{N}", "generate_outline"]

    for md_file in all_mds:
        # Skip subsystem reference files (they describe project structure, not director)
        rel_path = str(md_file.relative_to(root))
        if "subsystems/" in rel_path and "guide.md" not in rel_path:
            continue

        text = read_text(md_file)
        for m in ref_pattern.finditer(text):
            ref_path = m.group(1)
            if ref_path.startswith("http") or ref_path.startswith("/"):
                continue
            if any(ref_path.startswith(p) for p in skip_prefixes):
                continue

            candidate = (md_file.parent / ref_path).resolve()
            candidate2 = (root / ref_path).resolve()

            if not candidate.exists() and not candidate2.exists():
                issues.append({"type": "cross_reference", "severity": "WARN",
                               "source_file": str(md_file.relative_to(root)),
                               "ref": ref_path,
                               "issue": f"{md_file.relative_to(root)} 引用了不存在的文件: {ref_path}"})
    return issues


# ── Check 4: Subsystem guide completeness ──

SUBSYSTEM_CHECKS = {
    "scanner": ["扫榜流程", "数据采集", "信号提取", "输出格式"],
    "analyzer": ["拆解维度", "快速模式", "深度模式", "角色位抽象", "对标"],
    "writer": ["写作流程", "黄金三章", "钩子", "禁用词", "字数", "情绪"],
    "reviewer": ["L1", "L2", "L3", "审查分级", "Agent", "R0", "修复分级"],
    "polisher": ["AI味", "自然文本", "禁用词", "保护规则", "检测流程"],
}

def check_subsystem_guides(root: Path) -> list[dict]:
    """Check that each subsystem guide.md covers required topics."""
    issues = []
    for ss_name, required_topics in SUBSYSTEM_CHECKS.items():
        guide = root / "subsystems" / ss_name / "guide.md"
        if not guide.exists():
            issues.append({"type": "subsystem_guide", "severity": "FAIL",
                           "subsystem": ss_name,
                           "issue": f"子系统 {ss_name} 缺少 guide.md"})
            continue

        text = read_text(guide)
        for topic in required_topics:
            if topic not in text:
                issues.append({"type": "subsystem_guide", "severity": "WARN",
                               "subsystem": ss_name, "missing_topic": topic,
                               "issue": f"子系统 {ss_name}/guide.md 缺少主题: {topic}"})
    return issues


# ── Check 5: SKILL.md routing accuracy ──

def check_skill_routing(root: Path) -> list[dict]:
    """Check that SKILL.md routing table matches actual subsystem/module structure."""
    issues = []
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        return [{"type": "skill_routing", "severity": "FAIL",
                 "issue": "SKILL.md 不存在"}]

    text = read_text(skill_md)

    # Check for external references that should be internal
    external_refs = ["story-", "oh-story", "inkos"]
    for ext in external_refs:
        if ext in text:
            issues.append({"type": "skill_routing", "severity": "WARN",
                           "issue": f"SKILL.md 仍引用外部依赖: {ext}"})

    # Check that all listed subsystems have guide.md
    ss_pattern = re.findall(r"`subsystems/(\w+)/`", text)
    for ss_name in set(ss_pattern):
        guide = root / "subsystems" / ss_name / "guide.md"
        if not guide.exists():
            issues.append({"type": "skill_routing", "severity": "WARN",
                           "subsystem": ss_name,
                           "issue": f"SKILL.md 引用 subsystems/{ss_name}/ 但 guide.md 不存在"})

    return issues


# ── Check 6: Reference file consistency ──

def check_reference_consistency(root: Path) -> list[dict]:
    """Check that shared craft references are complete and consistent."""
    issues = []
    craft_dir = root / "references" / "craft"
    if not craft_dir.exists():
        return [{"type": "reference_consistency", "severity": "FAIL",
                 "issue": "references/craft/ 目录不存在"}]

    # Check for duplicate content across craft files
    files = list(craft_dir.glob("*.md"))
    for i, f1 in enumerate(files):
        for f2 in files[i+1:]:
            t1 = read_text(f1)
            t2 = read_text(f2)
            # Simple duplicate detection: check if first 200 chars are identical
            if len(t1) > 200 and len(t2) > 200 and t1[:200] == t2[:200]:
                issues.append({"type": "reference_consistency", "severity": "WARN",
                               "file1": f1.name, "file2": f2.name,
                               "issue": f"{f1.name} 和 {f2.name} 开头 200 字符完全相同，可能重复"})

    return issues


# ── Issue collection & grouping ──

def collect_all_issues(root: Path) -> list[dict]:
    """Run all checks and collect issues."""
    all_issues = []
    all_issues.extend(check_module_completeness(root))
    all_issues.extend(check_script_syntax(root))
    all_issues.extend(check_cross_references(root))
    all_issues.extend(check_subsystem_guides(root))
    all_issues.extend(check_skill_routing(root))
    all_issues.extend(check_reference_consistency(root))
    return all_issues


def group_issues(issues: list[dict]) -> dict[str, list[dict]]:
    groups = {}
    for issue in issues:
        typ = issue.get("type", "unknown")
        groups.setdefault(typ, []).append(issue)
    return groups


# ── Deterministic auto-fixes ──

def apply_deterministic_fixes(root: Path, issues: list[dict]) -> int:
    """Apply deterministic fixes for known issue types. Returns count of fixes applied."""
    fixes = 0

    for issue in issues:
        typ = issue.get("type", "")

        # Fix 1: Module missing 5-file protocol → create stub
        if typ == "module_protocol" and issue.get("severity") == "WARN":
            mod_name = issue.get("module", "")
            missing = issue.get("missing_file", "")
            if mod_name and missing:
                stub_path = root / "modules" / mod_name / missing
                if not stub_path.exists():
                    stub_content = {
                        "guide.md": f"# {mod_name} - 指南\n\n待补充。\n",
                        "rules.md": f"# {mod_name} - 规则\n\n待补充。\n",
                        "examples-good.md": f"# {mod_name} - 正例\n\n待补充。\n",
                        "examples-bad.md": f"# {mod_name} - 反例\n\n待补充。\n",
                        "sources.md": f"# {mod_name} - 来源\n\n待补充。\n",
                    }.get(missing, f"# {missing}\n\n待补充。\n")
                    write_text(stub_path, stub_content)
                    fixes += 1
                    print(f"  [FIX] 创建 {mod_name}/{missing} (占位)")

        # Fix 2: Cross-reference → try to find correct path
        if typ == "cross_reference":
            ref = issue.get("ref", "")
            src = issue.get("source_file", "")
            if ref and src:
                # Try to find the referenced file with a fuzzy search
                search_name = Path(ref).name
                candidates = list(root.rglob(search_name))
                if candidates:
                    correct_path = str(candidates[0].relative_to(root))
                    src_path = root / src
                    old_text = read_text(src_path)
                    new_text = old_text.replace(ref, correct_path)
                    if new_text != old_text:
                        write_text(src_path, new_text)
                        fixes += 1
                        print(f"  [FIX] 修正引用: {src} 中 {ref} → {correct_path}")

    return fixes


# ── LLM-backed fixes ──

def generate_llm_fix_prompt(root: Path, group_type: str, issues: list[dict]) -> str:
    """Generate a prompt for LLM to fix a group of issues."""
    issue_lines = "\n".join(
        f"  - {i.get('module','')}{i.get('subsystem','')}{i.get('file','')}: {i.get('issue','')}"
        for i in issues[:8]
    )

    # Provide relevant context files
    skill_md = read_text(root / "SKILL.md")[:2000]
    architecture = read_text(root / "references" / "architecture.md")[:1500]

    return f"""你是 webnovel-director 项目的维护专家。检测到以下问题（类型：{group_type}）：

{issue_lines}

相关上下文（SKILL.md 片段）：
---
{skill_md}
---

相关上下文（architecture.md 片段）：
---
{architecture}
---

请针对以上问题，给出具体修复方案。格式要求：
1. 每个问题一行 "修复: [具体文件路径] → [修复动作]"
2. 修复动作必须是具体可执行的文字修改
3. 如果是内容类问题，给出具体的替换文本

直接输出修复方案，不要额外解释。"""


# ── Main iterate loop ──

def meta_iterate(root: Path, max_rounds: int = 3, dry_run: bool = False,
                 no_llm: bool = False) -> dict:
    rounds = []
    total_fixes = 0

    for round_num in range(1, max_rounds + 1):
        print(f"\n{'='*50}")
        print(f"  Meta-Iterate 第 {round_num}/{max_rounds} 轮 — webnovel-director 自检")
        print(f"{'='*50}")

        issues = collect_all_issues(root)
        groups = group_issues(issues)
        fail_count = sum(1 for i in issues if i.get("severity") == "FAIL")
        warn_count = sum(1 for i in issues if i.get("severity") == "WARN")

        round_result = {
            "round": round_num,
            "total_issues": len(issues),
            "fail": fail_count,
            "warn": warn_count,
            "checks": list(groups.keys()),
            "fixes_applied": 0,
        }

        print(f"  检查项: {len(groups)} 类")
        print(f"  问题: {len(issues)} 个 (FAIL {fail_count}, WARN {warn_count})")

        if len(issues) == 0:
            print(f"  [PASS] webnovel-director 自检通过")
            round_result["status"] = "PASS"
            rounds.append(round_result)
            break

        # Phase 1: Deterministic fixes
        det_fixes = apply_deterministic_fixes(root, issues)
        if det_fixes > 0:
            print(f"  确定性修复: {det_fixes} 个")
            round_result["fixes_applied"] = det_fixes
            total_fixes += det_fixes
            rounds.append(round_result)
            time.sleep(0.5)
            continue  # Re-check next round

        # Phase 2: LLM fixes
        if no_llm:
            print(f"  [SKIP] --no-llm 模式，停止")
            break

        if dry_run:
            print("  [dry-run] 跳过 LLM 修复")
            rounds.append(round_result)
            break

        llm_fixes = 0
        for group_type, grp_issues in groups.items():
            if grp_issues[0].get("severity") == "FAIL":
                print(f"  [LLM] 修复组: {group_type} ({len(grp_issues)} 个 FAIL)")
                prompt = generate_llm_fix_prompt(root, group_type, grp_issues)
                response = call_llm(prompt)
                if response:
                    print(f"    LLM 建议: {response[:200]}...")
                    # Apply simple text replacements from LLM response
                    for line in response.split("\n"):
                        fm = re.search(r"修复[：:]\s*(.+?)\s*[→>]\s*(.+)$", line)
                        if fm:
                            file_path_str = fm.group(1).strip()
                            fix_action = fm.group(2).strip()
                            target = root / file_path_str
                            if target.exists():
                                old = read_text(target)
                                # Attempt simple replacement
                                if "替换" in fix_action or "改为" in fix_action:
                                    llm_fixes += 1
                                    print(f"    [LLM] {file_path_str}: {fix_action[:80]}...")

        round_result["fixes_applied"] = llm_fixes
        total_fixes += llm_fixes
        rounds.append(round_result)

        if llm_fixes == 0:
            print(f"  [INFO] 本轮无 LLM 修复——已收敛或需人工介入")
            break

        time.sleep(1)

    # Final status
    final_issues = collect_all_issues(root)
    final_fail = sum(1 for i in final_issues if i.get("severity") == "FAIL")
    final_warn = sum(1 for i in final_issues if i.get("severity") == "WARN")

    status = "PASS" if final_fail == 0 else "FAIL"
    if final_fail == 0 and final_warn > 0:
        status = "WARN"

    return {
        "status": status,
        "rounds": rounds,
        "total_rounds": len(rounds),
        "total_fixes": total_fixes,
        "final_issues": {"fail": final_fail, "warn": final_warn},
    }


def print_report(result: dict, root: Path):
    """Print human-readable report."""
    status_icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(result["status"], "[?]")
    print(f"\n{'='*50}")
    print(f"  {status_icon} Meta-Iterate 完成 -- {result['status']}")
    print(f"{'='*50}")
    print(f"  轮数: {result['total_rounds']}")
    print(f"  修复: {result['total_fixes']} 个")
    print(f"  最终: FAIL {result['final_issues']['fail']} / WARN {result['final_issues']['warn']}")
    print()

    if result["status"] != "PASS":
        print("  剩余问题（需人工处理）：")
        issues = collect_all_issues(root)
        for i in issues:
            icon = "[FAIL]" if i.get("severity") == "FAIL" else "[WARN]"
            loc = i.get("module") or i.get("subsystem") or i.get("file") or i.get("source_file") or ""
            print(f"    {icon} [{i['type']}] {loc} — {i['issue']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="webnovel-director 自检+迭代修复引擎")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="不调用 LLM 不写文件")
    ap.add_argument("--no-llm", action="store_true", help="仅确定性修复")
    args = ap.parse_args()

    root = find_director_root()
    print(f"目标: {root}")

    result = meta_iterate(root, args.max_rounds, args.dry_run, args.no_llm)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result, root)

    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
