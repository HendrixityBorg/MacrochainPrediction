from __future__ import annotations

from typing import Any
import numpy as np

from .evaluate import spearman


def _interval(draws: np.ndarray, level: float, scale: float = 1.0) -> tuple[float, float, float]:
    mean = float(np.mean(draws))
    alpha = (1.0 - level) / 2.0
    low, high = (float(value) for value in np.quantile(draws, [alpha, 1.0 - alpha]))
    return mean, max(0.0, mean - scale * (mean - low)), min(1.0, mean + scale * (high - mean))


def run_oracle(config: dict[str, Any]) -> dict[str, Any]:
    settings = config["oracle"]
    rng = np.random.default_rng(int(settings["seed"]))
    rows = int(settings["rows"])
    posterior_draws = int(settings["draws"])
    level = float(config["project"]["interval_level"])
    records = []
    scenarios = ["correlated_measurement", "regime_shift", "gold_heavy_tail", "external_cutoff"]
    for index in range(rows):
        hops = int(rng.integers(int(settings["minimum_hops"]), int(settings["maximum_hops"]) + 1))
        scenario = scenarios[index % len(scenarios)]
        true_links = rng.beta(1.0, 1.0, size=hops)
        true_cutoff = float(rng.beta(1.0, 19.0))
        sample_sizes = rng.integers(6, 90, size=hops)
        proxy_count = int(rng.integers(1, 4))
        proxy_correlation = float(rng.uniform(0.0, 0.8))
        effective = np.maximum(5, np.rint(sample_sizes / (1.0 + (proxy_count - 1) * proxy_correlation)).astype(int))
        successes = np.asarray([rng.binomial(int(n), p) for n, p in zip(effective, true_links)])
        link_samples = np.vstack([rng.beta(1.0 + s, 1.0 + n - s, size=posterior_draws) for s, n in zip(successes, effective)])
        extra_sd = {"correlated_measurement": 0.04, "regime_shift": 0.12, "gold_heavy_tail": 0.16, "external_cutoff": 0.03}[scenario]
        logits = np.log(np.clip(link_samples, 1e-7, 1 - 1e-7) / np.clip(1 - link_samples, 1e-7, 1))
        common = rng.normal(0.0, 1.0, size=posterior_draws)[None, :] * (
            extra_sd / np.sqrt(np.maximum(effective, 1))
        )[:, None]
        logits = logits + common
        link_samples = 1.0 / (1.0 + np.exp(-logits))
        cutoff_n = int(rng.integers(15, 100))
        cutoff_successes = int(rng.binomial(cutoff_n, true_cutoff))
        cutoff_samples = rng.beta(1 + cutoff_successes, 19 + cutoff_n - cutoff_successes, size=posterior_draws)
        chain_samples = np.prod(link_samples, axis=0) * (1.0 - cutoff_samples)
        true_probability = float(np.prod(true_links) * (1.0 - true_cutoff))
        mean, low, high = _interval(chain_samples, level)
        records.append({
            "row": index, "scenario": scenario, "hops": hops, "true_probability": true_probability,
            "mean": mean, "base_lower": low, "base_upper": high, "base_width": high - low,
            "sample_sizes": sample_sizes.tolist(), "effective_sample_sizes": effective.tolist(),
            "proxy_correlation": proxy_correlation,
        })
    split = rows // 4
    scales = np.arange(1.0, 3.01, 0.05)
    selected = float(scales[-1])
    calibration_coverage = 0.0
    for candidate in scales:
        covered = []
        for row in records[:split]:
            mean = row["mean"]
            low = max(0.0, mean - float(candidate) * (mean - row["base_lower"]))
            high = min(1.0, mean + float(candidate) * (row["base_upper"] - mean))
            covered.append(low <= row["true_probability"] <= high)
        coverage = float(np.mean(covered))
        if coverage >= 0.90:
            selected, calibration_coverage = float(candidate), coverage
            break
    test = records[split:]
    covered = []
    widths = []
    errors = []
    by_scenario: dict[str, list[bool]] = {}
    by_hop: dict[int, list[bool]] = {}
    for row in test:
        mean = row["mean"]
        low = max(0.0, mean - selected * (mean - row["base_lower"]))
        high = min(1.0, mean + selected * (row["base_upper"] - mean))
        hit = low <= row["true_probability"] <= high
        covered.append(hit)
        widths.append(high - low)
        errors.append(abs(mean - row["true_probability"]))
        by_scenario.setdefault(row["scenario"], []).append(hit)
        by_hop.setdefault(row["hops"], []).append(hit)
    rho, p_value = spearman(widths, errors, permutations=1999, seed=int(settings["seed"]) + 1)
    return {
        "data_generating_process": "Bayesian conditional links with correlated proxies, effective evidence loss, regime drift, heavy-tail inflation and explicit competing-risk cutoff",
        "rows": rows, "calibration_rows": split, "test_rows": len(test),
        "interval_level": level, "calibrated_interval_scale": selected,
        "calibration_coverage": calibration_coverage,
        "test_coverage": float(np.mean(covered)),
        "test_mean_width": float(np.mean(widths)),
        "ci_width_error_spearman_rho": rho, "ci_width_error_p_value": p_value,
        "coverage_by_scenario": {key: float(np.mean(value)) for key, value in by_scenario.items()},
        "coverage_by_hops": {str(key): float(np.mean(value)) for key, value in sorted(by_hop.items())},
        "hidden_truth_not_used_for_test_tuning": True,
    }
