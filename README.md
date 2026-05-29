# webnovel-director — 网文导演系统 v3.0.0

中文长篇网文的导演台：从选题到完本，三阶段闸门把关。导演（小爪爪）亲自执行，不调外部 Agent/LLM。

---

## 核心理念

- **导演即执行者**：所有写作、审查、细纲生成由导演亲自完成，脚本只做结构化校验
- **三阶段闸门**：选题锁定 → 大纲布设 → 正文产出，每阶段有硬通过条件
- **自包含**：五个子系统内置完整方法论，clone 即用，无需外部 skill

---

## 三阶段工作流

```
Phase 1: 选题锁定
  scanner 扫榜 → concept-gate 六维打分 → init_project → premise.md
  闸门: concept-gate PASS + premise 非空

Phase 2: 大纲布设
  volume_map → chapter_queue → truth files → outline_gate PASS
  闸门: outline 全 PASS + canWrite=true

Phase 3: 正文产出（逐章循环）
  extend_outline 储备检查 → build_task_package → 导演写正文
  → reviewer 审查 → polisher 润色 → post_writeback 回写
```

---

## 五个子系统

| 子系统 | 目录 | 角色 | Guide |
|--------|------|------|-------|
| **scanner** | `subsystems/scanner/` | 市场雷达——扫榜、找趋势 | `guide.md` |
| **analyzer** | `subsystems/analyzer/` | 拆文引擎——对标分析、提取模块 | `guide.md` |
| **writer** | `subsystems/writer/` | 正文方法论——钩子/禁用词/写作技法 | `guide.md` |
| **reviewer** | `subsystems/reviewer/` | L1/L2/L3 分级审查 | `guide.md` |
| **polisher** | `subsystems/polisher/` | 去 AI 味——润色 | `guide.md` |

---

## 所有脚本

| 脚本 | 用途 |
|------|------|
| `scripts/concept_gate.py` | 六维概念验证打分 |
| `scripts/concept_gate_import.py` | story-* skill 输出直通概念闸门 |
| `scripts/init_project.py` | 初始化 director/truth 骨架 |
| `scripts/extract_premise.py` | 从 story 文件生成 premise 初稿 |
| `scripts/director_doctor.py` | 一键体检项目状态 |
| `scripts/project_manager.py` | 多书索引 + 批量 doctor |
| `scripts/migrate_project.py` | 旧项目 → webnovel-director 迁移 |
| `scripts/sync_inkos_state.py` | 旧项目状态同步 |
| `scripts/outline_gate_review.py` | 大纲六维审查 |
| `scripts/outline_causal_check.py` | 大纲逻辑验证 |
| `scripts/outline_iterate.py` | 迭代修复引擎 |
| `scripts/generate_outline_queue.py` | 从卷纲生成 chapter_queue 骨架 |
| `scripts/extend_outline.py` | 细纲储备检查 + 生成请求文件（导演手动续） |
| `scripts/build_task_package.py` | 生成结构化章节任务包 |
| `scripts/check_wordcount.py` | 章节字数统计 + 达标校验 |
| `scripts/audit_chapters.py` | 快速章节关键词审计 |
| `scripts/review_chapter.py` | L1 审查报告 |
| `scripts/review_parallel.py` | 4 线程并行审查 + 交叉矛盾检测 |
| `scripts/scoring_card.py` | 审查评分卡 A~F |
| `scripts/trend_chart.py` | 章节趋势图表 |
| `scripts/repair_plan.py` | FAIL/WARN 自动分级 R0-R4 + 修复 |
| `scripts/post_writeback.py` | 审查后回写 director/truth |
| `scripts/validate_relationships.py` | 关系图因果边完整性 |
| `scripts/validate_pacing.py` | 细纲 vs 卷纲 pace 对齐检测 |
| `scripts/check_cron_prompt.py` | cron prompt 合规检查 |
| `scripts/cron_auditor.py` | gateway cron 自动检测 + 告警 |
| `scripts/dashboard_server.py` | Web 仪表盘 |
| `scripts/director_meta_iterate.py` | director 自检 + 迭代修复 |
| `scripts/test_smoke.py` | 全链路冒烟测试 |

---

## 目录结构

```
webnovel-director/
├── SKILL.md                    # 完整工作流
├── README.md                   # 本文件
├── CHANGELOG.md                # 版本历史
├── requirements.txt            # pyyaml
│
├── subsystems/                 # 5 个自包含执行器
│   ├── scanner/     → guide.md + references
│   ├── analyzer/    → guide.md + references
│   ├── writer/      → guide.md + 18 references
│   ├── reviewer/    → guide.md + rubric
│   └── polisher/    → guide.md
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
├── scripts/                    # 29 个脚本（均不写正文/不调外部 LLM）
│
├── references/                 # 架构文档 + 22 篇共享 craft
│
└── templates/                  # director/truth 模板
```

---

## 快速开始

```bash
# 1. 验证概念
python scripts/concept_gate.py --inline "书名: 示例
梗概: 主角+目标+阻碍+反转
金手指: 独特能力
世界观: 2-3句
平台: 番茄"

# 2. 初始化项目
python scripts/init_project.py ./我的小说 --title "我的小说"

# 3. 填写 premise.md、volume_map、chapter_queue
#    然后跑体检
python scripts/director_doctor.py ./我的小说

# 4. 大纲审查
python scripts/outline_gate_review.py ./我的小说
python scripts/outline_causal_check.py ./我的小说

# 5. 生成任务包 → 导演写正文
python scripts/build_task_package.py ./我的小说 --chapter 1
```

---

## 闸门强制规则

| 闸门 | 位置 | PASS 条件 | FAIL 时 |
|------|------|----------|---------|
| 概念闸 | Phase 1 末 | concept-gate ≥70 + premise 非空 | 修改或重新提案 |
| 大纲闸 | Phase 2 末 | outline 全 PASS + canWrite=true | 迭代修复至 PASS |
| 写前闸 | 每章写作前 | 禁飞区无偏离、细纲储备 ≥5 | 停止并修复 |

---

## 常见问题

**Q: 需要安装其他 skill 吗？**
A: 不需要。五个子系统全部自包含。

**Q: 细纲怎么续？**
A: 跑 `python scripts/extend_outline.py ./书 --auto`，储备不足时生成请求文件，导演读取后手动续。

**Q: 能自动日更吗？**
A: 每章由导演亲自写，写后自动跑 reviewer → polisher → post_writeback。不自动发布。

**Q: 如何迁移旧项目？**
A: `python scripts/migrate_project.py ./旧书`

---

## 许可

MIT
