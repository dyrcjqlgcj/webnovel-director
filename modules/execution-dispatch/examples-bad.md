# 执行派发反例

## 反例 1：裸 prompt

「继续写第 12 章，爽一点。」

为什么错：没有 premise、状态、禁区、写后审查，极易跑偏。

## 反例 2：canWrite=false 仍写

director_state.blockers 显示「第10章触犯禁飞区」，仍派发第11章。

为什么错：执行派发不能越过导演闸门。

## 反例 3：只给剧情不要求回写

写完正文后不更新 current_state/pending_hooks/last_audit。

为什么错：下一章会失去连续性。

## 反例 4：强行绕过脚本 FAIL

`build_task_package.py` 返回 `canWrite=false`，但助手手写一个 prompt 交给 inkos。

为什么错：脚本 FAIL 就代表导演闸门没有放行；手写 prompt 等于裸写正文。
