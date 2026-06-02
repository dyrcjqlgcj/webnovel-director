# webnovel-director

中文长篇网文的结构化写作调度工具。把选材、大纲、写作、审查、回写拆成独立阶段，每个阶段用脚本做自动化检查和修复。

## 两种使用方式

| 方式 | 适用场景 | 需要配置 | 入口 |
|------|----------|----------|------|
| 🧩 **作为 Skill 安装** | 已有 Agent 环境（OpenClaw / Claude Code） | 无需配模型 | 对话直接使用 |
| 🛠️ **直接使用项目** | 独立运行，想用仪表盘、CLI 全流程 | 需要配 API Key + 模型 | CLI + Web 仪表盘 |

---

## 🧩 方式一：作为 Skill 安装

适用于已部署 OpenClaw 或 Claude Code 的用户。安装后直接对话即可使用，**无需手动配置 API Key（继承宿主 Agent 的模型配置）**。

### OpenClaw — ClawHub 安装

```bash
clawhub install webnovel-director
```

### OpenClaw — 本地软链接

```bash
cd ~/.openclaw/skills
ln -s /path/to/webnovel-director webnovel-director
```

### Claude Code — 本地软链接

```bash
cd ~/.claude/skills
ln -s /path/to/webnovel-director webnovel-director
```

安装后，在对话中说「帮我写小说」「分析我的书」「启动仪表盘」等即可触发对应能力。

---

## 🛠️ 方式二：直接使用项目

需要 Python ≥ 3.11，LLM 需要 OpenAI 兼容 API（支持 14 家厂商：DeepSeek / OpenAI / OpenRouter / Groq / Together / Fireworks / 硅基流动 / 智谱 / 月之暗面 / 百川 / 通义千问 / DeepBricks / 自定义兼容端点）。

### 1. 克隆安装

```bash
git clone https://github.com/dyrcjqlgcj/webnovel-director.git
cd webnovel-director
pip install pyyaml
```

### 2. 配置 API Key

三种方式，优先级从高到低：

**方式一：环境变量（推荐）**
```bash
# Windows PowerShell (永久)
[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "sk-...", "User")

# Windows PowerShell (当前会话)
$env:DEEPSEEK_API_KEY = "sk-..."

# Linux / macOS
export DEEPSEEK_API_KEY="sk-..."
```

子进程会自动继承父进程的环境变量，无需重复设置。支持的环境变量：
- `DEEPSEEK_API_KEY` — DeepSeek
- `OPENAI_API_KEY` — OpenAI
- `OPENROUTER_API_KEY` — OpenRouter
- 以及其他厂商对应的 `{PROVIDER}_API_KEY`

**方式二：config.local.yaml（项目级，已 gitignore）**
```yaml
# webnovel-director/config.local.yaml
api_keys:
  deepseek: "sk-..."
  # openai: "sk-..."
```

**方式三：仪表盘保存（最方便）**
```
启动仪表盘 → 顶部 ⚙️ API Key 面板
→ 输入 Key → 选择厂商（或选"自动检测"）→ 点 🔍 验证
→ 自动识别厂商 → 列出可用模型 → 选择一个 → 点 💾 保存
```
写入 `config.local.yaml`，仪表盘进程即时生效。

### 3. 启动仪表盘

```bash
# 为已有项目启动仪表盘
python scripts/dashboard_server.py "books/领地战争-每日一格" --port 8765

# 或通过 wd CLI
python wd.py dashboard "books/领地战争-每日一格"
```

打开浏览器访问 **http://127.0.0.1:8765**

仪表盘功能：
- **P0 项目设置** — 选题验证、创建项目、初始化大纲队列
- **P1 概览操作台** — 项目摘要、健康检查、批量生成、批量修复、L2/L3 审查
- **P2 大纲管理** — 卷结构编辑、章节队列编辑、大纲审查
- **P3 写作管线** — 逐章写作、单章审查、正文查看、任务包构建
- **P3 状态管理** — Truth 文件编辑（current_state / resource_ledger / relationship_graph / hooks 等）

「P1 概览操作台」中，每张操作卡都支持一键执行：点击按钮即可运行对应的脚本，结果实时显示。

### 4. CLI 使用

```bash
# 选题验证
python wd.py gate concept --inline "梗概: ..."

# 建项目
python wd.py init ../轮回塔 --title "轮回塔"
# → 编辑 ../轮回塔/director/premise.md
# → 编辑 ../轮回塔/director/volume_map.md
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

## CLI 命令

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

## 仪表盘 API

向本地仪表盘发起 HTTP 请求可驱动所有操作（支持远程调度）：

```
/api/state                 项目状态摘要
/api/books                 多书列表
/api/outline/full          大纲全量
/api/provider_presets      14 家厂商预设
/api/chapter_content?chapter=N   章节正文
/api/file?path=...         文件读写
/api/action/review_ch_N    单章审查
/api/action/review_parallel_N   卷末审查（L3，含 fallback）
/api/action/repair_N       单章修复
/api/action/write_chapter_N     写一章
/api/batch_write?job=...   批量写章（异步轮询）
/api/write_flow            写作流水线（生成任务包 → 写章 → 审查 → 回写）
/api/concept_gate          选题验证
/api/verify_key            验证 API Key + 自动识别厂商
/api/save_key              保存 API Key 到 config.local.yaml
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

审查 → review_chapter (L1 每章 / L2 每 10 章 / L3 卷末并行 + 回退机制)
  → post_writeback (更新 director_state + truth files)
```

## 闸门

| 闸门 | 阶段 | 检查 |
|------|------|------|
| concept-gate | 选题 | 主角不可替代性、爽点可见性、持续可写性、市场匹配度、差异化、成长梯度 |
| outline-gate | 大纲 | 命题贡献、禁飞区、爽点递进、钩子整合、可执行性 |
| causal-check | 大纲 | 因果链、爽点密度、角色弧线、力量曲线、卷结构同步 |
| premise-guard | 写作中 | 每章是否兑现书名承诺、是否触犯禁飞区 |
| chapter-review | 写后 | L1 每章 / L2 每 10 章 / L3 卷末并行（build 失败自动回退 review_chapter） |

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
│   ├── templates/
│   └── static/
├── references/craft/      # 22 个共享写作参考
└── templates/             # 项目模板
```

## License

MIT
