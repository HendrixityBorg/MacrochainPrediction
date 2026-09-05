# 数据契约

`events.csv` 一行是一场独立宏观发布，不把分支或前缀重复计为样本。每个 `_z` 字段都必须同时有
对应 `_response`、`_scale`、`_source_id`；`z = orientation × response / scale`。所有 scale 的
最后输入日必须早于 `release_date`。

主测量标签固定使用 `policy_h15_2y_z`、`real_h15_5y_z` 和 `gold_gld_z`。代理字段只进入潜变量
后验和敏感性报告。缺失代理允许为空，缺失任一主测量则该事件不得进入主评估。

`evidence_status` 只允许：

- `development_seen`；
- `confirmation_protocol_locked`；
- `live_outcome_unresolved`；
- `live_resolved`。

源清单必须记录 URL、下载时间、原文件 SHA-256、再分发状态和变换。确认集还必须记录协议哈希与
首次生成标签时间。禁止事后覆写；新数据只能生成新版本目录。

