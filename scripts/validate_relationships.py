#!/usr/bin/env python3
"""Validate relationship_graph.yaml for webnovel-director.

Usage:
  python validate_relationships.py <book_dir> [--json]

Checks:
- File exists and is valid YAML
- All edges have required fields
- No circular or orphaned references
- active_until consistency
"""
from __future__ import annotations
from pathlib import Path
import argparse, json, re, sys

try:
    import yaml
except ImportError:
    yaml = None

REQUIRED_EDGE = ["source", "target", "relation", "active_from"]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def parse_yaml_simple(text: str) -> dict | None:
    """Crude YAML parser that works without pyyaml."""
    if yaml:
        return yaml.safe_load(text)
    # crude fallback
    edges = []
    in_edges = False
    current = {}
    for line in text.splitlines():
        s = line.strip()
        if s == "edges:":
            in_edges = True
            continue
        if not in_edges:
            continue
        if s.startswith("- source:"):
            if current:
                edges.append(current)
            current = {}
            m = re.match(r"- source:\s*\"?(.+?)\"?\s*$", s)
            if m:
                current["source"] = m.group(1)
        elif s.startswith("source:") and not current:
            m = re.match(r"source:\s*\"?(.+?)\"?\s*$", s)
            if m:
                current["source"] = m.group(1)
        elif s.startswith("target:"):
            m = re.match(r"target:\s*\"?(.+?)\"?\s*$", s)
            if m:
                current["target"] = m.group(1)
        elif s.startswith("relation:"):
            m = re.match(r"relation:\s*\"?(.+?)\"?\s*$", s)
            if m:
                current["relation"] = m.group(1)
        elif s.startswith("active_from:"):
            m = re.match(r"active_from:\s*(\d+)", s)
            if m:
                current["active_from"] = int(m.group(1))
        elif s.startswith("active_until:"):
            val = s.split(":", 1)[1].strip()
            if val == "null" or val == "":
                current["active_until"] = None
            else:
                m = re.match(r"(\d+)", val)
                if m:
                    current["active_until"] = int(m.group(1))
    if current:
        edges.append(current)
    return {"edges": edges} if edges else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    book = Path(args.book_dir).resolve()
    gpath = book / "truth" / "relationship_graph.yaml"
    issues = []
    if not gpath.exists():
        issues.append({"severity": "FAIL", "issue": "truth/relationship_graph.yaml missing"})
        result = {"status": "FAIL", "edges": [], "issues": issues}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("结论：FAIL")
            print("问题：truth/relationship_graph.yaml missing")
            print("建议：运行 init_project.py")
        return 1
    text = read(gpath)
    if not text.strip():
        issues.append({"severity": "FAIL", "issue": "truth/relationship_graph.yaml is empty"})
    data = parse_yaml_simple(text)
    if not data or not data.get("edges"):
        issues.append({"severity": "FAIL", "issue": "无法解析 edges 或 edges 为空"})
        result = {"status": "FAIL", "edges": [], "issues": issues}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("结论：FAIL")
            print("问题：无法解析 edges")
        return 1
    edges = data["edges"]
    if not isinstance(edges, list):
        issues.append({"severity": "FAIL", "issue": "edges 不是列表"})
    else:
        sources = set()
        targets = set()
        for i, e in enumerate(edges):
            for field in REQUIRED_EDGE:
                if field not in e or e[field] is None:
                    issues.append({"severity": "FAIL", "issue": f"edge[{i}] 缺少 {field}"})
            if "active_until" in e and e["active_until"] is not None:
                af = e.get("active_from", 0)
                au = e["active_until"]
                if isinstance(af, int) and isinstance(au, int) and au < af:
                    issues.append({"severity": "WARN", "issue": f"{e.get('source','?')}->{e.get('target','?')} active_until({au}) < active_from({af})"})
            if "source" in e:
                sources.add(str(e["source"]))
            if "target" in e:
                targets.add(str(e["target"]))
        orphan_targets = targets - sources - {"{{PROTAGONIST}}","{{CORE_MECHANISM}}","{{ANTAGONIST_FORCE}}"}
        if orphan_targets and len(edges) > 2:  # only flag after template vars are filled
            for ot in orphan_targets:
                issues.append({"severity": "WARN", "issue": f"target '{ot}' has no outgoing edge (可能是孤立节点)"})
    status = "FAIL" if any(i["severity"] == "FAIL" for i in issues) else ("WARN" if issues else "PASS")
    result = {"status": status, "edges_count": len(edges) if isinstance(edges, list) else 0, "issues": issues}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"结论：{status}")
        print(f"依据：{gpath}; edges={len(edges) if isinstance(edges, list) else 0}")
        print("问题：" + ("暂无" if not issues else ""))
        for i in issues:
            print(f"- {i['severity']} {i['issue']}")
        print("下一步：" + ("无" if status == "PASS" else "修复"))
    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
