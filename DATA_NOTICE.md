# 数据与再分发声明

`data/frozen/events.csv` 是为 SX-CH-001 离线复现保留的有限事件级派生记录，不是原始数据供应商
历史库的替代品。冻结清单记录来源 URL、抓取时间、文件哈希、变换规则、缺失情况和协议哈希。

仓库包含以下可审计的官方原始输入，以保证 NFP 根变量与主要 H.15 标签能够在干净克隆中复核：

- Philadelphia Fed EMPLOY first-release 工作簿；
- Federal Reserve H.15 nominal/real 日频文件；
- ALFRED/BLS Employment Situation 发布日期文件。

Yahoo 提供的 GLD、GC、ZT、TIP、DXY、UUP 原始长历史不随仓库再分发。仓库只提交有限事件级派生量、
来源 URL 和抓取时文件的 SHA-256。`run.sh --offline` 使用冻结事件记录，不要求联网或重新下载 Yahoo 数据。

公开可访问不自动等于具有再分发权。提交或商业使用前，维护者仍应复核届时适用的服务条款。Federal
Reserve、BLS、Philadelphia Fed、FRED/ALFRED 与 Yahoo 均不认可或背书本项目及其结论。

若主办方要求从全部原始价格历史重新构建，应由参赛者或主办方在其有权使用的数据环境中运行
`./run.sh --build-data`，并与冻结事件文件做不可覆盖的逐值比较；不得以未授权原始文件替代这一流程。
