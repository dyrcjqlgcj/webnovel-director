# 项目初始化运行规则

## 输入

必需：
- 用户提供的书名/题材/一句话方向/已有项目目录，至少一项。

可选：
- 已有大纲、黄金三章、人物表、设定文档。
- 平台目标、字数目标、更新频率、已有 inkos 项目路径。

## 处理流程

1. **识别项目形态**
   - 新书：创建完整目录。
   - 旧书接入：只补 director/truth，禁止移动原正文。
   - 半成品导入：先生成导入清单，再建立 director 层。
2. **生成 premise 初稿**
   - 书名承诺。
   - 命题三要素：主角处境 / 核心爽点 / 长线代价。
   - 禁飞区：会让本书变成普通套路的方向。
   - 角色功能锁：主角、对手、盟友、资源位的叙事功能。
3. **生成 director_state**
   - 当前卷、当前章、executor、canWrite、blockers。
4. **生成 truth files**
   - `truth/current_state.md`
   - `truth/resource_ledger.md`
   - `truth/particle_ledger.md`
   - `truth/pending_hooks.md`
5. **交接给 outline-gate**
   - 输出下一步需要生成的卷纲/前 10-20 章细纲。

## 输出

```text
结论：PASS / WARN / FAIL
依据：创建/读取的文件列表
问题：缺失信息或冲突
建议：最多3条
下一步：进入 outline-gate / 补充信息 / 停止
```

## PASS 条件

- `director/premise.md` 存在且包含命题三要素、禁飞区、角色功能锁。
- `director/director_state.json5` 存在且 `canWrite` 字段明确。
- truth files 至少包含 current_state 与 pending_hooks。

## WARN 条件

- 书名/卖点不清，但可先建立空项目。
- 旧项目存在多个大纲版本，需要后续合并。
- 没有平台/字数目标，但不影响建目录。

## FAIL 条件

- 项目目录不可写。
- 用户方向互相矛盾，无法形成单一书名承诺。
- 已有正文与用户声明方向明显不是同一本书。

## 禁止

- 禁止覆盖已有正文和大纲。
- 禁止把 premise 写成完整世界观百科。
- 禁止没有 premise 就创建自动写作 cron。
