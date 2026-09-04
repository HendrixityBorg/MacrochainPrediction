from __future__ import annotations

import unittest

from macro_gold_latent.config import ROOT
from macro_gold_latent.io import read_json
from macro_gold_latent.report import chinese_live_demo_report


class ChineseReportingTests(unittest.TestCase):
    def test_live_report_contains_required_end_to_end_fields(self) -> None:
        model_run = read_json(ROOT / "reports" / "model_run.json")
        prediction = model_run["predictions"][0]
        payload = {
            "status": "current_macro_demo_outcomes_unresolved",
            "prediction_recorded_at_utc": "2026-09-04T14:03:26+00:00",
            "downstream_outcome_available_after_utc": "2026-09-04T20:00:00+00:00",
            "protocol_sha256": "protocol",
            "precommit_sha256": "precommit",
            "current_demo_sha256": "current-record",
            "prediction_evidence": {"git_commit": "commit"},
            "input": {
                "event_id": "REPORT_TEST",
                "root_measure": "total_nonfarm_payroll_first_release_monthly_change_thousands",
                "root_actual": 100.0,
                "root_consensus_or_nowcast": 68.5,
                "root_scale": 124.42677605270522,
                "root_actual_source": {
                    "summary_url": "https://www.bls.gov/news.release/empsit.nr0.htm",
                    "retrieved_at_utc": "2026-09-04T12:31:00+00:00",
                    "cross_check": "test",
                    "record_sha256_at_commit": "source",
                },
                "decision_rule": {
                    "break_even_probability": 0.208,
                    "maximum_ci_width": 0.3,
                },
            },
            "prediction": prediction,
        }
        report = chinese_live_demo_report(payload, model_run)
        for required in (
            "BLS 官方 actual", "每跳概率", "90% CI", "外部截断概率",
            "每跳停止判断", "交易决策", "当期记录 SHA-256", "反事实诊断",
            "第一跳为什么停止", "不是对因果链或模型有效性的单样本否定",
        ):
            self.assertIn(required, report)


if __name__ == "__main__":
    unittest.main()
