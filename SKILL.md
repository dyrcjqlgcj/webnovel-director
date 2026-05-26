---
name: webnovel-director
version: 2.0.0
description: |
  中文长篇网文导演系统——从选题到完本的全流程调度台。
  内置五个自包含子系统 + web 仪表盘 + 全书画布 + 进度硬校验 + 自动写作闭环。
---

# webnovel-director — 网文导演系统

它不是正文写手，而是导演台：判断任务属于哪一层，调用对应子系统，维护作品唯一真相源，防止长篇写着写着滑向标准模板。

## 核心原则

1. **主路由不承载全部知识**：只判断任务、分发模块、维护全局约束。
2. **长篇必须有唯一真相源**：`templates\premise.md` + `director/director_state.json5|yaml`。
3. **卷纲/细纲强拦截**：偏离命题或触犯禁飞区，不进入正文。
4. **正文分级审查**：Level 1 每章，Level 2 每10章，Level 3 每30章/卷末/连续 WARN/FAIL。
5. **执行器自包含**：writer 子系统内置完整写作方法论，即装即用。

## 五个子系统

| 子系统 | 目录 | 角色 | 触发时机 |
|--------|------|------|----------|
| **scanner** | `subsystems/scanner/` | 市场雷达——扫榜、找趋势 | 开书前，选题不明确时 |
| **analyzer** | `subsystems/analyzer/` | 拆文引擎——对标分析、提取模块 | 有对标书时，概念阶段 |
| **writer** | `subsystems/writer/` | 正文执行器——方法论+钩子+禁用词 | 大纲通过后，每章写作 |
| **reviewer** | `subsystems/reviewer/` | 深度审查——L1/L2/L3 分级 | 每章写完后自动触发 |
| **polisher** | `subsystems/polisher/` | 去AI味——文字润色 | 发布前 |

## 任务路由

| 用户意图 | 路由模块 | 调用子系统 |
|---|---|---|
| 开新长篇 | `modules/project-init/` + `modules/premise-guard/` | — |
| 扫榜/看市场 | `subsystems/scanner/` | scanner |
| 拆文/对标分析 | `subsystems/analyzer/` | analyzer |
| 选材/概念验证 | `modules/concept-gate/` | — |
| 写卷纲/细纲 | `modules/outline-gate/` | — |
| 大纲逻辑验证+迭代 | `modules/outline-gate/` + scripts\outline_causal_check.py + scripts\outline_iterate.py | — |
| 写/续写正文 | `modules/execution-dispatch/` | writer |
| 检查偏离 | `modules/premise-guard/` + `modules/chapter-review/` | reviewer |
| 修稿/回炉 | `modules/repair-feedback/` | writer + reviewer |
| 检查转场/对白/章末 | `modules/transition-module/` + `modules/consistency-module/` | — |
| 去AI味 | `subsystems/polisher/` | polisher |
| 自动写作/cron | `references/cron-interface.md` | writer + reviewer |

## 标准工作流

### A. 开书（完整 9 步）

1. **scanner 扫榜选材**：若方向不明确，先用 scanner 扫榜；或手动出多提案让用户选。
2. **概念闸门**：对 1-3 个候选概念跑 `scripts\concept_gate.py`，六维打分，PASS 才能进入下一步。FAIL 则修改或重新提案。有对标书时先跑 analyzer。
3. **跑 init_project.py**：建目录骨架。
4. **填 premise.md**：书名承诺 / 命题三要素 / 禁飞区 / 角色功能锁。
5. **写 story/outline/volume_map.md**：卷结构 × 章数 × 核心事件 × 卷末状态。
6. **写 chapter_queue.md**：前 10-20 章细纲（每章 Goal / Premise Must Hit / Forbidden）。
7. **填 truth files**：current_state / resource_ledger / particle_ledger / pending_hooks / relationship_graph 非空。
8. **大纲闸门**：跑 `scripts\outline_gate_review.py`（六维）→ `scripts\outline_causal_check.py`（逻辑）→ `scripts\outline_iterate.py`（迭代修复）。全部 PASS 后 canWrite=true。
9. **跑 build_task_package.py**：生成第一章任务包，派发到 writer 子系统。

⚠ 常见遗漏：
- 跳过 concept-gate → 写了几章才发现主角优势不成立
- 只填 premise 但 truth files 全空 → director_doctor PASS 但没内容
- 有细纲没卷纲 → 跑到中段剧情漂移
- 有人物名没人设 → 第一章写不出人物性格

### B. 写前闸门

每次写章前必须读取：`templates\premise.md`、`director/director_state.json5|yaml`、`templates\last_audit.md`、`templates\chapter_queue.md`、truth files。若卷纲/细纲触犯禁飞区或命题偏离，停止并给修复方案。

### C. 正文执行

1. `execution-dispatch` 生成写作任务包。
2. 派发到 writer 子系统写正文。
3. 按需调用 reviewer + polisher 做写后处理。

### D. 写后审查与回写

1. L1 每章快速筛查 → L2 每10章 → L3 每30章/卷末/连续 WARN/FAIL。
2. 更新 `director_state`、`last_audit`、`chapter_queue`、truth files。

## 严重偏离自动修正规则

可自动改正文的条件：A：主角违反禁飞区 / B：连续3章偏离命题 / C：细纲执行成了相反方向 / D：用户未发布且改动范围 ≤10章。满足 A/B/D 任意两项，或满足 C，可自动重写正文。

## 当前可用脚本

| 脚本 | 用途 | 是否写正文 |
|---|---|---|
| `scripts\concept_gate.py` | 六维概念验证打分 | 否 |
| `scripts\init_project.py` | 初始化 director/truth 骨架 | 否 |
| `scripts\director_doctor.py` | 一键体检项目状态/队列/闸门 | 否 |
| `scripts\extract_premise.py` | 从 story 文件自动生成 premise 初稿 | 否 |
| `scripts\outline_gate_review.py` | 逐章六维审查报告 | 否 |
| `scripts\outline_causal_check.py` | 大纲逻辑验证：因果链/爽点密度/角色弧线/力量曲线 | 否 |
| `scripts\outline_iterate.py` | 迭代修复：检查→分组→LLM修复→重查→循环至通过 | 否 |
| `scripts\build_task_package.py` | 在闸门通过后生成章节任务包 | 否 |
| `scripts\audit_chapters.py` | 快速章节关键词审计 | 否 |
| `scripts\review_chapter.py` | 正文→任务包对照 L1 审查报告 | 否 |
| `scripts\review_parallel.py` | 4 子 Agent 并行审查 + 交叉矛盾检测 | 否 |
| `scripts\post_writeback.py` | 写后根据审查结果回写 director/truth | 否 |
| `scripts\repair_plan.py` | FAIL/WARN 自动分级 R0-R4 + 修复步骤 | 否 |
| `scripts\sync_inkos_state.py` | 同步 inkos 风格项目到 director state | 否 |
| `scripts\director_meta_iterate.py` | webnovel-director 自检+迭代修复引擎 | 否 |
| `scripts\validate_relationships.py` | 检查关系图因果边完整性 | 否 |
| `scripts\check_cron_prompt.py` | 检查 cron prompt 是否绕过 director | 否 |
| `scripts\generate_outline_queue.py` | 从卷纲自动生成 chapter_queue 骨架 | 否 |
| `scripts\validate_pacing.py` | 检查细纲进度是否与卷纲 pace 对齐（过快/过慢检测） | 否 |
| `scripts\test_smoke.py` | 全链路冒烟测试 | 否 |
| `scripts\dashboard_server.py` | Web 仪表盘服务器：项目状态/审查色块/一键操作 | 否 |

## 主要参考文件

- `references/architecture.md`：总架构
- `references/module-protocol.md`：模块协议
- `references/integration-subsystems.md`：五个子系统集成
- `references/cron-interface.md`：cron 接口
- `references/state-files.md`：director/truth 文件定义
- `references/operations.md`：操作手册
- `references/roadmap.md`：路线图
- `references/post-writeback.md`：写后回写

标准顺序：

```text
init_project / extract_premise
↓
director_doctor
↓
concept_gate
↓
outline_gate_review → outline_causal_check → outline_iterate
↓
build_task_package
↓
writer 子系统写作
↓
reviewer 子系统审查 (review_chapter / review_parallel)
↓
polisher 子系统润色
↓
post_writeback
```
