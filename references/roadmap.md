# 路线图

## 已完成

| 层 | 能力 | 状态 |
|---|---|---|
| 架构重构 | V3.0 导演直执行模式 | ✅ |
| 三阶段工作流 | 选题锁定 → 大纲布设 → 正文产出 | ✅ |
| 去外部 LLM | extend_outline.py 改为生成请求文件 | ✅ |
| 项目初始化 | `scripts/init_project.py` + `scripts/sync_inkos_state.py` | ✅ |
| 一键体检 | `scripts/director_doctor.py` | ✅ |
| outline-gate | `scripts/outline_gate_review.py` + `outline_causal_check.py` + `outline_iterate.py` | ✅ |
| 任务包生成 | `scripts/build_task_package.py` | ✅ |
| 写后回写 | `scripts/post_writeback.py` | ✅ |
| 细纲储备 | `scripts/extend_outline.py`（V3.0 无 LLM 版） | ✅ |
| chapter_queue 生成 | `scripts/generate_outline_queue.py` | ✅ |
| L1/L2/L3 审查 | `scripts/review_chapter.py` + `scripts/review_parallel.py` | ✅ |
| 修复引擎 | `scripts/repair_plan.py`（R0-R4 分级） | ✅ |
| 评分卡 | `scripts/scoring_card.py`（A~F + 趋势箭头） | ✅ |
| 趋势图 | `scripts/trend_chart.py` | ✅ |
| 字数检查 | `scripts/check_wordcount.py` | ✅ |
| cron 审计 | `scripts/check_cron_prompt.py` + `scripts/cron_auditor.py` | ✅ |
| 项目管理 | `scripts/project_manager.py` + `scripts/migrate_project.py` | ✅ |
| 节奏校验 | `scripts/validate_pacing.py` | ✅ |
| 关系校验 | `scripts/validate_relationships.py` | ✅ |
| concept-gate 导入 | `scripts/concept_gate_import.py` | ✅ |
| 仪表盘 | `scripts/dashboard_server.py` | ✅ |
| 自检引擎 | `scripts/director_meta_iterate.py` | ✅ |

## 还缺什么

| 缺口 | 说明 | 优先级 |
|------|------|--------|
| Windows 全链路真跑测试 | 29 个脚本在 Windows 上全部跑通 | P1 |
| dashboard_server.py Windows 验证 | 仪表盘未在 Windows 上实测 | P1 |
| 章节版本管理 | Git tag/快照自动记录每章提交点 | P2 |
| 发布格式导出 | TXT/HTML 一键导出 | P3 |

## 不做

- 不内置全文写手（导演亲自写）
- 不自动发布
- 不自动改已发布章节
- 不调外部 LLM/Agent
