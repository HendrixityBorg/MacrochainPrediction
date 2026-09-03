# SX-CH-001 黄金潜变量链提交报告

> 机器状态：**NOT_S_READY**。未通过项：`rare_method_calibration_n_ge_20, independent_custody_attestation, prospective_current_macro_demo`。

## 摘要

本项目实现多测量潜变量模型，但最终审计标签始终由 H.15 2 年期、H.15 5 年期实际利率和 GLD 主测量定义。
预测模型用 2005–2010 非农事件开发，2011–2024 确认批的任何结果均不回流训练。CPI 被保留为真实当期演示根事件。

## 图与公式

```text
macro surprise S → policy path M → real rate R → gold G
                         ↘ inflation Π ↗      ↑
                                  USD D / external Q
```

测量方程：`y[j,t] = alpha[j] + lambda[j] X[t] + epsilon[j,t]`；主测量 `alpha=0, lambda=1`。
结构概率：`P_chain = E[(1-q) p1 p2 p3 | development evidence]`。这里的 `p2` 与 `p3` 是前缀成功条件概率，
不是把三个无条件边际频率相乘。外部截断 `q` 与链路自身断裂分别输出。

## 参数估计与有效证据

- 第 1 跳：方法 `prefix_conditional_latent_fractional_logistic`，n_raw=61，n_eff=56.17，软成功量=18.75。
- 第 2 跳：方法 `prefix_conditional_latent_fractional_logistic`，n_raw=22，n_eff=20.10，软成功量=11.86。
- 第 3 跳：方法 `prefix_conditional_latent_fractional_logistic`，n_raw=16，n_eff=14.86，软成功量=6.33。

每个预测的 `p_i`、`n_i`、证据事件 ID、特征、系数、协方差与随机种子保存在 `edge_evidence.json`。
少于 5 个条件实例时，代码强制退回同跳宏观参考类；本确认路线的估计法另在不少于 20 个已知开发实例上报告校准记录。

## 确认评估

- 有效确认链：133；终点成功：22；实际率：0.165；
- 潜变量条件模型 Brier：0.1447；朴素边际连乘：0.1558；条件 Beta：0.1443；
- climatology Brier：0.1430；无根信号消融：0.1471；主测量-only：0.1418；
- 逐跳前缀率：0.421 → 0.293 → 0.165；
- CI 宽度—绝对误差 Spearman rho=0.680，p=0.0002。

![可靠性图](reliability.png)

![逐跳衰减](hop_decay.png)

## 认识论置信区间

90% CI 由参数后验、潜变量测量误差、代理残差相关、制度漂移和外部截断概率共同传播；没有对跳点乱序，
也没有把不同聚合器的分歧当 CI。合成 oracle 在校准分区选择区间尺度后冻结，在隐藏 test truth 上评估。

- oracle test coverage：0.920；目标 ≥0.85；
- oracle CI 宽度—真概率误差 rho=0.821，p=0.0005；
- 证据增强方向：中心上移=True，区间收窄=True。

## 停止与交易决策

每个前缀均计算 90% CI、break-even probability、一次复核 EVSI 与复核成本。终点 CI 下沿高于盈亏平衡概率才建仓；
上沿低于阈值则拒绝；跨阈值则弃权。CI 宽且下一次复核 EVSI 不覆盖成本时提前停止。最大跳数仅是保护栏。
建议仓位规则：`CI lower > break-even` 才开仓；`CI width > 0.30` 不开仓；否则仓位上限按 `(lower-threshold)/(1-threshold)` 缩放。

## 可复现性与失败案例

随机三跳复算最大 |delta p_i|=0.00000000。失败案例逐条保存在 `evaluation.json`，
包括预测、结果、CI 宽度和断裂跳。任何确认指标失败都保留为冻结负结果。

## 局限性与盲点

1. 日频 close-to-close 窗口会混入发布后其他新闻，因果识别弱于 30 分钟期货窗口；
2. Yahoo 代理原始历史不可随仓库再分发，只提交事件级派生量和源哈希；
3. 现有本地原始价格历史意味着仍需独立托管/签名声明，才能把确认批提升为最强证据；
4. 没有真实、结果未决的 CPI 封存记录前，不得声称全 S；
5. 黄金同时受美元、安全港、流动性和央行需求影响；这些属于显式干扰项，而不是事后解释链路成功。

## 扩展方向

采购授权的 30 分钟 ZT/SOFR/TIPS/GC 数据复做同协议；前瞻积累 CPI 演示；增加安全港新闻的事前可用测量；
在不接触确认标签的下一版本中比较粒子滤波/完整状态空间 Bayes，而不是扩大当前模型后再重测同一确认集。
