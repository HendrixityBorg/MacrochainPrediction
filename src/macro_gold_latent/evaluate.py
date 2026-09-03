from __future__ import annotations

from collections import defaultdict
import math
from typing import Any

import numpy as np


def brier(probabilities: list[float], outcomes: list[int]) -> float:
    if not probabilities:
        return float("nan")
    return float(np.mean((np.asarray(probabilities) - np.asarray(outcomes)) ** 2))


def _ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    index = 0
    while index < len(values):
        end = index + 1
        while end < len(values) and values[order[end]] == values[order[index]]:
            end += 1
        ranks[order[index:end]] = (index + end - 1) / 2.0 + 1.0
        index = end
    return ranks


def spearman(x: list[float], y: list[float], *, permutations: int = 4999, seed: int = 9917) -> tuple[float, float]:
    left, right = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(left) < 3 or np.std(left) == 0 or np.std(right) == 0:
        return 0.0, 1.0
    left_rank, right_rank = _ranks(left), _ranks(right)
    observed = float(np.corrcoef(left_rank, right_rank)[0, 1])
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(permutations):
        candidate = float(np.corrcoef(left_rank, rng.permutation(right_rank))[0, 1])
        if abs(candidate) >= abs(observed):
            exceed += 1
    return observed, (exceed + 1.0) / (permutations + 1.0)


def reliability(probabilities: list[float], outcomes: list[int], minimum_bin: int) -> list[dict[str, Any]]:
    ordered = sorted(zip(probabilities, outcomes), key=lambda item: item[0])
    if not ordered:
        return []
    bins = max(1, min(10, len(ordered) // minimum_bin))
    output = []
    for index, chunk in enumerate(np.array_split(np.asarray(ordered, dtype=float), bins), 1):
        if len(chunk) == 0:
            continue
        output.append({
            "bin": index, "n": int(len(chunk)), "mean_probability": float(np.mean(chunk[:, 0])),
            "observed_rate": float(np.mean(chunk[:, 1])),
            "absolute_gap": float(abs(np.mean(chunk[:, 0]) - np.mean(chunk[:, 1]))),
            "min_probability": float(np.min(chunk[:, 0])), "max_probability": float(np.max(chunk[:, 0])),
        })
    return output


def _metric(predictions: list[dict[str, Any]], field: str) -> float:
    return brier([float(row[field]) for row in predictions], [int(row["outcome"]) for row in predictions])


def _method_track_record(model_run: dict[str, Any]) -> dict[str, Any]:
    records = []
    for fit in model_run["link_fits"]:
        n = int(fit["n_raw"])
        predicted = (float(fit["soft_success_sum"]) + 1.0) / (n + 2.0)
        observed = int(fit["hard_success_sum"]) / n if n else 0.0
        records.append({
            "hop": int(fit["hop"]), "known_outcomes": n, "predicted_soft_rate": predicted,
            "observed_primary_rate": observed, "absolute_calibration_error": abs(predicted - observed),
            "method": fit["method"],
        })
    fallback_triggered = any("same_hop_macro_reference_class" in item["method"] for item in records)
    return {
        "scope": "same macro-release link estimator on known 2005-2010 NFP outcomes",
        "minimum_known_outcomes": min(item["known_outcomes"] for item in records),
        "rare_event_clause_applicable": fallback_triggered,
        "fallback_triggered": fallback_triggered,
        "records": records,
        "note": "No confirmation outcome is used. The >=20 rare-method clause is required only if the <5 fallback is triggered; raw counts remain disclosed even when not applicable.",
    }


def evaluate(model_run: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    predictions = [row for row in model_run["predictions"] if row.get("outcome") is not None]
    outcomes = [int(row["outcome"]) for row in predictions]
    probabilities = [float(row["chain_probability"]) for row in predictions]
    methods = {
        "latent_conditional_dynamic": "chain_probability",
        "naive_marginal_product": "naive_marginal_probability",
        "conditional_beta_chain": "conditional_beta_probability",
        "climatology": "climatology_probability",
        "always_zero": "always_zero_probability",
        "primary_only": "primary_only_probability",
        "proxy_only": "proxy_only_probability",
        "no_root_ablation": "no_root_probability",
    }
    scores = {name: _metric(predictions, field) for name, field in methods.items()}
    hop_counts = []
    for hop in range(1, 4):
        successes = sum(all(row["hop_outcomes"][:hop]) for row in predictions)
        hop_counts.append({"hop": hop, "events": len(predictions), "prefix_successes": successes, "prefix_rate": successes / len(predictions)})
    errors = [abs(probability - outcome) for probability, outcome in zip(probabilities, outcomes)]
    widths = [float(row["ci_width"]) for row in predictions]
    rho, p_value = spearman(widths, errors)
    median = float(np.median(widths))
    narrow = [error for width, error in zip(widths, errors) if width <= median]
    wide = [error for width, error in zip(widths, errors) if width > median]
    table = reliability(probabilities, outcomes, int(config["evaluation"]["minimum_reliability_bin_size"]))
    ece = sum(item["n"] * item["absolute_gap"] for item in table) / max(sum(item["n"] for item in table), 1)
    terminal_rate = float(np.mean(outcomes))
    climatology_brier = scores["climatology"]
    brier_skill = 1.0 - scores["latent_conditional_dynamic"] / climatology_brier if climatology_brier > 0 else float("nan")
    return {
        "evidence_boundary": model_run["evidence_boundary"],
        "confirmation_events": len(predictions), "terminal_successes": int(sum(outcomes)),
        "terminal_rate": terminal_rate, "brier": scores,
        "brier_skill_vs_climatology": brier_skill,
        "non_naive_minus_naive_brier": scores["latent_conditional_dynamic"] - scores["naive_marginal_product"],
        "reliability": {"bins": table, "expected_calibration_error": ece},
        "hop_decay": hop_counts,
        "ci_width_error": {
            "spearman_rho": rho, "permutation_p_value_two_sided": p_value,
            "median_ci_width": median,
            "narrow_mean_absolute_error": float(np.mean(narrow)) if narrow else None,
            "wide_mean_absolute_error": float(np.mean(wide)) if wide else None,
            "direction_ok": bool(rho > 0 and p_value < 0.05 and np.mean(wide) > np.mean(narrow)),
        },
        "rare_method_calibration": _method_track_record(model_run),
        "failure_cases": [
            {
                "event_id": row["event_id"], "probability": row["chain_probability"], "outcome": row["outcome"],
                "absolute_error": abs(row["chain_probability"] - row["outcome"]),
                "ci_width": row["ci_width"], "hop_outcomes": row["hop_outcomes"],
            }
            for row in sorted(predictions, key=lambda item: abs(item["chain_probability"] - item["outcome"]), reverse=True)[:12]
        ],
    }
