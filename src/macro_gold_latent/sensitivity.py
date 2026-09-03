from __future__ import annotations

from typing import Any
import numpy as np


def chain_evidence_strength_response(draws: int = 120000, seed: int = 73019) -> dict[str, Any]:
    """Hold a chain fixed and strengthen one hop from 30% to 60% evidence.

    The strong case has both a higher success ratio and ten times the evidence
    concentration. Other hops and the competing-risk distribution use paired
    draws, so the comparison isolates this one evidence change.
    """
    rng = np.random.default_rng(seed)
    p2 = rng.beta(301, 199, size=draws)
    p3 = rng.beta(201, 299, size=draws)
    cutoff = rng.beta(6, 194, size=draws)
    weak_p1 = rng.beta(7, 15, size=draws)      # posterior mean ~0.318, n=20
    strong_p1 = rng.beta(121, 81, size=draws)  # posterior mean ~0.599, n=200
    weak = weak_p1 * p2 * p3 * (1.0 - cutoff)
    strong = strong_p1 * p2 * p3 * (1.0 - cutoff)

    def summary(values: np.ndarray, p1: np.ndarray, evidence_n: int) -> dict[str, Any]:
        low, high = np.quantile(values, [0.05, 0.95])
        return {
            "changed_hop_mean": float(np.mean(p1)), "changed_hop_effective_n": evidence_n,
            "chain_mean": float(np.mean(values)), "chain_ci_lower": float(low),
            "chain_ci_upper": float(high), "chain_ci_width": float(high - low),
        }

    weak_result = summary(weak, weak_p1, 20)
    strong_result = summary(strong, strong_p1, 200)
    return {
        "controlled_change": "only hop-1 evidence changes; p2, p3 and cutoff draws are paired",
        "weak_evidence_30pct": weak_result, "strong_evidence_60pct": strong_result,
        "center_moves_up": strong_result["chain_mean"] > weak_result["chain_mean"],
        "ci_narrows": strong_result["chain_ci_width"] < weak_result["chain_ci_width"],
        "seed": seed, "draws": draws,
    }

