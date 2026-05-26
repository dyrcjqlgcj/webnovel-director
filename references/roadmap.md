# 路线图

## 已完成

| 层 | 能力 | 状态 |
|---|---|---|
| 项目初始化 | `scripts\init_project.py` + `scripts\sync_inkos_state.py` | ✅ |
| 一键体检 | `scripts\director_doctor.py` | ✅ |
| outline-gate 结构闸 | `scripts\outline_gate_review.py` | ✅ |
| outline-gate 逐章审查 | `scripts\outline_gate_review.py`（六维判定+逐章报告） | ✅ |
| 任务包生成 | `scripts\build_task_package.py` | ✅ |
| 写后回写 | `scripts\post_writeback.py` | ✅ |
| cron 审计 | `scripts\check_cron_prompt.py` | ✅ |
| 关键词快筛 | `scripts\audit_chapters.py` | ✅ |
| 模块文档 | 9 modules × 5 files | ✅ |
| 操作入口 | `references/operations.md` | ✅ |

## 还缺什么

### P1：提升自动化（可手动替代，不急）

| G1: premise 概念锚点匹配 | scripts\outline_gate_review.py 从纯关键词改为全幅 premise 概念锚点提取 | ✅ DONE |
| G2: truth 文件幂等回写 | scripts\post_writeback.py 从 append 改为 upsert（重复回写不重复） | ✅ DONE |
| P1-1: 关系图 | `templates\relationship_graph.yaml` + `scripts\validate_relationships.py` | ✅ DONE |
| P1-2: 时序记忆 | ledger 加 `expired_at` 列 + post_writeback 支持 `--expire-resource` | ✅ DONE |
| P1-3: 自动提取 premise | `scripts\extract_premise.py` 读 story 文件生成 premise 初稿 | ✅ DONE |

| 缺口 | 说明 |
|---|---|
| `scripts\generate_outline_queue.py` | 从卷纲/用户方向生成候选 chapter_queue | ✅ DONE |
| `scripts\review_chapter.py` | 基于任务包+正文+truth 输出 Level 1 审查报告 | ✅ DONE |
| `scripts\repair_plan.py` | 把 FAIL/WARN 转成 R0-R4 修复计划 | ✅ DONE |

### P2：与生态集成（先等 director 内部跑顺）

| P2-1: 多 Agent 并行审查 | `scripts\review_parallel.py` 4 子 Agent 并行 + 交叉矛盾检测 | ✅ DONE |

| 缺口 | 说明 |
|---|---|
| cron job 列表审计 | 直接检查 gateway cron 中的小说任务是否绕过 director |
| inkos 执行器适配 | 把 task package 转为 inkos 可读输入 |
| story-* skill 策略调用模板 | 扫榜/拆文输出必须经过 premise-guard |

## 不做或晚做

- 不内置全文写手
- 不自动发布
- 不自动改已发布章节
- 不把所有方法论塞进 SKILL.md

## 当前判断

**核心链路完整、可用。** 初始化 → 体检 → 审查 → 任务包 → 写后回写 五个环节都有脚本支撑。

P1 缺口已全部填补。P2 缺口仅剩 cron 审计、inkos 适配、story-* 集成三项。




