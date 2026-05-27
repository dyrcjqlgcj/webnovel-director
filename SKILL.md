---
name: webnovel-director
version: 2.1.0
description: |
  中文长篇网文的结构化写作调度工具。选材→大纲→写作→审查→回写，每阶段自动化检查和修复。
  统一 CLI: wd.py；Web 仪表盘: dashboard_server.py。
---

# webnovel-director

判断用户意图属于哪个阶段，调用对应脚本或子系统方法，维护 `director/` 目录下的唯一真相源。

## 核心原则

1. 只判断任务阶段、路由到对应脚本/模块，不把所有知识堆在一个 prompt 里
2. 长篇唯一真相源在 `director/premise.md` + `director/director_state.json5` + `truth/` 文件
3. 大纲/细纲必须过闸门，偏离命题或触犯禁飞区不能进入正文
4. 正文分级审查：L1 每章、L2 每 10 章、L3 每 30 章/卷末
5. 先确定性修复，再调 LLM。能用正则解决的问题不动用模型

## 任务路由

| 用户意图 | 执行操作 |
|----------|----------|
| 开新书、建项目 | `python wd.py init <book_dir> --title "书名"` |
| 选题验证 | `python wd.py gate concept <yaml_file|--inline "...">` |
| 扫榜、看市场 | 读取 `subsystems/scanner/guide.md` + reference 文件 |
| 拆文、对标分析 | 读取 `subsystems/analyzer/guide.md` + reference 文件 |
| 写/修卷纲细纲 | `python wd.py gate outline <book_dir> [--fix]` |
| 大纲逻辑验证 | `python scripts/outline_causal_check.py <book_dir>` |
| 迭代修复大纲 | `python scripts/outline_iterate.py <book_dir> [--max-rounds 3]` |
| 生成写作任务包 | `python wd.py build <book_dir> --chapter N` |
| 写/续写正文 | `python wd.py write <book_dir> --chapter N`（调 LLM 写作） |
| 检查是否偏离命题 | `python wd.py review <book_dir> --chapter N` |
| 修稿/回炉 | `python scripts/repair_plan.py <book_dir> --chapter N` |
| 检查转场/对白/章末 | 读取 `modules/transition-module/` 和 `modules/consistency-module/` |
| 去 AI 味 | 读取 `subsystems/polisher/guide.md` |
| 一键体检 | `python wd.py doctor <book_dir>` |
| 项目状态摘要 | `python wd.py status <book_dir>` |
| 开仪表盘 | `python wd.py dashboard <book_dir>` |
| 自动写作/cron | 读取 `references/cron-interface.md` |

## 标准工作流

### 开书

1. `python wd.py gate concept --inline "..."` — 六维打分，≥70 PASS
2. `python wd.py init <book_dir> --title "书名"` — 建 director/ + truth/ 目录
3. 指导用户填写 `director/premise.md`（书名承诺+禁飞区+角色锁）
4. 指导用户填写 `story/outline/volume_map.md` 和 `director/chapter_queue.md`
5. `python wd.py gate outline <book_dir> --fix` — 大纲审查+逻辑验证+迭代修复
6. `python wd.py build <book_dir> --chapter 1` — 生成任务包

### 日更

1. 检查 `director/director_state.json5` 确认 canWrite=true
2. `python wd.py write <book_dir> --chapter N` — LLM 写正文
3. `python wd.py review <book_dir> --chapter N` — L1 审查
4. 按需：`python scripts/post_writeback.py <book_dir> --chapter N`
5. `python wd.py doctor <book_dir>` — 状态检查

### 审查分级

- L1（每章）：禁飞区扫描、命题贴合、字数、钩子
- L2（每 10 章）：剧情逻辑、人物目标、情绪关系
- L3（每 30 章/卷末）：`python scripts/review_parallel.py <book_dir> --chapter N`（4 Agent 并行）

## 五个子系统

| 子系统 | 路径 | 作用 |
|--------|------|------|
| scanner | `subsystems/scanner/` | 市场雷达：扫榜、跨样本信号提取、可写性评估 |
| analyzer | `subsystems/analyzer/` | 拆文引擎：对标书拆解、角色位抽象 |
| writer | `subsystems/writer/` | 正文执行：情绪驱动、黄金三章、钩子十三式、禁用词表 |
| reviewer | `subsystems/reviewer/` | 深度审查：L1/L2/L3 分级、评分标准 |
| polisher | `subsystems/polisher/` | 去 AI 味：AI/自然文本对比、分级保护 |

## 关键文件

- `director/premise.md` — 书名承诺、禁飞区、角色功能锁
- `director/director_state.json5` — 当前章、canWrite、blockers
- `director/chapter_queue.md` — 细纲表（Goal / Premise Must Hit / Forbidden / Status）
- `truth/current_state.md` — 当前世界状态
- `truth/resource_ledger.md` — 资源账
- `truth/pending_hooks.md` — 伏笔账
- `references/cron-interface.md` — cron 自动写作接口
