# 项目初始化

用于「开新长篇 / 导入长篇 / 给现有项目接入导演系统」。本模块只负责把作品变成可被长期维护的项目，不负责写正文。

## 解决的问题

- 把用户的模糊创意固化为可审计的目录与状态文件。
- 建立唯一真相源：`director/premise.md` 与 `director/director_state.json5`。
- 创建与 inkos 兼容的 truth files，避免后续每次写作都重新发明设定。
- 给 outline-gate 和 execution-dispatch 提供稳定输入。

## 什么时候用

- 用户说「开书」「新建一本」「把这个想法做成长篇」。
- 用户已有正文/大纲，但缺少 director/truth 文件。
- 自动日更任务启动前发现目标书目录没有 director 层。

## 本模块不做

- 不评价题材市场前景；需要时转 `references/integration-oh-story.md`。
- 不写正式章节。
- 不把大量世界观塞进 premise；premise 只存命题约束和禁飞区。
