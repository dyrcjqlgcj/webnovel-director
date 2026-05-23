# 写后回写接口

`post_writeback.py` 用于在 chapter-review Level 1 之后，把审查结论写回 director/truth 层。

它不写正文，也不修改章节文件。

## 命令

默认 dry-run：

```bash
python scripts/post_writeback.py <book_dir> \
  --chapter 31 \
  --audit PASS \
  --summary "本章完成第7块碎片验证，主角确认神殿标记会响应在线碎片"
```

实际写回：

```bash
python scripts/post_writeback.py <book_dir> \
  --chapter 31 \
  --audit PASS \
  --summary "本章完成第7块碎片验证" \
  --state-change "主角确认核心标记与在线碎片同步" \
  --resource-change "第7块碎片仍在线，不能直接取走" \
  --particle "神殿标记响应在线碎片" \
  --hook "连接器需要苏州4块离线碎片参与" \
  --write
```

## 审查结果行为

| audit | director_state | chapter_queue | 下一步 |
|---|---|---|---|
| PASS | `currentChapter` 推进，`canWrite=true`，blockers 清空 | 目标章 → `DONE` | 可继续下一章 |
| WARN | `canWrite=false`，写入 WARN blocker | 目标章 → `WARN_REVIEW` | 人工复核 |
| FAIL | `canWrite=false`，写入 FAIL blocker | 目标章 → `BLOCKED` | repair-feedback |

## 更新文件

`--write` 会备份并更新：

- `director/director_state.json5`
- `director/last_audit.md`
- `director/audit_log.md`
- `director/chapter_queue.md`
- `truth/current_state.md`
- `truth/resource_ledger.md`
- `truth/particle_ledger.md`
- `truth/pending_hooks.md`

备份格式：`<filename>.bak.YYYYMMDD-HHMMSS`

## 禁止

- 禁止在没有 chapter-review 的情况下伪造 PASS。
- 禁止用它修改正文。
- WARN/FAIL 后禁止继续 build_task_package 写下一章。

