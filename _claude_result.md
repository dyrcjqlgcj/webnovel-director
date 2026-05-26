# 仪表盘 UI 重构 — 完成摘要

## 修改文件
`scripts/dashboard_server.py`

## 变更内容

### 1. 后端 actions 字典
- 无需修改——原代码仅含 `doctor` 和 `review` 两个 action（`review_ch_` 按章审查为动态注入）
- 已删除的按钮（causal/iterate/scoring/trend/batch_repair/pacing/l3_review/cron_audit）仅存在于 HTML 层

### 2. 操作按钮精简
从 12 个按钮精简为 4 个：
- 🔍 一键体检（primary）
- 📋 大纲审查
- 📋 导出
- 🔃 刷新

### 3. 章节表格内嵌评分
- 第 4 列（原为文件修改时间 mTime）改为调用 `scoreHtml(c)` 显示评分+趋势
- 列布局：`# | 标题 | 字数 | 评分 | 审查 | 审查时间 | 审查详情 | 状态 | 操作`

### 4. calcScore() 修正
删除「已写但未审」的额外 +1 加分，对齐任务规范：
- 有正文 +1
- 有 Goal +1
- 有 MustHit +1
- 审查 PASS +2 / WARN +1 / FAIL +0
- 5=A / 4=B / 3=C / 2=D / <2=-

### 5. scoreHtml() + 趋势箭头
已有实现保留，每行评分带 ↑↓→ 趋势（与前一章对比）

## 验证
- `python -m py_compile dashboard_server.py` 通过
