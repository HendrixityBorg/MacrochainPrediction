from __future__ import annotations

from typing import Any
import numpy as np

from .bayes import features, fit_fractional_logistic_laplace, sigmoid, time_weights
from .model import primary_labels


def add_direct_terminal_baseline(
    model_run: dict[str, Any], rows: list[dict[str, Any]], config: dict[str, Any],
) -> dict[str, Any]:
    """Development-only direct terminal logistic, preregistered as a comparator.

    This baseline never supplies per-hop probabilities and can therefore not
    replace the chain model even when its Brier score is lower.
    """
    threshold = float(config["data"]["materiality_sigma"])
    development = []
    for row in rows:
        labels = primary_labels(row, threshold)
        if row["split"] == "development" and labels is not None:
            development.append((row, int(all(labels))))
    x = np.vstack([features(row) for row, _ in development])
    y = np.asarray([outcome for _, outcome in development], dtype=float)
    weights = time_weights([row for row, _ in development], float(config["model"]["time_half_life_years"]))
    coefficient, covariance = fit_fractional_logistic_laplace(
        x, y, weights,
        prior_sd_intercept=float(config["model"]["prior_sd_intercept"]),
        prior_sd_coefficient=float(config["model"]["prior_sd_coefficient"]),
        ridge=float(config["measurement"]["ridge"]),
    )
    lookup = {row["event_id"]: row for row in rows}
    predictions = []
    outcomes = []
    for item in model_run["predictions"]:
        if item.get("outcome") is None:
            item["direct_terminal_logistic_probability"] = None
            continue
        probability = float(sigmoid(features(lookup[item["event_id"]]) @ coefficient))
        item["direct_terminal_logistic_probability"] = probability
        predictions.append(probability)
        outcomes.append(int(item["outcome"]))
    score = float(np.mean((np.asarray(predictions) - np.asarray(outcomes)) ** 2))
    return {
        "name": "direct_terminal_logistic",
        "role": "predictive comparator only; has no auditable per-hop decomposition",
        "fit_boundary": "development only",
        "training_events": len(development),
        "coefficient": coefficient.tolist(), "covariance": covariance.tolist(),
        "confirmation_events": len(predictions), "brier": score,
    }

