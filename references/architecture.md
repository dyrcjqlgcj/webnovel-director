# webnovel-director 架构

## 分层

```text
Router 总路由
├─ Subsystems 子系统层：scanner / analyzer / writer / reviewer / polisher
├─ Concept Gate 概念闸门层：六维验证/选题收束
├─ Canon & Premise 真相层：premise/director_state/角色锁/禁飞区/truth files
├─ Outline Gate 卷纲细纲闸门：命题贡献/禁飞区/转场预案/风险点 + 逻辑验证 + 迭代修复
├─ Execution 正文执行：writer 子系统
├─ Scene Craft 场景表达：转场/对白/章末/去AI味
├─ Review 审查：L1/L2/L3
└─ Repair Feedback 修复回写：状态、审计、cron口径
```

## 运行链路

### 开书链路

```text
用户方向
↓
scanner 扫榜 → 多提案
↓
concept-gate：六维验证 → PASS 才进入下一步
↓
project-init：建 director/truth
↓
premise-guard：固化书名承诺、禁飞区、角色锁
↓
outline-gate：卷纲 + 前 10-20 章细纲 → 六维审查
↓
outline_causal_check：因果链/爽点密度/角色弧线/力量曲线
↓
outline_iterate：迭代修复至通过
↓
execution-dispatch：生成任务包 → 派发 writer 子系统
```

### 日更链路

```text
用户/cron 触发续写
↓
读取 director_state + premise + chapter_queue + truth + last_audit
↓
premise-guard：写前防偏
↓
execution-dispatch：派发 writer 子系统
↓
reviewer (L1)
↓
consistency-module / transition-module 按需
↓
repair-feedback 处理 WARN/FAIL
↓
polisher 去AI味
↓
回写 director_state + truth + audit_log
```

## 核心吸收

### 五个子系统
- **scanner**：市场雷达——扫榜、找趋势
- **analyzer**：拆文引擎——对标分析、提取模块
- **writer**：正文执行器——黄金三章/钩子13式/禁用词/字数标准
- **reviewer**：深度审查——L1每章/L2每10章/L3每30章+4Agent并行
- **polisher**：去AI味——AI味检测/自然文本基准/过度去味保护

### 日更链路

```text
用户/cron 触发续写
↓
读取 director_state + premise + chapter_queue + truth + last_audit
↓
premise-guard：写前防偏
↓
execution-dispatch：派发 writer 子系统写作
↓
chapter-review Level 1
↓
consistency-module / transition-module 按需局部处理
↓
repair-feedback 处理 WARN/FAIL
↓
回写 director_state + truth + audit_log
```

## 模块边界

| 层 | 能做 | 不能做 |
|---|---|---|
| concept-gate | 概念验证打分 | 替代用户直觉判断 |
| project-init | 建目录、模板、初始状态 | 写正文、覆盖旧正文 |
| premise-guard | 判断命题偏离 | 替代一致性检查 |
| outline-gate | 放行/拦截卷纲细纲 | FAIL 后继续写 |
| execution-dispatch | 生成任务包、调执行器 | 裸 prompt 写正文 |
| chapter-review | 写后判定与回写建议 | 只做文风点评 |
| consistency-module | 查状态/资源/伏笔冲突 | 判断书名命题是否成立 |
| transition-module | 修转场、对白、钩子 | 大改剧情方向 |
| repair-feedback | 把问题变成修复动作 | 已发布内容无确认大改 |

## 五个子系统（自包含）

所有子系统内置完整方法论，无需外部 skill 依赖。详细规则见各子系统的 `guide.md`。

### scanner — 市场雷达
- 平台数据采集（番茄/起点/盐言/七猫等）
- 跨样本信号提取 + 可写性评估
- 热点题材趋势 + 饱和风险分析
- 参考：`subsystems/scanner/guide.md`

### analyzer — 拆文引擎
- 黄金三章逐章拆解
- 整体结构分析（故事线/人物位/节奏/反派）
- 快速模式 + 深度模式（逐章结构化输出）
- 角色位抽象：把对标书角色映射为功能位
- 参考：`subsystems/analyzer/guide.md`

### writer — 正文执行器
- 完整写作方法论（情绪驱动/黄金三章/钩子13式/三维度织入）
- 禁用词表 + AI 味检测规则
- 长篇/短篇双模式
- 日更工作流 + 大修工作流
- 参考：`subsystems/writer/guide.md`

### reviewer — 深度审查
- L1/L2/L3 分级审查
- 4 Agent 并行深审（命题/一致性/结构/伏笔）
- R0-R4 自动分级修复
- 参考：`subsystems/reviewer/guide.md`

### polisher — 去AI味
- AI 味 vs 自然文本基准对比
- 分级保护（轻度≤15%/中度≤25%/重度≤35%删除上限）
- 自然替换参考词表
- 参考：`subsystems/polisher/guide.md`

## 第一版边界

已实现：
- 主入口 SKILL.md。
- references 架构/状态/cron/集成说明。
- 8 个模块五文件协议骨架。
- 项目模板与初始化/校验脚本。
- 5 个子系统自包含 modules\chapter-review\guide.md + 完整 reference 文件。

暂不做：
- 自动改现有 cron。
- 全量正文生成器。
- 自动发布平台内容。
