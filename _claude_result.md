# 审查结果（review_chapter / repair_plan / post_writeback）

## review_chapter.py
钩子检测过于简陋（仅靠标点/关键词在末400字内的出现次数判断），且缺少角色一致性、节奏密度等维度；但命题兑现的滑窗匹配对中文碎片化命中较实用，JSON输出格式可机读、对接下游工具良好。

## repair_plan.py
关键词分级存在重叠（"密度"同时出现在R1和R3），可能导致分级歧义；但自动修复安全边界正确——仅R0/R1可自动应用且均不修改正文内容，R2+强制人工介入，风险可控。

## post_writeback.py
truth文件的 expire_res_rows 和 res_rows 针对同一章节时存在覆盖丢失 bug：两次 `upsert_table_rows` 各自先删后写，后一次调用会抹掉前一次写入的行；备份机制可靠（写前全量 .bak），但无回滚能力。
