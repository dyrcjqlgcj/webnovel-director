# Changelog

## v2.0.0 (2026-05-26)

### P0: 路径修复
- 11 处双路径错误修复
- 8 处 templates 路径修复

### P1: 自愈引擎增强 + CI/CD
- `scripts\director_meta_iterate.py` 增强：自动修复双路径等常见错误
- GitHub CI：push 自动跑 `scripts\test_smoke.py` + `scripts\director_meta_iterate.py`

### P2: 项目管理
- 新增 `scripts\project_manager.py`：多书索引 + 批量 doctor + 切换活跃项目
- 新增 `scripts\migrate_project.py`：inkos → webnovel-director 一键迁移
- `templates\director_state.json5` 升级：加 vcs/remote/branch 字段

### P3: 审查增强
- L3 审查自动化：每 30 章/卷末自动触发 4 Agent 并行
- 新增 `scripts\scoring_card.py`：审查评分卡 A~F + 趋势箭头
- `scripts\validate_pacing.py` → `scripts\outline_gate_review.py` 联动拦截

### P4: 仪表盘升级
- `scripts\dashboard_server.py` CLI 模式（`--mode cli` 终端彩色面板）
- 新增 `scripts\trend_chart.py`：章节趋势图表（字数 × 审查分 × 偏离度）
- 一键修复按钮：批量触发 `scripts\repair_plan.py`

### P5: 工具链集成
- 新增 `scripts\concept_gate_import.py`：story-* skill 输出直通概念闸门
- 新增 `scripts\cron_auditor.py`：自动检测 gateway cron + 失联告警
- 封面生成联动：`build_task_package.py --with-cover`

### 脚本总数
- 21 → 27

## v1.1.0 (2026-05-25)

### 子系统自包含化（P0）

**五大子系统不再依赖外部 story-* skill，内置完整方法论。**

- scanner: 新增 `modules\chapter-review\guide.md`（扫榜流程+平台数据源+信号提取规则）+ 5 个专用 reference 文件
- analyzer: 新增 `modules\chapter-review\guide.md`（快速/深度拆文流程+角色位抽象）+ 5 个专用 reference 文件
- writer: 新增 `modules\chapter-review\guide.md`（完整写作方法论：情绪驱动/黄金三章/钩子13式/三维度织入/禁用词/长篇短篇双模式）+ 18 个专用 reference 文件
- reviewer: 新增 `modules\chapter-review\guide.md`（L1/L2/L3 分级+4 Agent 并行审查+R0-R4 修复分级）
- polisher: 新增 `modules\chapter-review\guide.md`（AI味 vs 自然文本基准+分级保护+替换词表）

### 共享 reference 整合

- 新增 `references/craft/` 目录，整合 22 个跨子系统共享的写作参考文件
- 删除旧的子系统 README.md（仅含外部 skill 路由占位）
- 更新 `references/architecture.md` 和 `references/integration-subsystems.md`，移除外部 skill 依赖

### 即装即用

从 GitHub clone 后无需安装任何 story-* 系列 skill，所有子系统方法论自包含。

## v1.0.0 (2026-05-23)

### 首发版本

**五大子系统**（内嵌，无需额外安装）
- scanner: 市场雷达——扫榜、找趋势
- analyzer: 拆文引擎——对标分析、提取模块
- writer: 正文执行器——黄金三章/钩子13式/禁用词/字数标准
- reviewer: 深度审查——L1每章/L2每10章/L3每30章+4Agent并行
- polisher: 去AI味——AI味检测/自然文本基准

**九大模块**（五文件协议：guide/rules/examples-good/examples-bad/sources）
- concept-gate: 六维概念验证（主角不可替代性/爽点可见性/持续可写性/市场匹配/差异化/金手指梯度）
- project-init: 项目初始化 + 目录骨架
- premise-guard: 命题防偏 + 禁飞区 + 角色功能锁
- outline-gate: 大纲六维审查 + 因果链/爽点密度/角色弧线/力量曲线逻辑验证
- execution-dispatch: 写作任务包生成 + 执行器派发
- chapter-review: 章节审查
- consistency-module: 资源/关系/伏笔一致性
- transition-module: 转场/对话/章末
- repair-feedback: FAIL→WARN修复链路 + R0-R4自动分级

**16 个脚本**
- concept_gate.py: 六维概念验证打分
- init_project.py: 项目初始化
- director_doctor.py: 一键体检
- outline_gate_review.py: 大纲六维审查
- outline_causal_check.py: 大纲逻辑验证
- outline_iterate.py: 迭代修复引擎（检查→分组→LLM修复→重查→循环）
- build_task_package.py: 章节任务包生成
- review_chapter.py: L1 审查
- review_parallel.py: 4 Agent 并行审查 + 交叉矛盾检测
- post_writeback.py: 写后状态回写
- repair_plan.py: R0-R4 自动分级修复
- validate_relationships.py: 关系图因果边完整性检查
- audit_chapters.py: 快速关键词审计
- check_cron_prompt.py: cron prompt 合规检查
- sync_inkos_state.py: inkos 状态同步
- extract_premise.py: premise 自动生成

**目录模板**（11个）
- director/: premise / director_state / chapter_queue / last_audit / audit_log
- truth/: current_state / resource_ledger / particle_ledger / pending_hooks / relationship_graph
- story/outline/: volume_map
