# cron 接口设计

第一版只设计接口，不自动改 cron。任何自动写作 cron 都必须先过 director 闸门。

## 未来流程

```text
cron wake
↓
webnovel-director 写前闸门
↓
读取 premise / director_state / last_audit / chapter_queue / truth files
↓
判断 canWrite + blockers
↓
生成写作任务包
↓
调用 inkos 或内部执行器
↓
Level 1 审查
↓
回写 director_state / last_audit / chapter_queue / truth files
↓
通知
```

## cron prompt 最小格式

```text
这是 webnovel-director 自动写作任务。
项目路径：<book_dir>
目标：写/修第 <N> 章
必须先执行：
1. 读取 director/premise.md
2. 读取 director/director_state.json5
3. 读取 director/chapter_queue.md
4. 读取 director/last_audit.md
5. 读取 truth/current_state.md、truth/resource_ledger.md、truth/particle_ledger.md、truth/pending_hooks.md

闸门：
- canWrite=false 或 blockers 非空 → 不写正文，只报告阻塞
- 当前章不在 chapter_queue → 不写正文，要求 outline-gate
- premise-guard WARN/FAIL → 不写正文，进入 repair-feedback

写后：
- 运行 chapter-review Level 1
- 更新 last_audit、director_state、chapter_queue、truth files
- 汇报 PASS/WARN/FAIL 与下一步
```

## 写前必须检查

- 是否存在未修复 FAIL。
- `director_state.canWrite` 是否为 true。
- `director_state.blockers` 是否为空。
- chapter_queue 是否包含当前章。
- chapter_queue 是否过期或与 currentChapter 冲突。
- cron prompt 是否与 director_state 中的 title/currentChapter/activeVolume 一致。
- 卷纲/细纲是否通过 outline-gate。

## 写后必须更新

- `director/director_state.json5`
- `director/last_audit.md`
- `director/audit_log.md`
- `director/chapter_queue.md`
- `truth/current_state.md`
- `truth/resource_ledger.md`
- `truth/particle_ledger.md`
- `truth/pending_hooks.md`
- 项目 memory 摘要（只记录关键状态，不贴整章正文）

## 禁止

- 禁止 cron 直接要求「继续写下一章」而不指定项目路径和 director 文件。
- 禁止自动任务在 FAIL 后继续写新章。
- 禁止自动任务修改已发布章节，除非用户明确授权。
