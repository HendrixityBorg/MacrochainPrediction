# 隔离复现记录

完成时间：2026-09-03T07:04:14Z。

本记录不是复制原工作目录，而是从公开远程仓库
`https://github.com/HendrixityBorg/MacrochainPrediction.git` 新克隆 commit
`07a10a4bac9c1899683dac79076e160147716ea2` 到临时目录。克隆中不含原工作区 `.venv`、`__pycache__`
或未再分发的 Yahoo 原始长历史；仓库内四个可再分发官方原始输入均存在。

实际执行环境为 Darwin 25.5.0 arm64、Python 3.11.9。执行命令：

```bash
MACRO_GOLD_PYTHON=python3.11 ./setup.sh
./run.sh --offline
./test.sh
.venv/bin/python scripts/verify_protocol_timestamp.py
.venv/bin/python scripts/verify_live_precommit_timestamp.py \
  NFP_202608_REL_20260904_A004
```

结果：18/18 tests 通过；离线管线运行成功；协议锁与选定 A004 预承诺的 DigiCert RFC 3161 时间戳均
验证有效。核心产物与提交工作树逐字节一致：

| 产物 | SHA-256 | 结果 |
|---|---|---|
| `reports/model_run.json` | `e351f4fa42b74e988e25df606b149e92f45548c5811b48cebef86507f3852e1f` | PASS |
| `reports/evaluation.json` | `1952ccbe0730cf41a59be1c51bf49f17b835f90d9ffaef4f54a8ae53758525a5` | PASS |
| `reports/oracle.json` | `764bec186326e18c67d7ed5bc5d20801c23ca31cffad69e4dc9a05c892f22817` | PASS |
| `reports/reproduction.json` | `5a67c4eb5b4ff10817fc1138042fc48be36375699d47810e792ad8776bab6aee` | PASS |
| `reports/prediction_ledger.csv` | `48d5ff1edd4371301bf5a0c33dcab9a0b16862c831bcd19fbd911e52027f49d8` | PASS |
| `reports/stop_trace.csv` | `a099f9404e1136d857d27407092d7d3098b7cdd18b7c6e5dc36d167b195aacc2` | PASS |

`run --offline` 后只有 `reports/s_grade_gate.json` 因当时尚未包含本审计文件而发生预期变化。加入本审计后，
隔离复现硬门可通过；尚未通过的唯一题面硬门仍是 2026-09-04 发布后的真实当期演示 seal。

Dockerfile 同样使用 `python:3.11-slim` 与固定依赖，但当前主机没有可用 Docker daemon，因此不虚构
Docker 运行记录。机器可读证据见 `reports/submission_package_audit.json`。
