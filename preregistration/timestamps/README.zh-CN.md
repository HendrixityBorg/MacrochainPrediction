# RFC 3161 外部时间戳

`PROTOCOL_LOCK.tsr` 是 DigiCert 对 Amendment 001 协议锁 SHA-256 imprint 签发的 RFC 3161 响应，
时间为 2026-09-03 04:00:33 UTC。运行：

```bash
PYTHONPATH=src python scripts/verify_protocol_timestamp.py
```

它证明当前修订锁最迟在签发时已存在，但签发晚于确认标签首次生成，不能倒推出修订前独立性，也不
替代主办方对机械 bugfix 的接受。原始、真正早于标签的本地锁另存为
`preregistration/PROTOCOL_LOCK.v1.0.0.json`，但原始版本含零响应缺失 bug。

