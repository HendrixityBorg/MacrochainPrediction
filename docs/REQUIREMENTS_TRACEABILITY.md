# 交付内容与证据索引

本页只帮助读者定位产物。方法结论以 `reports/SUBMISSION_REPORT.zh-CN.md` 和机器可读结果为准。

| 内容 | 实现或结果 | 主要证据 |
|---|---|---|
| 完整工程 | 固定依赖、配置、运行/测试脚本、Docker 离线入口 | `README.md`、`requirements.lock.txt`、`run.sh`、`test.sh`、`Dockerfile` |
| 端到端输出 | 链概率、逐跳 `p_i/n_i`、CI、停止、不确定性和评估 | `reports/model_run.json`、`reports/stop_trace.csv`、`reports/evaluation.json` |
| 条件链模型 | `P(E1)P(E2|E1)P(E3|E1,E2)`，共同后验采样 | `docs/METHODOLOGY.zh-CN.md`、`src/macro_gold_latent/model.py` |
| 内生与外部风险 | 内生完整传导概率与外部截断 `q` 分别输出 | `reports/model_run.json`、`reports/SUBMISSION_REPORT.md` |
| 朴素比较 | 主模型 Brier 0.1193，朴素边际连乘 0.1284 | `reports/baseline_report.json`、`reports/evaluation.json` |
| 每跳来源 | 开发事件 ID、特征、系数、协方差、种子、n_raw/n_eff | `reports/edge_evidence.json`、`reports/three_hop_reproduction.json` |
| 停止规则 | CI 边界、盈亏阈值、EVSI、复核成本、首个实际停止 | `src/macro_gold_latent/stopping.py`、`reports/stop_trace.csv` |
| 历史确认 | 164 条确认链，22 条终点成功，Brier 0.1193 | `data/frozen/events.csv`、`reports/evaluation.json` |
| 可靠性 | 固定 10 桶表、Wilson 区间与可靠性图 | `reports/reliability_table.csv`、`reports/reliability.png` |
| 逐跳衰减 | 0.348 → 0.238 → 0.134 | `reports/hop_decay.csv`、`reports/hop_decay.png` |
| CI 来源 | 参数、测量、漂移、共同 frailty、外部截断 | `reports/model_run.json`、`docs/METHODOLOGY.md` |
| 合成覆盖 | 隐藏真值 test coverage 0.920 | `reports/oracle.json` |
| CI 有效性 | 宽度—绝对误差 ρ=0.721，p=0.0002 | `reports/evaluation.json` |
| 证据更新 | 中心沿证据方向移动，证据增强后区间收窄 | `reports/evidence_update.json` |
| 三跳复算 | 随机三跳最大 `|Δp_i|=0` | `reports/three_hop_reproduction.json` |
| 当期演示 | 2026-09-04 NFP，预测记录早于下游日终结果 | `demo/current/NFP_202608_REL_20260904_A004.json`、`demo/runs/NFP_202608_REL_20260904_A004.zh-CN.md` |
| 交易动作 | 第一跳 `STOP_ABSTAIN`，最终 `NO_POSITION` | 当期演示记录、`reports/stop_trace.csv` |
| 后续追踪 | 下游 outcome 追加与六个月回查 | `demo/TRACKING_PLAN.zh-CN.md` |
| 负结果 | 低估、climatology 比较、日频因果边界、标签接触边界 | `docs/KNOWN_LIMITATIONS.zh-CN.md` |

## 最短复核路径

```bash
./setup.sh
./run.sh --offline
./test.sh
PYTHONPATH=src .venv/bin/python -m macro_gold_latent.cli verify-current-demo \
  --input demo/current/NFP_202608_REL_20260904_A004.json
```

完成后先看 `reports/SUBMISSION_REPORT.zh-CN.md`，再按上表检查 JSON/CSV 原始产物。
