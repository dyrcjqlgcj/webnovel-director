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
| 模块文档 | 8 modules × 5 files | ✅ |
| 操作入口 | `references/operations.md` | ✅ |
| premise 概念锚点匹配 | `scripts\outline_gate_review.py` 全幅 premise 概念锚点提取 | ✅ |
| truth 文件幂等回写 | `scripts\post_writeback.py` upsert 模式 | ✅ |
| 关系图验证 | `scripts\validate_relationships.py` | ✅ |
| 时序记忆 | ledger `expired_at` 列 | ✅ |
| 自动提取 premise | `scripts\extract_premise.py` | ✅ |
| 审章 | `scripts\review_chapter.py` L1 审查报告 | ✅ |
| 修复计划 | `scripts\repair_plan.py` R0-R4 分级修复 | ✅ |
| 大纲队列生成 | `scripts\generate_outline_queue.py` | ✅ |
| 多 Agent 并行审查 | `scripts\review_parallel.py` 4 子 Agent 并行 + 交叉矛盾检测 | ✅ |
| 进度校验 | `scripts\validate_pacing.py` | ✅ |
| Web 仪表盘 | `scripts\dashboard_server.py` | ✅ |
| 自检修复 | `scripts\director_meta_iterate.py` | ✅ |
| InkOS 状态同步 | `scripts\sync_inkos_state.py` | ✅ |

## 还缺什么

### P2：与生态集成（先等 director 内部跑顺）

| 缺口 | 说明 |
|---|---|
| cron job 列表审计 | 直接检查 gateway cron 中的小说任务是否绕过 director |
| inkos 执行器适配 | 把 task package 转为 inkos 可读输入 |
| oh-story 策略调用模板 | 扫榜/拆文输出必须经过 premise-guard |

## 不做或晚做

- 不内置全文写手
- 不自动发布
- 不自动改已发布章节
- 不把所有方法论塞进 SKILL.md

## 当前判断

**核心链路完整、可用。** 初始化 → 体检 → 审查 → 任务包 → 写后回写 五个环节都有脚本支撑。

P1 缺口已全部补齐。P2 剩余生态集成三项待推进。




