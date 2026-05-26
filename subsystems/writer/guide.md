# writer — 正文执行器

webnovel-director 的写作执行子系统。接收 execution-dispatch 派发的任务包，产出正文。

## 核心哲学

1. **先定情绪，再定故事**：动笔前必须确定本节目标情绪（爽感释放/意难平/反转震撼/治愈温暖/细思极恐/共鸣感动），所有内容为这个情绪服务。
2. **从验证过的模式出发**：有对标书就按 analyzer 拆解结果做模块组装，没有就从题材框架（`references/craft/genre-catalog.md`）找验证过的剧情模式。
3. **用模块组装，不重新发明**：铺垫段、升级段、反转段各有成熟写法。参考 `references/craft/genre-writing-formulas.md`。
4. **只加载必需信息**：写每节前明确目标情绪和要用的技法，答不出就先回读参考。

## 写作流程

### 准备层（每章写作前）

1. **状态筛选**：从 `templates\current_state.md`、`templates\particle_ledger.md`、`templates\resource_ledger.md` 筛选本章涉及的状态和资源。
2. **模块召回**：① 本章目标情绪词？② 借鉴哪个参考文件的哪个技法？③ 用在哪些段落？
3. **指令确认**：综合细纲 + 状态 + 模块召回，用一句话概括本章写作意图。
4. **字数约束**（强制）：
   - 从 `director/chapter_queue.md` 读取本章的 `Scenes` 和 `Words` 列
   - 若 `Words` 已设定：硬限制目标字数，超出部分自动裁剪（优先减环境描写和内心独白）
   - 若 `Scenes` 已设定：场景数 × 800 字作为软上限
   - 默认上限：4000 字（未设定 Scenes 和 Words 时）
   - prompt 中强制注入：`本章字数限制：N 字。若超限，优先精简环境描写和内心独白，保留核心情节和对话。`

### 正文执行

按**三维度织入**写作（发生 + 感知 + 反应织入同一段连续正文），但仍按镜头断段：
- 一段只承载一个动作/信息变化
- 优先一段一句，避免一段到底
- 输出前做密度重排：段落 >60 字按句号/动作转折拆开，单句 >45 字拆短

## 篇章结构

### 黄金三章铁律

- 500 字内必须有钩子——前 3 句不能是环境描写，必须是事件/对话/动作/信息炸弹
- 内心戏必须外化为可见事件（决定/误判/对话/物件变化/外部压力）
- 第 3 章结束前，读者必须能说出"这本书爽在哪里"
- 爽点密度：每 3000-5000 字一个情绪节点

### 单章结构

```
开头（前 300-500 字）：3 句话内抓住读者
  ├─ 冲突前置 / 信息差钩 / 反常行为 / 重生反常 / 超自然身份 / 悬念句
  └─ 前 100 字事件密度 ≥ 3

铺垫（30-40%）：建立羁绊 + 埋反转线索
  ├─ 用物件/数字/习惯建立羁绊
  ├─ 至少 3 个反转线索分散在不同小节
  ├─ 每 2-3 小节一个钩子
  └─ 情绪强度逐节递增

升级（20-30%）：冲突升级 + 紧迫感
  ├─ 强度/范围/代价至少一个维度上升
  ├─ 插入倒计时钩子或代价钩子
  ├─ 埋入误导信息
  └─ 一动一静交替

反转（10-15%）：在一节内完成揭示
  ├─ 揭示后确保前面铺垫可被回溯
  ├─ 情绪冲击强度 > 前面所有节
  └─ 用证物/证人/偷听/剥洋葱揭露

结尾（5-10%）：钩子或余韵
  └─ 用安静细节收尾（一个物件/一个动作/一句短话）
```

## 章尾钩子 13 式

| # | 类型 | 说明 |
|---|------|------|
| 1 | 信息断崖 | 关键信息说一半 |
| 2 | 危机预告 | 预告即将到来的危险 |
| 3 | 反转揭示 | 揭示颠覆性信息 |
| 4 | 身份悬念 | 暗示某角色身份有问题 |
| 5 | 能力觉醒 | 主角能力出现变化 |
| 6 | 冲突升级 | 矛盾加剧 |
| 7 | 规则改变 | 世界规则被打破 |
| 8 | 时间压力 | 倒计时或截止日期 |
| 9 | 情感冲击 | 情感上的重大变化 |
| 10 | 谜题抛出 | 新的谜团 |
| 11 | 对比震撼 | 强对比制造震撼 |
| 12 | 代价出现 | 行动带来的代价 |
| 13 | 视角切换 | 切换到另一个视角 |

## 字数标准

| 节奏 | 最低字数 |
|------|----------|
| 高速推进 | ≥ 2000 字/章 |
| 正常节奏 | ≥ 3000 字/章 |
| 高潮爆发 | ≥ 2000 字/章 |

> 短篇：每节 ≥ 800 字，总字数 8000-30000。爽文可降至 ≥ 500 字/节。

字数统计使用 `python3 -c "from pathlib import Path; print(len(Path('文件路径').read_text(encoding='utf-8')))"`。禁止用 `wc -c` 或模型估算。

## AI 味禁用词

完整禁用词列表和自然替换参考见 `references/craft/banned-words.md`（一级/二级分级，含替换建议和例句）。写后检查阶段对照该文件进行全量扫描。

## 开头技巧

| 技巧 | 说明 |
|------|------|
| 冲突前置 | 第一句就是矛盾 |
| 信息差钩 | 给读者一个角色不知道的信息 |
| 反常行为 | 用一个不合常理的行为引起好奇 |
| 悬念句 | 抛出一个需要解释的事实 |
| 代入式提问 | 直接让读者产生共鸣 |

## 对话规则

- 60%+ 无对话标签，用动作替代"说"
- 对话推进剧情或揭示性格
- 有打断、有口头禅、有废话——不像演讲稿

## 写后检查

1. 章尾是否有钩子
2. 爽点是否到位
3. 字数是否达标
4. 禁用词扫描（对照 `references/craft/banned-words.md`）
5. 更新 `truth/` 文件（current_state / particle_ledger / pending_hooks）

## 长篇 vs 短篇差异

| 维度 | 长篇 | 短篇 |
|------|------|------|
| 结构 | 卷 → 章 → 节 | 段 → 节 |
| 情绪 | 多线并进、有起伏周期 | 一条情绪线贯穿 |
| 反转 | 多个反转分散在各卷 | 一个核心反转撑全篇 |
| 人称 | 第三人称为主 | 第一人称为主（盐言） |
| 钩子密度 | 每章有章尾钩子 | 每 2-3 小节一个钩子 |
| 追踪 | truth files 全量维护 | 简化版追踪 |

## 参考文件

| 文件 | 用途 |
|------|------|
| `references/craft/genre-catalog.md` | 题材框架速查 |
| `references/craft/genre-writing-formulas.md` | 各题材创作公式 |
| `references/craft/hooks-chapter.md` | 章首/章尾钩子设计 |
| `references/craft/hooks-paragraph.md` | 段落级钩子技巧 |
| `references/craft/hooks-suspense.md` | 悬念设计 |
| `references/craft/banned-words.md` | 禁用词全表 |
| `references/craft/anti-ai-writing.md` | AI 味检测与修复 |
| `references/craft/writing-craft.md` | 写作技法全程参考 |
| `references/craft/dialogue-mastery.md` | 对话写作 |
| `references/craft/character-basics.md` | 人物基础设定 |
| `references/craft/character-design-methods.md` | 人设方法 |
| `references/craft/character-relations.md` | 人物关系设计 |
| `references/craft/emotional-methods.md` | 情绪操控技法 |
| `references/craft/emotional-arc-design.md` | 情绪弧线设计 |
| `references/craft/reversal-toolkit.md` | 反转设计工具箱 |
| `references/craft/opening-design.md` | 黄金三章法则 |
| `references/craft/state-tracking.md` | 状态追踪协议 |
| `references/craft/quality-checklist.md` | 质量检查清单 |
| `references/craft/format-and-structure.md` | 格式规范 |
| `subsystems/writer/references/workflow-daily.md` | 日更工作流 |
| `subsystems/writer/references/workflow-revision.md` | 大修工作流 |
| `subsystems/writer/references/outline-methods.md` | 大纲方法 |
| `subsystems/writer/references/plot-core-methods.md` | 连续性追踪 |
