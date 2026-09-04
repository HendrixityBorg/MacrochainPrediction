# 提交范围说明

本仓库的评审入口只有一条最终路线：

```text
宏观首次发布创新 → 政策路径重定价 → 实际利率重定价 → 黄金重定价
```

历史验证使用冻结的 164 条事件；当期演示只使用
`NFP_202608_REL_20260904_A004`。提交包不分发早期候选事件、替代链实验或开发阶段输出，避免把模型选择
过程与最终验证对象混为一谈。

评审可按以下顺序阅读：

1. `README.md`：问题、结果和复现入口；
2. `reports/SUBMISSION_REPORT.zh-CN.md`：方法、实验、结果与局限；
3. `demo/runs/NFP_202608_REL_20260904_A004.zh-CN.md`：当期演示；
4. `docs/REQUIREMENTS_TRACEABILITY.zh-CN.md`：机器证据索引；
5. `reports/SUBMISSION_MANIFEST.json`：内容提交、验证命令与哈希。

`preregistration/` 中保留的是模型、标签、阈值和评估口径的时间戳审计链。它服务于防止事后改规则，不构成
第二套模型或第二条演示路径。
