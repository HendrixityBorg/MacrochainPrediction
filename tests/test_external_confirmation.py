from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from macro_gold_latent.external_confirmation import audit_bundle
from macro_gold_latent.io import sha256_file


class ExternalConfirmationTests(unittest.TestCase):
    def test_fifty_event_bundle_is_sealed_before_label_unlock(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            bundle = Path(directory) / "bundle"
            (root / "reports").mkdir(parents=True)
            (root / "data" / "frozen").mkdir(parents=True)
            bundle.mkdir()
            (root / "reports" / "model_run.json").write_text("{}", encoding="utf-8")
            (root / "data" / "frozen" / "events.csv").write_text("event_id\nOLD_EVENT\n", encoding="utf-8")
            prediction_fields = [
                "event_id", "predicted_at_utc", "label_unlock_not_before_utc",
                "chain_probability", "ci_lower", "ci_upper",
                "p_1", "p_2", "p_3", "n_1", "n_2", "n_3",
            ]
            with (bundle / "predictions.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=prediction_fields)
                writer.writeheader()
                for index in range(50):
                    writer.writerow({
                        "event_id": f"NEW_{index:03d}",
                        "predicted_at_utc": now.isoformat(),
                        "label_unlock_not_before_utc": (now + timedelta(days=1)).isoformat(),
                        "chain_probability": 0.1, "ci_lower": 0.02, "ci_upper": 0.25,
                        "p_1": 0.5, "p_2": 0.5, "p_3": 0.4,
                        "n_1": 60, "n_2": 20, "n_3": 10,
                    })
            manifest = {
                "batch_id": "NEW_V1", "topic": "new_macro_family",
                "created_at_utc": now.isoformat(), "protocol_sha256": "protocol-test",
                "model_run_sha256": sha256_file(root / "reports" / "model_run.json"),
                "custodian_attestation_reference": "signed:test",
                "prediction_file_sha256": sha256_file(bundle / "predictions.csv"),
                "minimum_events": 50,
            }
            (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            lock = {"valid": True, "protocol_sha256": "protocol-test"}
            with patch("macro_gold_latent.external_confirmation.verify_lock", return_value=lock):
                before = audit_bundle(bundle, root=root)
                self.assertTrue(before["eligible"], before)
                with (bundle / "labels.csv").open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=["event_id", "outcome", "label_available_at_utc"])
                    writer.writeheader()
                    for index in range(50):
                        writer.writerow({
                            "event_id": f"NEW_{index:03d}", "outcome": index % 2,
                            "label_available_at_utc": (now + timedelta(days=1)).isoformat(),
                        })
                self.assertFalse(audit_bundle(bundle, root=root)["eligible"])
                after = audit_bundle(bundle, root=root, unlocked=True)
                self.assertTrue(after["eligible"], after)
                self.assertEqual(after["labels_checked"], 50)


if __name__ == "__main__":
    unittest.main()

