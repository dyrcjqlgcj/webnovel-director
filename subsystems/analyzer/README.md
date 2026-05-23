# analyzer — 拆文引擎

导演系统的对标分析模块。在概念阶段，深度拆解对标书的结构、爽点、节奏、人设，为选题提供数据支撑。

## 核心原则

- 看懂别人的爆款，才能写出自己的爆款
- 拆文不是抄，是提取可复用模块，做角色位抽象
- 快速模式：黄金三章 + 整体结构；深度模式：逐章拆解

## 导演调用

```bash
# concept-gate 阶段自动提示：若有对标书，先拆文
python scripts/concept_gate.py --with-analysis <对标书名>
```

## 关键输出维度

1. 黄金三章钩子设计
2. 爽点密度与节奏
3. 人设架构（角色功能位抽象）
4. 世界观展开方式
5. 可借鉴套路（不是抄剧情，是抄模式）

## 参考

- 完整拆文管线：外部 skill `story-long-analyze`
- 输出模板：`story-long-analyze/references/output-templates.md`
