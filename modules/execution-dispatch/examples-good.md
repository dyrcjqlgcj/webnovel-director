# 执行派发正例

## 例：生成第 12 章任务包

```text
结论：PASS
依据：chapter_queue 第12章；director_state.canWrite=true；last_audit 无 blocker
问题：暂无
建议：
1. 本章必须兑现「低阶怪复利收益第一次反噬」。
2. 禁止写成主角正面打赢精英队。
下一步：调用 inkos，并在写后运行 chapter-review Level 1
```

任务包重点：
- 读者变化：知道复利不是免费金手指。
- 场景目标：主角想低调清怪。
- 冲突：别人通关导致怪物刷新逻辑异常。
- 转折：收益翻倍但身体/资源出现副作用。
- 钩子：下一章副作用被敌人误判成弱点。

## 例：脚本生成任务包

命令：

```bash
python scripts/build_task_package.py D:/novels/book-a --chapter 12 --out D:/novels/book-a/director/task_packages/0012.yaml
```

成功输出：

```text
结论：PASS
依据：chapter_queue 第 0012 章；director_state.canWrite=true；blockers=0
问题：暂无
建议：
1. 将任务包交给 inkos/执行器。
2. 写后运行 chapter-review Level 1。
3. 回写 director/truth。
下一步：调用执行器，任务包=...
```

为什么对：任务包不是凭空生成，而是由 director_state、chapter_queue、premise、truth files 共同约束。
