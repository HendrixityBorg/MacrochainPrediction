from __future__ import annotations

import unittest
import numpy as np

from macro_gold_latent.latent import estimate, fit_measurement_state


class LatentTests(unittest.TestCase):
    def test_main_anchor_and_multiple_measurements(self) -> None:
        rng = np.random.default_rng(42)
        rows = []
        for latent in rng.normal(size=80):
            rows.append({"main_z": latent + rng.normal(0, 0.5), "proxy_z": 0.2 + 1.3 * latent + rng.normal(0, 0.5)})
        fit = fit_measurement_state(
            rows, state="x", measurements=["main", "proxy"], main="main",
            prior_variance=4.0, covariance_shrinkage=0.3, ridge=1e-6, iterations=25,
        )
        self.assertEqual(fit.loadings[0], 1.0)
        self.assertEqual(fit.intercepts[0], 0.0)
        both = estimate({"main_z": 0.8, "proxy_z": 1.1}, fit)
        main_only = estimate({"main_z": 0.8, "proxy_z": ""}, fit)
        self.assertLess(both.variance, main_only.variance)


if __name__ == "__main__":
    unittest.main()

