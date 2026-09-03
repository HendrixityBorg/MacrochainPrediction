from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np


def _number(row: dict[str, Any], key: str) -> float:
    value = row.get(key, "")
    if value in (None, ""):
        return float("nan")
    return float(value)


def _safe_inverse(matrix: np.ndarray, ridge: float) -> np.ndarray:
    regularized = (matrix + matrix.T) / 2.0 + np.eye(matrix.shape[0]) * ridge
    values, vectors = np.linalg.eigh(regularized)
    return vectors @ np.diag(1.0 / np.maximum(values, ridge)) @ vectors.T


@dataclass
class MeasurementFit:
    state: str
    measurements: list[str]
    main: str
    intercepts: np.ndarray
    loadings: np.ndarray
    residual_covariance: np.ndarray
    prior_variance: float
    training_rows: int
    mean_posterior_sd: float
    proxy_correlations: dict[str, float]
    robust_student_df: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "measurements": self.measurements,
            "main": self.main,
            "identification": "main intercept fixed 0 and loading fixed 1",
            "intercepts": self.intercepts.tolist(),
            "loadings": self.loadings.tolist(),
            "residual_covariance": self.residual_covariance.tolist(),
            "prior_variance": self.prior_variance,
            "training_rows": self.training_rows,
            "mean_posterior_sd": self.mean_posterior_sd,
            "proxy_correlations": self.proxy_correlations,
            "robust_student_df": self.robust_student_df,
        }


@dataclass
class LatentEstimate:
    mean: float
    variance: float
    observed: list[str]
    main_observed: bool


def _posterior(
    values: np.ndarray, intercepts: np.ndarray, loadings: np.ndarray,
    covariance: np.ndarray, prior_variance: float, ridge: float,
) -> tuple[float, float]:
    observed = np.isfinite(values)
    if not np.any(observed):
        return 0.0, prior_variance
    y = values[observed]
    alpha = intercepts[observed]
    loading = loadings[observed]
    precision = _safe_inverse(covariance[np.ix_(observed, observed)], ridge)
    variance = 1.0 / (1.0 / prior_variance + float(loading @ precision @ loading))
    mean = variance * float(loading @ precision @ (y - alpha))
    return mean, variance


def fit_measurement_state(
    rows: list[dict[str, Any]], *, state: str, measurements: list[str], main: str,
    prior_variance: float, covariance_shrinkage: float, ridge: float,
    iterations: int, robust_student_df: float | None = None,
) -> MeasurementFit:
    if not rows:
        raise ValueError("measurement training rows cannot be empty")
    if main not in measurements:
        raise ValueError(f"main measurement {main} missing from state {state}")
    ordered = [main, *[name for name in measurements if name != main]]
    matrix = np.asarray([[_number(row, f"{name}_z") for name in ordered] for row in rows], dtype=float)
    retained = np.isfinite(matrix[:, 0])
    matrix = matrix[retained]
    if len(matrix) < 5:
        raise ValueError(f"state {state} has fewer than five main-measurement rows")
    dimension = len(ordered)
    intercepts = np.zeros(dimension)
    loadings = np.ones(dimension)
    covariance = np.eye(dimension) * 0.6
    means = np.nan_to_num(matrix[:, 0], nan=0.0)
    variances = np.full(len(matrix), 0.25)
    row_weights = np.ones(len(matrix))

    for _ in range(iterations):
        for index, values in enumerate(matrix):
            means[index], variances[index] = _posterior(
                values, intercepts, loadings, covariance, prior_variance, ridge
            )
        for column in range(1, dimension):
            valid = np.isfinite(matrix[:, column])
            if np.sum(valid) < 5:
                intercepts[column], loadings[column] = 0.0, 1.0
                continue
            design = np.column_stack([np.ones(np.sum(valid)), means[valid]])
            weights = row_weights[valid]
            information = (design.T * weights) @ design + np.diag([ridge, 0.05])
            target = design.T @ (weights * matrix[valid, column])
            coefficient = np.linalg.solve(information, target)
            intercepts[column] = coefficient[0]
            loadings[column] = float(np.clip(coefficient[1], 0.10, 3.0))
        residual_cov = np.zeros((dimension, dimension))
        residual_n = np.zeros((dimension, dimension))
        for row_index, values in enumerate(matrix):
            observed = np.isfinite(values)
            residual = values - intercepts - loadings * means[row_index]
            indices = np.flatnonzero(observed)
            for left in indices:
                for right in indices:
                    residual_cov[left, right] += row_weights[row_index] * (
                        residual[left] * residual[right] + loadings[left] * loadings[right] * variances[row_index]
                    )
                    residual_n[left, right] += row_weights[row_index]
        covariance = np.divide(residual_cov, np.maximum(residual_n, 1.0))
        diagonal = np.diag(np.maximum(np.diag(covariance), 0.03))
        covariance = (1.0 - covariance_shrinkage) * covariance + covariance_shrinkage * diagonal
        covariance = (covariance + covariance.T) / 2.0 + np.eye(dimension) * ridge
        if robust_student_df is not None:
            for index, values in enumerate(matrix):
                observed = np.isfinite(values)
                residual = values[observed] - intercepts[observed] - loadings[observed] * means[index]
                precision = _safe_inverse(covariance[np.ix_(observed, observed)], ridge)
                distance = float(residual @ precision @ residual)
                row_weights[index] = (robust_student_df + int(np.sum(observed))) / (robust_student_df + distance)

    proxy_correlations: dict[str, float] = {}
    for column, name in enumerate(ordered[1:], 1):
        valid = np.isfinite(matrix[:, 0]) & np.isfinite(matrix[:, column])
        proxy_correlations[name] = float(np.corrcoef(matrix[valid, 0], matrix[valid, column])[0, 1]) if np.sum(valid) >= 3 else float("nan")
    return MeasurementFit(
        state=state, measurements=ordered, main=main, intercepts=intercepts,
        loadings=loadings, residual_covariance=covariance, prior_variance=prior_variance,
        training_rows=len(matrix), mean_posterior_sd=float(np.mean(np.sqrt(variances))),
        proxy_correlations=proxy_correlations, robust_student_df=robust_student_df,
    )


def estimate(row: dict[str, Any], fit: MeasurementFit, ridge: float = 1e-6) -> LatentEstimate:
    values = np.asarray([_number(row, f"{name}_z") for name in fit.measurements])
    mean, variance = _posterior(
        values, fit.intercepts, fit.loadings, fit.residual_covariance,
        fit.prior_variance, ridge,
    )
    observed = [name for name, value in zip(fit.measurements, values) if math.isfinite(float(value))]
    return LatentEstimate(mean=mean, variance=variance, observed=observed, main_observed=fit.main in observed)


def fit_all(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, MeasurementFit]:
    settings = config["measurement"]
    output = {}
    for state, measurements in settings["states"].items():
        output[state] = fit_measurement_state(
            rows, state=state, measurements=list(measurements), main=settings["main"][state],
            prior_variance=float(settings["prior_variance"]),
            covariance_shrinkage=float(settings["covariance_shrinkage"]),
            ridge=float(settings["ridge"]), iterations=int(settings["iterations"]),
            robust_student_df=float(settings["gold_student_df"]) if state == "gold" else None,
        )
    return output


def estimate_all(row: dict[str, Any], fits: dict[str, MeasurementFit]) -> dict[str, LatentEstimate]:
    return {state: estimate(row, fit) for state, fit in fits.items()}


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def directional_material_probability(estimate_: LatentEstimate, direction: float, threshold: float) -> float:
    sd = math.sqrt(max(estimate_.variance, 1e-12))
    return normal_cdf((direction * estimate_.mean - threshold) / sd)


def pair_directional_probability(
    parent: LatentEstimate, target: LatentEstimate, *, multiplier: float,
    threshold: float, seed: int, draws: int = 1024,
) -> float:
    rng = np.random.default_rng(seed)
    left = rng.normal(parent.mean, math.sqrt(max(parent.variance, 1e-12)), size=draws)
    right = rng.normal(target.mean, math.sqrt(max(target.variance, 1e-12)), size=draws)
    success = (np.sign(right) == np.sign(left) * multiplier) & (np.abs(right) >= threshold)
    return float(np.mean(success))

