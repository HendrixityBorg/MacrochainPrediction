from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
from typing import Any

import numpy as np

from .bayes import features, fit_fractional_logistic_laplace, kish, sigmoid, time_weights
from .latent import (
    LatentEstimate, MeasurementFit, directional_material_probability, estimate_all,
    fit_all, pair_directional_probability,
)
from .stopping import decide


@dataclass
class LinkFit:
    hop: int
    method: str
    coefficient: np.ndarray
    covariance: np.ndarray
    n_raw: int
    n_eff: float
    source_event_ids: list[str]
    soft_success_sum: float
    hard_success_sum: int
    measurement_uncertainty_sd: float
    external_cutoffs: int


def _f(row: dict[str, Any], key: str) -> float:
    value = row.get(key, "")
    return float(value) if value not in (None, "") else float("nan")


def primary_labels(row: dict[str, Any], threshold: float) -> list[int] | None:
    root = _f(row, "root_z")
    policy = _f(row, "policy_h15_2y_z")
    real = _f(row, "real_h15_5y_z")
    gold = _f(row, "gold_gld_z")
    if not all(math.isfinite(value) for value in (root, policy, real, gold)) or root == 0:
        return None
    first = int(np.sign(policy) == np.sign(root) and abs(policy) >= threshold)
    second = int(np.sign(real) == np.sign(policy) and abs(real) >= threshold)
    third = int(np.sign(gold) == -np.sign(real) and abs(gold) >= threshold)
    return [first, second, third]


def proxy_labels(row: dict[str, Any], threshold: float) -> list[int] | None:
    root = _f(row, "root_z")
    policy = _f(row, "policy_zt_z")
    real = _f(row, "real_tip_z")
    gold = _f(row, "gold_gc_z")
    if not all(math.isfinite(value) for value in (root, policy, real, gold)) or root == 0:
        return None
    return [
        int(np.sign(policy) == np.sign(root) and abs(policy) >= threshold),
        int(np.sign(real) == np.sign(policy) and abs(real) >= threshold),
        int(np.sign(gold) == -np.sign(real) and abs(gold) >= threshold),
    ]


def _soft_labels(
    row: dict[str, Any], states: dict[str, LatentEstimate], *, threshold: float, seed: int,
) -> list[float]:
    direction = 1.0 if float(row["root_z"]) > 0 else -1.0
    return [
        directional_material_probability(states["policy"], direction, threshold),
        pair_directional_probability(states["policy"], states["real_rate"], multiplier=1.0, threshold=threshold, seed=seed + 1),
        pair_directional_probability(states["real_rate"], states["gold"], multiplier=-1.0, threshold=threshold, seed=seed + 2),
    ]


def _fit_links(
    development: list[dict[str, Any]], estimates: dict[str, dict[str, LatentEstimate]],
    fits: dict[str, MeasurementFit], config: dict[str, Any], *, use_latent: bool = True, use_root: bool = True,
) -> list[LinkFit]:
    threshold = float(config["data"]["materiality_sigma"])
    primary = {row["event_id"]: primary_labels(row, threshold) for row in development}
    soft = {
        row["event_id"]: _soft_labels(row, estimates[row["event_id"]], threshold=threshold, seed=int(config["project"]["seed"]) + index * 10)
        for index, row in enumerate(development)
    }
    output: list[LinkFit] = []
    settings = config["model"]
    uncertainty_states = ["policy", "real_rate", "gold"]
    for hop in range(1, 4):
        risk = []
        for row in development:
            labels = primary[row["event_id"]]
            if labels is None:
                continue
            if all(labels[previous] == 1 for previous in range(hop - 1)):
                risk.append(row)
        method = "prefix_conditional_latent_fractional_logistic" if use_latent else "prefix_conditional_primary_hard_logistic"
        if len(risk) < int(settings["minimum_reference_events"]):
            risk = [row for row in development if primary[row["event_id"]] is not None]
            method = "same_hop_macro_reference_class_latent_logistic" if use_latent else "same_hop_macro_reference_class_hard_logistic"
        x = np.vstack([features(row) if use_root else np.asarray([1.0]) for row in risk])
        y = np.asarray([
            soft[row["event_id"]][hop - 1] if use_latent else primary[row["event_id"]][hop - 1]
            for row in risk
        ], dtype=float)
        weights = time_weights(risk, float(settings["time_half_life_years"]))
        coefficient, covariance = fit_fractional_logistic_laplace(
            x, y, weights, prior_sd_intercept=float(settings["prior_sd_intercept"]),
            prior_sd_coefficient=float(settings["prior_sd_coefficient"]), ridge=float(config["measurement"]["ridge"]),
        )
        measurement_sd = fits[uncertainty_states[hop - 1]].mean_posterior_sd / math.sqrt(max(kish(weights), 1.0)) if use_latent else 0.0
        output.append(LinkFit(
            hop=hop, method=method, coefficient=coefficient, covariance=covariance,
            n_raw=len(risk), n_eff=kish(weights), source_event_ids=[row["event_id"] for row in risk],
            soft_success_sum=float(weights @ y),
            hard_success_sum=sum(primary[row["event_id"]][hop - 1] for row in risk),
            measurement_uncertainty_sd=measurement_sd,
            external_cutoffs=sum(int(float(row.get("external_cutoff", 0) or 0)) for row in development),
        ))
    return output


def _residual_correlation(
    development: list[dict[str, Any]], link_fits: list[LinkFit],
    estimates: dict[str, dict[str, LatentEstimate]], config: dict[str, Any],
) -> np.ndarray:
    threshold = float(config["data"]["materiality_sigma"])
    residuals = []
    for index, row in enumerate(development):
        soft = _soft_labels(row, estimates[row["event_id"]], threshold=threshold, seed=70100 + index * 7)
        fitted = [float(sigmoid((features(row) if len(fit.coefficient) > 1 else np.asarray([1.0])) @ fit.coefficient)) for fit in link_fits]
        residuals.append(np.asarray(soft) - np.asarray(fitted))
    correlation = np.corrcoef(np.asarray(residuals), rowvar=False)
    correlation = np.nan_to_num(correlation, nan=0.0)
    correlation = 0.5 * correlation + 0.5 * np.eye(3)
    values, vectors = np.linalg.eigh((correlation + correlation.T) / 2.0)
    return vectors @ np.diag(np.maximum(values, 1e-4)) @ vectors.T


def _draw_event(
    row: dict[str, Any], link_fits: list[LinkFit], residual_correlation: np.ndarray,
    development_end: date, config: dict[str, Any], seed: int,
) -> dict[str, Any]:
    settings = config["model"]
    draws = int(settings["posterior_draws"])
    rng = np.random.default_rng(seed)
    point = date.fromisoformat(row["release_date"])
    gap_years = max(0.0, (point - development_end).days / 365.25)
    drift_sd = float(settings["parameter_drift_sd_per_year"]) * math.sqrt(gap_years)
    common = rng.multivariate_normal(np.zeros(3), residual_correlation * 0.04, size=draws)
    link_draws = []
    p_i = []
    for index, fit in enumerate(link_fits):
        covariance = fit.covariance + np.eye(len(fit.coefficient)) * drift_sd * drift_sd
        coefficients = rng.multivariate_normal(fit.coefficient, covariance, size=draws)
        x = features(row) if len(fit.coefficient) > 1 else np.asarray([1.0])
        measurement_noise = rng.normal(0.0, fit.measurement_uncertainty_sd, size=draws)
        probabilities = np.asarray(sigmoid(coefficients @ x + common[:, index] + measurement_noise), dtype=float)
        link_draws.append(probabilities)
        p_i.append(float(np.mean(probabilities)))
    intrinsic = np.prod(np.vstack(link_draws), axis=0)
    observed_cutoffs = link_fits[0].external_cutoffs
    cutoff_alpha = float(settings["unscheduled_cutoff_prior_alpha"]) + observed_cutoffs
    cutoff_beta = float(settings["unscheduled_cutoff_prior_beta"]) + len(link_fits[0].source_event_ids) - observed_cutoffs
    if int(float(row.get("scheduled_cutoff", 0) or 0)) == 1:
        cutoff_alpha = float(settings["scheduled_cutoff_prior_alpha"])
        cutoff_beta = float(settings["scheduled_cutoff_prior_beta"])
    cutoff = rng.beta(cutoff_alpha, cutoff_beta, size=draws)
    realized = intrinsic * (1.0 - cutoff)
    prefix_draws = []
    running = np.ones(draws)
    for values in link_draws:
        running = running * values
        prefix_draws.append(running * (1.0 - cutoff))
    level = float(config["project"]["interval_level"])
    alpha = (1.0 - level) / 2.0
    lower, upper = (float(value) for value in np.quantile(realized, [alpha, 1.0 - alpha]))
    intrinsic_low, intrinsic_high = (float(value) for value in np.quantile(intrinsic, [alpha, 1.0 - alpha]))

    # One-block-at-a-time Monte Carlo variances provide an auditable source
    # decomposition. They need not sum exactly because interactions are real.
    coefficient_only = []
    measurement_only = []
    drift_only = []
    common_only = []
    for fit in link_fits:
        coefficient = rng.multivariate_normal(fit.coefficient, fit.covariance, size=draws)
        x = features(row) if len(fit.coefficient) > 1 else np.asarray([1.0])
        coefficient_only.append(np.asarray(sigmoid(coefficient @ x)))
        logit_mean = math.log(np.clip(p_i[fit.hop - 1], 1e-6, 1 - 1e-6) / np.clip(1 - p_i[fit.hop - 1], 1e-6, 1))
        measurement_only.append(np.asarray(sigmoid(logit_mean + rng.normal(0, fit.measurement_uncertainty_sd, draws))))
        drift_only.append(np.asarray(sigmoid(logit_mean + rng.normal(0, drift_sd * float(np.linalg.norm(x)), draws))))
        common_only.append(np.asarray(sigmoid(logit_mean + common[:, fit.hop - 1])))

    cutoff_mean_multiplier = 1.0 - cutoff_alpha / (cutoff_alpha + cutoff_beta)
    prefix_uncertainty = []
    for hop in range(1, len(link_fits) + 1):
        total_variance = max(float(np.var(prefix_draws[hop - 1])), 1e-14)
        mean_intrinsic_prefix = float(np.mean(np.prod(np.vstack(link_draws[:hop]), axis=0)))
        coefficient_chain = np.prod(np.vstack(coefficient_only[:hop]), axis=0) * cutoff_mean_multiplier
        measurement_chain = np.prod(np.vstack(measurement_only[:hop]), axis=0) * cutoff_mean_multiplier
        drift_chain = np.prod(np.vstack(drift_only[:hop]), axis=0) * cutoff_mean_multiplier
        common_chain = np.prod(np.vstack(common_only[:hop]), axis=0) * cutoff_mean_multiplier
        q_only = mean_intrinsic_prefix * (1.0 - cutoff)
        prefix_uncertainty.append({
            "prefix_hops": hop,
            "link_parameter_variance_share": float(np.var(coefficient_chain) / total_variance),
            "measurement_variance_share": float(np.var(measurement_chain) / total_variance),
            "regime_drift_variance_share": float(np.var(drift_chain) / total_variance),
            "common_frailty_variance_share": float(np.var(common_chain) / total_variance),
            "external_cutoff_variance_share": float(np.var(q_only) / total_variance),
            "regime_drift_sd_per_coefficient": drift_sd,
            "interaction_note": "one-block-at-a-time variance ratios may overlap and need not sum to one",
        })

    prefixes = []
    for hop, prefix in enumerate(prefix_draws, 1):
        decision = decide(prefix, hop=hop, terminal_hop=3, config=config).as_dict()
        prefixes.append({
            "hop": hop, "p_i": p_i[hop - 1], "n_i": link_fits[hop - 1].n_eff,
            **decision, "uncertainty_decomposition": prefix_uncertainty[hop - 1],
        })
    executed_stop_index = next(
        (index for index, item in enumerate(prefixes) if item["state"] != "CONTINUE"),
        len(prefixes) - 1,
    )
    for index, item in enumerate(prefixes):
        item["execution_reached"] = index <= executed_stop_index
        item["is_executed_stop"] = index == executed_stop_index
        item["evaluation_mode"] = "executed" if index <= executed_stop_index else "counterfactual_after_stop"
    execution_stop = {
        key: prefixes[executed_stop_index][key]
        for key in ("hop", "state", "reason", "probability", "ci_lower", "ci_upper", "ci_width", "break_even_probability")
    }
    return {
        "event_id": row["event_id"], "release_date": row["release_date"], "split": row["split"],
        "p_i": p_i, "n_i": [fit.n_eff for fit in link_fits],
        "intrinsic_probability": float(np.mean(intrinsic)),
        "interruption_probability": float(np.mean(cutoff)),
        "interruption_posterior": {
            "alpha": cutoff_alpha, "beta": cutoff_beta,
            "observed_cutoffs": observed_cutoffs,
            "reference_events": len(link_fits[0].source_event_ids),
            "base_prior": {
                "alpha": float(settings["unscheduled_cutoff_prior_alpha"]),
                "beta": float(settings["unscheduled_cutoff_prior_beta"]),
            },
            "provenance": "locked weak-regularizing prior plus development external_cutoff labels",
            "center_sensitivity_q": {
                "q_0pct_multiplier": 1.0,
                "q_1_12pct_multiplier": 0.9888,
                "q_5pct_multiplier": 0.95,
                "q_10pct_multiplier": 0.90,
            },
        },
        "chain_probability": float(np.mean(realized)), "ci_lower": lower, "ci_upper": upper,
        "ci_width": upper - lower, "intrinsic_ci_lower": intrinsic_low, "intrinsic_ci_upper": intrinsic_high,
        "stop_trace": prefixes, "execution_stop": execution_stop,
        "uncertainty_decomposition": prefix_uncertainty[-1],
        "posterior_seed": seed, "posterior_draws": draws,
    }


def _beta_probability(successes: float, total: float) -> float:
    return (1.0 + successes) / (2.0 + total)


def _structural_diagnostics(
    development: list[dict[str, Any]], estimates: dict[str, dict[str, LatentEstimate]],
) -> dict[str, Any]:
    """Fit the parallel/competing paths on latent posterior means.

    These equations diagnose interference and generate a safe-haven residual;
    they do not redefine the primary H.15/GLD success labels.
    """
    root = np.asarray([float(row["root_z"]) for row in development])
    states = {
        state: np.asarray([estimates[row["event_id"]][state].mean for row in development])
        for state in ("policy", "inflation", "real_rate", "gold", "dollar")
    }

    def ridge(target: np.ndarray, predictors: np.ndarray, names: list[str]) -> dict[str, Any]:
        design = np.column_stack([np.ones(len(target)), predictors])
        penalty = np.eye(design.shape[1]) * 0.10
        penalty[0, 0] = 1e-6
        coefficient = np.linalg.solve(design.T @ design + penalty, design.T @ target)
        residual = target - design @ coefficient
        return {
            "feature_names": ["intercept", *names], "coefficients": coefficient.tolist(),
            "residual_sd": float(np.std(residual, ddof=design.shape[1])),
            "r_squared": float(1.0 - np.sum(residual ** 2) / max(np.sum((target - np.mean(target)) ** 2), 1e-12)),
        }

    policy = ridge(states["policy"], root[:, None], ["macro_surprise"])
    inflation = ridge(states["inflation"], root[:, None], ["macro_surprise"])
    real = ridge(states["real_rate"], np.column_stack([states["policy"], states["inflation"]]), ["policy_path", "inflation_expectation"])
    gold = ridge(states["gold"], np.column_stack([states["real_rate"], states["dollar"]]), ["real_rate", "dollar"])
    return {
        "policy_given_macro": policy,
        "inflation_given_macro": inflation,
        "real_rate_given_policy_and_inflation": real,
        "gold_given_real_rate_and_dollar": gold,
        "safe_haven_or_omitted_shock_definition": "residual of latent gold on latent real-rate and dollar states",
        "audit_label_unchanged": True,
    }


def run_model(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    development = [row for row in rows if row["split"] == "development" and int(float(row.get("primary_complete", 0))) == 1]
    confirmation = [row for row in rows if row["split"] == "confirmation" and int(float(row.get("primary_complete", 0))) == 1]
    if len(development) < 20 or len(confirmation) < 50:
        raise ValueError(f"insufficient development/confirmation rows: {len(development)}/{len(confirmation)}")
    measurement_fits = fit_all(development, config)
    estimates = {row["event_id"]: estimate_all(row, measurement_fits) for row in rows}
    full_fits = _fit_links(development, estimates, measurement_fits, config, use_latent=True, use_root=True)
    primary_fits = _fit_links(development, estimates, measurement_fits, config, use_latent=False, use_root=True)
    no_root_fits = _fit_links(development, estimates, measurement_fits, config, use_latent=True, use_root=False)
    correlation = _residual_correlation(development, full_fits, estimates, config)
    structural = _structural_diagnostics(development, estimates)
    development_end = max(date.fromisoformat(row["release_date"]) for row in development)
    threshold = float(config["data"]["materiality_sigma"])
    hard = {row["event_id"]: primary_labels(row, threshold) for row in development}
    proxy = {row["event_id"]: proxy_labels(row, threshold) for row in development}
    marginal = [_beta_probability(sum(labels[hop] for labels in hard.values() if labels is not None), sum(labels is not None for labels in hard.values())) for hop in range(3)]
    naive = float(np.prod(marginal))
    conditional = []
    for hop in range(3):
        risk = [labels for labels in hard.values() if labels is not None and all(labels[previous] == 1 for previous in range(hop))]
        conditional.append(_beta_probability(sum(labels[hop] for labels in risk), len(risk)))
    conditional_beta = float(np.prod(conditional))
    terminal = [int(all(labels)) for labels in hard.values() if labels is not None]
    climatology = _beta_probability(sum(terminal), len(terminal))
    proxy_terminal = [int(all(labels)) for labels in proxy.values() if labels is not None]
    proxy_probability = _beta_probability(sum(proxy_terminal), len(proxy_terminal)) if proxy_terminal else climatology
    predictions = []
    evidence = []
    for index, row in enumerate(confirmation):
        full = _draw_event(row, full_fits, correlation, development_end, config, int(config["project"]["seed"]) + 10000 + index * 17)
        primary_only = _draw_event(row, primary_fits, np.eye(3), development_end, config, int(config["project"]["seed"]) + 20000 + index * 17)
        no_root = _draw_event(row, no_root_fits, correlation, development_end, config, int(config["project"]["seed"]) + 30000 + index * 17)
        labels = primary_labels(row, threshold)
        full.update({
            "outcome": int(all(labels)) if labels is not None else None,
            "hop_outcomes": labels,
            "naive_marginal_probability": naive,
            "conditional_beta_probability": conditional_beta,
            "climatology_probability": climatology,
            "always_zero_probability": 0.0,
            "primary_only_probability": primary_only["chain_probability"],
            "proxy_only_probability": proxy_probability,
            "no_root_probability": no_root["chain_probability"],
            "evidence_status": row["evidence_status"],
            "model_version": config["project"]["model_version"],
        })
        predictions.append(full)
        for fit, probability in zip(full_fits, full["p_i"]):
            evidence.append({
                "event_id": row["event_id"], "hop": fit.hop, "p_i": probability, "n_i": fit.n_eff,
                "n_raw": fit.n_raw, "estimation_method": fit.method,
                "soft_success_sum": fit.soft_success_sum, "hard_success_sum": fit.hard_success_sum,
                "feature_names": ["intercept", "log1p_abs_root_z", "root_sign"],
                "feature_vector": features(row).tolist(), "posterior_mean_coefficients": fit.coefficient.tolist(),
                "posterior_covariance": fit.covariance.tolist(), "measurement_uncertainty_sd": fit.measurement_uncertainty_sd,
                "source_event_ids": fit.source_event_ids, "posterior_seed": full["posterior_seed"],
                "calibration_track_record": "reports/evaluation.json#rare_method_calibration",
            })
    return {
        "model_version": config["project"]["model_version"],
        "evidence_boundary": "development-only fit; confirmation batch labels never enter prediction",
        "development_events": len(development), "confirmation_events": len(confirmation),
        "measurement_fits": {state: fit.as_dict() for state, fit in measurement_fits.items()},
        "structural_diagnostics": structural,
        "link_residual_correlation": correlation.tolist(),
        "link_fits": [{
            "hop": fit.hop, "method": fit.method, "coefficient": fit.coefficient.tolist(),
            "covariance": fit.covariance.tolist(), "n_raw": fit.n_raw, "n_eff": fit.n_eff,
            "soft_success_sum": fit.soft_success_sum, "hard_success_sum": fit.hard_success_sum,
            "source_event_ids": fit.source_event_ids,
            "measurement_uncertainty_sd": fit.measurement_uncertainty_sd,
            "external_cutoffs": fit.external_cutoffs,
        } for fit in full_fits],
        "baselines": {"marginal_naive_product": naive, "conditional_beta_chain": conditional_beta, "climatology": climatology, "proxy_only": proxy_probability},
        "predictions": predictions, "edge_evidence": evidence,
    }


def reproduce_three_hops(model_run: dict[str, Any], rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    link_fits = [LinkFit(
        hop=int(item["hop"]), method=item["method"], coefficient=np.asarray(item["coefficient"], dtype=float),
        covariance=np.asarray(item["covariance"], dtype=float), n_raw=int(item["n_raw"]), n_eff=float(item["n_eff"]),
        source_event_ids=list(item["source_event_ids"]), soft_success_sum=float(item["soft_success_sum"]),
        hard_success_sum=int(item["hard_success_sum"]), measurement_uncertainty_sd=float(item["measurement_uncertainty_sd"]),
        external_cutoffs=int(item["external_cutoffs"]),
    ) for item in model_run["link_fits"]]
    development = [row for row in rows if row["split"] == "development" and int(float(row.get("primary_complete", 0))) == 1]
    lookup = {row["event_id"]: row for row in rows}
    development_end = max(date.fromisoformat(row["release_date"]) for row in development)
    correlation = np.asarray(model_run["link_residual_correlation"], dtype=float)
    rng = np.random.default_rng(int(config["project"]["seed"]) + 777)
    selected = rng.choice(len(model_run["predictions"]) * 3, size=3, replace=False)
    checks = []
    for flat in selected:
        event_index, hop_index = divmod(int(flat), 3)
        original = model_run["predictions"][event_index]
        repeated = _draw_event(
            lookup[original["event_id"]], link_fits, correlation, development_end, config,
            int(config["project"]["seed"]) + 10000 + event_index * 17,
        )
        delta = abs(float(original["p_i"][hop_index]) - float(repeated["p_i"][hop_index]))
        checks.append({
            "event_id": original["event_id"], "hop": hop_index + 1,
            "original_p_i": original["p_i"][hop_index], "reproduced_p_i": repeated["p_i"][hop_index],
            "original_n_i": original["n_i"][hop_index], "reproduced_n_i": repeated["n_i"][hop_index],
            "absolute_delta": delta,
        })
    return {"seed": int(config["project"]["seed"]) + 777, "checks": checks, "maximum_absolute_delta": max(item["absolute_delta"] for item in checks)}


def predict_locked_root(
    model_run: dict[str, Any], rows: list[dict[str, Any]], *, event_id: str,
    release_date: str, root_z: float, config: dict[str, Any], seed: int | None = None,
) -> dict[str, Any]:
    link_fits = [LinkFit(
        hop=int(item["hop"]), method=item["method"], coefficient=np.asarray(item["coefficient"], dtype=float),
        covariance=np.asarray(item["covariance"], dtype=float), n_raw=int(item["n_raw"]), n_eff=float(item["n_eff"]),
        source_event_ids=list(item["source_event_ids"]), soft_success_sum=float(item["soft_success_sum"]),
        hard_success_sum=int(item["hard_success_sum"]), measurement_uncertainty_sd=float(item["measurement_uncertainty_sd"]),
        external_cutoffs=int(item["external_cutoffs"]),
    ) for item in model_run["link_fits"]]
    development = [row for row in rows if row["split"] == "development" and int(float(row.get("primary_complete", 0))) == 1]
    development_end = max(date.fromisoformat(row["release_date"]) for row in development)
    pseudo = {
        "event_id": event_id, "release_date": release_date, "split": "live_demo", "root_z": root_z,
        "scheduled_cutoff": 0,
    }
    return _draw_event(
        pseudo, link_fits, np.asarray(model_run["link_residual_correlation"], dtype=float),
        development_end, config, seed if seed is not None else int(config["project"]["seed"]) + 900000,
    )
