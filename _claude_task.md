# 拆分后重命名阶段2: 自动拆分

修改 C:\Users\ThinkPad\.openclaw\skills\webnovel-director\scripts\check_wordcount.py 的 split 逻辑。

## 当前问题
现在是一拆二，如果拆分后还超4500字就再拆一轮。但这会产生多次后移，章号混乱。

## 新逻辑
一次性计算需要几段，统一拆分：

1. 字数 / 阈值 → 段数（向上取整）: 1段/2段(上下)/3段(上中下)/4段(一二三四)/5段(一二三四五)...
2. 在正文中找 N-1 个自然断点（优先场景分隔符>时间跳跃>空行簇>中点）
3. 一次性写入所有段
4. 后续章号后移 N-1
5. 一次性更新 chapter_queue

## 具体修改点

### 1. 新增函数 `calculate_segments(max_words, char_count) -> int`
```python
def calculate_segments(max_words: int, char_count: int) -> int:
    return max(1, (char_count + max_words - 1) // max_words)
```

### 2. 新增函数 `find_n_split_points(text, n) -> list[int]`
找 n-1 个断点。先把正文分成大致均匀的 n 段，每段区间内找最佳断点。

### 3. 新增函数 `segment_suffix(i, total) -> str`
```python
def segment_suffix(i, total):
    if total == 1: return ""
    if total == 2: return "（上）" if i == 0 else "（下）"
    if total == 3: return ["（上）","（中）","（下）"][i]
    cn = ["一","二","三","四","五","六","七","八","九","十"]
    return f"（{cn[i]}）"
```

### 4. 重写 `rename_and_shift` 函数
改为一次性处理：计算段数 → 找N-1个断点 → 写N个文件 → 后移(N-1) → 更新queue。

### 5. 修复章节编号
原来章节编号有跳号（Ch18缺失），新逻辑应该避免这种情况。

完成后：
- python -m py_compile 验证
- 对《逃离轮回》项目重新拆分（先 git reset 回拆分前，再跑新逻辑）
- 验证所有章在4500内且编号连续
- 不要 push
