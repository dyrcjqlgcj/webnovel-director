# webnovel-director

中文长篇网文的结构化写作调度工具。把选材、大纲、写作、审查、回写拆成独立阶段，每个阶段用脚本做自动化检查和修复。

## 安装

```bash
git clone https://github.com/dyrcjqlgcj/webnovel-director.git
cd webnovel-director
pip install pyyaml
```

Python ≥ 3.11，LLM 需要 OpenAI 兼容 API（DeepSeek / OpenAI / GPTsAPI）。

也可以作为 skill 安装到 Agent 中，安装后直接对话即可使用：

```bash
# OpenClaw — ClawHub 安装
clawhub install webnovel-director

# OpenClaw — 本地软链接
cd ~/.openclaw/skills
ln -s /path/to/webnovel-director webnovel-director

# Claude Code — 本地软链接
cd ~/.claude/skills
ln -s /path/to/webnovel-director webnovel-director
```

## 使用

```bash
# 选题验证
python wd.py gate concept --inline "
梗概: 主角死后保留记忆，在轮回塔中用死亡试错刷攻略
金手指: 死亡后保留全部记忆，攻略数据永不丢失
世界观: 无限轮回塔，每层有Boss，公会靠口传攻略
平台: 番茄
"

# 建项目（在 webnovel-director 目录外面）
python wd.py init ../轮回塔 --title "轮回塔"
# → 编辑 ../轮回塔/director/premise.md
# → 编辑 ../轮回塔/story/outline/volume_map.md
# → 编辑 ../轮回塔/director/chapter_queue.md

# 大纲审查 + 自动修复
python wd.py gate outline ../轮回塔 --fix

# 写正文
python wd.py build ../轮回塔 --chapter 1
python wd.py write ../轮回塔 --chapter 1

# 审查
python wd.py doctor ../轮回塔
python wd.py review ../轮回塔 --chapter 1
```

仪表盘：

```bash
python wd.py dashboard ./轮回塔
```

## CLI

```
wd init      <dir> --title "书名"       建项目
wd gate      concept <file|--inline>    选题验证
wd gate      outline <dir> [--fix]      大纲审查 + 逻辑验证 + 迭代修复
wd build     <dir> --chapter N          生成写作任务包
wd write     <dir> --chapter N          调 LLM 写正文
wd review    <dir> --chapter N          单章审查
wd doctor    <dir>                     文件完整性 / 状态同步 / 队列健康
wd status    <dir>                     项目摘要
wd dashboard <dir>                     Web 仪表盘
wd premis    <dir>                     从已有文件提取 premise
wd test                               全链路冒烟测试
wd doctor    --self                    自检脚本语法
```

## 配置

```bash
cp config.yaml config.local.yaml
```

```yaml
providers:
  deepseek:
    api_key_env: "DEEPSEEK_API_KEY"
    default_model: "deepseek-chat"
writing:
  max_tokens: 8000
  temperature: 0.8
dashboard:
  port: 8765
```

## 流程

```
选题 → scanner 扫榜 → analyzer 拆对标书
  → concept-gate (低于 70 分拒绝)

建项目 → premise.md (书名承诺 + 禁飞区 + 角色锁)
  → volume_map.md (卷结构) + chapter_queue.md (细纲)

大纲 → outline-gate (六维审查) → causal-check (因果链/爽点密度/角色弧线/力量曲线)
  → outline_iterate (确定性修复 + LLM 修复，迭代至 PASS)

写作 → build_task_package (生成任务包) → write_chapter (LLM 写正文)

审查 → review_chapter (L1 每章 / L2 每 10 章 / L3 每 30 章)
  → post_writeback (更新 director_state + truth files)
```

## 闸门

| 闸门 | 阶段 | 检查 |
|------|------|------|
| concept-gate | 选题 | 主角不可替代性、爽点可见性、持续可写性、市场匹配度、差异化、成长梯度 |
| outline-gate | 大纲 | 命题贡献、禁飞区、爽点递进、钩子整合、可执行性 |
| causal-check | 大纲 | 因果链、爽点密度、角色弧线、力量曲线、卷结构同步 |
| premise-guard | 写作中 | 每章是否兑现书名承诺、是否触犯禁飞区 |
| chapter-review | 写后 | L1 每章 / L2 每 10 章 / L3 每 30 章 + 4 Agent 并行 |

## 子系统

```
scanner/     市场雷达 — 平台数据采集、跨样本信号提取、可写性评估
analyzer/    拆文引擎 — 对标的书拆解、角色位抽象、模块提取
writer/      正文执行 — 情绪驱动写作、黄金三章、钩子十三式、禁用词表
reviewer/    深度审查 — L1/L2/L3 分级、4 Agent 并行、R0-R4 修复分级
polisher/    去 AI 味 — AI/自然文本对比、分级保护、替换词表
```

## 目录

```
webnovel-director/
├── wd.py                  # CLI 入口
├── config.yaml            # 配置
├── lib/                   # common.py + llm.py
├── scripts/               # 21 个脚本
├── modules/               # 9 个闸门模块
├── subsystems/            # 5 个子系统
├── dashboard/             # 仪表盘前端
├── references/craft/      # 22 个共享写作参考
└── templates/             # 项目模板
```

## License

MIT
