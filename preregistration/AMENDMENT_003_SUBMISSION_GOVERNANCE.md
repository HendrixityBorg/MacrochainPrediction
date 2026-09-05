# Amendment 003：提交治理门与诊断项分离

记录时间：2026-09-03，早于 2026-09-04 12:30 UTC 的 August 2026 Employment Situation 发布。

## 修改

1. 删除 `independent_custody_attestation` 与 `post_label_amendment_accepted` 两个特定签署文件硬门。
   题面要求预测由模型产生、结果独立产生且顺序不可颠倒，但没有规定提交前必须取得特定格式的第三方签名。
2. `positive_skill_vs_climatology` 保留在评估报告中，但不再列入题面 S 档机器必需项。题面要求
   Brier `<0.15`、可靠性展示及与朴素连乘定量比较，并未规定必须击败 climatology。
3. 预测—结果时间顺序仍由协议锁、源时间、RFC 3161、不可覆盖 precommit、官方发布源和 seal 截止时间验证。

## 不变内容

本修订不改变历史数据、任何标签、模型参数、主测量、代理、阈值、baseline、CI、停止规则、交易规则、
确认成绩或真实当期事件。Brier 略差于 climatology、整体低估、原始数据可访问以及 Amendment 001
发生在标签打开后等事实必须继续披露。

## 为什么不是删除审计历史

旧协议锁、Amendment 001/002、旧报告和所有 precommit 继续保留。删除的是提交前签署文件这一特定机制，
不是删除主办方审查权，也不是把修订版宣称为未经接触的 pristine holdout。主办方仍可依据题面要求补充
解释或判定证据不足，但无需为了运行代码而填写参赛者自定义的签署模板。
