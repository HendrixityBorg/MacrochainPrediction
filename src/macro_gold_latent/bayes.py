from __future__ import annotations

import math
import numpy as np


def sigmoid(values: np.ndarray | float) -> np.ndarray | float:
    array = np.asarray(values, dtype=float)
    output = np.empty_like(array)
    positive = array >= 0
    output[positive] = 1.0 / (1.0 + np.exp(-array[positive]))
    exponential = np.exp(array[~positive])
    output[~positive] = exponential / (1.0 + exponential)
    return float(output) if output.ndim == 0 else output


def fit_fractional_logistic_laplace(
    x: np.ndarray, y: np.ndarray, weights: np.ndarray, *,
    prior_sd_intercept: float, prior_sd_coefficient: float, ridge: float,
) -> tuple[np.ndarray, np.ndarray]:
    if x.ndim != 2 or len(x) != len(y) or len(y) != len(weights):
        raise ValueError("incompatible logistic shapes")
    dimension = x.shape[1]
    prior_sd = np.full(dimension, prior_sd_coefficient)
    prior_sd[0] = prior_sd_intercept
    prior_precision = np.diag(1.0 / np.maximum(prior_sd * prior_sd, ridge))
    coefficient = np.zeros(dimension)
    for _ in range(100):
        probability = np.clip(sigmoid(x @ coefficient), 1e-8, 1.0 - 1e-8)
        gradient = x.T @ (weights * (y - probability)) - prior_precision @ coefficient
        working = weights * probability * (1.0 - probability)
        information = (x.T * working) @ x + prior_precision + np.eye(dimension) * ridge
        step = np.linalg.solve(information, gradient)
        coefficient += step
        if float(np.max(np.abs(step))) < 1e-9:
            break
    probability = np.clip(sigmoid(x @ coefficient), 1e-8, 1.0 - 1e-8)
    working = weights * probability * (1.0 - probability)
    information = (x.T * working) @ x + prior_precision + np.eye(dimension) * ridge
    covariance = np.linalg.inv(information)
    covariance = (covariance + covariance.T) / 2.0
    values, vectors = np.linalg.eigh(covariance)
    covariance = vectors @ np.diag(np.maximum(values, ridge)) @ vectors.T
    return coefficient, covariance


def features(row: dict[str, str | float]) -> np.ndarray:
    root = float(row["root_z"])
    return np.asarray([1.0, float(np.clip(math.log1p(abs(root)), 0.0, 2.5)), 1.0 if root > 0 else -1.0])


def time_weights(rows: list[dict[str, str]], half_life_years: float) -> np.ndarray:
    if not rows:
        return np.empty(0)
    dates = np.asarray([np.datetime64(row["release_date"]) for row in rows])
    end = np.max(dates)
    years = (end - dates).astype("timedelta64[D]").astype(float) / 365.25
    raw = np.power(0.5, years / half_life_years)
    return raw * len(raw) / np.sum(raw)


def kish(weights: np.ndarray) -> float:
    denominator = float(np.sum(weights * weights))
    return float(np.sum(weights) ** 2 / denominator) if denominator > 0 else 0.0

