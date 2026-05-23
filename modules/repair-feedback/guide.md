# 修复反馈

用于把 WARN/FAIL 变成可执行修复动作，并在修完后解除 blocker 或更新 chapter_queue。

## 解决的问题

- 审查报告只有问题，没有改法。
- FAIL 后继续写，导致错误扩散。
- 局部修、整章重写、回滚细纲之间没有分级。

## 什么时候用

- premise-guard / outline-gate / chapter-review 返回 WARN/FAIL。
- 用户要求「回炉」「重写」「按审查意见修」。
- cron 自动写作失败后需要恢复。
