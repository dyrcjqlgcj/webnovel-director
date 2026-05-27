<p align="center">
  <b>webnovel-director</b> &nbsp; 网文导演台
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/dyrcjqlgcj/webnovel-director/stargazers"><img src="https://img.shields.io/github/stars/dyrcjqlgcj/webnovel-director?style=flat&logo=github&color=yellow" alt="stars"></a>
</p>

---

选材 → 大纲 → 写作 → 审查 → 回写。每一步都有一道闸门。

**不是替你写，是让你写完 50 万字之后，回过头看第一章，发现还是同一本书。**

---

## 解决什么问题

长篇网文最常见的失败模式不是文笔差，是**写到中期主角忘了自己是谁、爽点被套路替换、伏笔丢了三十章没人记得**。

这个项目把"导演"这个角色从你脑子里拆出来，变成一个可执行的工作台：

| 导演的职责 | webnovel-director 怎么做的 |
|-----------|--------------------------|
| 选题前看市场 | scanner 扫榜，不是看一本爆款，是跨样本提取重复信号 |
| 开拍前验证剧本 | concept-gate 六维打分，低于 70 分直接劝退 |
| 盯拍摄不跑偏 | premise-guard 每章检查：这一章还对得起书名承诺吗 |
| 审分镜合不合理 | outline-gate 逐章审查：因果链断了吗？爽点间距超过 3 章了吗？ |
| 喊"卡"重来 | repair-feedback 自动分级（R0-R4），该修就修 |
| 盯监视器 | dashboard 一个页面看完全书进度、审查色块、阻塞项 |

## 项目定位

跟同类项目的关系——不是替代，是不同环节：

| 项目 | 定位 |
|------|------|
| [InkOS](https://github.com/Narcooo/inkos) | 全自动多 Agent 小说生产线——写、审、改全接管，守护进程模式日更 |
| [Chinese-WebNovel-Skill](https://github.com/Tomsawyerhu/Chinese-WebNovel-Skill) | 模块化写作 skill——把写作问题拆成 10 个专项模块 + 本地语料检索 |
| **webnovel-director** | **闸门调度台——不替代前两者，而是在你"用 AI 写"和"自己写"之前，先用结构化验证拦住会毁掉长篇的决策** |

InkOS 管"写"，Chinese-WebNovel-Skill 管"怎么写好"，webnovel-director 管"**写之前和写之后该检查什么**"。

## 五分钟跑起来

```bash
git clone https://github.com/dyrcjqlgcj/webnovel-director.git
cd webnovel-director
pip install pyyaml

# 第一步：选题验证
python wd.py gate concept --inline "
梗概: 主角死后保留记忆，在轮回塔中用死亡试错刷攻略
金手指: 死亡后保留全部记忆，攻略数据永不丢失
世界观: 无限轮回塔，每层有Boss，公会靠口传攻略
平台: 番茄
"

# 第二步：建项目，写设定
python wd.py init ./轮回塔 --title "轮回塔"
# → 编辑 ./轮回塔/director/premise.md（书名承诺+禁飞区+角色锁）
# → 编辑 ./轮回塔/story/outline/volume_map.md（卷结构）
# → 编辑 ./轮回塔/director/chapter_queue.md（前 10-20 章细纲）

# 第三步：大纲过闸门
python wd.py gate outline ./轮回塔 --fix

# 第四步：生成任务包，调 LLM 写第一章
python wd.py build ./轮回塔 --chapter 1
python wd.py write ./轮回塔 --chapter 1

# 第五步：审查 → 回写 → 下一章
python wd.py review ./轮回塔 --chapter 1
python wd.py doctor ./轮回塔
```

Web 仪表盘：

```bash
python wd.py dashboard ./轮回塔
```

## 管线流程

```
选题                  大纲                    写作                    审查
  │                    │                      │                       │
scanner            outline-gate          execution-dispatch     chapter-review
  │               ┌──┴──┐               ┌──┴──┐               ┌──┴──┐
  ▼               │     │               │     │               │     │
analyzer      outline_  outline_    build_task  write_     review_   post_
(对标拆解)    gate_      causal_    _package    chapter    chapter   writeback
              review     check      (任务包)    (LLM写)   (L1审查)  (回写状态)
               │         │                                        │
               └────┬────┘                                        │
                    ▼                                              │
              outline_iterate                                     │
              (迭代修复至PASS)                                     │
                                                                  │
              ◄──────────────── 回到下一章 ────────────────────────┘
```

## 命令

```
wd init      <dir> --title "书名"       建项目骨架
wd gate      concept <file|--inline>    选题闸门，六维打分
wd gate      outline <dir> [--fix]      大纲闸门，审查+逻辑+迭代
wd build     <dir> --chapter N          生成写作任务包
wd write     <dir> --chapter N          调 LLM 写正文
wd review    <dir> --chapter N          单章审查
wd doctor    <dir>                     一键体检
wd status    <dir>                     项目摘要
wd dashboard <dir>                     开 Web 仪表盘
wd premis    <dir>                     从已有文件提取 premise 初稿
wd test                                全链路冒烟测试
wd doctor    --self                    自检所有脚本语法
```

## 配置

```bash
cp config.yaml config.local.yaml
```

```yaml
# config.local.yaml
providers:
  deepseek:
    api_key_env: "DEEPSEEK_API_KEY"
    default_model: "deepseek-chat"
writing:
  max_tokens: 8000
  temperature: 0.8
concept_gate:
  pass_threshold: 70        # 低于 70 分直接拒绝
outline_gate:
  max_iteration_rounds: 3   # 最多迭代 3 轮
dashboard:
  port: 8765
```

## 闸门一览

| 闸门 | 阶段 | 检查什么 | 不通过会怎样 |
|------|------|----------|------------|
| **concept-gate** | 选题 | 主角不可替代性 / 爽点可见性 / 可写性 / 市场匹配 / 差异化 / 成长梯度 | 直接拒绝，换选题 |
| **premise-guard** | 写作中 | 每章是否还在兑现书名承诺？是否触碰禁飞区？角色功能有没有越界？ | 警告，标记偏离 |
| **outline-gate** | 大纲 | 逐章审查：命题贡献 / 禁飞区 / 爽点递进 / 钩子整合 / 可执行性 | 拦停，不通过不能写正文 |
| **causal-check** | 大纲 | 因果链 / 爽点密度 / 角色弧线 / 力量曲线 / 卷结构同步 | 同上 |
| **chapter-review** | 写后 | L1 每章（禁飞区+命题+字数+钩子）、L2 每 10 章、L3 每 30 章（4 Agent 并行） | 分级修复 |

## 五大子系统

每个子系统内置完整方法论，clone 即用，不依赖外部 skill：

```
subsystems/
├── scanner/    市场雷达 — 扫榜流程、平台数据源、跨样本信号提取
├── analyzer/   拆文引擎 — 快速/深度拆解、角色位抽象、模块提取
├── writer/     正文执行 — 情绪驱动、黄金三章铁律、钩子十三式、禁用词表
├── reviewer/   深度审查 — L1/L2/L3 分级、4 Agent 并行、质量评分标准
└── polisher/   去 AI 味 — AI/自然文本对比基准、分级保护、替换词表
```

## 设计决策

1. **闸门必须过，不能跳过**。PASS 放行，WARN 人工确认，FAIL 必须修。没有"先写着后面再说"。
2. **确定性修复优先**。`outline_iterate.py` 内置 8 种正则规则，能不用 LLM 就不用。
3. **真相源唯一**。`director/` 目录是整本书的唯一约束来源，所有脚本读同一套文件。
4. **写前必读，写后必写**。写章前加载 premise + truth files；写完后必须回写 state + audit。
5. **脚本要能独立跑，也能被 import**。每个脚本可以命令行用，核心逻辑也暴露为 Python 函数。

## 项目结构

```
webnovel-director/
├── wd.py                      # 统一 CLI
├── config.yaml                # 全局配置
├── lib/                       # common.py（共享工具）+ llm.py（LLM 调用）
├── scripts/                   # 21 个脚本
├── modules/                   # 9 个闸门模块（教程/规则/正例/反例/来源）
├── subsystems/                # 5 个自包含写作子系统
├── dashboard/                 # Web 仪表盘前端
├── references/craft/          # 22 个共享写作参考
└── templates/                 # 项目模板
```

## License

MIT
