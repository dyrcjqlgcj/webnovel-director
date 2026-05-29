---
name: webnovel-director
version: 3.0.0
description: |
  中文长篇网文导演系统——从选题到完本的全流程调度台。
  V3.0：导演直执行模式，去掉外部 Agent spawn 和 LLM 调用。
---

# webnovel-director — 网文导演系统 V3.0

导演台 = 我（小爪爪）。判断任务、推进流程、维护唯一真相源、亲自下场写正文。
不 spawn 外部 Agent，不调外部 LLM。

## 核心原则

1. **导演即执行者**：所有写作、审查、大纲生成由我直接完成。脚本只做结构化校验。
2. **长篇必须有唯一真相源**：`templates/premise.md` + `director/director_state.json5`。
3. **卷纲/细纲强拦截**：偏离命题或触犯禁飞区，不进入正文。
4. **正文分级审查**：L1 每章，L2 每 10 章，L3 每 30 章/卷末/连续 WARN/FAIL。
5. **闸门不跳过**：三阶段各有闸门，PASS 才进入下一阶段。

## 三阶段工作流

### Phase 1：选题锁定

```
用户提方向/想法
  ↓
scanner 扫榜选材（若方向不明确）
  ↓
出 2-3 个候选概念，用户选或合
  ↓
concept-gate 六维打分
  ↓  ← 闸门1：PASS 才进入 Phase 2
init_project 建目录骨架
  ↓
填 premise.md：书名承诺/命题三要素/禁飞区/角色功能锁
```

**闸门1 通过条件：** concept-gate 返回 PASS + premise.md 非空。

### Phase 2：大纲布设

```
写 volume_map：卷结构 × 章数 × 核心事件 × 卷末状态
  ↓
写 chapter_queue：前 10-20 章细纲（Goal/Premise Must Hit/Forbidden）
  ↓
填 truth files：current_state/resource_ledger/particle_ledger/pending_hooks/relationship_graph 非空
  ↓
outline_gate_review（六维）→ outline_causal_check（逻辑）→ outline_iterate（迭代修复）
  ↓  ← 闸门2：全部 PASS → canWrite=true
```

**闸门2 通过条件：** outline 全 PASS + director_state 里 canWrite=true。

### Phase 3：正文产出（逐章循环）

```
每章写作前:
  extend_outline.py --auto  →  储备不足则生成请求文件
  导演读取 director/outline_extension_request.md 手动续细纲
  写前闸门：读 premise + chapter_queue + truth files
  build_task_package 生成任务包
  ↓
导演亲自写正文（按 writer 子系统方法论）
  ↓
review_chapter / review_parallel（L1/L2/L3 按触发条件）
  ↓
polisher 去 AI 味
  ↓
post_writeback 回写 truth + director_state
```

**逐章不跳过：** extend_outline 储备检查 → 写前闸门 → 写正文 → 审查 → 润色 → 回写。

## 五个子系统

| 子系统 | 目录 | 角色 | 触发时机 |
|--------|------|------|----------|
| **scanner** | `subsystems/scanner/` | 市场雷达——扫榜/找趋势/出候选概念 | Phase 1，选题不明确时 |
| **analyzer** | `subsystems/analyzer/` | 拆文引擎——对标分析/提取可复用模块 | Phase 1，有对标书时 |
| **writer** | `subsystems/writer/` | 正文执行器——方法论+钩子+禁用词 | Phase 3，写每章正文时 |
| **reviewer** | `subsystems/reviewer/` | 深度审查——L1/L2/L3 分级 | Phase 3，每章写完后 |
| **polisher** | `subsystems/polisher/` | 去AI味——文字润色 | Phase 3，审查通过后 |

所有子系统**自包含完整方法论**，无需外部 skill 依赖。导演读取 guide.md 后直接执行。

## 闸门强制规则

| 闸门 | 触发位置 | 通过条件 | FAIL 时 |
|------|---------|---------|---------|
| 概念闸 | Phase 1 末尾 | concept-gate PASS + premise 非空 | 修改或重新提案 |
| 大纲闸 | Phase 2 末尾 | outline 全 PASS + canWrite=true | 迭代修复至 PASS |
| 写前闸 | 每章写作前 | 禁飞区/命题无偏离、细纲储备 ≥5 | 停止并修复 |

## 严重偏离自动修正规则

可自动改正文的条件：A：主角违反禁飞区 / B：连续 3 章偏离命题 / C：细纲执行成了相反方向 / D：用户未发布且改动范围 ≤10 章。满足 A/B/D 任意两项，或满足 C，可自动重写正文。

## 所有脚本

| 脚本 | 用途 | 调外部 LLM |
|------|------|-----------|
| `scripts/concept_gate.py` | 六维概念验证打分 | 否 |
| `scripts/concept_gate_import.py` | story-* skill 输出直通概念闸门 | 否 |
| `scripts/init_project.py` | 初始化 director/truth 骨架 | 否 |
| `scripts/extract_premise.py` | 从 story 文件自动生成 premise 初稿 | 否 |
| `scripts/director_doctor.py` | 一键体检项目状态/队列/闸门 | 否 |
| `scripts/outline_gate_review.py` | 逐章六维审查报告 | 否 |
| `scripts/outline_causal_check.py` | 大纲逻辑验证：因果链/爽点密度/角色弧线/力量曲线 | 否 |
| `scripts/outline_iterate.py` | 迭代修复：检查→分组→修复→重查→循环至通过 | 否 |
| `scripts/generate_outline_queue.py` | 从卷纲自动生成 chapter_queue 骨架 | 否 |
| `scripts/extend_outline.py` | 细纲储备检查 + 生成请求文件（导演读后手动续） | **否（V3.0）** |
| `scripts/build_task_package.py` | 闸门通过后生成结构化任务包 | 否 |
| `scripts/audit_chapters.py` | 快速章节关键词审计 | 否 |
| `scripts/review_chapter.py` | 正文→任务包对照 L1 审查报告 | 否 |
| `scripts/review_parallel.py` | 4 线程并行审查 + 交叉矛盾检测 | 否 |
| `scripts/repair_plan.py` | FAIL/WARN 自动分级 R0-R4 + 修复步骤 | 否 |
| `scripts/scoring_card.py` | 审查评分卡 A~F + 趋势箭头 | 否 |
| `scripts/trend_chart.py` | 章节趋势图表（字数 × 审查分 × 偏离度） | 否 |
| `scripts/post_writeback.py` | 写后根据审查结果回写 director/truth | 否 |
| `scripts/validate_relationships.py` | 检查关系图因果边完整性 | 否 |
| `scripts/validate_pacing.py` | 检查细纲进度是否与卷纲 pace 对齐 | 否 |
| `scripts/check_cron_prompt.py` | 检查 cron prompt 是否绕过 director | 否 |
| `scripts/cron_auditor.py` | 自动检测 gateway cron + 失联告警 | 否 |
| `scripts/migrate_project.py` | inkos → webnovel-director 一键迁移 | 否 |
| `scripts/project_manager.py` | 多书索引 + 批量 doctor + 切换活跃项目 | 否 |
| `scripts/sync_inkos_state.py` | 同步 inkos 风格项目到 director state | 否 |
| `scripts/dashboard_server.py` | Web 仪表盘：项目状态/审查色块/一键操作 | 否 |
| `scripts/director_meta_iterate.py` | webnovel-director 自检+迭代修复引擎 | 否 |
| `scripts/check_wordcount.py` | 章节字数统计+达标校验 | 否 |
| `scripts/test_smoke.py` | 全链路冒烟测试 | 否 |

**所有脚本均不调外部 LLM。** extend_outline.py（V3.0 改）只生成请求文件，由导演读取后手动续细纲。

## 主要参考文件

| 文件 | 用途 |
|------|------|
| `references/architecture.md` | 总架构 |
| `references/module-protocol.md` | 模块协议 |
| `references/integration-subsystems.md` | 子系统集成 |
| `references/state-files.md` | director/truth 文件定义 |
| `references/operations.md` | 操作手册 |
| `references/post-writeback.md` | 写后回写 |
| `references/roadmap.md` | 路线图 |
| `subsystems/writer/guide.md` | 正文写作方法论（写前必读） |
| `subsystems/reviewer/guide.md` | 审查指南 |
| `subsystems/scanner/guide.md` | 扫榜指南 |
| `subsystems/analyzer/guide.md` | 拆文指南 |
| `subsystems/polisher/guide.md` | 去 AI 味指南 |
| `references/craft/` | 22 篇共享写作参考 |

## 语言

中文回复，代码和术语保留英文。
