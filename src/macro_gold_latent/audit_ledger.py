from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from .latent import MeasurementFit, estimate


def latent_state_rows(model_run: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fits = {}
    for state, item in model_run["measurement_fits"].items():
        fits[state] = MeasurementFit(
            state=state, measurements=list(item["measurements"]), main=item["main"],
            intercepts=np.asarray(item["intercepts"], dtype=float), loadings=np.asarray(item["loadings"], dtype=float),
            residual_covariance=np.asarray(item["residual_covariance"], dtype=float),
            prior_variance=float(item["prior_variance"]), training_rows=int(item["training_rows"]),
            mean_posterior_sd=float(item["mean_posterior_sd"]),
            proxy_correlations=dict(item["proxy_correlations"]), robust_student_df=item["robust_student_df"],
        )
    output = []
    for event in events:
        if event["split"] != "confirmation":
            continue
        for state, fit in fits.items():
            posterior = estimate(event, fit)
            measurements = {
                name: (None if event.get(f"{name}_z", "") in (None, "") else float(event[f"{name}_z"]))
                for name in fit.measurements
            }
            output.append({
                "event_id": event["event_id"], "release_date": event["release_date"], "state": state,
                "main_measurement": fit.main, "main_observed": int(posterior.main_observed),
                "observed_measurements": ";".join(posterior.observed),
                "measurement_z": json.dumps(measurements, sort_keys=True, separators=(",", ":")),
                "latent_posterior_mean": posterior.mean,
                "latent_posterior_sd": math.sqrt(max(posterior.variance, 0.0)),
                "loading_vector": json.dumps(fit.loadings.tolist(), separators=(",", ":")),
                "residual_covariance": json.dumps(fit.residual_covariance.tolist(), separators=(",", ":")),
                "fit_boundary": "development_only",
            })
    return output

