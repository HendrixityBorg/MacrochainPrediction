from __future__ import annotations

from pathlib import Path
import math
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .config import ROOT
from .demo import live_demo_status
from .io import read_json


def selected_live_demo_payload() -> dict[str, Any] | None:
    """Load the eligible current-event record selected by the machine gate."""
    status = live_demo_status()
    eligible = [
        item for item in status["records"]
        if item.get("valid") and item.get("eligible_for_submission")
    ]
    if not eligible:
        return None
    selected = sorted(eligible, key=lambda item: item["event_id"])[-1]
    return read_json(Path(selected["path"]))


def latest_live_failure() -> dict[str, Any] | None:
    directory = ROOT / "demo" / "failures"
    files = sorted(directory.glob("*.json")) if directory.exists() else []
    return read_json(files[-1]) if files else None


def chinese_live_demo_report(payload: dict[str, Any], model_run: dict[str, Any]) -> str:
    """Render the complete current macro-chain record in Chinese."""
    record = payload["input"]
    prediction = payload["prediction"]
    root_z = (
        (float(record["root_actual"]) - float(record["root_consensus_or_nowcast"]))
        / float(record["root_scale"])
    )
    source = record["root_actual_source"]
    feature = [1.0, math.log1p(abs(root_z)), 1.0 if root_z > 0 else -1.0]
    stop = prediction["execution_stop"]
    decision_text = {
        "STOP_ACCEPT": "允许按预承诺仓位上限建仓",
        "STOP_REJECT": "拒绝建仓",
        "STOP_ABSTAIN": "信息不足，放弃建仓",
    }.get(stop["state"], stop["state"])
    hop_names = {
        1: "宏观意外 → 政策路径重定价",
        2: "政策路径 → 实际利率重定价",
        3: "实际利率 → 黄金重定价",
    }
    lines = [
        f"# {record['event_id']} 真实当期宏观链运行记录", "",
        f"> 状态：`{payload['status']}`；预测记录时间：`{payload.get('prediction_recorded_at_utc', payload.get('sealed_at_utc'))}`；交易结论：**{decision_text}**。", "",
        "## 1. 输入与来源", "",
        f"- 宏观事件：2026 年 8 月美国非农就业首次发布；指标为 `{record['root_measure']}`。",
        f"- BLS 官方 actual：**{float(record['root_actual']):.1f} 千人**；参考类期望：{float(record['root_consensus_or_nowcast']):.1f} 千人。",
        f"- 事前尺度：{float(record['root_scale']):.6f} 千人；因此 `root_z={root_z:.6f}`。",
        f"- 根特征 `[1, log(1+|z|), sign(z)]`：`[{feature[0]:.6f}, {feature[1]:.6f}, {feature[2]:.0f}]`。",
        f"- 官方来源：{source.get('summary_url', source.get('url'))}；抓取时间：`{source['retrieved_at_utc']}`。",
        f"- 交叉核对：{source.get('cross_check', '见来源记录')}；证据记录 SHA-256：`{source.get('record_sha256_at_commit', source.get('sha256', '未提供'))}`。", "",
        "## 2. 每跳概率、证据量与来源", "",
        "每跳使用冻结开发集上的条件潜变量 fractional-logistic 后验；第 2/3 跳分别以此前前缀成功为风险集。",
        "所有系数、协方差、事件 ID 和随机种子均来自发布前绑定的 `reports/model_run.json`。", "",
        "| 跳 | 机制 | p_i | n_i | n_raw | 估计方法 |",
        "|---:|---|---:|---:|---:|---|",
    ]
    for fit, probability, effective_n in zip(model_run["link_fits"], prediction["p_i"], prediction["n_i"]):
        lines.append(
            f"| {fit['hop']} | {hop_names[fit['hop']]} | {probability:.6f} | {effective_n:.3f} | "
            f"{fit['n_raw']} | `{fit['method']}` |"
        )
    lines += [
        "", "## 3. 链级结果", "",
        f"- 内生完整传导概率：{prediction['intrinsic_probability']:.6f}；",
        f"- 外部截断概率：{prediction['interruption_probability']:.6f}；",
        f"- 实现概率 `E[(1-q)p1p2p3]`：**{prediction['chain_probability']:.6f}**；",
        f"- 90% CI：**[{prediction['ci_lower']:.6f}, {prediction['ci_upper']:.6f}]**，宽度 {prediction['ci_width']:.6f}。", "",
        "## 4. 每跳停止判断与认识论不确定性", "",
        "`execution_reached=false` 的后续跳仅用于完整审计，是首个停止动作之后的反事实诊断，不属于实际继续执行。", "",
        "| 跳 | 前缀概率 | 90% CI | 状态 | 原因 | 实际到达 | 参数/测量/漂移/相关/截断方差比 |",
        "|---:|---:|---|---|---|---|---|",
    ]
    for item in prediction["stop_trace"]:
        uncertainty = item["uncertainty_decomposition"]
        shares = "/".join(
            f"{uncertainty[key]:.3f}" for key in (
                "link_parameter_variance_share", "measurement_variance_share",
                "regime_drift_variance_share", "common_frailty_variance_share",
                "external_cutoff_variance_share",
            )
        )
        lines.append(
            f"| {item['hop']} | {item['probability']:.6f} | [{item['ci_lower']:.6f}, {item['ci_upper']:.6f}] | "
            f"`{item['state']}` | `{item['reason']}` | {str(item['execution_reached']).lower()} | {shares} |"
        )
    lines += [
        "", "方差比采用逐来源单独开启的 Monte Carlo 比值；来源存在交互，因此不要求机械相加为 1。", "",
        "### 第一跳为什么停止", "",
        f"第一跳前缀概率为 {stop['probability']:.6f}，但 90% CI 为 "
        f"[{stop['ci_lower']:.6f}, {stop['ci_upper']:.6f}]，宽度 {stop['ci_width']:.6f}，超过预设上限 "
        f"{float(record['decision_rule']['maximum_ci_width']):.2f}。区间下沿也低于盈亏平衡概率 "
        f"{float(record['decision_rule']['break_even_probability']):.3f}，保守效用为负，因此不能把中心值较高直接解释成可执行交易。",
        f"预设的一次复核 EVSI 为 {prediction['stop_trace'][0]['evsi']:.8g}，低于复核成本 "
        f"{prediction['stop_trace'][0]['review_cost']:.3f}；按照冻结规则，继续复核不足以补偿成本，故输出 `STOP_ABSTAIN`。", "",
        "这个停止是决策层面对不确定性的响应，不是对因果链或模型有效性的单样本否定。模型仍然输出全部三跳，"
        "便于复算和事后核验；只是第 2、3 跳被标成停止后的反事实诊断，不能当作实际继续执行。模型是否有效由"
        "历史批次的 Brier、可靠性、CI 覆盖和误差相关性共同评估，单个当期事件既不能证明模型有效，也不能证明其无效。", "",
        "## 5. 交易决策", "",
        f"- 预承诺盈亏平衡概率：{float(record['decision_rule']['break_even_probability']):.6f}；",
        f"- 最大允许 CI 宽度：{float(record['decision_rule']['maximum_ci_width']):.2f}；",
        f"- 首个实际停止点：第 {stop['hop']} 跳，`{stop['state']}` / `{stop['reason']}`；",
        f"- 最终动作：**{decision_text}**；不允许主观覆盖。", "",
        "## 6. 审计绑定与后续追踪", "",
        f"- 协议 SHA-256：`{payload['protocol_sha256']}`；",
        f"- precommit SHA-256：`{payload['precommit_sha256']}`；",
        f"- 当期记录 SHA-256：`{payload.get('current_demo_sha256', payload.get('seal_sha256'))}`；",
        f"- 预测证据提交：`{payload.get('prediction_evidence', {}).get('git_commit', 'legacy-seal')}`；",
        f"- 最早下游结果窗口完成时间：`{payload.get('downstream_outcome_available_after_utc', '见旧版记录')}`。", "",
        "该预测记录形成时，发布日收盘、H.15 数据及逐跳 outcome 尚未完成；它们不在本记录中伪装为已验证。",
        "后续按 `demo/TRACKING_PLAN.zh-CN.md` 追加不可覆盖的 outcome 与六个月覆盖率回查。", "",
    ]
    return "\n".join(lines)


def write_live_demo_report(payload: dict[str, Any], model_run: dict[str, Any]) -> Path:
    directory = ROOT / "demo" / "runs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{payload['input']['event_id']}.zh-CN.md"
    path.write_text(chinese_live_demo_report(payload, model_run), encoding="utf-8")
    return path


def reliability_rows(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    """Add 90% Wilson binomial intervals without changing predictions or bins."""
    z = 1.6448536269514722
    output: list[dict[str, Any]] = []
    for original in evaluation["reliability"]["bins"]:
        row = dict(original)
        n = int(row["n"])
        observed = float(row["observed_rate"])
        denominator = 1.0 + z * z / n
        center = (observed + z * z / (2.0 * n)) / denominator
        radius = z * ((observed * (1.0 - observed) / n + z * z / (4.0 * n * n)) ** 0.5) / denominator
        row["wilson90_lower"] = max(0.0, center - radius)
        row["wilson90_upper"] = min(1.0, center + radius)
        output.append(row)
    return output


def plots(evaluation: dict[str, Any]) -> None:
    report_dir = ROOT / "reports"
    reliability = reliability_rows(evaluation)
    fig, axis = plt.subplots(figsize=(5.5, 4.5))
    axis.plot([0, 1], [0, 1], linestyle="--", color="grey", label="perfect")
    means = [row["mean_probability"] for row in reliability]
    observed = [row["observed_rate"] for row in reliability]
    axis.errorbar(
        means, observed,
        yerr=[
            [row["observed_rate"] - row["wilson90_lower"] for row in reliability],
            [row["wilson90_upper"] - row["observed_rate"] for row in reliability],
        ],
        marker="o", capsize=3, label="latent chain (90% Wilson)",
    )
    axis.set(xlabel="Mean predicted probability", ylabel="Observed success rate", xlim=(0, 1), ylim=(0, 1), title="Confirmation reliability")
    axis.legend()
    fig.tight_layout()
    fig.savefig(report_dir / "reliability.png", dpi=160)
    plt.close(fig)

    hops = evaluation["hop_decay"]
    fig, axis = plt.subplots(figsize=(5.5, 4.5))
    axis.plot([row["hop"] for row in hops], [row["prefix_rate"] for row in hops], marker="o")
    axis.set(xlabel="Prefix length", ylabel="Observed prefix success rate", xticks=[1, 2, 3], ylim=(0, 1), title="Success decay by hop")
    fig.tight_layout()
    fig.savefig(report_dir / "hop_decay.png", dpi=160)
    plt.close(fig)


def chinese_report(
    model_run: dict[str, Any], evaluation: dict[str, Any], oracle: dict[str, Any],
    reproduction: dict[str, Any], evidence_update: dict[str, Any], gate: dict[str, Any] | None,
    live_payload: dict[str, Any] | None = None,
) -> str:
    brier = evaluation["brier"]
    failed = gate["failed_required_gates"] if gate else ["gate_pending"]
    state = gate["status"] if gate else "GATE_PENDING"
    hop = evaluation["hop_decay"]
    structural = model_run["structural_diagnostics"]
    real_coefficients = structural["real_rate_given_policy_and_inflation"]["coefficients"]
    gold_coefficients = structural["gold_given_real_rate_and_dollar"]["coefficients"]
    failures = evaluation["failure_cases"][:3]
    live_failure = latest_live_failure()
    check_text = "通过" if not failed else f"仍缺少：{', '.join(failed)}"
    lines = [
        "# SX-CH-001 黄金潜变量链提交报告", "",
        f"> 仓库内部证据检查：**{check_text}**。机器标识 `{state}` 仅表示清单产物状态，不替代评审。", "",
        "## 摘要", "",
        "本项目实现多测量潜变量模型，但最终审计标签始终由 H.15 2 年期、H.15 5 年期实际利率和 GLD 主测量定义。",
        "预测模型用 2005–2010 非农事件开发，2011–2024 确认批的任何结果均不回流训练。2026-09-04 NFP 被选为同域真实当期演示。", "",
        "原始协议锁早于确认标签；首次运行后只修复了“零响应被误当缺失”的机械错误，原锁和原输出均已归档。",
        "修订版不是无条件的 pristine holdout；该限制持续披露，但题面未规定提交前第三方签署格式。", "",
        "2026-09-04 NFP 的参考类期望、根尺度、模型/数据哈希、结果窗口和决策规则已在发布前固定并取得第三方时间戳；",
    ]
    if live_payload:
        prediction = live_payload["prediction"]
        lines += [
            f"官方 actual 输入模型后，预测在下游结果窗口完成前写入 Git；链概率={prediction['chain_probability']:.4f}，"
            f"90% CI=[{prediction['ci_lower']:.4f}, {prediction['ci_upper']:.4f}]。完整记录见 "
            f"`demo/runs/{live_payload['input']['event_id']}.zh-CN.md`。", "",
        ]
    else:
        if live_failure and live_failure.get("status") == "MISSED_SEAL_WINDOW_FAIL_CLOSED":
            lines += [
                "A004 没有通过项目早期自设的短时 seal；该失败记录继续保留。当前还未找到可核验的"
                "预测早于下游结果记录，因此当期演示证据为空。",
                "历史执行证据见 `demo/failures/NFP_202608_REL_20260904_A004.zh-CN.md`。", "",
            ]
        else:
            lines += ["precommit 本身不等于完成演示；还需证明根输入后的模型预测早于下游 outcome。", ""]
    lines += [
        "## 图与公式", "",
        "```text", "macro surprise S → policy path M → real rate R → gold G",
        "                         ↘ inflation Π ↗      ↑",
        "                                  USD D / external Q", "```", "",
        "测量方程：`y[j,t] = alpha[j] + lambda[j] X[t] + epsilon[j,t]`；主测量 `alpha=0, lambda=1`。",
        "在 Gaussian 先验 `X~N(0,V0)` 下，潜状态后验方差为 `V=(V0^-1+lambda'Ω^-1lambda)^-1`，",
        "后验均值为 `m=V lambda'Ω^-1(y-alpha)`；代理残差协方差 Ω 不被对角化，因此相关读数不会重复计数。",
        "每跳用 `logit(p_i)=x'beta_i`、Gaussian beta 先验和 fractional-Bernoulli likelihood；Laplace 近似给出",
        "系数后验。第 2/3 跳的风险集分别限定为此前 1/2 跳已经成功的开发事件。",
        "结构概率：`P_chain = E[(1-q) p1 p2 p3 | development evidence]`。这里的 `p2` 与 `p3` 是前缀成功条件概率，",
        "不是把三个无条件边际频率相乘。每次后验抽样共同抽取 beta、测量误差、制度漂移、跨跳 frailty 与 q，",
        "再对 `(1-q)Πp_i` 取 5%/95% 分位数形成 90% CI。外部截断 `q` 与链路自身断裂分别输出。", "",
        "## 参数估计与有效证据", "",
    ]
    for fit in model_run["link_fits"]:
        lines.append(f"- 第 {fit['hop']} 跳：方法 `{fit['method']}`，n_raw={fit['n_raw']}，n_eff={fit['n_eff']:.2f}，软成功量={fit['soft_success_sum']:.2f}。")
    lines += [
        "", "每个预测的 `p_i`、`n_i`、证据事件 ID、特征、系数、协方差与随机种子保存在 `edge_evidence.json`。",
        "少于 5 个条件实例时，代码强制退回同跳宏观参考类。本路线三跳条件 n_raw=69/23/16，均未触发 `<5` 稀有事件 fallback，",
        "所以题面的稀有估计法 ≥20 校准附加条款不适用；原始数量与校准误差仍完整报告，不把 16 伪写成 20。", "",
        "## 多路径与干扰项", "",
        f"开发集潜变量回归得到 `R ~ M + Π` 的系数 M={real_coefficients[1]:.3f}、Π={real_coefficients[2]:.3f}，R²={structural['real_rate_given_policy_and_inflation']['r_squared']:.3f}；",
        f"`G ~ R + D` 的系数 R={gold_coefficients[1]:.3f}、D={gold_coefficients[2]:.3f}，R²={structural['gold_given_real_rate_and_dollar']['r_squared']:.3f}。",
        "通胀预期与美元因此成为显式并行/竞争路径；剩余 gold residual 定义为安全港或遗漏冲击。它们参与不确定性解释，但不会事后改写主标签。", "",
        "外部截断使用锁定的 Beta(1,19) 弱正则先验，并与开发集显式截断标签更新；当前 69 个开发事件为 0 次，后验 Beta(1,88)，",
        "均值约 1.12%。固定内生概率时，q=0%/1.12%/5%/10% 分别把中心乘以 1.000/0.9888/0.950/0.900；它不计入任何 p_i 的 n_i。", "",
        "## 确认评估", "",
        f"- 有效确认链：{evaluation['confirmation_events']}；终点成功：{evaluation['terminal_successes']}；实际率：{evaluation['terminal_rate']:.3f}；",
        f"- 潜变量条件模型 Brier：{brier['latent_conditional_dynamic']:.4f}；朴素边际连乘：{brier['naive_marginal_product']:.4f}；条件 Beta：{brier['conditional_beta_chain']:.4f}；",
        f"- climatology Brier：{brier['climatology']:.4f}；direct terminal logistic：{brier.get('direct_terminal_logistic', float('nan')):.4f}；无根信号消融：{brier['no_root_ablation']:.4f}；主测量-only：{brier['primary_only']:.4f}；",
        f"- 逐跳前缀率：{hop[0]['prefix_rate']:.3f} → {hop[1]['prefix_rate']:.3f} → {hop[2]['prefix_rate']:.3f}；",
        f"- CI 宽度—绝对误差 Spearman rho={evaluation['ci_width_error']['spearman_rho']:.3f}，p={evaluation['ci_width_error']['permutation_p_value_two_sided']:.4f}。", "",
        "主模型满足题面 Brier 和相对朴素连乘门槛，但略差于 climatology、primary-only 和 direct terminal logistic。后者缺少逐跳解释，不能替代链模型；",
        "多测量层用于显式表达测量不确定性，但没有在该确认批证明点预测增益，因此 climatology skill 诊断保持失败（不是题面硬门）。按年份区块 bootstrap，",
        "主模型相对 climatology 的 Brier 差 90% CI 跨 0；相对朴素连乘的差为 [-0.01422, -0.00414]。事后候选和开发集滚动选择审计见 `model_skill_audit.json`。", "",
        f"可靠性图保留冻结的 10 个分桶，并为每个实际率增加 90% Wilson 二项区间；ECE={evaluation['reliability']['expected_calibration_error']:.4f}。"
        "第 5、7–10 桶呈现较明显低估，区间只表达每桶有限样本噪声，不替代 ECE 或 Brier，也不把该偏差描述成已经解决。", "",
        "![可靠性图](reliability.png)", "", "![逐跳衰减](hop_decay.png)", "",
        "## 认识论置信区间", "",
        "90% CI 由参数后验、潜变量测量误差、代理残差相关、制度漂移和外部截断概率共同传播；没有对跳点乱序，",
        "也没有把不同聚合器的分歧当 CI。合成 oracle 在校准分区选择区间尺度后冻结，在隐藏 test truth 上评估。", "",
        f"- oracle test coverage：{oracle['test_coverage']:.3f}；目标 ≥0.85；",
        f"- oracle CI 宽度—真概率误差 rho={oracle['ci_width_error_spearman_rho']:.3f}，p={oracle['ci_width_error_p_value']:.4f}；",
        f"- 证据增强方向：中心上移={evidence_update['center_moves_up']}，区间收窄={evidence_update['ci_narrows']}。", "",
        "## 停止与交易决策", "",
        "每个前缀均计算 90% CI、break-even probability、一次复核 EVSI 与复核成本。终点 CI 下沿高于盈亏平衡概率才建仓；",
        "上沿低于阈值则拒绝；跨阈值则弃权。CI 宽且下一次复核 EVSI 不覆盖成本时提前停止。最大跳数仅是保护栏。",
        "首个非 CONTINUE 判断是实际执行的停止点，后续前缀只保留为反事实审计，不再冒充已执行推理。",
        "建议仓位规则：`CI lower > break-even` 才开仓；`CI width > 0.30` 不开仓；否则仓位上限按 `(lower-threshold)/(1-threshold)` 缩放。", "",
        "## 可复现性与失败案例", "",
        f"随机三跳复算最大 |delta p_i|={reproduction['maximum_absolute_delta']:.8f}。失败案例逐条保存在 `evaluation.json`，",
        "包括预测、结果、CI 宽度和断裂跳。任何确认指标失败都保留为冻结负结果。", "",
        "最大误差的三个事件：", "",
    ]
    for item in failures:
        lines.append(
            f"- `{item['event_id']}`：预测={item['probability']:.3f}，结果={item['outcome']}，"
            f"绝对误差={item['absolute_error']:.3f}，CI 宽度={item['ci_width']:.3f}，逐跳={item['hop_outcomes']}。"
        )
    lines += [""]
    if live_payload:
        live_prediction = live_payload["prediction"]
        live_stop = live_prediction["execution_stop"]
        lines += [
            "## 真实当期宏观链演示", "",
            f"- 事件：`{live_payload['input']['event_id']}`；官方 actual={float(live_payload['input']['root_actual']):.1f} 千人；",
            f"- 每跳 p_i={[round(value, 6) for value in live_prediction['p_i']]}；n_i={[round(value, 3) for value in live_prediction['n_i']]}；",
            f"- 链概率={live_prediction['chain_probability']:.6f}；90% CI=[{live_prediction['ci_lower']:.6f}, {live_prediction['ci_upper']:.6f}]；",
            f"- 内生概率={live_prediction['intrinsic_probability']:.6f}；外部截断={live_prediction['interruption_probability']:.6f}；",
            f"- 实际停止：第 {live_stop['hop']} 跳 `{live_stop['state']}` / `{live_stop['reason']}`；",
            f"- 当期记录 SHA-256：`{live_payload.get('current_demo_sha256', live_payload.get('seal_sha256'))}`；",
            f"- 预测记录时间 `{live_payload.get('prediction_recorded_at_utc', live_payload.get('sealed_at_utc'))}`，"
            f"早于最早下游结果窗口完成时间 `{live_payload.get('downstream_outcome_available_after_utc', '见旧版记录')}`。", "",
            "第一跳停止来自宽 CI 与低复核 EVSI 的组合：区间下沿不足以支持保守决策，继续一次等价复核又不足以覆盖成本。"
            "这是一次可执行的弃权，不等于模型失效；后两跳仍输出但明确标为反事实。", "",
        ]
    elif live_failure and live_failure.get("status") == "MISSED_SEAL_WINDOW_FAIL_CLOSED":
        diagnostic = live_failure["post_window_diagnostic_not_a_seal"]
        lines += [
            "## 历史短时流程记录", "",
            "- A004 错过项目自设的短时 seal，程序拒绝写入旧版 sealed record；",
            f"- BLS 截止后核对 actual={live_failure['official_actual_observed_after_deadline']['value_thousands']:.1f} 千人；",
            f"- 仅供复盘的链概率={diagnostic['chain_probability']:.6f}；90% CI=[{diagnostic['ci90'][0]:.6f}, {diagnostic['ci90'][1]:.6f}]；",
            "- 若不存在预测早于下游结果的独立时间证据，上述诊断本身不能构成当期演示。", "",
        ]
    lines += [
        "## 局限性与盲点", "",
        "1. 日频 close-to-close 窗口会混入发布后其他新闻，因果识别弱于 30 分钟期货窗口；",
        "2. Yahoo 代理原始历史不可随仓库再分发，只提交事件级派生量和源哈希；",
        "3. 现有本地原始价格历史意味着确认批弱于真正第三方托管 holdout；本项目完整披露，但不设置题面之外的签名硬门；",
        ("4. NFP 预测已在下游结果窗口完成前记录；收盘与 T+2 outcome 仍只能按追踪计划追加，不得写成预测时已验证；"
         if live_payload else
         "4. 仅有根输入后的诊断不足以建立当期演示，必须另有预测早于下游结果的时间证据；"),
        "5. 黄金同时受美元、安全港、流动性和央行需求影响；这些属于显式干扰项，而不是事后解释链路成功；",
        "6. direct terminal logistic 的 Brier 更好，意味着当前复杂链的价值主要在可审计分解/CI，而非最佳点预测。", "",
        "## 扩展方向", "",
        "采购授权的 30 分钟 ZT/SOFR/TIPS/GC 数据复做同协议；前瞻积累同域 NFP 演示；增加安全港新闻的事前可用测量；",
        "在不接触确认标签的下一版本中比较粒子滤波/完整状态空间 Bayes，而不是扩大当前模型后再重测同一确认集。", "",
        "新外部确认批由 `data/contracts/external_confirmation/` 的 fail-closed 接入器约束：至少 50 个新事件、预测早于逐事件标签解锁，",
        "解锁前出现标签文件或与当前确认事件重叠均直接拒绝。", "",
    ]
    return "\n".join(lines)
