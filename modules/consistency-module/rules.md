# 一致性模块运行规则

## 输入

必需：
- 待审正文/大纲
- `templates\current_state.md`

建议读取：
- `templates\resource_ledger.md`
- `templates\particle_ledger.md`
- `templates\pending_hooks.md`
- `templates\audit_log.md`

## 检查维度

1. **人物状态**：目标、立场、关系、伤势、认知。
2. **资源账**：钱、道具、经验、技能、消耗品、冷却。
3. **时间线**：章节内外时间跨度是否合理。
4. **空间位置**：人物是否能合理到场。
5. **伏笔账**：新增、推进、回收、废弃。
6. **设定规则**：本章是否改写了既有规则。

## 输出

```text
结论：PASS / WARN / FAIL
依据：正文位置 + truth 条目
问题：冲突列表
建议：最多3条修复或回写动作
下一步：回写 / 局部修 / 停止
```

## PASS

- 无硬冲突。
- 新增状态均可回写。

## WARN

- 有轻微模糊，可通过补一句或回写解释解决。
- 伏笔暂未回收但未过期。

## FAIL

- 同一资源重复使用。
- 人物在不可能时间/地点出现。
- 关键设定被无解释推翻。
- 伏笔回收与前文承诺相反。

## 禁止

- 禁止因为「情节需要」忽略硬冲突。
- 禁止把命题偏离判为一致性问题后放轻。
- 禁止检查后不列出需要更新的 truth 文件。

## 关系图验证

新增 `templates\relationship_graph.yaml` 用于记录人物、资源、钩子之间的因果边。

验证命令：

```bash
python scripts/validate_relationships.py <book_dir>
```

一致性检查应同时参考 ledger（资源账）和 graph（关系图）：
- ledger 说"碎片数量 = 2"——不再只是数字，而是"碎片2 ←脉冲同步→ 在线碎片7"这条边是否仍然成立
- graph 中 `active_until` 标记 —— 过期边不再参考
- 孤立节点（有 incoming 无 outgoing）—— 可能遗漏因果关系
