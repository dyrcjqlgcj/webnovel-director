# 命题防偏运行规则

## 输入

必需：
- `templates\premise.md`
- 待审对象：用户请求 / 卷纲 / 细纲 / 章节 / cron prompt

建议读取：
- `director/forbidden_zones.md`
- `director/role_locks.md`
- `templates\director_state.json5`
- `templates\last_audit.md`
- `templates\current_state.md`

## 判断维度

1. **书名承诺**：当前内容是否兑现标题/核心卖点。
2. **主角路径**：主角是否仍在用本书独有机制解决问题。
3. **禁飞区**：是否出现 premise 明确禁止的套路。
4. **角色功能锁**：配角/反派/系统是否越权替主角完成关键爽点。
5. **长线代价**：是否保留成本、风险、反噬或更大问题。

## 输出

```text
结论：PASS / WARN / FAIL
依据：引用 premise 条目 + 待审文本位置
问题：列出偏离点
建议：最多3条修复方向
下一步：继续 / 修复 / 停止
```

## PASS

- 核心爽点仍由主角以本书机制完成。
- 未触犯禁飞区。
- 章节推进会强化而非稀释命题。

## WARN

- 本章命题元素较弱，但上下文可解释。
- 出现套路苗头，尚未造成方向反转。
- 配角功能接近越界，需要下一章收束。

## FAIL

- 主角采取 premise 禁止路径解决核心问题。
- 连续章节没有兑现核心爽点。
- 细纲执行方向与书名承诺相反。
- 自动任务 prompt 绕过 director/truth 文件裸写正文。

## 自动修正规则

满足以下任意情况，必须停止写作并进入 repair-feedback：

- 触犯 A：主角违反禁飞区。
- 触犯 B：连续 3 章偏离命题。
- 触犯 C：细纲执行成相反方向。
- 已发布内容：默认只给修复方案，不自动改正文。

## 禁止

- 不因「市场常见套路」放宽 premise。
- 不把 consistency-check 当 premise-check。
- 不在未读 premise 的情况下判断是否偏离。
