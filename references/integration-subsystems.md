# 子系统集成

## 角色

五个子系统（scanner/analyzer/writer/reviewer/polisher）是导演台的执行层。每个子系统内嵌核心方法论，可独立运行。若需要完整的扫榜/拆文/审查管线，可调用外部 story-* 系列 skill 获取更详细的参考数据。

## 子系统调用

- scanner → 扫榜 → 市场趋势报告
- analyzer → 拆文 → 对标分析 + 可复用模块
- writer → 写作 → 正文执行，遵循黄金三章/钩子/禁用词规范
- reviewer → 审查 → L1/L2/L3 分级审查，L3 可 spawn 4 Agent 并行
- polisher → 润色 → AI 味检测 + 自然文本改写

## 目录映射

| 子系统 | 内嵌目录 | 外部可选扩展 |
|--------|----------|-------------|
| scanner | `subsystems/scanner/` | `story-long-scan`（完整扫榜管线） |
| analyzer | `subsystems/analyzer/` | `story-long-analyze`（深度拆文管线） |
| writer | `subsystems/writer/` | `story-long-write`（完整写作方法论库） |
| reviewer | `subsystems/reviewer/` | `story-review`（多 Agent 深审） |
| polisher | `subsystems/polisher/` | `story-deslop`（完整去AI味管线） |

## 风险

外部 skill 追求成熟网文套路，可能把差异化题材拉回标准模板。所有外部产出必须经过 director premise-guard。

## 禁止

- 禁止让对标书剧情路径替代本书命题
- 禁止只因市场成熟就改写核心卖点
- 禁止把 consistency-checker 当 premise-checker
