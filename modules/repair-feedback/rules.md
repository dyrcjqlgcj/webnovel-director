# 修复反馈运行规则

## 输入

必需：
- 上游审查报告
- 待修对象：大纲/细纲/章节/状态文件

建议读取：
- `templates\last_audit.md`
- `templates\director_state.json5`
- `templates\chapter_queue.md`
- truth files

## 修复分级

- **R0 记录**：无需改正文，只更新 last_audit/truth。
- **R1 局部修**：修改片段/转场/钩子，不改变章节主事件。
- **R2 整章回炉**：章节目标未完成或结构错误。
- **R3 细纲重排**：多章方向错误。
- **R4 卷级回滚**：卷目标违背 premise。

## 处理流程

1. 归类问题来源：命题 / 细纲 / 执行 / 连续性 / 文风读感。
2. 选择最小有效修复级别。
3. 输出修复补丁或重写任务包。
4. 指定回写文件。
5. 修后交回对应模块复审。

## 输出

```text
结论：PASS / WARN / FAIL
依据：上游报告 + 文件位置
问题：需要修复的根因
建议：最多3条修复动作
下一步：局部修 / 重写 / 重排细纲 / 等用户确认
```

## 自动修复边界

可自动修：
- 未发布内容。
- 改动范围 ≤10 章。
- 满足严重偏离自动修正规则。
- 不改变用户明确确认过的核心设定。

必须确认：
- 已发布章节。
- 需要改变书名命题/主角核心能力。
- 需要删除大量已写正文。

## 禁止

- 禁止只说「加强」「优化」不落到具体文本/章节。
- 禁止把 R3/R4 伪装成小修。
- 禁止修完不复审。

## 脚本接口

```bash
python scripts/repair_plan.py <book_dir> --chapter <N> --verdict FAIL --problem "问题描述"
python scripts/repair_plan.py <book_dir> --chapter <N> --from-review review.json
```

自动将问题分级为 R0-R4 并输出修复步骤。
