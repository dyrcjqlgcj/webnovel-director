# 项目初始化正例

## 例 1：新书

用户：开一本《别人通关我刷怪，经验复利到成神》。

输出：
```text
结论：PASS
依据：已创建 director/premise.md、director/director_state.json5、truth/current_state.md、truth/pending_hooks.md
问题：暂无
建议：
1. 先生成第一卷卷纲，不直接写第一章。
2. 把「不能抢首通、不能建公会碾压」写入禁飞区。
下一步：进入 outline-gate
```

为什么对：先固化书名命题和禁飞区，再进入卷纲，不让执行器直接套升级流。

## 例 2：旧书接入

用户：这个项目已有 36 章，帮我接入导演系统。

输出重点：
- 不移动正文。
- 扫描已有目录，生成 `templates\audit_log.md` 初始记录。
- `director_state.currentChapter = 36`。
- `canWrite = false`，直到 premise-guard 对已有主线过一遍。
