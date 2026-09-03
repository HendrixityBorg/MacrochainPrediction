from __future__ import annotations

from datetime import date
import math
import unittest

import numpy as np

from macro_gold_latent.config import load_config
from macro_gold_latent.evaluate import evaluate
from macro_gold_latent.model import primary_labels, reproduce_three_hops, run_model


MEASUREMENTS = [
    "policy_h15_2y", "policy_h15_1y", "policy_zt", "inflation_be5", "inflation_be10",
    "real_h15_5y", "real_h15_10y", "real_tip", "gold_gld", "gold_gc", "dollar_dxy", "dollar_uup",
]


def synthetic_rows() -> list[dict[str, str]]:
    rng = np.random.default_rng(88)
    rows = []
    for index in range(125):
        year = 2005 + index // 12
        month = index % 12 + 1
        root = rng.normal()
        policy = 0.75 * root + rng.normal(0, 0.9)
        real = 0.8 * policy + rng.normal(0, 0.8)
        gold = -0.9 * real + rng.normal(0, 1.0)
        values = {
            "policy_h15_2y": policy, "policy_h15_1y": policy + rng.normal(0, 0.3), "policy_zt": policy + rng.normal(0, 0.4),
            "inflation_be5": 0.25 * root + rng.normal(0, 0.8), "inflation_be10": 0.25 * root + rng.normal(0, 0.8),
            "real_h15_5y": real, "real_h15_10y": real + rng.normal(0, 0.3), "real_tip": real + rng.normal(0, 0.45),
            "gold_gld": gold, "gold_gc": gold + rng.normal(0, 0.35),
            "dollar_dxy": 0.3 * root + rng.normal(0, 0.8), "dollar_uup": 0.3 * root + rng.normal(0, 0.8),
        }
        row = {
            "event_id": f"S{index:03d}", "release_date": date(year, month, min(5, 28)).isoformat(),
            "split": "development" if index < 65 else "confirmation", "primary_complete": "1",
            "root_z": str(root), "external_cutoff": "0", "scheduled_cutoff": "0",
            "evidence_status": "development_seen" if index < 65 else "confirmation_protocol_locked",
        }
        for name, value in values.items():
            row[f"{name}_z"] = str(value)
        rows.append(row)
    return rows


class ModelTests(unittest.TestCase):
    def test_primary_labels(self) -> None:
        row = {"root_z": 2, "policy_h15_2y_z": 1.2, "real_h15_5y_z": 1.1, "gold_gld_z": -1.4}
        self.assertEqual(primary_labels(row, 1.0), [1, 1, 1])

    def test_end_to_end_and_reproduction(self) -> None:
        config = load_config()
        config["model"]["posterior_draws"] = 250
        rows = synthetic_rows()
        result = run_model(rows, config)
        self.assertEqual(result["confirmation_events"], 60)
        report = evaluate(result, config)
        self.assertTrue(math.isfinite(report["brier"]["latent_conditional_dynamic"]))
        for prediction in result["predictions"]:
            self.assertIn("execution_stop", prediction)
            self.assertEqual(sum(item["is_executed_stop"] for item in prediction["stop_trace"]), 1)
            self.assertTrue(all(item["uncertainty_decomposition"] for item in prediction["stop_trace"]))
        reproduction = reproduce_three_hops(result, rows, config)
        self.assertEqual(reproduction["maximum_absolute_delta"], 0.0)


if __name__ == "__main__":
    unittest.main()
