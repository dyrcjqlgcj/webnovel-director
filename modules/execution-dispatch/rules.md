# 执行派发运行规则

## 输入

必需：
- `director/premise.md`
- `director/director_state.json5`
- `director/chapter_queue.md`
- 当前要写的章节编号/目标

建议读取：
- `director/last_audit.md`
- `truth/current_state.md`
- `truth/resource_ledger.md`
- `truth/particle_ledger.md`
- `truth/pending_hooks.md`

## 任务包必须包含

```yaml
chapter: 0001
title_hint: ""
chapter_goal: "本章读者读完应获得的变化"
premise_must_hit:
  - "本章必须兑现的命题元素"
forbidden:
  - "本章禁止走的套路"
state_before:
  - "人物/资源/伏笔起点"
beats:
  - goal: "场景目标"
    conflict: "阻碍"
    turn: "变化"
    hook: "章末或场景末钩子"
continuity:
  read_files: []
  update_files: []
audit_after: "level_1"
```


## 脚本接口

第一版真实任务包由脚本生成：

```bash
python scripts/build_task_package.py <book_dir> --chapter 12 --out <book_dir>/director/task_packages/0012.yaml
```

脚本会保守失败，以下情况不产出任务包：

- 缺少 director/truth 必需文件。
- `director_state.canWrite=false`。
- `director_state.blockers` 非空。
- `chapter_queue.md` 中没有目标章节。
- 目标章节状态不是 PASS/READY/待写/可写。
- 目标章节缺少 Goal 或 Premise Must Hit。

产出的任务包必须交给执行器，并要求写后执行 chapter-review Level 1 与状态回写。

## 执行器选择

1. 默认：inkos。
2. 若需要拆文/市场素材：oh-story 只做参考，不直接写正文。
3. 若 inkos 输出缺少状态回写或审查：由 director 补审查，不跳过。

## 输出

```text
结论：PASS / WARN / FAIL
依据：章节队列 + 状态文件
问题：任务包缺项
建议：最多3条
下一步：调用执行器 / 补任务包 / 停止
```

## PASS

- chapter_queue 当前章存在且通过 outline-gate。
- 任务包包含目标、冲突、转折、钩子、禁区。
- canWrite 为 true，且无 blockers。

## WARN

- 任务包可写，但 last_audit 有注意事项。
- truth files 有轻微缺项，可在写后补。

## FAIL

- canWrite 为 false。
- chapter_queue 缺当前章。
- 未读 premise 或禁飞区。
- cron prompt 要求裸写正文。

## 禁止

- 禁止把用户一句话直接转给执行器。
- 禁止跳过写后 Level 1 审查。
- 禁止在 blocker 未清空时继续写新章。

