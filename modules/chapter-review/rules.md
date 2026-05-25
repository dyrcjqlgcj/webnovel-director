# 章节审查运行规则

## 输入

必需：
- 待审章节正文
- 章节任务包或 `templates\chapter_queue.md`
- `templates\premise.md`

建议读取：
- `templates\last_audit.md`
- `templates\current_state.md`
- `templates\resource_ledger.md`
- `templates\particle_ledger.md`
- `templates\pending_hooks.md`

## Level 1：每章快速审查

检查：
1. 本章目标是否完成。
2. 是否触犯禁飞区。
3. 主角机制是否可见。
4. 章末钩子是否成立。
5. 需要回写的状态变化。

## Level 2：每 10 章普通审查

增加：
- 情节逻辑链。
- 人物目标连续性。
- 资源/伤势/技能账本。
- 伏笔新增、回收、过期。
- 情绪关系递进。

## Level 3：每 30 章/卷末/连续 WARN/FAIL

增加：
- 命题深审。
- 卷级爽点兑现。
- 读者承诺是否变形。
- 可调用 story-review 多视角审查。


## 写后回写脚本

chapter-review Level 1 完成后，用 `scripts\post_writeback.py` 回写状态：

```bash
python scripts/scripts\post_writeback.py <book_dir> --chapter <N> --audit PASS|WARN|FAIL --summary "审查摘要" --write
```

规则：

- PASS：推进 `currentChapter`，清空 blockers，目标章标记 DONE。
- WARN：`canWrite=false`，目标章标记 WARN_REVIEW，等待复核。
- FAIL：`canWrite=false`，目标章标记 BLOCKED，进入 repair-feedback。

脚本只改 director/truth 文件，不改正文。

## 输出

```text
结论：PASS / WARN / FAIL
依据：章节段落 + premise / task package / truth files
问题：按严重度列出
建议：最多3条修复动作
下一步：回写状态 / 局部修 / 回炉 / 停止
```

## PASS

- 章节目标完成。
- 无禁飞区。
- 可明确回写状态。

## WARN

- 可发布/可进入下一章，但有小问题需记录。
- 钩子弱、情绪不足、局部连续性待补。

## FAIL

- 命题反转。
- 章节目标未完成。
- 关键设定/资源账冲突。
- 需要重写才能继续。

## 禁止

- 禁止只夸质量不做判定。
- 禁止审查后不更新 last_audit。
- 禁止把文风意见放在命题/连续性之前。

