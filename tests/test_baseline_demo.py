from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from macro_gold_latent.baselines import add_direct_terminal_baseline
from macro_gold_latent.config import load_config
from macro_gold_latent.demo import live_demo_status, prepare_seal_input, precommit, seal, verify_precommitted, verify_sealed
from macro_gold_latent.model import run_model
from test_model import synthetic_rows


class BaselineDemoTests(unittest.TestCase):
    @staticmethod
    def _live_payload(now: datetime) -> dict:
        return {
            "event_id": "PROSPECTIVE_TEST", "topic": "cpi",
            "release_time_utc": (now + timedelta(hours=1)).isoformat(),
            "seal_deadline_utc": (now + timedelta(hours=2)).isoformat(),
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
            "outcome_windows": {"policy": "release-to-close", "real_rate": "release-to-close", "gold": "release-to-close"},
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
        self.assertEqual(probabilities, [row["direct_terminal_logistic_probability"] for row in first["predictions"]])

    def test_retroactive_demo_is_refused_before_any_write(self) -> None:
        now = datetime.now(timezone.utc)
        payload = {
            "event_id": "RETRO_TEST", "topic": "cpi",
            "release_time_utc": (now - timedelta(hours=2)).isoformat(),
            "seal_deadline_utc": (now - timedelta(hours=1)).isoformat(),
            "root_actual": 0.3, "root_consensus_or_nowcast": 0.2, "root_scale": 0.1,
            "tracking_due_utc": (now + timedelta(days=180)).isoformat(),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "deadline has passed"):
                seal(path, {"chain_probability": 0.2})

    def test_two_stage_demo_binds_pre_release_fields_and_timeline(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        payload = self._live_payload(now)
        with tempfile.TemporaryDirectory() as directory:
            root = self._temporary_evidence_root(directory)
            input_path = root / "input.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            lock = {"valid": True, "protocol_sha256": "protocol-test"}
            with patch("macro_gold_latent.demo.verify_lock", return_value=lock), patch("macro_gold_latent.demo._now", return_value=now):
                committed = precommit(input_path, root=root)
                self.assertTrue(verify_precommitted(root / "demo" / "precommitted" / "PROSPECTIVE_TEST.json", root=root)["valid"])
                with self.assertRaisesRegex(FileExistsError, "cannot be overwritten"):
                    precommit(input_path, root=root)
                payload["root_actual"] = 0.3
                payload["root_actual_source"] = {
                    "source_id": "actual", "url": "https://example.test/actual",
                    "retrieved_at_utc": (now + timedelta(hours=1, minutes=10)).isoformat(),
                    "sha256": "actual-evidence-hash",
                }
                input_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "has not occurred"):
                    seal(input_path, {"chain_probability": 0.2}, root=root)

            released = now + timedelta(hours=1, minutes=10)
            with patch("macro_gold_latent.demo.verify_lock", return_value=lock), patch("macro_gold_latent.demo._now", return_value=released):
                sealed = seal(input_path, {"chain_probability": 0.2}, root=root)
                self.assertEqual(sealed["precommit_sha256"], committed["precommit_sha256"])
                self.assertTrue(verify_sealed(root / "demo" / "sealed" / "PROSPECTIVE_TEST.json", root=root)["valid"])
                self.assertTrue(live_demo_status(root=root)["passes"])
                withdrawal = root / "demo" / "withdrawals" / "PROSPECTIVE_TEST.json"
                withdrawal.parent.mkdir(parents=True)
                withdrawal.write_text(json.dumps({
                    "event_id": "PROSPECTIVE_TEST",
                    "status": "WITHDRAWN_NOT_USED_FOR_SUBMISSION",
                }), encoding="utf-8")
                status = live_demo_status(root=root)
                self.assertFalse(status["passes"])
                self.assertEqual(status["valid_pre_release_commitments"], 0)

    def test_post_release_change_to_precommitted_scale_is_refused(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        payload = self._live_payload(now)
        with tempfile.TemporaryDirectory() as directory:
            root = self._temporary_evidence_root(directory)
            input_path = root / "input.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            lock = {"valid": True, "protocol_sha256": "protocol-test"}
            with patch("macro_gold_latent.demo.verify_lock", return_value=lock), patch("macro_gold_latent.demo._now", return_value=now):
                precommit(input_path, root=root)
            released = now + timedelta(hours=1, minutes=10)
            payload["root_actual"] = 0.3
            payload["root_scale"] = 0.2
            payload["root_actual_source"] = {
                "source_id": "actual", "url": "https://example.test/actual",
                "retrieved_at_utc": released.isoformat(), "sha256": "actual-evidence-hash",
            }
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("macro_gold_latent.demo.verify_lock", return_value=lock), patch("macro_gold_latent.demo._now", return_value=released):
                with self.assertRaisesRegex(ValueError, "root_scale"):
                    seal(input_path, {"chain_probability": 0.2}, root=root)

    def test_prepare_seal_input_only_adds_actual_and_hash_bound_source(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        payload = self._live_payload(now)
        with tempfile.TemporaryDirectory() as directory:
            root = self._temporary_evidence_root(directory)
            input_path = root / "input.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            lock = {"valid": True, "protocol_sha256": "protocol-test"}
            with patch("macro_gold_latent.demo.verify_lock", return_value=lock), patch("macro_gold_latent.demo._now", return_value=now):
                committed = precommit(input_path, root=root)
            released = now + timedelta(hours=1, minutes=10)
            source = root / "demo" / "evidence" / "actual.txt"
            source.parent.mkdir(parents=True)
            source.write_text("official actual: 123", encoding="utf-8")
            os.utime(source, (released.timestamp(), released.timestamp()))
            prepared_path = root / "demo" / "seal_inputs" / "PROSPECTIVE_TEST.json"
            with patch("macro_gold_latent.demo.verify_lock", return_value=lock), patch("macro_gold_latent.demo._now", return_value=released):
                result = prepare_seal_input(
                    event_id="PROSPECTIVE_TEST", root_actual=123,
                    actual_source_path=source, actual_source_url="https://example.test/actual",
                    output_path=prepared_path, root=root,
                )
                prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
                for key in committed["input"]:
                    if key != "root_actual":
                        self.assertEqual(prepared[key], committed["input"][key])
                self.assertEqual(prepared["root_actual"], 123.0)
                self.assertEqual(result["root_z"], 1228.0)
                source.write_text("tampered", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "local hash mismatch"):
                    seal(prepared_path, {"chain_probability": 0.2}, root=root)

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
