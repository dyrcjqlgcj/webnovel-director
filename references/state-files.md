# 状态文件规范

## 每本书目录

```text
{book}/
├── director/
│   ├── premise.md
│   ├── director_state.json5
│   ├── forbidden_zones.md
│   ├── role_locks.md
│   ├── volume_state.md
│   ├── chapter_queue.md
│   ├── last_audit.md
│   └── audit_log.md
├── truth/
│   ├── templates\current_state.md
│   ├── templates\resource_ledger.md
│   ├── templates\particle_ledger.md
│   └── templates\pending_hooks.md
```

## premise.md

必须包含：
- 书名命题
- 命题三要素
- 禁飞区
- 角色功能锁
- 卷级禁区
- 偏离日志

## director_state.json5

建议字段：

```json5
{
  bookId: "",
  title: "",
  status: "drafting",
  activeVolume: 1,
  currentChapter: 1,
  premiseFile: "director/premise.md",
  lastAudit: "director/last_audit.md",
  chapterQueue: "director/chapter_queue.md",
  executor: "inkos",
  canWrite: true,
  blockers: [],
  updatedAt: ""
}
```

## truth files

兼容 inkos：
- `templates\current_state.md`
- `templates\particle_ledger.md`
- `templates\pending_hooks.md`

也可增加更通用的 `templates\resource_ledger.md`，但必须声明与 inkos 文件的同步关系。

## 与 inkos 项目的同步

已有 inkos 项目通常有：

```text
templates\current_state.md
templates\pending_hooks.md
story/chapter_summaries.md
story/state/*.json
chapters/*.md|txt
```

webnovel-director 接入时不要直接改 inkos 原文件。使用：

```bash
python scripts/sync_inkos_state.py <book_dir> --write
```

同步原则：

- `templates\current_state.md` → `templates\current_state.md`
- `templates\pending_hooks.md` → `templates\pending_hooks.md`
- `chapters/` 最新编号 → `director_state.currentChapter`
- `story/current_focus.md` 若落后，只在 audit 中 WARN，不自动改原文件
- `canWrite` 默认保持 false，直到 outline-gate PASS

## truth/relationship_graph.yaml

记录人物、资源、钩子之间的因果边。consistency-module 用于检查关系链断裂。

```yaml
edges:
  - source: "主角.核心物品"
    target: "地点.关键设施"
    relation: "脉冲同步"
    active_from: 30
    active_until: null
```

字段：
- `active_until`: null=持续有效，数字=第N章后过期
- 验证：`scripts/validate_relationships.py`

