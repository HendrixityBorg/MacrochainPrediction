from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

import numpy as np


@dataclass(frozen=True)
class StopDecision:
    hop: int
    state: str
    reason: str
    probability: float
    ci_lower: float
    ci_upper: float
    ci_width: float
    break_even_probability: float
    expected_utility: float
    conservative_utility: float
    evsi: float
    review_cost: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _beta_moments(samples: np.ndarray) -> tuple[float, float]:
    mean = float(np.mean(samples))
    variance = float(np.var(samples, ddof=1)) if len(samples) > 1 else 1e-8
    maximum = max(mean * (1.0 - mean), 1e-10)
    variance = min(max(variance, 1e-10), maximum * 0.999)
    concentration = max(mean * (1.0 - mean) / variance - 1.0, 0.01)
    return max(mean * concentration, 1e-6), max((1.0 - mean) * concentration, 1e-6)


def one_review_evsi(samples: np.ndarray, settings: dict[str, Any]) -> float:
    alpha, beta = _beta_moments(np.clip(samples, 1e-8, 1.0 - 1e-8))
    gain = float(settings["success_gain"])
    loss = float(settings["failure_loss"])
    transaction = float(settings["transaction_cost"])
    evidence = max(1, int(settings["review_equivalent_evidence"]))

    def utility(probability: float) -> float:
        return probability * gain - (1.0 - probability) * loss - transaction

    current = max(0.0, utility(alpha / (alpha + beta)))
    after = 0.0
    for successes in range(evidence + 1):
        log_weight = (
            math.lgamma(evidence + 1) - math.lgamma(successes + 1) - math.lgamma(evidence - successes + 1)
            + math.lgamma(alpha + successes) + math.lgamma(beta + evidence - successes)
            - math.lgamma(alpha + beta + evidence) - math.lgamma(alpha) - math.lgamma(beta)
            + math.lgamma(alpha + beta)
        )
        posterior = (alpha + successes) / (alpha + beta + evidence)
        after += math.exp(log_weight) * max(0.0, utility(posterior))
    return max(0.0, after - current)


def break_even_probability(config: dict[str, Any]) -> float:
    """Return the unique decision threshold implied by the locked payoff inputs."""
    settings = config["stopping"]
    gain = float(settings["success_gain"])
    loss = float(settings["failure_loss"])
    transaction = float(settings["transaction_cost"])
    return (loss + transaction) / (gain + loss)


def decide(samples: np.ndarray, *, hop: int, terminal_hop: int, config: dict[str, Any]) -> StopDecision:
    settings = config["stopping"]
    level = float(config["project"]["interval_level"])
    alpha = (1.0 - level) / 2.0
    mean = float(np.mean(samples))
    lower, upper = (float(value) for value in np.quantile(samples, [alpha, 1.0 - alpha]))
    gain = float(settings["success_gain"])
    loss = float(settings["failure_loss"])
    transaction = float(settings["transaction_cost"])
    threshold = break_even_probability(config)

    def utility(probability: float) -> float:
        return probability * gain - (1.0 - probability) * loss - transaction

    evsi = one_review_evsi(samples, settings)
    review_cost = float(settings["review_cost"])
    width = upper - lower
    if upper < threshold:
        state, reason = "STOP_REJECT", "ci_upper_below_break_even"
    elif hop >= terminal_hop and lower > threshold:
        state, reason = "STOP_ACCEPT", "terminal_ci_lower_above_break_even"
    elif hop >= terminal_hop:
        state, reason = "STOP_ABSTAIN", "terminal_ci_straddles_break_even"
    elif hop >= int(settings["maximum_hops"]):
        state, reason = "STOP_ABSTAIN", "maximum_hops_guardrail"
    elif width > float(settings["maximum_interval_width"]) and evsi <= review_cost + float(settings["minimum_evsi"]):
        state, reason = "STOP_ABSTAIN", "wide_ci_and_review_evsi_below_cost"
    elif evsi <= review_cost + float(settings["minimum_evsi"]):
        state = "STOP_REJECT" if utility(mean) <= 0 else "STOP_ABSTAIN"
        reason = "next_review_evsi_below_cost"
    else:
        state, reason = "CONTINUE", "next_review_evsi_exceeds_cost"
    return StopDecision(
        hop=hop, state=state, reason=reason, probability=mean, ci_lower=lower,
        ci_upper=upper, ci_width=width, break_even_probability=threshold,
        expected_utility=utility(mean), conservative_utility=utility(lower),
        evsi=evsi, review_cost=review_cost,
    )


def evidence_update_demo(prior_alpha: float = 3.0, prior_beta: float = 7.0) -> dict[str, Any]:
    """Deterministic acceptance test for directional Bayesian evidence response."""
    rng = np.random.default_rng(91027)
    weak = rng.beta(prior_alpha + 3.0, prior_beta + 7.0, size=100000)
    strong = rng.beta(prior_alpha + 30.0, prior_beta + 20.0, size=100000)
    result = {}
    for name, values in (("weak_evidence_30pct", weak), ("strong_evidence_60pct", strong)):
        low, high = np.quantile(values, [0.05, 0.95])
        result[name] = {"mean": float(np.mean(values)), "ci_lower": float(low), "ci_upper": float(high), "ci_width": float(high - low)}
    result["center_moves_up"] = result["strong_evidence_60pct"]["mean"] > result["weak_evidence_30pct"]["mean"]
    result["ci_narrows"] = result["strong_evidence_60pct"]["ci_width"] < result["weak_evidence_30pct"]["ci_width"]
    return result
