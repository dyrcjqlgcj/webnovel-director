# outline_iterate.py 审查报告

> 审查时间：2026-05-26 | 文件：scripts/outline_iterate.py（579 行）

---

## 1. 迭代推理的终止条件

**结论：基本合理，但有两个瑕疵。**

当前终止条件（按优先级）：

| 条件 | 位置 | 评价 |
|---|---|---|
| issues==0 或 (FAIL==0 且 WARN≤2) | L441 | ✅ 合理，允许少量 WARN 残留 |
| groups 为空 | L447 | ✅ 兜底保护 |
| --no-llm 模式下确定性修复后停止 | L473-477 | ✅ 符合预期 |
| 本轮 LLM 无修复（已收敛） | L505-507 | ✅ 避免空转 |
| max_rounds 硬上限（默认 3） | L421 | ✅ 最终安全阀 |

**瑕疵 1**：L470 确定性修复后 `continue`，跳过了当轮 L441 的早期退出判断。如果确定性修复恰好解决了全部问题，也要等到下一轮 `collect_issues` 重新跑完才能退出——多浪费一整轮（包括重新调用 3 个子脚本）。

**瑕疵 2**：L441 的阈值 `warn_count <= 2` 是硬编码的，无法通过 CLI 参数调节。对于某些严格场景可能需要更低的阈值。

---

## 2. LLM 调用的重试和超时保护

**结论：Direct API 路径有保护但有 bug，Gateway 路径保护不足。**

### Direct API（`_call_deepseek_api`，L51-81）

- ✅ 重试 3 次，退避延迟 [2, 5, 10] 秒
- ✅ 超时 120s（可配置）
- ❌ **Bug：`urllib.request.Request` 对象（L64）在 retry 循环外创建**。根据 Python 文档，一次失败后的 Request 对象可能处于不可重用状态（已发送的 socket / 连接状态），导致后续重试也失败
- ❌ 所有重试共用同一个 `req`，若第一次因网络问题失败，后续重试大概率也失败

### Gateway fallback（`_try_llm_gateway`，L84-99）

- ❌ **无重试逻辑**，仅尝试 1 次
- ✅ subprocess 超时 120s
- ❌ 如果 `openclaw` 进程挂死，会损失 120s 才进入下一步

### 策略调度（`call_llm`，L102-121）

- 注释声称"each with 3 retries"（L106），但实际只有 DeepSeek 路径有 3 次重试，Gateway 只有 1 次 —— **文档与代码不一致**

---

## 3. 修复应用机制是否可回滚

**结论：完全没有回滚机制，且 `--dry-run` 存在严重误导。**

- ❌ **无任何备份**：`apply_deterministic_fix` 和 `apply_fix` 直接 `write()` 覆盖 `chapter_queue.md`，不保存原始内容
- ❌ **无 git 快照**：没有在修改前执行 `git add` / `git stash` 或创建备份文件
- ❌ **`--dry-run` 不防确定性修复**（严重 bug）：L480 的 `if dry_run` 只跳过了 LLM 修复（Phase 2），但 L453-468 的确定性修复（Phase 1）完全不受 `dry_run` 控制。帮助文本说"不调用 LLM，不修改文件"，但实际上文件依然会被确定性修复修改
- ✅ 每次修改有 stdout 日志输出，人工可追溯

---

## 4. 明显的性能或逻辑问题

### 4.1 `apply_deterministic_fix` 的未使用参数（L138 / L459）

`ch_lines` 参数在函数签名中声明，但函数体内直接读文件，从未使用该参数。调用处（L459）传入 `[str(g) for g in groups]`（group 名称列表），类型错误但恰好因参数未使用而不报错。

### 4.2 LLM 响应解析只提取一条修复（L326）

```python
fix_match = re.search(r"修改后[：:]\s*(.+?)(?:$|\n|。)", suggestion)
```

prompt 要求 LLM 为每组返回多条修复（每 issue 一行），但 `apply_fix` 只匹配**第一个** "修改后：" 模式。LLM 返回的其他 N-1 条修复被丢弃。此外 `.+?` 在遇到第一个 `。` 即截断，长句会丢失后半部分。

### 4.3 无问题去重

`collect_issues` 合并 3 个子脚本的输出，若同一 chapter 的同一 dimension 被多个脚本报告，会重复修复。虽不会造成逻辑错误，但浪费算力并产生重复日志。

### 4.4 `subprocess.run` 环境变量拼写

L41: `env={**__import__("os").environ, ...}` —— `os.environ` 已在上方导入，这里却重新 `__import__`，不必要但无功能影响。L91 也有类似写法。属于代码风格问题。

### 4.5 Pattern 8 单向修改 volume_map.md

L268-283 的正则替换 `re.sub(r"(\d+)\s*章", ...)` 只替换第一个匹配，且无验证替换后数据正确性。如果 volume_map.md 有多处 "XX 章"，可能改错位置。

---

## 5. 优化建议

| 优先级 | 问题 | 建议 |
|---|---|---|
| 🔴 高 | `--dry-run` 不阻止确定性修复 | 在 L453 之前加 `if dry_run: print("[dry-run] 跳过确定性修复"); continue` |
| 🔴 高 | Request 对象在重试循环外创建 | 将 L64-68 移入 `for attempt` 循环内部，每次重试新建 Request |
| 🔴 高 | 无回滚/备份机制 | 修改前自动备份 `chapter_queue.md` → `chapter_queue.md.bak.{timestamp}` |
| 🟡 中 | LLM 响应只解析第一条修复 | 改为逐行匹配 `ChXXX: ... → 修改后: yyy` 模式，或使用 `re.findall` |
| 🟡 中 | Gateway 无重试 | 给 `_try_llm_gateway` 加 2 次重试 |
| 🟡 中 | 确定性修复后浪费一轮 | L470 的 `continue` 前，先重新 `collect_issues` 检查是否已满足退出条件 |
| 🟢 低 | `ch_lines` 未使用参数 | 从函数签名中移除，调用处同步清理 |
| 🟢 低 | 无问题去重 | 在 `group_issues` 中按 `(chapter, dimension)` 去重 |
| 🟢 低 | 硬编码退出阈值 | `warn_count <= 2` 改为 CLI 参数 `--max-warn`（默认 2） |

---

## 总体评价

代码骨架设计良好：两阶段修复（确定性→LLM）+ 多轮迭代 + 多策略 LLM 调用的思路正确。但存在 **3 个必须修复的问题**（`--dry-run` 无效、Request 对象复用、无回滚），以及若干影响修复效果的解析和去重问题。建议在投入生产使用前优先处理高优先级项。
