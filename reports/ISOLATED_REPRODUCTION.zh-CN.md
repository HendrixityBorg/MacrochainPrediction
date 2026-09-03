# 隔离复现记录

时间：2026-09-03。

把项目复制到新的 `/tmp/macro-gold-repro-a003.V48C9l`，明确排除原工作区 `.venv` 与 `__pycache__`；
在副本中创建全新 Python venv、按 `requirements.txt` 安装，并执行：

```bash
./run.sh --offline
./test.sh
PYTHONPATH=src .venv/bin/python scripts/verify_live_precommit_timestamp.py NFP_202608_REL_20260904_A003
PYTHONPATH=src .venv/bin/python scripts/verify_protocol_timestamp.py
```

结果：16/16 tests 通过；数据质量 PASS；选定 NFP precommit 的模型/数据/来源绑定和 DigiCert RFC 3161
时间戳验证通过。`run --offline` 不访问网络，也不重建冻结标签；它成功生成逐字节相同的模型、评估和 oracle：

| artifact | original SHA-256 | isolated SHA-256 | result |
|---|---|---|---|
| `reports/evaluation.json` | `1952ccbe0730cf41a59be1c51bf49f17b835f90d9ffaef4f54a8ae53758525a5` | same | PASS |
| `reports/oracle.json` | `764bec186326e18c67d7ed5bc5d20801c23ca31cffad69e4dc9a05c892f22817` | same | PASS |
| `reports/model_run.json` | `f98ef64c2925d394171b5235740ff00e055d50a12d43efb5c939e1885ff6aa12` | same | PASS |
| `reports/prediction_ledger.csv` | `cb3f7198b3f45cf1a7ba56feb01fd77ca3e4b1fd4138fed9e830f3305f6c462c` | same | PASS |

Dockerfile 同样使用 `python:3.11-slim` 和 `run --offline`，但当前主机没有可用 Docker daemon，因此
本次实际隔离验证使用新目录+新虚拟环境完成，不虚构 Docker 运行记录。
