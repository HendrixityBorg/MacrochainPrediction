# 最终内容提交的隔离复现记录

复现对象：commit `6b7c409259c715f433ec7ff86685b23bfe7be751`。

2026-09-04 14:37 UTC，从公开远端执行新的 `--depth 1` 浅克隆，在全新 Python 3.11 虚拟环境中安装
`requirements.lock.txt`，随后执行：

```bash
./run.sh --offline
./test.sh
PYTHONPATH=src .venv/bin/python -m macro_gold_latent.cli verify-current-demo \
  --input demo/current/NFP_202608_REL_20260904_A004.json
```

结果：

- 离线管线完成，内部机器检查无缺失项；
- 22 项测试全部通过；
- 当期演示验证通过；
- 浅克隆不含较早的预测 commit，验证器按设计使用分发快照及固定 SHA-256，`prediction_matches_prior_commit=true`；
- `model_run.json`、`evaluation.json`、`oracle.json`、`three_hop_reproduction.json` 和当期演示 JSON 的
  SHA-256 与原工作区逐项相同；
- `s_grade_gate.json` 包含绝对工作路径和 Git 历史可用性诊断，因此运行后会产生环境相关文本差异；它的
  通过/失败结论不变，也不属于核心数值复现哈希。

关键结果与文件哈希汇总在 `reports/SUBMISSION_MANIFEST.json`。
