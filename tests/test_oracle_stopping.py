from __future__ import annotations

import unittest
import numpy as np

from macro_gold_latent.config import load_config
from macro_gold_latent.oracle import run_oracle
from macro_gold_latent.sensitivity import chain_evidence_strength_response
from macro_gold_latent.stopping import decide, evidence_update_demo


class OracleStoppingTests(unittest.TestCase):
    def test_evidence_response(self) -> None:
        result = chain_evidence_strength_response(draws=20000)
        self.assertTrue(result["center_moves_up"])
        self.assertTrue(result["ci_narrows"])

    def test_stop_rejects_low_upper_bound(self) -> None:
        result = decide(np.full(500, 0.03), hop=1, terminal_hop=3, config=load_config())
        self.assertEqual(result.state, "STOP_REJECT")

    def test_oracle_coverage(self) -> None:
        config = load_config()
        config["oracle"]["rows"] = 240
        config["oracle"]["draws"] = 300
        result = run_oracle(config)
        self.assertGreaterEqual(result["test_coverage"], 0.80)


if __name__ == "__main__":
    unittest.main()
