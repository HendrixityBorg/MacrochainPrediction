# 数据来源、授权与派生规则

| 数据 | 用途 | 原始来源 | 仓库策略 |
|---|---|---|---|
| EMPLOY RTDSM first release | NFP 首次发布根值 | Philadelphia Fed | 原表本地缓存；事件派生值可审计 |
| Employment Situation dates | 精确发布日期 | ALFRED/FRED `rid=50`，源为 BLS | 保存文本、URL、哈希；映射规则固定 |
| H.15 nominal/real | 1Y/2Y/5Y/10Y 名义与实际收益率 | Federal Reserve Board | 官方日频；保存源哈希和事件变化 |
| GLD/TIP/UUP | 黄金/实际利率/美元 ETF | Yahoo chart endpoint | 原始历史不随提交再分发；只提交事件量 |
| ZT/GC continuous | 政策与黄金期货代理 | Yahoo chart endpoint | 仅敏感性；披露连续合约换月风险 |
| DXY | 美元代理 | Yahoo chart endpoint | 仅干扰路径；不定义主 outcome |

主要入口：

- https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/employ
- https://alfred.stlouisfed.org/release/downloaddates?ff=txt&rid=50
- https://www.federalreserve.gov/releases/h15/
- https://query2.finance.yahoo.com/v8/finance/chart/{symbol}

## 映射与可用性

根参考月 `YYYY:MM` 的发布日期，是该月月末后 25 天内的第一条 ALFRED Employment Situation
发布日期。开发前验证将该规则与 Philadelphia Fed 1966–2010 表交叉；2005–2010 可比的 71 个
事件全部一致。2025 年政府停摆造成的延迟/合并不在确认范围内，确认固定截止 2024-12。

市场响应固定为上一个有效市场收盘到发布日收盘。波动尺度使用严格早于发布日的 60 个有效变化，
至少 40 个。收益率用百分点差；ETF/期货/美元指数用 `100*log(P_t/P_t-1)`。ZT 和 TIP 乘以 -1，
统一成“收益率/紧缩上行”为正方向。

## 防泄漏

`data/frozen/manifest.json` 记录协议哈希、标签首次生成时间、数据文件哈希、每个原始源哈希。目标文件
一旦存在，构建器只允许逐字一致的复算，不允许覆写。确认批所有预测使用同一开发模型；同批早期
outcome 不进入后期预测。

## 权利边界

公开可访问不自动等于可再分发。项目不提交 Yahoo 原始长历史，只提交有限事件级变换、来源 URL 与
哈希；参赛前应由维护者复核当时条款。Federal Reserve 与 BLS/Philadelphia Fed 的引用不表示机构
认可本分析。若主办方要求完全离线原始源复算，应使用获得授权的数据包或由主办方在审查环境运行
采集器。

