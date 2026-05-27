# webnovel-director — 网文导演系统

> 不是替你写小说，是让小说不会写着写着就歪了。

中文长篇网文的全流程调度台：从选题到完本，每一步都有闸门把关。

## 快速开始

```bash
git clone https://github.com/dyrcjqlgcj/webnovel-director.git
cd webnovel-director
pip install pyyaml

# 统一入口
python wd.py init ./我的小说 --title "轮回塔"
python wd.py gate concept --inline "梗概: 主角死后保留记忆，用死亡试错刷攻略..."
python wd.py gate outline ./我的小说 --fix
python wd.py build ./我的小说 --chapter 1
python wd.py write ./我的小说 --chapter 1
python wd.py review ./我的小说 --chapter 1
python wd.py doctor ./我的小说
python wd.py dashboard ./我的小说
```

前置：Python ≥ 3.11，可访问 OpenAI 兼容 API 的 LLM。

## CLI 命令一览

```
wd init      <dir> --title "书名"      初始化项目
wd gate      concept <file|--inline>    概念闸门（六维验证）
wd gate      outline <dir> [--fix]      大纲闸门（审查+逻辑验证+迭代修复）
wd build     <dir> [--chapter N]        生成章节任务包
wd write     <dir> --chapter N          调用 LLM 写正文
wd review    <dir> --chapter N          章节审查
wd doctor    <dir>                      一键体检
wd dashboard <dir> [--port 8765]        启动 Web 仪表盘
wd status    <dir>                      项目状态摘要
wd premis    <dir>                      自动提取 premise
wd test                                 全链路冒烟测试
```

## 架构

```
                    ┌─────────────────────┐
                    │  webnovel-director   │
                    │      (导演台)        │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
   scanner          analyzer         writer          reviewer
  (市场雷达)       (拆文引擎)      (正文执行)       (深度审查)
        │                │               │               │
   concept-gate ──→ premise-guard ──→ outline-gate ──→ execution-dispatch
                                                              │
                                              ┌───────────────┴───────────┐
                                         chapter-review            repair-feedback
                                              │                          │
                                         post-writeback ──────→ cron-interface
```

## 从概念到完本

```
scanner 扫榜 → analyzer 拆文 → concept-gate (六维打分)
  ↓ PASS
init_project → premise.md (书名承诺+禁飞区+角色锁)
  ↓
volume_map + chapter_queue (卷纲+细纲)
  ↓
outline_gate_review → outline_causal_check → outline_iterate
  ↓ PASS
build_task_package → write_chapter (LLM 写正文)
  ↓
review_chapter → post_writeback → 下一章
```

## 项目结构

```
webnovel-director/
├── wd.py                        # 统一 CLI 入口
├── config.yaml                  # LLM 提供商/闸门阈值/路径配置
├── lib/                         # 共享库
│   ├── common.py                #   文件 I/O / 解析 / 字数统计 / 路径常量
│   └── llm.py                   #   统一 LLM 调用 (DeepSeek/OpenAI/GPTsAPI)
├── scripts/                     # 20+ 可执行脚本
│   ├── concept_gate.py          #   六维选题验证
│   ├── init_project.py          #   项目初始化
│   ├── outline_gate_review.py   #   大纲六维审查
│   ├── outline_causal_check.py  #   因果链/爽点密度/角色弧线验证
│   ├── outline_iterate.py       #   迭代修复引擎（确定式+LLM）
│   ├── build_task_package.py    #   章节任务包生成
│   ├── write_chapter.py         #   LLM 写作执行
│   ├── review_parallel.py       #   4 Agent 并行审查
│   ├── dashboard_server.py      #   Web 仪表盘
│   └── ...
├── modules/                     # 9 个功能模块（五文件协议）
├── subsystems/                  # 5 个自包含子系统
├── dashboard/                   # 仪表盘前端资源
├── references/craft/            # 22 个共享写作参考
└── templates/                   # 项目模板
```

## 配置

复制 `config.yaml` 为 `config.local.yaml` 进行本地覆盖：

```yaml
providers:
  deepseek:
    api_key_env: "DEEPSEEK_API_KEY"
    default_model: "deepseek-chat"
writing:
  model: "deepseek-chat"
  max_tokens: 8000
dashboard:
  port: 8765
```

## 九个模块

| 模块 | 触发时机 |
|------|----------|
| concept-gate | 开书前，六维打分（≥70 PASS） |
| project-init | 选题 PASS 后，建目录骨架 |
| premise-guard | 每章，命题防偏 |
| outline-gate | 大纲阶段，卷纲细纲审查+逻辑验证+迭代修复 |
| execution-dispatch | 每章写作前，生成任务包 |
| chapter-review | 每章/每10章/每30章 |
| consistency-module | 资源/关系/伏笔一致性 |
| transition-module | 转场/对话/章末钩子 |
| repair-feedback | 审查 FAIL→WARN 修复链路 |

## 许可

MIT
