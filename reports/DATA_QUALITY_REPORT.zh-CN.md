# 数据质量审计

> 总状态：`PASS`。

## 检查

- [x] `event_ids_unique`
- [x] `candidate_universe_71_plus_168`
- [x] `confirmation_evaluable_ge_50`
- [x] `no_scale_time_leakage`
- [x] `standardization_recomputes`
- [x] `frozen_event_hash_matches`
- [x] `base_lock_precedes_first_label_generation`
- [x] `base_to_amendment_lock_chain_valid`
- [x] `all_available_raw_source_hashes_match`

## 覆盖

- 总候选 239；development=71；confirmation=168；
- 主评估有效 confirmation=164；主测量缺失=6；
- 所有响应尺度截止日严格早于发布日；标准化方向与 response/scale 可逐项复算。

## 锁链

- 原始协议锁：2026-09-03T03:54:22.286472+00:00；
- 首次标签生成：2026-09-03T03:54:43.646988+00:00；
- 当前链式修订锁：2026-09-03T06:55:51.054430+00:00；修订数=4。

原始锁早于标签；Amendment 001 晚于标签，故其非 pristine 性质必须披露。Amendment 002 只替换尚未发布的演示主题，
Amendment 003 只把自定义签署/skill 门与题面硬门分离；二者均不改变历史预测、标签、模型或阈值。
