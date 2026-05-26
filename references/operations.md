# 操作手册

本文件是 webnovel-director 的最小入口导航。详细规则仍按模块读取。


## 开新书完整清单

| 步骤 | 命令/动作 | 说明 |
|---|---|---|
| 1 | 扫榜选材 | 用 oh-story 或手动出 3-5 个提案 |
| 2 | `scripts\init_project.py <dir> --title "书名"` | 生成全部目录 + truth 占位 |
| 3 | 填写 `templates\premise.md` | 书名承诺+三要素+禁飞区+角色锁 |
| 4 | 填写 `templates\volume_map.md` | 七卷×章数×核心事件 |
| 5 | 填写 `templates\chapter_queue.md` | Ch1-20 逐章 Goal/Forbidden/Must Hit |
| 6 | 填写 5 个 truth 文件 | current_state / resource / particle / hooks / relationship_graph |
| 7 | 创建人物文件 `story/roles/` | 主角+买方+卖方性格设计 |
| 8 | `scripts\director_doctor.py <dir>` | 体检 |
| 9 | `scripts\outline_gate_review.py <dir>` | 六维审查 → PASS |
| 10 | `scripts\build_task_package.py <dir> --chapter 1` | 生成任务包 → 开始写 |

## 你要做什么？

| 目标 | 先读 | 命令/模块 | 产物 |
|---|---|---|---|
| 新书接入 director | `modules/project-init/rules.md` | `scripts\init_project.py` | director/truth 骨架 |
| 旧 inkos 项目接入 | `scripts/sync_inkos_state.py` | `scripts\sync_inkos_state.py --write` | 同步 currentChapter/truth |
| 检查项目健康 | 本文件即可 | `scripts\director_doctor.py` | PASS/WARN/FAIL |
| 审查待写队列 | `modules/outline-gate/rules.md` | `scripts\outline_gate_review.py` | 队列是否可派发 |
| 多 Agent 并行审查 | `scripts/review_parallel.py` | 4 子 Agent 并行 + 交叉矛盾检测 | 否 |
| 生成写作任务包 | `modules/execution-dispatch/rules.md` | `scripts\build_task_package.py` | YAML-like task package |
| 写后回写 | `references/post-writeback.md` | `scripts\post_writeback.py --write` | director/truth 更新 |
| 从旧项目提取 premise | `scripts/extract_premise.py` | 读 story 文件生成 premise 初稿 | 否 |
| 验证关系图 | `scripts/validate_relationships.py` | 检查因果边的完整性 | 否 |
| 审查已写章节 | `scripts/review_chapter.py` | 正文→任务包对照 Level 1 审查 | 否 |
| 生成修复计划 | `scripts/repair_plan.py` | FAIL/WARN 自动分级 R0-R4 + 修复步骤 | 否 |
| 审计自动任务 | `references/cron-interface.md` | `scripts\check_cron_prompt.py` | cron prompt 风险 |

## 标准链路

```text
project-init 或 sync-inkos-state
↓
director_doctor
↓
outline_gate_review / outline_gate_check
↓
build_task_package
↓
外部执行器写作
↓
chapter-review
↓
post_writeback
↓
director_doctor
```

## 强制闸门

- `director_doctor` FAIL：不写。
- `outline_gate_review / outline_gate_check` FAIL：不写。
- `director_state.canWrite=false`：不生成任务包。
- `post_writeback` WARN/FAIL：不继续下一章。

## 安全边界

这些脚本不写正文：

- `scripts\init_project.py`
- `scripts\init_project.py`
- `scripts\sync_inkos_state.py`
- `scripts\director_doctor.py`
- `scripts\outline_gate_review.py`
- `scripts\build_task_package.py`
- `scripts\post_writeback.py`
- `scripts\check_cron_prompt.py`

真正生成正文只能由外部执行器完成，而且必须在 director 闸门通过后。






