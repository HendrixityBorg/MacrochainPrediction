# 宏观事件多跳因果链不确定性

本仓库实现一个事件索引的**多测量潜变量条件贝叶斯链**，用于估计一条
事前固定的宏观传导链能否完整实现：

```text
宏观首次发布创新 → 政策路径重定价 → 实际利率重定价 → 黄金重定价
```

第 2、3 跳分别估计前缀成功条件下的概率，并在同一次 Monte Carlo 中传播结构参数、测量误差、代理相关、制度漂移、共同 frailty 和外部截断风险。

## 先用一分钟理解本项目

本项目不自动发现因果图，也不从多条路径中事后选择表现最好的一条。调用者先给出机制链和根事件，系统再
回答四个问题：每跳成立的条件概率是多少、整条链实现的概率是多少、估计有多不确定，以及现有证据是否
值得继续推理或采取交易动作。

| 容易混淆的对象 | 本项目中的准确含义 |
|---|---|
| 固定主链 | 唯一进入链级概率的三跳拓扑；历史标签始终由 H.15 2Y、H.15 5Y real、GLD 定义 |
| 多测量潜变量 | 同一个经济状态由主测量和代理共同估计；代理不能替换主标签，也不等于另一条预测路径 |
| 通胀预期与美元 | 用于检查竞争解释的结构诊断变量；当前版本不把它们作为可替代路径加入 `P_chain` |
| 链内断裂 | 指定传导在某一跳没有继续，由逐跳 outcome 识别 |
| 外部截断 `q` | 其他事件覆盖原链的独立竞争风险，与链内失败分开输出 |
| 90% CI | 对未知链实现概率的认识论可信区间，不是黄金价格区间或单次结果区间 |
| 停止 | 决策层认为继续行动缺乏足够证据或价值，不等于宣告因果边不存在或模型失效 |

因此，本项目的贡献重点是**条件链聚合、真实不确定性传播、证据溯源和可执行弃权**，而不是声称获得了
最佳点预测。更短的评审说明见 [两分钟评审导读](docs/EVALUATOR_GUIDE.md)。

## 当前审计结果

- 2011–2024 年同一固定拓扑下的有效确认事件：164 条，终点成功 22 条；
- 主模型 Brier：0.1193，满足 `<0.15`；
- 朴素边际连乘 Brier：0.1284，主模型定量优于题面 baseline；
- 逐跳实际前缀率：0.348 → 0.238 → 0.134；
- 合成隐藏真值上的 90% CI 覆盖率：0.920；
- CI 宽度—实际绝对误差：Spearman ρ=0.721，p=0.0002；
- 随机三跳复算最大 `|Δp_i|=0`。

必须同时披露：主模型略差于 climatology 和 direct terminal logistic，并存在整体低估。确认集不再用于
调参。2026-09-04 NFP 作为真实当期演示：根输入公布后生成的预测已在当日下游市场结果窗口完成前写入
Git，当前逐跳 outcome 保持未决并按追踪计划追加。

## 主测量、代理与诊断变量

| 角色 | 潜在状态 | 审计主测量 | 代理/敏感性测量 |
|---|---|---|---|
| 主链节点 | 政策路径 | Federal Reserve H.15 2Y | H.15 1Y、反向 ZT return |
| 主链节点 | 实际贴现率 | H.15 5Y real | H.15 10Y real、反向 TIP return |
| 主链节点 | 黄金 | GLD return | GC continuous future return |
| 结构诊断 | 通胀预期 | 5Y nominal−5Y real | 10Y nominal−10Y real |
| 结构诊断 | 美元 | DXY return | UUP return |

最终历史标签始终由 `H.15 2Y → H.15 5Y real → GLD` 定义；代理不能在看到结果后替换主测量。
通胀预期和美元列用于结构诊断，不构成额外的链级预测分支。

## 一键复现

推荐 Python 3.11。在仓库根目录执行：

```bash
./setup.sh
./run.sh --offline
./test.sh
```

如系统同时安装了多个 Python，可显式指定解释器，例如：

```bash
MACRO_GOLD_PYTHON=python3.11 ./setup.sh
```

`setup.sh` 默认使用固定版本的 `requirements.lock.txt`。`run --offline` 只读取仓库内冻结事件记录，
不访问网络，也不重新生成已冻结标签。

也可以使用 Docker：

```bash
docker build -t macrochain-prediction .
docker run --rm macrochain-prediction
```

## 主要输出

- `reports/SUBMISSION_REPORT.md`：总报告；
- `reports/model_run.json`：每跳 `p_i/n_i`、链概率、90% CI、内生/外部风险和逐前缀不确定性；
- `reports/edge_evidence.json`：每跳来源事件、特征、系数、协方差及随机种子；
- `reports/stop_trace.csv`：每个前缀的 CI、EVSI、停止原因、实际首停与反事实标记；
- `reports/evaluation.json`：Brier、baseline、可靠性、逐跳衰减、失败案例；
- `reports/oracle.json`：1–6 跳合成隐藏真值 CI 覆盖验证；
- `reports/s_grade_gate.json`：逐项机器检查；
- `demo/current/*.json`：真实当期演示及其时间顺序证据；
- `demo/runs/*.md`：真实当期演示的中文逐跳运行记录；
- `docs/REQUIREMENTS_TRACEABILITY.md`：交付内容与证据位置索引。

## 真实当期演示

A004 选择 2026-09-04 发布的 2026 年 8 月美国非农就业。发布前已经固定根参考类期望、尺度、模型/数据
哈希、结果窗口和交易规则；BLS 公布 `actual=162` 千人后，模型在 14:03:26 UTC 前生成了逐跳概率、
链级区间和停止判断。包含这些数值的 Git 提交早于最早下游结果窗口完成时间 20:00 UTC，因此该事件按
“方法先固定—根输入发布—预测先记录—下游结果后产生”的顺序作为当期演示。完整记录见
`demo/runs/NFP_202608_REL_20260904_A004.md`。

这里的 68.5 千人是冻结开发样本得到的参考类中位数，不是商业市场共识；因此 `root_z` 是相对该参考类的
模型创新。该演示证明输入、推理、CI、停止和交易规则能够按时间顺序运行，不以单个尚未完成的 outcome
证明模型预测成功。

该事件存放在 `demo/current/`，不是 `data/frozen/events.csv` 的第 165 条记录；在 outcome 完成前不参与
Brier、可靠性或任何重新估计，完成后也先作为单独的前瞻样本报告。

当前演示以“预测记录早于最早下游 outcome 可用时间”为时间隔离条件。机器核验命令为：

```bash
PYTHONPATH=src .venv/bin/python -m macro_gold_latent.cli verify-current-demo \
  --input demo/current/NFP_202608_REL_20260904_A004.json
```

交易阈值不接受手填：

```text
tau = (failure_loss + transaction_cost) / (success_gain + failure_loss)
    = (0.25 + 0.01) / (1.00 + 0.25)
    = 0.208
```

只有 90% CI 下沿超过 `tau` 且 CI 宽度不超过 0.30 才允许建仓。首个非 `CONTINUE` 判断是真正执行的
停止点；其后的跳仍输出供审计，但明确标成反事实。

本次在第一跳输出 `STOP_ABSTAIN`。第一跳前缀概率约 0.398，90% CI 为 `[0.185, 0.643]`，宽度
0.458 超过上限 0.30，且区间下沿低于盈亏平衡概率 0.208；一次等价复核的 EVSI 又低于 0.01 的复核
成本，因此规则要求不继续、不建仓。停止表示当前证据不足以支持稳健行动，不代表模型被单个事件判定为
无效。模型有效性仍由历史 Brier、可靠性和 CI 检验共同判断。

## 文档导航

- [方法与公式](docs/METHODOLOGY.md)
- [两分钟评审导读](docs/EVALUATOR_GUIDE.md)
- [数据来源与授权](docs/DATA_SOURCE.md)
- [失败案例和边界](docs/FAILURE_MODES.md)
- [提交状态与披露](docs/S_GRADE_STATUS.md)
- [提交范围说明](docs/SUBMISSION_SCOPE.md)
- [交付证据索引](docs/REQUIREMENTS_TRACEABILITY.md)
- [已知限制](docs/KNOWN_LIMITATIONS.md)
- [确认协议](preregistration/CONFIRMATION_PROTOCOL.md)
- [六个月追踪计划](demo/TRACKING_PLAN.md)
- [数据声明](DATA_NOTICE.md)

## 数据边界

仓库提交有限的冻结事件级记录，以及可再分发的 Philadelphia Fed、Federal Reserve 和 ALFRED
官方原始文件。Yahoo 原始长历史不再分发，只保留事件级派生量、URL、抓取时间和 SHA-256。
详见 `DATA_NOTICE.md` 与 `docs/DATA_SOURCE.md`。

## 诚实限制

日频 close-to-close 窗口会混入宏观发布后的其他新闻，弱于授权的 30 分钟期货事件窗；潜变量能处理
测量误差，却不能把同时发生的价格反应自动变成结构因果证明。标签接触边界、负结果和方法局限均在
报告中披露。
