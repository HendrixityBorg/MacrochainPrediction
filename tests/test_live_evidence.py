from __future__ import annotations

import statistics
import unittest
from unittest.mock import patch

from macro_gold_latent.config import ROOT
from macro_gold_latent.data import _first_releases, _root_innovations
from macro_gold_latent.demo import verify_current_demo, verify_precommitted
from macro_gold_latent.io import read_json


class LiveEvidenceTests(unittest.TestCase):
    def test_selected_nfp_precommit_reproduces_locked_root_transform(self) -> None:
        event_id = "NFP_202608_REL_20260904_A004"
        committed = read_json(ROOT / "demo" / "precommitted" / f"{event_id}.json")
        evidence = read_json(ROOT / "demo" / "evidence" / "NFP_202608_root_definition_20260903.json")
        first = _first_releases(ROOT / "data" / "raw" / "employ.xlsx")
        ordered = sorted(first)
        expected = statistics.median(first[item] for item in ordered[-12:])
        synthetic = dict(first)
        synthetic["2026:08"] = expected
        derived = _root_innovations(synthetic)["2026:08"]
        record = committed["input"]
        self.assertEqual(ordered[-1], "2026:07")
        self.assertAlmostEqual(expected, evidence["expected_change_thousands"], places=14)
        self.assertAlmostEqual(derived["scale"], evidence["root_scale_thousands"], places=14)
        self.assertAlmostEqual(record["root_consensus_or_nowcast"], expected, places=14)
        self.assertAlmostEqual(record["root_scale"], derived["scale"], places=14)
        self.assertTrue(verify_precommitted(ROOT / "demo" / "precommitted" / f"{event_id}.json")["valid"])

    def test_current_nfp_prediction_precedes_downstream_outcomes(self) -> None:
        path = ROOT / "demo" / "current" / "NFP_202608_REL_20260904_A004.json"
        check = verify_current_demo(path)
        self.assertTrue(check["valid"])
        self.assertTrue(check["git_evidence_valid"] or check["evidence_snapshot_valid"])
        self.assertTrue(check["prediction_matches_prior_commit"])
        self.assertTrue(check["timeline_valid"])
        self.assertTrue(check["actual_source_valid"])

    def test_current_demo_can_be_verified_from_distributed_snapshot_without_git(self) -> None:
        path = ROOT / "demo" / "current" / "NFP_202608_REL_20260904_A004.json"
        with patch("macro_gold_latent.demo._git_blob", side_effect=FileNotFoundError):
            check = verify_current_demo(path)
        self.assertTrue(check["valid"])
        self.assertFalse(check["git_evidence_valid"])
        self.assertTrue(check["evidence_snapshot_valid"])


if __name__ == "__main__":
    unittest.main()
