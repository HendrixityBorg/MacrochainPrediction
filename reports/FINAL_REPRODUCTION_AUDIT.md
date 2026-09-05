# 最终内容提交的隔离复现记录

复现对象：commit `642a8f74b003e4a5a7f2d2ab69815117eeb790ff`。

2026-09-05 07:11 UTC，从公开远端执行新的 `--depth 1` 浅克隆，在全新 Python 3.11 虚拟环境中安装
`requirements.lock.txt`，随后执行：

```bash
./run.sh --offline
./test.sh
PYTHONPATH=src .venv/bin/python -m macro_gold_latent.cli verify-current-demo \
  --input demo/current/NFP_202608_REL_20260904_A004.json
PYTHONPATH=src .venv/bin/python scripts/verify_protocol_timestamp.py
PYTHONPATH=src .venv/bin/python scripts/verify_live_precommit_timestamp.py \
  NFP_202608_REL_20260904_A004
```

结果：

- 离线管线完成，内部机器检查无缺失项；
- 16 项测试全部通过；
- 已时间戳的协议锁与唯一当期预承诺的 RFC 3161 时间戳有效；之后的文件名规范化修订可沿锁链核验；
- 当期演示验证通过，官方根值元数据、分发预测快照及预测数值匹配均有效；
- 浅克隆不含较早的预测提交对象，验证器按设计使用固定 SHA-256 的分发快照；
- 模型、评估、oracle、三跳复算、账本和当期演示文件与内容提交逐字节一致。
- 实际文件名中不存在 `zh-CN`，代码、报告和评审入口均使用规范化后的路径。

机器可读环境、命令、结果与哈希见 `reports/submission_package_audit.json`。核心结果索引见
`reports/SUBMISSION_MANIFEST.json`。
