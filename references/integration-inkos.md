# inkos 集成

## 角色

inkos 是执行层：正文 + audit + revise。

## 吸收点

- Radar → Architect → Writer → Auditor → Reviser
- 三大真相文件：current_state / particle_ / pending_hooks
- audit → revise → until pass
- 标记人工审核

## 调用前必须注入

- premise.md
- director_state
- last_audit
- chapter_queue
- truth files

## 任务包交接

webnovel-director 不直接让 inkos 自由发挥，而是先生成任务包：

```bash
python scripts/build_task_package.py <book_dir> --chapter <N> --out <book_dir>/director/task_packages/<NNNN>.yaml
```

inkos 执行时读取任务包，遵守：

- `premise_must_hit` — 本章必须兑现的命题元素
- `forbidden` — 本章禁止走的套路
- `state_before` — 写前状态起点
- `continuity.read_files` — 必读的 truth 文件
- `continuity.update_files` — 写后必须更新的文件
- `audit_after: level_1` — 写后审查级别

## 写后流程

```bash
# Level 1 快速审查（串行，5 维）
python scripts/review_chapter.py <book_dir> --chapter <N> --text chapters/<NNNN>_*.txt

# Level 1 深度审查（并行 4 Agent + 交叉矛盾检测）
python scripts/review_parallel.py <book_dir> --chapter <N> --text chapters/<NNNN>_*.txt

# 回写 director/truth
python scripts/post_writeback.py <book_dir> --chapter <N> --audit PASS --summary "审查摘要" --write
```

## 替换条件

如出现以下情况，考虑由 webnovel-director 自建执行器：

1. 正文质量不稳定
2. 文件结构难以与 director 对齐
3. 自动化经常失败
4. 状态回写不满足

## 禁止

- 禁止让 inkos 独立决定卷纲方向。
- 禁止 cron 裸调 inkos 写正文。
- 禁止跳过 director 写前闸门。
