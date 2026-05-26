# reviewer — 深度审查

webnovel-director 的多视角审查子系统。每章写完后自动触发，分三级审查 + 4 Agent 并行深审。

## 审查分级

| Level | 频率 | 检查内容 | 模式 |
|-------|------|----------|------|
| L1 | 每章 | 禁飞区扫描、命题贴合、字数、钩子 | solo |
| L2 | 每 10 章 | 剧情逻辑、人物目标、情绪关系、伏笔 | solo |
| L3 | 每 30 章/卷末 | 多 Agent 并行深审 | full（4 Agent 并行） |

> L3 也可以手动触发：`/审查` 或 `python scripts\review_parallel.py <book_dir>`

## L1 审查（每章）

执行 `scripts\review_chapter.py`，检查：
1. **禁飞区**：对照 premise.md 的禁飞区列表扫描。命中 → FAIL
2. **命题贴合**：本章是否兑现了 chapter_queue 中的 Premise Must Hit
3. **字数达标**：是否 ≥ 目标字数的 90%
4. **钩子检查**：章尾是否有钩子（类型不限，但不能无）
5. **禁用词扫描**：对照 `references/craft/banned-words.md` 一级词

输出：PASS / WARN / FAIL + 具体问题列表

## L2 审查（每 10 章）

在 L1 基础上增加：
1. **剧情逻辑**：前 10 章的因果链是否自洽
2. **人物目标**：主角是否有清晰的阶段性目标并推进
3. **情绪关系**：关键角色间情绪关系是否有变化
4. **伏笔状态**：已埋伏笔是否有推进/回收，是否伏笔太多太散

执行：`scripts\review_chapter.py --level 2 --range 1-10`

## L3 审查（每 30 章/卷末）— 4 Agent 并行

使用 `scripts\review_parallel.py` 并行 spawn 4 个子 Agent，各从不同视角审查，主线程综合裁决。

### Agent 1：命题审查（premise agent）
- 命题偏离检测（对照 premise.md 三要素）
- 禁飞区触犯扫描
- 书名承诺兑现度
- 角色功能锁是否被破坏

### Agent 2：一致性审查（consistency agent）
- 资源账本冲突（resource_ledger 前后不一致）
- 关系图矛盾（relationship_graph 被违反）
- 设定冲突（力量体系/世界观被破坏）
- 时间线自洽性

### Agent 3：结构审查（structure agent）
- 钩子质量（章首/章尾/段落级）
- 对白质量（AI 味检测、角色语言风格一致性）
- 节奏均匀度（有无连续多节无情绪变化）
- 段落密度（一段一句原则、≤60 字控制）

### Agent 4：伏笔审查（foreshadowing agent）
- 伏笔回收率（已埋/已回收/逾期未回收）
- 新增伏笔密度（是否过多）
- 伏笔合理性（是否硬埋/强行反转）

### 综合裁决规则

收集 4 个 Agent 的 VERDICT 后：
- 4 个全部 APPROVE → PASS
- 有 CONCERNS 无 REJECT → WARN
- 有 REJECT → FAIL

Agent 间有分歧时，明确呈现双方理由让用户裁决，不自动妥协。

## 审查输出格式

```markdown
=== 审查报告 ===
审查范围: 第 N-M 章
审查等级: L1/L2/L3
综合评定: PASS / WARN / FAIL

## 发现的问题
{S1→S4 分级列出}

## Agent 分歧（如有）
{列出不同意见}

## 修复建议
{按优先级排列}

## 下一步
- PASS → 继续下一章
- WARN → 可选修复后继续
- FAIL → 进入 repair-feedback，不修复不继续
```

## 修复分级（R0-R4）

审查发现的问题按严重程度分五级：

| 等级 | 描述 | 处理方式 |
|------|------|----------|
| R0 | 记录即可 | 更新 last_audit / truth，不改正文 |
| R1 | 局部修改 | 修改片段/转场/钩子，不改变主事件 |
| R2 | 整章回炉 | 章节目标未完成或结构错误 |
| R3 | 细纲重排 | 多章方向错误 |
| R4 | 卷级回滚 | 卷目标违背 premise |

执行：`python scripts/repair_plan.py <book_dir> --chapter N`

## 强制闸门

- FAIL 后不继续写新章
- 连续 3 章 WARN → 升级为 FAIL 处理
- post_writeback 发现 FAIL/WARN → 不更新 currentChapter

## 参考文件

| 文件 | 用途 |
|------|------|
| `references/craft/quality-checklist.md` | 质量检查清单 |
| `references/craft/banned-words.md` | 禁用词全表 |
| `references/craft/anti-ai-writing.md` | AI 味检测 |
| `subsystems/reviewer/references/quality-rubric.md` | 平台评分标准 |
| `subsystems/reviewer/references/rubrics/` | 各平台 rubric |
