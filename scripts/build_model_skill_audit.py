#!/usr/bin/env python3
from __future__ import annotations

import copy
from datetime import date, datetime, timezone
import json
from pathlib import Path

import numpy as np

from macro_gold_latent.config import ROOT, load_config
from macro_gold_latent.data import load_events
from macro_gold_latent.io import read_json, write_json
from macro_gold_latent.latent import estimate_all, fit_all
from macro_gold_latent.model import (
    _draw_event, _fit_links, _residual_correlation, primary_labels,
)


def _brier(probabilities: list[float], outcomes: list[int]) -> float:
    return float(np.mean((np.asarray(probabilities) - np.asarray(outcomes)) ** 2))


def _development_prequential(rows: list[dict], config: dict, start: int) -> dict:
    development = sorted(
        [row for row in rows if row["split"] == "development" and int(float(row["primary_complete"])) == 1],
        key=lambda row: row["release_date"],
    )
    outcomes: list[int] = []
    latent_center: list[float] = []
    primary_anchor: list[float] = []
    climatology: list[float] = []
    local = copy.deepcopy(config)
    local["model"]["posterior_draws"] = 2000
    for index in range(start, len(development)):
        training = development[:index]
        target = development[index]
        measurement_fits = fit_all(training, local)
        estimates = {row["event_id"]: estimate_all(row, measurement_fits) for row in [*training, target]}
        latent_fits = _fit_links(training, estimates, measurement_fits, local, use_latent=True, use_root=True)
        anchored_fits = _fit_links(training, estimates, measurement_fits, local, use_latent=False, use_root=True)
        correlation = _residual_correlation(training, latent_fits, estimates, local)
        for anchored, latent in zip(anchored_fits, latent_fits):
            anchored.measurement_uncertainty_sd = latent.measurement_uncertainty_sd
        training_end = max(date.fromisoformat(row["release_date"]) for row in training)
        seed = 880000 + index * 31
        latent_center.append(_draw_event(target, latent_fits, correlation, training_end, local, seed)["chain_probability"])
        primary_anchor.append(_draw_event(target, anchored_fits, correlation, training_end, local, seed)["chain_probability"])
        labels = primary_labels(target, float(local["data"]["materiality_sigma"]))
        outcomes.append(int(all(labels)))
        history = [int(all(primary_labels(row, float(local["data"]["materiality_sigma"])))) for row in training]
        climatology.append((1.0 + sum(history)) / (2.0 + len(history)))
    return {
        "start_after_events": start,
        "predictions": len(outcomes),
        "positives": sum(outcomes),
        "brier": {
            "latent_center": _brier(latent_center, outcomes),
            "primary_anchor_multi_measurement_ci": _brier(primary_anchor, outcomes),
            "expanding_climatology": _brier(climatology, outcomes),
        },
        "mean_probability": {
            "latent_center": float(np.mean(latent_center)),
            "primary_anchor_multi_measurement_ci": float(np.mean(primary_anchor)),
            "expanding_climatology": float(np.mean(climatology)),
        },
    }


def _block_bootstrap(predictions: list[dict], left: str, right: str, *, draws: int = 20000) -> dict:
    outcomes = np.asarray([float(row["outcome"]) for row in predictions])
    p_left = np.asarray([float(row[left]) for row in predictions])
    p_right = np.asarray([float(row[right]) for row in predictions])
    years = np.asarray([row["release_date"][:4] for row in predictions])
    blocks = sorted(set(years))
    rng = np.random.default_rng(20260905)
    differences = []
    for _ in range(draws):
        selected = rng.choice(blocks, len(blocks), replace=True)
        indices = np.concatenate([np.flatnonzero(years == block) for block in selected])
        differences.append(float(np.mean((p_left[indices] - outcomes[indices]) ** 2 - (p_right[indices] - outcomes[indices]) ** 2)))
    observed = float(np.mean((p_left - outcomes) ** 2 - (p_right - outcomes) ** 2))
    lower, upper = np.quantile(differences, [0.05, 0.95])
    return {
        "left": left, "right": right, "observed_brier_difference_left_minus_right": observed,
        "year_block_bootstrap_90ci": [float(lower), float(upper)],
        "bootstrap_probability_left_better": float(np.mean(np.asarray(differences) < 0)),
        "draws": draws, "seed": 20260905,
    }


def main() -> int:
    rows = load_events()
    config = load_config()
    model_run = read_json(ROOT / "reports/model_run.json")
    predictions = model_run["predictions"]
    development = [row for row in rows if row["split"] == "development" and int(float(row["primary_complete"])) == 1]
    confirmation = [row for row in predictions if row.get("outcome") is not None]
    dev_outcomes = [int(all(primary_labels(row, 1.0))) for row in development]
    con_outcomes = [int(row["outcome"]) for row in confirmation]
    output = {
        "status": "POST_LABEL_DIAGNOSTIC_NOT_CONFIRMATORY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "regime_shift": {
            "development_events": len(dev_outcomes), "development_positives": sum(dev_outcomes),
            "development_rate": float(np.mean(dev_outcomes)),
            "confirmation_events": len(con_outcomes), "confirmation_positives": sum(con_outcomes),
            "confirmation_rate": float(np.mean(con_outcomes)),
        },
        "development_only_prequential_selection_check": [
            _development_prequential(rows, config, 36),
            _development_prequential(rows, config, 48),
        ],
        "confirmation_uncertainty": [
            _block_bootstrap(predictions, "chain_probability", "climatology_probability"),
            _block_bootstrap(predictions, "chain_probability", "naive_marginal_probability"),
            _block_bootstrap(predictions, "primary_only_probability", "climatology_probability"),
            _block_bootstrap(predictions, "direct_terminal_logistic_probability", "climatology_probability"),
        ],
        "decision": {
            "promote_primary_anchor": False,
            "reason": "The primary-anchor variant looks better only after opening confirmation labels; both frozen development prequential checks favor expanding climatology. Promotion would be outcome-driven model switching.",
            "legitimate_next_evidence": "At least 50 new custodian-controlled events or genuinely prospective predictions under a newly frozen protocol.",
        },
    }
    write_json(ROOT / "reports/model_skill_audit.json", output)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

