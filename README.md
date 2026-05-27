# webnovel-director

> 长篇网文写到 30 万字最容易发生的事：主角忘了自己是谁，爽点换成了套路，伏笔丢了半年。这个项目做的事很简单——**在每个关键节点拦住你，问你一句：这章还对得起你最初给读者的承诺吗？**

## 一句话

**给网文作者一个不撒谎的工作台。** 从选题到完本，每往前推进一步，都有一道闸门验证你是不是还在写同一本书。

## 安装

```bash
git clone https://github.com/dyrcjqlgcj/webnovel-director.git
cd webnovel-director
pip install pyyaml
```

需要 Python ≥ 3.11，以及能访问 OpenAI 兼容 API 的 LLM（DeepSeek / OpenAI / GPTsAPI 均可）。

## 十分钟跑通全流程

```bash
# 1. 初始化项目骨架
python wd.py init ./轮回塔 --title "轮回塔"

# 2. 验证你的选题能不能撑起一部长篇
python wd.py gate concept --inline "
梗概: 主角死后保留记忆，在轮回塔中用死亡试错刷攻略
金手指: 死亡后保留全部记忆，攻略数据永不丢失
世界观: 无限轮回塔，每层有Boss，公会靠口传攻略
平台: 番茄
"

# 3. 写完卷纲和细纲后，过闸门
python wd.py gate outline ./轮回塔 --fix

# 4. 生成任务包，调 LLM 写第一章
python wd.py build ./轮回塔 --chapter 1
python wd.py write ./轮回塔 --chapter 1

# 5. 写后审查 + 回写状态
python wd.py review ./轮回塔 --chapter 1
python wd.py doctor ./轮回塔
```

不想记命令的话，开仪表盘点点鼠标就行：

```bash
python wd.py dashboard ./轮回塔
```

## 它到底在管什么

长篇小说最大的敌人不是写不出来，是**写着写着就歪了**。这个项目把最容易歪的五个环节各装了一道闸门：

| 环节 | 闸门 | 拦什么 |
|------|------|--------|
| 选题 | **concept-gate** | 六维打分：主角有没有不可替代性？爽点读者一眼能看懂吗？能撑 50 万字吗？市场有人看吗？跟已有作品差在哪？成长梯度够不够？低于 70 分直接劝退 |
| 大纲 | **outline-gate** | 逐章审查：每章对书名承诺有贡献吗？触犯禁飞区了吗？爽点间距超过 3 章了吗？钩子回收了吗？Goal 能落地执行吗？ |
| 逻辑 | **causal-check** | 因果链是否断裂？角色有没有弧线？力量曲线有没有平坦区？有没有 5 章连续无爽点？ |
| 写作 | **premise-guard** | 这一章还在兑现书名承诺吗？还是为了凑字数塞了一堆跟命题无关的内容？禁飞区扫描、命题贴合检查 |
| 审查 | **reviewer** | L1 每章（禁飞区/命题/字数/钩子）、L2 每 10 章（剧情逻辑/人物目标/情绪关系）、L3 每 30 章（4 Agent 并行深审） |

## 五个子系统

每个子系统都是一套独立方法论，clone 即用，不需要额外装任何东西：

```
scanner          analyzer         writer           reviewer         polisher
市场雷达         拆文引擎         正文执行器        深度审查          去AI味
──────────────────────────────────────────────────────────────────────────
扫榜找趋势       拆解对标书       情绪驱动写作      L1/L2/L3 分级     AI味检测
平台数据采集     角色位抽象       黄金三章铁律      禁飞区扫描        分级保护
可写性评估       模块提取         钩子十三式        命题贴合检查      替换词表
跨样本信号提取   快速+深度模式    禁用词表          多Agent并行       自然文本基准
```

## 命令参考

```
wd init      <dir> --title "书名"       建项目骨架
wd gate      concept <file|--inline>    选题闸门（六维验证）
wd gate      outline <dir> [--fix]      大纲闸门（审查+逻辑+迭代修复）
wd build     <dir> --chapter N          生成写作任务包
wd write     <dir> --chapter N          调 LLM 写正文
wd review    <dir> --chapter N          单章审查
wd doctor    <dir>                     一键体检（文件完整性/状态同步/队列健康）
wd dashboard <dir>                      开 Web 仪表盘
wd status    <dir>                      项目状态摘要
wd test                                全链路冒烟测试
wd doctor    --self                    自检所有脚本语法
```

## 配置

复制 `config.yaml` 为 `config.local.yaml`（已在 `.gitignore` 中），改你的 key 和模型名：

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

## 项目结构

```
webnovel-director/
├── wd.py                  # 统一命令行入口
├── config.yaml            # 全局配置
├── lib/                   # 共享库（common.py + llm.py）
├── scripts/               # 20+ 可执行脚本
├── modules/               # 9 个闸门模块（每个包含教程/规则/正例/反例/来源）
├── subsystems/            # 5 个自包含写作子系统
│   ├── scanner/           #   市场雷达 + 5 个参考文件
│   ├── analyzer/          #   拆文引擎 + 5 个参考文件
│   ├── writer/            #   正文执行 + 18 个参考文件
│   ├── reviewer/          #   深度审查 + 评分标准
│   └── polisher/          #   去AI味 + AI/自然文本对比基准
├── dashboard/             # Web 仪表盘前端
├── references/craft/      # 22 个共享写作参考
└── templates/             # 项目模板
```

## 设计原则

1. **闸门可以 WARN，但不能跳过**。每道闸门给出 PASS / WARN / FAIL，WARN 可以人工放行，FAIL 必须修。
2. **先确定性修复，再调 LLM**。`outline_iterate.py` 内置 8 种正则级别的修复规则，能不用 LLM 就不用。
3. **长篇必须有一个真相源**。`director/` 目录维护作品的全部约束：书名承诺、禁飞区、角色功能锁、卷纲、细纲、状态文件。
4. **写前必读，写后必写**。每章写作前必须加载 premise + truth files；每章写完后必须回写 director_state + audit_log。
5. **子系统自包含**。五个子系统不依赖任何外部 skill 或插件，clone 即用。

## 许可

MIT
