# webnovel-director 架构 V3.0

## 分层

```text
Director（小爪爪 = 总导演 + 总执行者）
├─ Phase 1: 选题锁定
│   ├─ scanner 扫榜选材 → 多提案
│   ├─ concept-gate 六维验证 → PASS
│   ├─ project-init 建目录
│   └─ premise-guard 固化命题/禁飞区/角色锁
├─ Phase 2: 大纲布设
│   ├─ volume_map 卷结构
│   ├─ chapter_queue 细纲
│   ├─ truth files 填充
│   └─ outline-gate 审查 → canWrite=true
└─ Phase 3: 正文产出（逐章循环）
    ├─ extend_outline 细纲储备检查
    ├─ build_task_package 任务包
    ├─ 导演亲自写正文
    ├─ reviewer 分级审查
    ├─ polisher 去 AI 味
    └─ post_writeback 回写 state
```

## 核心变更（V2 → V3）

| V2 | V3 |
|----|----|
| spawn Claude Code/Agent 执行 | 导演（小爪爪）直执行 |
| extend_outline.py 调外部 LLM | 生成请求文件，导演手动续 |
| 9 步手动流程 | 3 阶段自动推进，闸门处确认 |
| scanner/analyzer 需外部 skill | scanner/analyzer 是 director 内置子系统 |

## 运行链路

### 开书链路（3 阶段）

```
Phase 1: 选题锁定
  用户方向 → scanner 扫榜 → 出候选 → concept-gate → init → premise
  闸门: concept-gate PASS + premise 非空

Phase 2: 大纲布设
  volume_map → chapter_queue → truth files → outline_gate → iterate → PASS
  闸门: outline 全 PASS + canWrite=true

Phase 3: 正文产出
  逐章: extend_check → build_task → 写正文 → review → polish → writeback
```

### 日更链路

```
extend_outline.py --auto → 储备不足时生成请求文件
  ↓
导演读取 outline_extension_request.md 手动续细纲
  ↓
写前闸门：读 premise + chapter_queue + truth + last_audit
  ↓
build_task_package 出任务包
  ↓
导演写正文（按 writer/guide.md）
  ↓
review_chapter（L1）→ review_parallel（L2 每 10 章）
  ↓
polisher 去 AI 味
  ↓
post_writeback 回写
```

## 五个子系统

- **scanner**：市场雷达——扫榜、找趋势
- **analyzer**：拆文引擎——对标分析、提取模块
- **writer**：正文执行器——方法论文档，导演写前必读
- **reviewer**：深度审查——L1/L2/L3 + 4 线程并行
- **polisher**：去 AI 味

所有子系统自包含，导演读取 guide.md 后直接执行。

## 模块边界

| 层 | 能做 | 不能做 |
|---|---|---|
| concept-gate | 概念验证打分 | 替代用户直觉判断 |
| project-init | 建目录、模板、初始状态 | 写正文、覆盖旧正文 |
| premise-guard | 判断命题偏离 | 替代一致性检查 |
| outline-gate | 放行/拦截卷纲细纲 | FAIL 后继续写 |
| execution-dispatch | 生成任务包 | 代替导演写正文 |
| chapter-review | 写后判定与回写建议 | 只做文风点评 |
| consistency-module | 查状态/资源/伏笔冲突 | 判断书名命题是否成立 |
| transition-module | 修转场、对白、钩子 | 大改剧情方向 |
| repair-feedback | 把问题变成修复动作 | 已发布内容无确认大改 |

## 边界的边界

已实现：
- 主入口 SKILL.md（V3.0 重写）
- references 架构/状态/操作说明
- 9 个模块五文件协议骨架
- 项目模板与初始化/校验脚本（29 个）
- 5 个子系统自包含 guide.md + 完整 reference 文件

暂不做：
- 自动发布平台内容
- 全量正文生成器
- 自动改已发布章节
- 调外部 LLM/Agent
