# 仪表盘前端重写 — 完成摘要

## 验证
- `python -m py_compile dashboard_server.py` 通过，无语法错误

## 改动范围
仅替换 `HTML_TEMPLATE` 字符串（~280行→~320行），后端 Python 逻辑**零改动**：
- `get_project_state()` — 不变
- `run_action()` — 不变
- `save_chapter_queue()` — 不变
- `DashboardHandler` — 不变
- `run_cli_mode()` / `main()` — 不变

## 新设计要点

| 要求 | 实现 |
|------|------|
| 深色主题 | `:root` 变量 `--bg:#0d1117`, `--card:#161b22`，纯暗色 |
| 顶部项目名+状态色块 | `<header>` 含标题 + `.status-block`（PASS/WARN/FAIL/NONE 四色） |
| 三个操作按钮 | 一键体检(蓝色primary) / 大纲审查 / 刷新，外加导出 |
| 章节表格6列 | # | 标题 | 字数 | 评分(A-F彩色) | 状态(彩色) | 审查按钮 |
| 评分计算 | 有正文+1, Goal+1, MustHit+1, PASS+2/WARN+1/否则有正文+1 → 5=A,4=B,3=C,2=D,<2=- |
| 侧边栏 | 进度条+章节/字数 → 审查统计(PASS/WARN/FAIL/待审) → 最近审计(最近8条审查记录) → 阻塞项 |
| 30s自动刷新 | `DOMContentLoaded` 初始化后 `setInterval(30000)` + 每秒倒计时显示 |
| 点击行弹出modal | 详情弹窗含 Goal/MustHit/Forbidden，支持编辑+保存(POST /api/save_chapter) |

## 关键修复
- **初始化方式**：旧代码用直接 `refresh()` 调用 → 新代码用 `document.addEventListener('DOMContentLoaded', init)`
- **评分函数**：按任务规范重写 `calcScore()`，FAIL/未审但已写→+1
- **模板字符串**：JS 内避免使用箭头函数和模板字面量中的 `${}`（会与 Python raw string 冲突），改用 `function` + 字符串拼接
