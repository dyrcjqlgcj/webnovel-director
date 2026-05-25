# webnovel-director — 网文导演系统

中文长篇网文的全流程调度台：从选题到完本，每一步都有闸门把关。

## 一句话

> 不是替你写小说，是让小说不会写着写着就歪了。

## 架构

```
                    ┌─────────────────────┐
                    │  webnovel-director   │
                    │      (导演台)        │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │          │           │           │          │
   scanner     analyzer     writer    reviewer    polisher
  (市场雷达)   (拆文引擎)  (正文执行)  (深度审查)  (去AI味)
        │          │           │           │          │
   concept-gate ──→ premise-guard ──→ outline-gate ──→ execution-dispatch
                                                         │
                                              ┌──────────┴──────────┐
                                         chapter-review    repair-feedback
                                              │                  │
                                         post-writeback ── cron-interface
```

## 快速开始

### 1. 安装

```bash
git clone https://github.com/worldwonderer/webnovel-director.git
cd webnovel-director
pip install -r requirements.txt
```

前置条件：Python ≥ 3.11，可访问 OpenAI 兼容 API 的 LLM。

### 2. 从零开一本新书

```bash
# Step 1: 选题（scanner 扫榜 + concept-gate 验证）
python scripts/concept_gate.py --inline "
书名: 你的暂定书名
梗概: 一句话说清主角+目标+阻碍+反转
金手指: 主角的独特能力
世界观: 2-3句话描述世界
平台: 番茄
"

# Step 2: 初始化项目
python scripts/init_project.py ./我的小说 --title "我的小说"

# Step 3: 填写 premise.md（书名承诺/禁飞区/角色锁）
# 手动编辑 ./我的小说/director/premise.md

# Step 4: 写卷纲和细纲
# 手动填写 ./我的小说/story/outline/volume_map.md
# 手动填写 ./我的小说/director/chapter_queue.md

# Step 5: 大纲审查 + 迭代修复
python scripts/outline_gate_review.py ./我的小说
python scripts/outline_causal_check.py ./我的小说
python scripts/outline_iterate.py ./我的小说 --max-rounds 3

# Step 6: 开始写作
python scripts/build_task_package.py ./我的小说 --chapter 1
# → 派发到 writer 子系统写正文
# → 写完后 reviewer 自动审查
# → polisher 去AI味
# → post_writeback 回写状态
```

### 3. 关键技术决策

| 问题 | 答案 |
|------|------|
| 需要额外安装 skill 吗？ | **不需要。** 五个子系统已内嵌，即装即用 |
| 支持什么平台？ | 默认番茄。起点/晋江可通过 scanner 配置 |
| 能自动日更吗？ | 能。配置 cron + `references/cron-interface.md` |
| 写作如何执行？ | 内置 writer 子系统，含完整方法论、钩子库、禁用词表 |

---

## 目录结构

```
webnovel-director/
├── SKILL.md                    # 导演台路由+工作流
├── README.md                   # 本文件
├── LICENSE                     # MIT
├── requirements.txt            # Python 依赖
│
├── modules/                    # 9 个功能模块（每个含 guide/rules/examples/sources）
│   ├── concept-gate/           # 概念闸门：六维选题验证
│   ├── project-init/           # 项目初始化
│   ├── premise-guard/          # 命题防偏
│   ├── outline-gate/           # 大纲闸门：六维审查+逻辑验证
│   ├── execution-dispatch/     # 写作任务派发
│   ├── chapter-review/         # 章节审查
│   ├── consistency-module/     # 一致性检查
│   ├── transition-module/      # 转场/对话/章末
│   └── repair-feedback/        # 修复+回写
│
├── subsystems/                 # 5 个自包含子系统（无需外部 skill）
│   ├── scanner/                # 市场雷达：subsystems/scanner/guide.md + 5 个 reference 文件
│   ├── analyzer/               # 拆文引擎：subsystems/analyzer/guide.md + 5 个 reference 文件
│   ├── writer/                 # 正文执行器：subsystems/writer/guide.md + 18 个 reference 文件
│   ├── reviewer/               # 深度审查：subsystems/reviewer/guide.md + rubric 文件
│   └── polisher/               # 去AI味：subsystems/polisher/guide.md + 共享 craft 引用
│
├── scripts/                    # 15+ 个可执行脚本
│   ├── concept_gate.py         # 概念验证
│   ├── init_project.py         # 项目初始化
│   ├── scripts\director_doctor.py      # 一键体检
│   ├── outline_gate_review.py  # 大纲六维审查
│   ├── outline_causal_check.py # 大纲逻辑验证
│   ├── outline_iterate.py      # 迭代修复引擎
│   ├── build_task_package.py   # 任务包生成
│   ├── review_chapter.py       # L1 审查
│   ├── review_parallel.py      # 4 Agent 并行审查
│   ├── post_writeback.py       # 写后回写
│   └── ...
│
├── references/                 # 架构/集成/接口文档
│   └── craft/                  # 22 个共享写作参考文件（禁用词/技法/情绪/人物）
├── templates/                  # director/truth 模板
└── .gitignore
```

---

## 九个模块

每个模块遵循五文件协议：`modules\chapter-review\guide.md`（教程）、`modules\chapter-review\rules.md`（运行规则）、`modules\chapter-review\examples-good.md`（正例）、`modules\chapter-review\examples-bad.md`（反例）、`modules\chapter-review\sources.md`（来源）。

| 模块 | 功能 | 触发时机 |
|------|------|----------|
| concept-gate | 六维选题打分（主角不可替代性/爽点/可写性/市场/差异/梯度） | 开书前 |
| project-init | 建 director/ + truth/ 目录骨架 | 选题 PASS 后 |
| premise-guard | 写前/写后命题防偏 | 每章 |
| outline-gate | 卷纲细纲六维审查 + 逻辑验证 + 迭代修复 | 大纲阶段 |
| execution-dispatch | 生成任务包，派发 writer 子系统 | 每章写作前 |
| chapter-review | L1/L2/L3 分级审查 | 每章/每10章/每30章 |
| consistency-module | 资源/关系/伏笔一致性 | 按需 |
| transition-module | 转场/对话/章末钩子 | 按需 |
| repair-feedback | FAIL→WARN 的修复链路 | 审查发现 FAIL 时 |

---

## 从概念到完本的完整链路

```
scanner 扫榜
  ↓
analyzer 拆文（有对标书时）
  ↓
concept-gate（六维打分）
  ↓ PASS
project-init（建目录）
  ↓
premise.md（书名承诺+禁飞区+角色锁）
  ↓
volume_map.md + chapter_queue.md（卷纲+细纲）
  ↓
outline_gate_review → outline_causal_check → outline_iterate
  ↓ 全部 PASS
build_task_package
  ↓
writer 子系统（写正文）
  ↓
reviewer 子系统（L1 审查）
  ↓
polisher 子系统（去AI味）
  ↓
post_writeback（更新状态）
  ↓
下一章 ← 循环
```

---

## 实测验证

经实际项目跑通完整链路：concept-gate（六维验证）→ init_project → premise → volume_map + chapter_queue → outline_gate_review → outline_causal_check → outline_iterate。

| 阶段 | 工具 | 结果 |
|------|------|------|
| 概念验证 | concept_gate.py | PASS（≥70 分可用） |
| 项目初始化 | init_project.py | PASS |
| 大纲审查 | outline_gate_review.py | 0 FAIL |
| 逻辑验证 | outline_causal_check.py | 0 FAIL |
| 迭代修复 | outline_iterate.py | 收敛 |

---

## 贡献

1. 所有模块遵循五文件协议
2. 脚本需通过 `python -m compileall scripts/`
3. 新增功能先写正例+反例再写规则
4. PR 前跑 `scripts\director_doctor.py` 验证

## 许可

MIT License

> Coworker 自动化已就绪 ✓
