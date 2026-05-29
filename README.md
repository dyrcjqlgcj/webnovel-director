# webnovel-director — 网文导演系统

中文长篇网文的导演台：从选题到完本的全流程调度系统。导演（小爪爪）亲自执笔，脚本做结构化校验，三阶段闸门确保不跑偏。

---

## 目录

- [三阶段工作流](#三阶段工作流)
- [五个子系统](#五个子系统)
- [全部脚本](#全部脚本)
- [闸门规则](#闸门规则)
- [快速开始](#快速开始)
- [目录结构](#目录结构)
- [常见问题](#常见问题)

---

## 三阶段工作流

### Phase 1：选题锁定

```
用户方向/想法
  ↓
scanner 扫榜选材（方向不明确时启用）
  ↓
出 2–3 个候选概念，用户选或合并
  ↓
concept-gate 六维打分
  ↓ ← 闸门：PASS 才进入下一阶段
init_project 建目录骨架
  ↓
填 premise.md：书名承诺 / 命题三要素 / 禁飞区 / 角色功能锁
```

**六维打分维度：** 主角不可替代性 / 爽点可见性 / 持续可写性 / 市场匹配 / 差异化 / 金手指梯度。低于 70 分自动拦截。

### Phase 2：大纲布设

```
写 volume_map：卷结构 × 章数 × 核心事件 × 卷末状态
  ↓
写 chapter_queue：前 10–20 章细纲（Goal / Premise Must Hit / Forbidden）
  ↓
填 truth files：current_state / resource_ledger / particle_ledger / pending_hooks / relationship_graph
  ↓
outline_gate_review（六维审查）
  ↓
outline_causal_check（因果链 / 爽点密度 / 角色弧线 / 力量曲线）
  ↓
outline_iterate（迭代修复至通过）
  ↓ ← 闸门：全部 PASS → canWrite=true
```

### Phase 3：正文产出

```
每章循环：
  extend_outline 储备检查 → 储备不足则生成请求文件，导演手动续细纲
  ↓
  写前闸门：读 premise + chapter_queue + truth files，防偏
  ↓
  build_task_package 生成结构化任务包
  ↓
  导演按 writer 子系统方法论写正文
  ↓
  review_chapter / review_parallel 分级审查
  ↓
  polisher 去 AI 味
  ↓
  post_writeback 回写 director_state + truth files
```

**审查触发条件：** L1 每章 / L2 每 10 章 / L3 每 30 章或卷末或连续 WARN/FAIL。

**严重偏离自动修正：** 主角违反禁飞区、连续 3 章偏离命题、细纲执行反向——任意两项满足可自动重写（限未发布 + 改动 ≤10 章）。

---

## 五个子系统

所有子系统自包含完整方法论，从 clone 后无需安装任何外部 skill。

### scanner — 市场雷达
- 多平台数据采集（番茄/起点/盐言/七猫等）
- 跨样本信号提取 + 可写性评估
- 热点题材趋势 + 饱和风险分析

### analyzer — 拆文引擎
- 对标书逐章拆解（黄金三章 + 整体结构）
- 角色位抽象：把对标书角色映射为可复用的功能位
- 快速模式 + 深度模式

### writer — 正文执行器
- 完整写作方法论：情绪驱动 / 黄金三章 / 钩子 13 式 / 三维度织入
- 长篇短篇双模式，日更大修两套工作流
- 禁用词表 + AI 味检测规则

### reviewer — 深度审查
- L1（每章）/ L2（每 10 章）/ L3（每 30 章/卷末）
- 4 线程并行深审：命题 / 一致性 / 结构 / 伏笔
- 交叉矛盾检测 + R0–R4 自动分级修复

### polisher — 去 AI 味
- AI 味 vs 自然文本基准对比
- 分级保护：轻度 ≤15% / 中度 ≤25% / 重度 ≤35% 删除上限
- 自然替换参考词表

---

## 全部脚本

所有脚本均做结构化校验，不写正文，不调外部 LLM。

### 选题与初始化

| 脚本 | 功能 |
|------|------|
| `concept_gate.py` | 六维概念验证打分 |
| `concept_gate_import.py` | story-* 输出直通概念闸门 |
| `init_project.py` | 初始化 director/truth 目录骨架 |
| `extract_premise.py` | 从 story 文件自动生成 premise 初稿 |
| `migrate_project.py` | 旧项目 → webnovel-director 一键迁移 |
| `sync_inkos_state.py` | 旧项目状态同步 |

### 大纲与细纲

| 脚本 | 功能 |
|------|------|
| `outline_gate_review.py` | 逐章六维审查报告 |
| `outline_causal_check.py` | 因果链 / 爽点密度 / 角色弧线 / 力量曲线 |
| `outline_iterate.py` | 迭代修复引擎：检查→分组→修复→重查→循环至 PASS |
| `generate_outline_queue.py` | 从卷纲自动生成 chapter_queue 骨架 |
| `extend_outline.py` | 细纲储备检查 + 生成扩展请求文件 |
| `validate_pacing.py` | 细纲进度 vs 卷纲 pace 对齐检测 |

### 写作与字数

| 脚本 | 功能 |
|------|------|
| `build_task_package.py` | 闸门通过后生成结构化写作任务包 |
| `check_wordcount.py` | 章节字数统计 + 达标校验 |
| `audit_chapters.py` | 快速章节关键词审计 |

### 审查与修复

| 脚本 | 功能 |
|------|------|
| `review_chapter.py` | 正文→任务包对照 L1 审查报告 |
| `review_parallel.py` | 4 线程并行审查 + 交叉矛盾检测 |
| `scoring_card.py` | 审查评分卡 A–F + 趋势箭头 |
| `repair_plan.py` | FAIL/WARN 自动分级 R0–R4 + 修复步骤 |
| `post_writeback.py` | 审查后回写 director_state + truth files |

### 项目管理

| 脚本 | 功能 |
|------|------|
| `director_doctor.py` | 一键体检：项目状态 / 队列 / 闸门全景 |
| `project_manager.py` | 多书索引 + 批量 doctor + 切换活跃项目 |
| `validate_relationships.py` | 人物关系图因果边完整性检查 |

### 监控与仪表盘

| 脚本 | 功能 |
|------|------|
| `check_cron_prompt.py` | cron prompt 合规检查 |
| `cron_auditor.py` | gateway cron 自动检测 + 失联告警 |
| `dashboard_server.py` | Web 仪表盘：项目状态 / 审查色块 / 一键操作 |
| `trend_chart.py` | 章节趋势图表（字数 × 审查分 × 偏离度） |

### 自检

| 脚本 | 功能 |
|------|------|
| `director_meta_iterate.py` | director 自身审计 + 迭代修复 |
| `test_smoke.py` | 全链路冒烟测试 |

---

## 闸门规则

| 闸门 | 触发位置 | 通过条件 | FAIL 时 |
|------|---------|---------|---------|
| 概念闸 | Phase 1 末 | concept-gate ≥70 + premise 非空 | 修改或重新提案 |
| 大纲闸 | Phase 2 末 | outline 全 PASS + canWrite=true | outline_iterate 修复至通过 |
| 写前闸 | 每章写作前 | 禁飞区无偏离 + 细纲储备 ≥5 | 停止并修复 |
| 写后闸 | 每章写完后 | review 非 FAIL | repair_plan 修复后重审 |

---

## 快速开始

### 环境

- Python ≥ 3.11
- `pip install -r requirements.txt`

### 开一本新书

```bash
# 1. 概念验证
python scripts/concept_gate.py --inline "
书名: 示例书名
梗概: 主角+目标+阻碍+反转
金手指: 独特能力
世界观: 2-3句
平台: 番茄
"

# 2. 初始化
python scripts/init_project.py ./我的小说 --title "我的小说"

# 3. 填写 premise、volume_map、chapter_queue 后体检
python scripts/director_doctor.py ./我的小说

# 4. 大纲审查
python scripts/outline_gate_review.py ./我的小说
python scripts/outline_causal_check.py ./我的小说

# 5. 生成任务包 → 开始写作
python scripts/build_task_package.py ./我的小说 --chapter 1
```

### 日更循环

```bash
# 细纲储备检查
python scripts/extend_outline.py ./我的小说 --auto

# 写前闸门（导演读取 premise + truth files）
# 导演写正文
# 写后审查
python scripts/review_chapter.py ./我的小说 --chapter 1 --text 正文/第01章.md

# 回写状态
python scripts/post_writeback.py ./我的小说 --chapter 1
```

---

## 目录结构

```
webnovel-director/
├── SKILL.md                    # OpenClaw 路由入口
├── README.md                   # 本文件
├── CHANGELOG.md                # 版本历史
├── requirements.txt            # pyyaml
│
├── subsystems/                 # 5 个自包含执行器
│   ├── scanner/      市场雷达
│   ├── analyzer/     拆文引擎
│   ├── writer/       正文方法论（18 篇 reference）
│   ├── reviewer/     分级审查
│   └── polisher/     去 AI 味
│
├── modules/                    # 9 个功能模块（五文件协议）
│   ├── concept-gate/           # 概念闸门
│   ├── project-init/           # 项目初始化
│   ├── premise-guard/          # 命题防偏
│   ├── outline-gate/           # 大纲闸门
│   ├── execution-dispatch/     # 任务派发
│   ├── chapter-review/         # 章节审查
│   ├── consistency-module/     # 一致性
│   ├── transition-module/      # 转场/对话
│   └── repair-feedback/        # 修复回写
│
├── scripts/                    # 29 个脚本
├── references/                 # 架构文档 + 22 篇共享写作参考
└── templates/                  # director/truth 模板
```

---

## 常见问题

**需要安装其他 skill 吗？**

不需要。五个子系统全部自包含，clone 即用。

**细纲写完不够了怎么办？**

跑 `python scripts/extend_outline.py ./书 --auto`。储备不足时自动生成请求文件，导演读取 vol 纲 + premise + 已写章节后手动续细纲。

**写完一章之后做什么？**

跑 `review_chapter.py` 审查 → `polisher` 去 AI 味 → `post_writeback.py` 回写状态。然后回到写前闸门开始下一章。

**能自动日更吗？**

每章由导演亲自执笔，写后自动跑审查→润色→回写。不自动发布到任何平台。

**支持哪些平台？**

默认番茄小说。起点/晋江可通过 scanner 子系统配置数据源。

**如何迁移旧项目？**

```bash
python scripts/migrate_project.py ./旧书
```

**能同时写多本书吗？**

可以。每本书独立目录，`project_manager.py` 统一管理。

---

## 许可

MIT
