# 任务检查结论

## 1. README.md 与 SKILL.md 脚本表对比

**实际脚本数量**：29 个（`scripts/*.py` 文件系统验证）

### README.md 脚本表（全部脚本章节）
- 表格列出 **27** 个，缺 **2** 个：
  - `extend_outline.py`（细纲自动扩展）
  - `check_wordcount.py`（字数检查）
- 注：目录结构部分标题写"27个可执行脚本"，实际列出了28个（含 extend_outline.py 但不含 check_wordcount.py），与表格数量不一致。

### SKILL.md 脚本表
- 表格列出 **21** 个，缺 **8** 个：
  - `concept_gate_import.py`（story-* 输出直通概念闸门）
  - `project_manager.py`（多书索引管理）
  - `migrate_project.py`（inkos 一键迁移）
  - `scoring_card.py`（审查评分卡 A~F）
  - `cron_auditor.py`（cron 自动检测+失联告警）
  - `trend_chart.py`（三线趋势图）
  - `extend_outline.py`（细纲自动扩展）
  - `check_wordcount.py`（字数检查）

## 2. CHANGELOG.md 脚本数量

第34行写"21 → 29"，实际确有 29 个 `.py` 脚本，**数字正确**。

## 3. references/roadmap.md 已完成项一致性

### "已完成"表（10项）
全部与实际一致，所列脚本/文档均存在。

### P1 缺口（6项 DONE）
标记正确，对应脚本均存在。

### P2-1（review_parallel.py）
标记 DONE，正确。

### "当前判断"过时
原文："P2 缺口仅剩 cron 审计、inkos 适配、story-* 集成三项"

- **cron 审计** → `cron_auditor.py` 已实现 ✅
- **story-* 集成** → `concept_gate_import.py` 已实现 ✅
- **inkos 执行器适配** → 仍缺

与 README V3.0 路线图（16项全标 ✅）不一致。roadmap.md 的"当前判断"未同步更新，也未提及 extend_outline.py、check_wordcount.py 等新增脚本。

---

完成时间: 2026-05-26
