from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from macro_gold_latent.baselines import add_direct_terminal_baseline
from macro_gold_latent.config import load_config
from macro_gold_latent.demo import precommit, verify_precommitted
from macro_gold_latent.model import run_model
from test_model import synthetic_rows


class BaselineDemoTests(unittest.TestCase):
    @staticmethod
    def _live_payload(now: datetime) -> dict:
        return {
            "event_id": "PROSPECTIVE_TEST", "topic": "cpi",
            "release_time_utc": (now + timedelta(hours=1)).isoformat(),
            "downstream_outcome_available_after_utc": (now + timedelta(hours=8)).isoformat(),
            "root_measure": "core_cpi_first_release_mom_pct",
            "root_actual": None,
            "root_consensus_or_nowcast": 0.2, "root_scale": 0.1,
            "expectation_asof_utc": (now - timedelta(minutes=2)).isoformat(),
            "scale_asof_utc": (now - timedelta(minutes=1)).isoformat(),
            "pre_event_features": {"policy_regime": "test"},
            "source_records": [{
                "source_id": "pre", "url": "https://example.test/pre",
                "retrieved_at_utc": now.isoformat(), "sha256": "external-evidence-hash",
            }],
            "outcome_windows": {
                "policy": "release-to-close", "real_rate": "release-to-close", "gold": "release-to-close",
            },
            "decision_rule": {"maximum_ci_width": 0.3, "break_even_probability": 0.208},
            "tracking_due_utc": (now + timedelta(days=180)).isoformat(),
        }

    @staticmethod
    def _temporary_evidence_root(directory: str) -> Path:
        root = Path(directory)
        (root / "reports").mkdir(parents=True)
        (root / "data" / "frozen").mkdir(parents=True)
        (root / "reports" / "model_run.json").write_text("{}", encoding="utf-8")
        (root / "data" / "frozen" / "events.csv").write_text("event_id\n", encoding="utf-8")
        return root

    def test_direct_baseline_does_not_read_confirmation_outcomes(self) -> None:
        config = load_config()
        config["model"]["posterior_draws"] = 80
        rows = synthetic_rows()
        first = run_model(rows, config)
        add_direct_terminal_baseline(first, rows, config)
        probabilities = [row["direct_terminal_logistic_probability"] for row in first["predictions"]]
        for row in first["predictions"]:
            if row["outcome"] is not None:
                row["outcome"] = 1 - row["outcome"]
        add_direct_terminal_baseline(first, rows, config)
        self.assertEqual(
            probabilities,
            [row["direct_terminal_logistic_probability"] for row in first["predictions"]],
        )

    def test_precommit_binds_method_before_release(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        payload = self._live_payload(now)
        with tempfile.TemporaryDirectory() as directory:
            root = self._temporary_evidence_root(directory)
            input_path = root / "input.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            lock = {"valid": True, "protocol_sha256": "protocol-test"}
            with patch("macro_gold_latent.demo.verify_lock", return_value=lock), patch(
                "macro_gold_latent.demo._now", return_value=now,
            ):
                committed = precommit(input_path, root=root)
                check = verify_precommitted(
                    root / "demo" / "precommitted" / "PROSPECTIVE_TEST.json", root=root,
                )
                self.assertTrue(check["valid"])
                self.assertEqual(
                    committed["input"]["downstream_outcome_available_after_utc"],
                    payload["downstream_outcome_available_after_utc"],
                )
                with self.assertRaisesRegex(FileExistsError, "cannot be overwritten"):
                    precommit(input_path, root=root)

    def test_retroactive_precommit_is_refused(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        payload = self._live_payload(now)
        payload["release_time_utc"] = (now - timedelta(hours=1)).isoformat()
        payload["downstream_outcome_available_after_utc"] = (now + timedelta(hours=1)).isoformat()
        payload["expectation_asof_utc"] = (now - timedelta(hours=2)).isoformat()
        payload["scale_asof_utc"] = (now - timedelta(hours=2)).isoformat()
        payload["source_records"][0]["retrieved_at_utc"] = (now - timedelta(hours=2)).isoformat()
        with tempfile.TemporaryDirectory() as directory:
            root = self._temporary_evidence_root(directory)
            input_path = root / "input.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("macro_gold_latent.demo._now", return_value=now):
                with self.assertRaisesRegex(ValueError, "release has occurred"):
                    precommit(input_path, root=root)

    def test_precommit_rejects_rule_that_differs_from_executable_threshold(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        payload = self._live_payload(now)
        payload["decision_rule"]["break_even_probability"] = 0.26
        with tempfile.TemporaryDirectory() as directory:
            root = self._temporary_evidence_root(directory)
            input_path = root / "input.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from executable payoff formula"):
                precommit(input_path, root=root)


if __name__ == "__main__":
    unittest.main()
