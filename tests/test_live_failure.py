from __future__ import annotations

import unittest

from macro_gold_latent.report import latest_live_failure


class LiveFailureTests(unittest.TestCase):
    def test_missed_legacy_window_record_is_retained(self) -> None:
        failure = latest_live_failure()
        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertEqual(failure["status"], "MISSED_SEAL_WINDOW_FAIL_CLOSED")
        self.assertFalse(failure["eligible_for_submission"])
        self.assertFalse(failure["failure"]["seal_input_written"])
        self.assertFalse(failure["failure"]["sealed_record_written"])
        self.assertFalse(
            failure["official_actual_observed_after_deadline"]["observation_is_valid_seal_evidence"]
        )


if __name__ == "__main__":
    unittest.main()
