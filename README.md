# webnovel-director — 网文导演系统 v2.0

中文长篇网文的全流程调度台：从选题到完本，每一步都有闸门把关。不是替你写小说，是让小说不会写着写着就歪了。

---

## 目录

- [核心能力](#核心能力)
- [五个子系统](#五个子系统)
- [九个模块](#九个模块)
- [全部脚本](#全部脚本)
- [快速开始](#快速开始)
- [完整工作流](#完整工作流)
- [目录结构](#目录结构)
- [配置与集成](#配置与集成)
- [V3.0 路线图](#v30-路线图)
- [常见问题](#常见问题)
- [贡献指南](#贡献指南)
- [许可](#许可)

---

## 核心能力

### 选题把关
- **市场雷达**（scanner）：跨平台扫榜，热点题材趋势 + 饱和风险
- **概念闸门**（concept-gate）：六维打分——主角不可替代性 / 爽点可见性 / 持续可写性 / 市场匹配 / 差异化 / 金手指梯度。低于 70 分自动拦截

### 大纲验证
- **大纲闸门**（outline-gate）：逐章六维审查 + 因果链/爽点密度/角色弧线/力量曲线逻辑验证
- **命题守恒**（premise-guard）：写前/写后双向防偏，禁飞区 + 角色功能锁 + 卷级禁区

### 正文执行
- **任务包派发**（execution-dispatch）：禁止裸 prompt 写正文，必须通过闸门
- **内置写手**（writer）：黄金三章 / 钩子 13 式 / 禁用词表 / 长篇短篇双模式 / 日更大修两套工作流

### 审查体系
- **三级审查**（reviewer）：L1 每章 / L2 每 10 章 / L3 每 30 章或卷末
- **4 Agent 并行深审**：命题 / 一致性 / 结构 / 伏笔，交叉矛盾检测
- **自动分级修复**（repair-feedback）：FAIL → R0-R4 自动分级 + 修复步骤

### 状态管理
- **唯一真相源**（truth files）：current_state / resource_ledger / particle_ledger / pending_hooks / relationship_graph
- **一键体检**（director_doctor）：项目健康 + 待写队列 + 闸门状态全景视图

### 去 AI 味
- **polisher 子系统**：AI 味检测 → 自然文本基准对比 → 分级保护（轻度 ≤15% / 中度 ≤25% / 重度 ≤35% 删除上限）
- 共享 22 个写作技法 reference 文件

---

## 五个子系统

| 子系统 | 目录 | 角色 | Guide |
|--------|------|------|-------|
| **scanner** | `subsystems/scanner/` | 市场雷达——扫榜、找趋势 | `subsystems/scanner/guide.md` |
| **analyzer** | `subsystems/analyzer/` | 拆文引擎——对标分析、提取模块 | `subsystems/analyzer/guide.md` |
| **writer** | `subsystems/writer/` | 正文执行器——方法论 + 钩子 + 禁用词 | `subsystems/writer/guide.md` |
| **reviewer** | `subsystems/reviewer/` | 深度审查——L1/L2/L3 分级 | `subsystems/reviewer/guide.md` |
| **polisher** | `subsystems/polisher/` | 去AI味——文字润色 | `subsystems/polisher/guide.md` |

所有子系统**自包含完整方法论**，从 GitHub clone 后无需安装任何外部 skill，即装即用。

---

## 九个模块

每个模块遵循五文件协议：`guide.md`（教程）/ `rules.md`（运行规则）/ `examples-good.md`（正例）/ `examples-bad.md`（反例）/ `sources.md`（来源）。

| 模块 | 功能 | 触发时机 | 输出 |
|------|------|----------|------|
| **concept-gate** | 六维选题打分 | 开书前 | PASS（≥70）/ FAIL |
| **project-init** | 建 director + truth 目录骨架 | 选题 PASS 后 | 目录结构 |
| **premise-guard** | 命题防偏 + 禁飞区 + 角色锁 | 每章写前/写后 | PASS / WARN / FAIL |
| **outline-gate** | 卷纲细纲审查 + 逻辑验证 | 大纲阶段 | 审查报告 + 修复建议 |
| **execution-dispatch** | 生成任务包 → 派发 writer | 每章写作前 | YAML 任务包 |
| **chapter-review** | L1 每章审查 + 回写建议 | 每章写后 | 审查报告 |
| **consistency-module** | 资源/关系/伏笔冲突检测 | 按需 | PASS / WARN |
| **transition-module** | 转场/对白/章末钩子 | 按需 | 修复建议 |
| **repair-feedback** | FAIL→WARN 自动分级修复 | 审查 FAIL 时 | R0-R4 修复计划 |

---

## 全部脚本

| 脚本 | 用途 | 写正文 |
|------|------|:----:|
| `scripts\concept_gate.py` | 六维概念验证打分 | 否 |
| `scripts\init_project.py` | 初始化 director/truth 骨架 | 否 |
| `scripts\director_doctor.py` | 一键体检项目状态/队列/闸门 | 否 |
| `scripts\extract_premise.py` | 从 story 文件自动生成 premise 初稿 | 否 |
| `scripts\outline_gate_review.py` | 逐章六维审查报告 | 否 |
| `scripts\outline_causal_check.py` | 因果链/爽点密度/角色弧线/力量曲线 | 否 |
| `scripts\outline_iterate.py` | 检查→分组→LLM修复→重查→循环至 PASS | 否 |
| `scripts\generate_outline_queue.py` | 从卷纲自动生成 chapter_queue 骨架 | 否 |
| `scripts\build_task_package.py` | 闸门通过后生成章节任务包 | 否 |
| `scripts\audit_chapters.py` | 快速章节关键词审计 | 否 |
| `scripts\review_chapter.py` | 正文→任务包对照 L1 审查报告 | 否 |
| `scripts\review_parallel.py` | 4 子 Agent 并行审查 + 交叉矛盾检测 | 否 |
| `scripts\post_writeback.py` | 审查后回写 director/truth | 否 |
| `scripts\repair_plan.py` | FAIL/WARN 自动分级 R0-R4 + 修复步骤 | 否 |
| `scripts\director_meta_iterate.py` | webnovel-director 自身审计 + 迭代修复 | 否 |
| `scripts\validate_relationships.py` | 检查关系图因果边完整性 | 否 |
| `scripts\validate_pacing.py` | 细纲进度 vs 卷纲 pace 对齐检测 | 否 |
| `scripts\check_cron_prompt.py` | 检查 cron prompt 是否绕过 director | 否 |
| `scripts\sync_inkos_state.py` | inkos 项目状态同步 | 否 |
| `scripts\test_smoke.py` | 全链路冒烟测试 | 否 |
| `scripts\dashboard_server.py` | Web 仪表盘：项目状态/审查色块/一键操作 | 否 |

> 安全边界：以上全部脚本**不写正文**。正文只能由 writer 子系统在闸门通过后生成。

---

## 快速开始

### 前置条件

- Python ≥ 3.11
- 可访问 OpenAI 兼容 API 的 LLM（配置 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`）
- 可选：inkos CLI（用于旧项目迁移）

### 安装

```bash
git clone https://github.com/worldwonderer/webnovel-director.git
cd webnovel-director
pip install -r requirements.txt
```

### 5 分钟开一本新书

```bash
# 1. 概念验证（六维打分，低于 70 分拦截）
python scripts\concept_gate.py --inline "
书名: 我的暂定书名
梗概: 主角+目标+阻碍+反转 一句话
金手指: 主角独特能力
世界观: 2-3 句
平台: 番茄
"

# 2. 初始化项目
python scripts\init_project.py .\我的小说 --title "我的小说"

# 3. 填写 premise.md（书名承诺/禁飞区/角色锁）
#    手动编辑: .\我的小说\director\premise.md

# 4. 写卷纲 + 细纲
#    手动: .\我的小说\story\outline\volume_map.md
#    手动或脚本: .\我的小说\director\chapter_queue.md

# 5. 大纲审查 + 迭代
python scripts\outline_gate_review.py .\我的小说
python scripts\outline_causal_check.py .\我的小说
python scripts\outline_iterate.py .\我的小说 --max-rounds 3

# 6. 生成任务包 → 开始写作
python scripts\build_task_package.py .\我的小说 --chapter 1
# → writer 子系统写正文
# → reviewer 自动审查
# → polisher 去 AI 味
# → post_writeback 回写状态
```

### 旧 inkos 项目接入

```bash
python scripts\sync_inkos_state.py .\我的旧书 --write
python scripts\extract_premise.py .\我的旧书
python scripts\director_doctor.py .\我的旧书
```

---

## 完整工作流

### A. 开书（9 步）

```
scanner 扫榜 → 多提案
  ↓
concept-gate（六维打分）
  ↓ PASS
project-init（建目录）
  ↓
premise.md（书名承诺 + 禁飞区 + 角色锁）
  ↓
volume_map.md + chapter_queue.md（卷纲 + 细纲）
  ↓
outline_gate_review → outline_causal_check → outline_iterate
  ↓ 全部 PASS
build_task_package
  ↓
writer 子系统 → 写正文
```

### B. 日更循环

```
用户/cron 触发
  ↓
premise-guard（写前防偏）
  ↓
execution-dispatch → writer 子系统
  ↓
reviewer（L1 每章审查）
  ↓
consistency/transition 按需
  ↓
repair-feedback（WARN/FAIL 处理）
  ↓
polisher（去 AI 味）
  ↓
post_writeback（回写状态）
  ↓
下一章 ← 循环
```

### C. 强制闸门

| 闸门 | 条件 | 不满足后果 |
|------|------|------------|
| `director_doctor` | FAIL | 不写 |
| `outline_gate_review` | FAIL | 不写 |
| `director_state.canWrite` | false | 不生成任务包 |
| `post_writeback` | WARN/FAIL | 不继续下一章 |

---

## 目录结构

```
webnovel-director/
├── SKILL.md                      # OpenClaw 路由 + 完整工作流
├── README.md                     # 本文件
├── CHANGELOG.md                  # 版本历史
├── LICENSE                       # MIT
├── requirements.txt              # Python 依赖
│
├── modules/                      # 9 个功能模块（五文件协议）
│   ├── concept-gate/             #   概念闸门
│   ├── project-init/             #   项目初始化
│   ├── premise-guard/            #   命题防偏
│   ├── outline-gate/             #   大纲闸门
│   ├── execution-dispatch/       #   任务派发
│   ├── chapter-review/           #   章节审查
│   ├── consistency-module/       #   一致性
│   ├── transition-module/        #   转场/对话
│   └── repair-feedback/          #   修复回写
│
├── subsystems/                   # 5 个自包含执行器
│   ├── scanner/                  #   市场雷达 → guide.md + references
│   ├── analyzer/                 #   拆文引擎 → guide.md + references
│   ├── writer/                   #   正文执行 → guide.md + 18 references
│   ├── reviewer/                 #   深度审查 → guide.md + rubric
│   └── polisher/                 #   去AI味 → guide.md + 共享 craft
│
├── scripts/                      # 21 个可执行脚本（均不写正文）
│   ├── concept_gate.py           # 概念验证
│   ├── init_project.py           # 项目初始化
│   ├── director_doctor.py        # 一键体检
│   ├── extract_premise.py        # 自动生成 premise
│   ├── outline_gate_review.py    # 大纲六维审查
│   ├── outline_causal_check.py   # 逻辑验证
│   ├── outline_iterate.py        # 迭代修复引擎
│   ├── generate_outline_queue.py # 细纲自动生成
│   ├── build_task_package.py     # 任务包生成
│   ├── audit_chapters.py         # 快速关键词审计
│   ├── review_chapter.py         # L1 审查
│   ├── review_parallel.py        # 4 Agent 并行
│   ├── post_writeback.py         # 写后回写
│   ├── repair_plan.py            # R0-R4 修复
│   ├── director_meta_iterate.py  # 项目自检
│   ├── validate_relationships.py # 关系图验证
│   ├── validate_pacing.py        # 节奏验证
│   ├── check_cron_prompt.py      # cron 审计
│   ├── sync_inkos_state.py       # inkos 同步
│   ├── test_smoke.py             # 冒烟测试
│   └── dashboard_server.py       # Web 仪表盘
│
├── references/                   # 架构/接口/集成文档
│   ├── architecture.md           # 总架构
│   ├── module-protocol.md        # 模块协议
│   ├── integration-subsystems.md # 子系统集成
│   ├── cron-interface.md         # cron 接口
│   ├── state-files.md            # 状态文件规范
│   ├── operations.md             # 操作手册
│   ├── roadmap.md                # 路线图
│   ├── post-writeback.md         # 写后回写协议
│   └── craft/                    # 22 个共享写作参考文件
│       ├── anti-ai-writing.md
│       ├── banned-words.md
│       ├── character-basics.md
│       ├── character-design-methods.md
│       ├── character-relations.md
│       ├── dialogue-mastery.md
│       ├── emotional-arc-design.md
│       ├── emotional-methods.md
│       ├── format-and-structure.md
│       ├── genre-catalog.md
│       ├── genre-core-mechanics.md
│       ├── genre-readers.md
│       ├── genre-writing-formulas.md
│       ├── genre-writing-techniques.md
│       ├── hooks-chapter.md
│       ├── hooks-paragraph.md
│       ├── hooks-suspense.md
│       ├── opening-design.md
│       ├── quality-checklist.md
│       ├── reversal-toolkit.md
│       ├── state-tracking.md
│       └── writing-craft.md
│
└── templates/                    # director/truth 模板
    ├── premise.md                # 书名承诺 + 禁飞区
    ├── director_state.json5      # 项目状态
    ├── chapter_queue.md          # 待写队列
    ├── last_audit.md             # 最近审计
    ├── audit_log.md              # 审计日志
    ├── volume_map.md             # 卷纲
    ├── current_state.md          # 当前状态
    ├── resource_ledger.md        # 资源账本
    ├── particle_ledger.md        # 粒子账本
    ├── pending_hooks.md          # 待回收钩子
    └── relationship_graph.yaml   # 关系图
```

---

## 配置与集成

### 环境变量

```bash
export OPENAI_API_KEY="sk-..."      # LLM API 密钥
export OPENAI_BASE_URL="..."        # API 端点（可选，默认 OpenAI）
```

### cron 自动日更

参考 `references/cron-interface.md`。核心规则：
- 每章写完 → reviewer → polisher → post_writeback → 下一章
- 发现 WARN/FAIL → 停止 + 通知
- 10 章批处理（如 1:00-6:00，每 30 分钟一章）

### 仪表盘

```bash
python scripts\dashboard_server.py    # 启动 Web 仪表盘（默认 http://localhost:8080）
```

仪表盘提供：
- 项目健康总览（PASS/WARN/FAIL 色块）
- 章节队列可视化
- 一键触发审查/修复/回写
- 大纲/细纲快速导航

---

## V3.0 路线图

| 优先级 | 能力 | 状态 |
|:---:|------|:---:|
| **P1** | `director_meta_iterate.py` 增强：自动修复双路径等常见错误 | 📋 |
| **P1** | CI/CD：push 自动跑 `test_smoke.py` + `director_meta_iterate.py` | 📋 |
| **P2** | `project_manager.py`：多书索引 + 批量 doctor + 切换活跃项目 | 📋 |
| **P2** | `migrate_project.py`：inkos → webnovel-director 一键迁移 | 📋 |
| **P2** | `director_state.json5` 升级：加 vcs/remote/branch 字段 | 📋 |
| **P3** | L3 审查自动化：每 30 章/卷末自动触发 4 Agent 并行 | 📋 |
| **P3** | 审查评分卡：A~F + 趋势箭头替代纯 P/W/F | 📋 |
| **P3** | `validate_pacing.py` → `outline_gate_review.py` 联动拦截 | 📋 |
| **P4** | `dashboard_server.py` CLI 模式（`--mode cli` 终端彩色面板） | 📋 |
| **P4** | 章节趋势图表：字数 × 审查分 × 偏离度 三线同屏 | 📋 |
| **P4** | 一键修复按钮：批量触发 `repair_plan.py` | 📋 |
| **P5** | story-* skill 输出直通 `concept_gate.py` | 📋 |
| **P5** | `cron-interface.md` 升级：自动检测 gateway cron + 失联告警 | 📋 |
| **P5** | 封面生成联动：`build_task_package.py --with-cover` | 📋 |

---

## 常见问题

**Q: 需要安装其他 skill 吗？**
A: 不需要。五个子系统全部自包含，clone 即用。

**Q: 支持哪些平台？**
A: 默认番茄小说。起点/晋江可通过 scanner 配置数据源。

**Q: 能自动日更吗？**
A: 能。配置 cron + `references/cron-interface.md`，写前/写后全部自动。

**Q: 会自己发章节吗？**
A: 不会。webnovel-director 不自动发布到任何平台。

**Q: 和 inkos 的关系？**
A: webnovel-director 是调度台，inkos 是执行器之一。通过 `sync_inkos_state.py` 双向同步。

**Q: 能并发写多本书吗？**
A: 可以。每本书独立目录，独立状态。V3.0 将提供 `project_manager.py` 统一管理。

---

## 贡献指南

1. 所有模块遵循五文件协议（guide / rules / examples-good / examples-bad / sources）
2. 脚本需通过 `python -m compileall scripts\`
3. 新增功能先写正例 + 反例，再写规则
4. PR 前跑 `python scripts\director_doctor.py` + `python scripts\test_smoke.py`

---

## 许可

MIT License — 详见 [LICENSE](LICENSE)
