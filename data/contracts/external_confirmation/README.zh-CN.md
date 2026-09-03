# 新外部确认批接入契约

该目录只定义未来/第三方确认数据的接口，不声称当前已有新的确认结果。现有 NFP confirmation、CPI
v2/v3 和 FOMC 探索资产都已经被操作者打开，不能重新包装为 untouched holdout。

一个候选 bundle 必须包含：

1. `manifest.json`：绑定当前 protocol、`reports/model_run.json`、预测文件哈希和独立托管引用；
2. `predictions.csv`：至少 50 个唯一事件，每个预测时间严格早于该事件的 label unlock 时间；
3. 解锁前不得存在 `labels.csv`；解锁后标签必须与预测事件一一对应，且记录实际可得时间。

预解锁检查：

```bash
macro-gold-s audit-external-batch --bundle /path/to/bundle
```

解锁后检查：

```bash
macro-gold-s audit-external-batch --bundle /path/to/bundle --unlocked
```

失败项必须保留；不能缩短事件集、复用当前确认事件或在标签解锁后重算预测。

