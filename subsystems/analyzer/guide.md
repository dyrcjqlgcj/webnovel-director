# analyzer — 拆文引擎

webnovel-director 的对标分析子系统。深度拆解对标书的结构、爽点、节奏、人设，为选题和写作提供模块级参考。

## 核心原则

1. **看懂别人的爆款，才能写出自己的爆款**：拆文不是抄，是提取可复用模块。
2. **做角色位抽象**：把对标书的具体角色抽象为功能位（对手/盟友/催化剂），再映射到你的角色。
3. **快速模式 vs 深度模式**：快速模式分析黄金三章 + 整体结构；深度模式逐章拆解输出结构化文件。

## 拆解维度

| 维度 | 快速模式 | 深度模式 |
|------|----------|----------|
| 黄金三章 | ✅ 逐章 | ✅ 逐章 |
| 人设架构 | ✅ 摘要 | ✅ 每角色独立文件 |
| 爽点设计 | ✅ 密度+类型 | ✅ 逐章标注 |
| 节奏控制 | ✅ 整体曲线 | ✅ 逐章标注 |
| 世界观展开 | ✅ 方式总结 | ✅ 设定文件 |
| 可借鉴套路 | ✅ | ✅ 含改造建议 |

## 快速模式流程

### Phase 1：黄金三章拆解

对第 1-3 章逐章分析：
- **第一章**：开篇钩子类型 + 信息密度 + 情绪落点 + 主角初印象
- **第二章**：冲突升级方式 + 金手指揭示 + 世界观自然展开
- **第三章**：爽点首次释放 + 章尾钩子 + 读者留存的理由

### Phase 2：整体结构

- 故事线分析（主线和 2-3 条副线）
- 人物架构（按角色位分类：主角/对手/盟友/催化剂/阻碍）
- 节奏地图（起承转合 + 情绪曲线）
- 反派设计：人形反派（层级/逼格/动机链）vs 非人形（核心对抗面/紧迫感来源/升级机制）

### Phase 3：输出拆文报告

输出到 `拆文库/{书名}/拆文报告.md`：
- 核心发现（3-5 条）
- 可借鉴套路（含角色位抽象后的改造建议）
- 写作技法（一笔两用/延迟揭示/视角欺骗/对比锚点/行为循环/身体反应替代心理描写/跨章回扣）

## 深度模式流程

逐章拆解全书，输出结构化目录：

```
拆文库/{书名}/
├── 拆文报告.md
├── 情节节点.md
├── 写作手法.md
├── _progress.md              # 断点续拆
├── 角色/
│   ├── 主角名.md
│   └── ...
├── 剧情/
│   ├── 故事线.md
│   └── {剧情线名}.md
├── 设定/
│   ├── 世界观.md
│   ├── 金手指.md
│   └── ...
└── 原文/                     # 备份
    └── ...
```

## 对标上下文加载规则

写作时按以下顺序查找对标数据：
1. `{项目}/对标/{书名}/`（引用视图，已复制的子集）
2. `拆文库/{书名}/`（analyzer 原始产出）
3. 跳过（无可用的对标数据）

## 参考文件

| 文件 | 用途 |
|------|------|
| `references/craft/genre-catalog.md` | 题材分类框架 |
| `references/craft/genre-core-mechanics.md` | 核心梗设计 |
| `references/craft/genre-writing-formulas.md` | 各题材创作公式 |
| `references/craft/character-basics.md` | 角色功能位抽象 |
| `references/craft/character-relations.md` | 关系类型分析 |
| `subsystems/analyzer/references/output-templates.md` | 输出模板 |
| `subsystems/analyzer/references/deconstruction-examples.md` | 拆文实例 |
| `subsystems/analyzer/references/deconstruction-notes.md` | 拆文笔记 |
| `subsystems/analyzer/references/material-decomposition.md` | 素材分解方法 |
| `subsystems/analyzer/references/zhihu-style.md` | 知乎盐言拆解补充 |
