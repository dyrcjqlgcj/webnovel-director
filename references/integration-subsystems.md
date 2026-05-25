# 子系统集成

## 角色

五个子系统（scanner/analyzer/writer/reviewer/polisher）是导演台的执行层。每个子系统**自包含**完整方法论和 reference 文件，无需安装任何外部 skill 即可独立运行。

另有一个 **dashboard** 子系统提供 web 仪表盘。

## 子系统调用

- scanner → 扫榜 → 市场趋势报告（见 `subsystems/scanner/guide.md`）
- analyzer → 拆文 → 对标分析 + 可复用模块（见 `subsystems/analyzer/guide.md`）
- writer → 写作 → 正文执行，遵循黄金三章/钩子/禁用词规范（见 `subsystems/writer/guide.md`）
- reviewer → 审查 → L1/L2/L3 分级审查，L3 可 spawn 4 Agent 并行（见 `subsystems/reviewer/guide.md`）
- polisher → 润色 → AI 味检测 + 自然文本改写（见 `subsystems/polisher/guide.md`）

## 共享 reference 文件

所有子系统共享 `references/craft/` 目录下的核心写作参考文件（禁用词、写作技法、情绪设计等），避免重复。各子系统专属 reference 文件存放在各自 `references/` 子目录。

## 安全边界

- 所有子系统的分析/产出必须通过 director premise-guard
- 禁止让对标书剧情路径替代本书命题
- 禁止只因市场成熟就改写核心卖点
- 禁止把 consistency-checker 当 premise-checker
