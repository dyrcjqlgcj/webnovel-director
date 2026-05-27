# Changelog

## v1.1.0 (2026-05-25)

### 子系统自包含化（P0）

**五大子系统不再依赖外部 story-* skill，内置完整方法论。**

- scanner: 新增 `subsystems/scanner/guide.md`（扫榜流程+平台数据源+信号提取规则）+ 5 个专用 reference 文件
- analyzer: 新增 `subsystems/analyzer/guide.md`（快速/深度拆文流程+角色位抽象）+ 5 个专用 reference 文件
- writer: 新增 `subsystems/writer/guide.md`（完整写作方法论：情绪驱动/黄金三章/钩子13式/三维度织入/禁用词/长篇短篇双模式）+ 18 个专用 reference 文件
- reviewer: 新增 `subsystems/reviewer/guide.md`（L1/L2/L3 分级+4 Agent 并行审查+R0-R4 修复分级）
- polisher: 新增 `subsystems/polisher/guide.md`（AI味 vs 自然文本基准+分级保护+替换词表）

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
