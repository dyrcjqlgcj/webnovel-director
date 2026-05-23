# inkos 状态同步

用于把已有 inkos 项目的 `story/` 与 `chapters/` 状态同步到 webnovel-director 的 `director/` 与 `truth/` 层。

## 命令

只检查，不写入：

```bash
python scripts/sync_inkos_state.py <book_dir>
```

写入 director/truth 层：

```bash
python scripts/sync_inkos_state.py <book_dir> --write
```

## 安全边界

- 只读取 `chapters/` 与 `story/`。
- `--write` 只更新：
  - `director/director_state.json5`
  - `director/audit_log.md`
  - `truth/current_state.md`
  - `truth/resource_ledger.md`
  - `truth/particle_ledger.md`
  - `truth/pending_hooks.md`
- 不修改正文。
- 不修改 inkos 原始 `story/*.md`。
- 不把 `canWrite` 改成 true；是否可写必须由 outline-gate 决定。

## 主要检查

- `chapters/` 最新章节号。
- `story/current_focus.md` 是否落后于最新章节。
- `story/current_state.md` 和 `story/pending_hooks.md` 是否存在。
- 生成 resource/particle 摘要，作为 director 写前读取依据。

## 输出

```text
结论：PASS / WARN / FAIL
依据：latest=ChXXXX; focus=N; book=<path>
问题：...
建议：同步 current_focus / 审 chapter_queue / outline-gate PASS 后再 canWrite=true
下一步：outline-gate
```
