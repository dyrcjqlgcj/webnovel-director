# 卷纲/细纲闸门运行规则

## 输入

必需：
- `director/premise.md`
- 卷纲或章节细纲

建议读取：
- `director/volume_state.md`
- `director/chapter_queue.md`
- `director/last_audit.md`
- `truth/current_state.md`
- `truth/pending_hooks.md`

## 检查维度

1. **卷承诺**：本卷要兑现什么升级、关系、危机或认知变化。
2. **命题贴合**：每 3 章至少一次可见命题兑现。
3. **禁飞区扫描**：抢首通、建公会碾压、正面推本等禁区是否出现。
4. **爽点递进**：小爽点是否累积到卷级爽点，而不是随机事件。
5. **钩子回收**：pending_hooks 是否被使用、延后或废弃说明。
6. **执行可写性**：每章是否有明确目标、冲突、转折、章末钩子。
7. **大纲逻辑性**（新增）：因果链完整性、爽点密度、角色弧线、力量曲线（详见 outline_causal_check.py）



## 逐章审查报告

升级版 `outline_gate_review.py` 会读取 `premise.md` 解析命题、禁飞区、角色锁、卷级禁区，读取 `pending_hooks.md` 检查钩子覆盖，然后对 `chapter_queue.md` 的每一章生成六维审查报告：

1. **卷承诺** — 是否落入卷级禁区。
2. **命题贴合** — goal/premise_must_hit 是否与书名承诺关键词有交集。
3. **禁飞区扫描** — goal 中是否出现 premise 禁止的套路表达。
4. **爽点递进** — 连续章节是否保持命题兑现密度。
5. **钩子回收** — 有大量开放钩子时是否被涉及。
6. **可执行性** — Goal 长度、Premise Must Hit、动作词。

```bash
python scripts/outline_gate_review.py <book_dir>
python scripts/outline_gate_review.py <book_dir> --write-report  # 写入 director/outline_review.md

# 逻辑验证（因果链/爽点密度/角色弧线/力量曲线）——在六维审查后运行
python scripts/outline_causal_check.py <book_dir>
python scripts/outline_causal_check.py <book_dir> --write-report  # 写入 director/outline_logic_review.md
```

与旧版区别：旧版 `outline_gate_check.py` 只做结构门禁（行存在/状态字段/缺Goal）；新版做语义审查（六维判定 + 逐章报告 + 特定建议）；`outline_causal_check.py` 做逻辑结构审查（因果链/密度/弧线/曲线）。

## 脚本接口

第一版提供保守检查脚本：

```bash
python scripts/outline_gate_check.py <book_dir>
```

它只检查 `director/chapter_queue.md` 是否可派发，不生成正文。

FAIL 条件包括：

- 缺少 `director/premise.md` 或 `director/chapter_queue.md`。
- chapter_queue 没有章节行。
- 章节缺少 Goal 或 Premise Must Hit。
- 章节状态为 `NEEDS_OUTLINE_GATE / FAIL / BLOCKED / STOP / 修复 / 未通过`。
- 章节目标疑似触犯无系统禁区且没有写在 Forbidden 中。

WARN 条件包括：

- Forbidden 缺失。
- Goal 过短，不可执行。
- 状态字段不明确。

只有脚本 PASS 后，才允许清空 blockers、设置 `canWrite=true`，再进入 execution-dispatch。

## 输出

```text
结论：PASS / WARN / FAIL
依据：引用 premise / volume_state / 细纲条目
问题：按章列出
建议：最多3条修复动作
下一步：进入 execution-dispatch / 修复细纲 / 停止
```

## PASS

- 卷目标清晰，且不违背 premise。
- 章节队列可执行：每章至少有「目标-阻碍-变化-钩子」。
- 没有禁飞区。

## WARN

- 个别章节目标模糊，但可通过任务包补足。
- 爽点密度偏低，但卷目标仍正确。
- 钩子较弱，需要 transition-module 辅助。

## FAIL

- 卷目标与书名命题相反。
- 多章连续走常规套路替代本书机制。
- 细纲没有可执行单位，只有概念描述。
- 关键人物功能越界。

## 禁止

- 禁止 FAIL 后继续派发正文。
- 禁止把「再写时注意」当修复。
- 禁止未更新 chapter_queue 就启动自动写作。


