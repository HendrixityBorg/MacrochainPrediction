from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import ROOT
from .demo import live_demo_status
from .io import read_json
from .locking import verify_lock
from .stopping import break_even_probability


def _gate(passed: bool, evidence: Any) -> dict[str, Any]:
    return {"passed": bool(passed), "evidence": evidence}


def evaluate_gates(
    model_run: dict[str, Any], evaluation: dict[str, Any], oracle: dict[str, Any],
    reproduction: dict[str, Any], evidence_update: dict[str, Any], config: dict[str, Any],
) -> dict[str, Any]:
    required_files = [
        "README.md", "requirements.txt", "requirements.lock.txt", "config/default.json", "run.sh", "test.sh", "Dockerfile",
        ".dockerignore", "DATA_NOTICE.md",
        "docs/METHODOLOGY.zh-CN.md", "docs/DATA_SOURCES.zh-CN.md",
        "preregistration/CONFIRMATION_PROTOCOL.zh-CN.md", "demo/TRACKING_PLAN.zh-CN.md",
        "data/raw/employ.xlsx", "data/raw/h15_nominal.csv", "data/raw/h15_real.csv",
        "data/raw/release_dates_50.txt",
    ]
    repository_files = {path: (ROOT / path).exists() for path in required_files}
    predictions = model_run["predictions"]
    settings = config["evaluation"]
    scores = evaluation["brier"]
    lock = verify_lock()
    live = live_demo_status()
    active_precommits = [
        read_json(Path(item["path"])) for item in live["precommit_records"]
        if item.get("valid") and item.get("eligible_for_submission")
    ]
    expected_break_even = break_even_probability(config)
    decision_rules_match = bool(active_precommits) and all(
        abs(float(item["input"]["decision_rule"]["break_even_probability"]) - expected_break_even) <= 1e-12
        and abs(
            float(item["input"]["decision_rule"]["maximum_ci_width"])
            - float(config["stopping"]["maximum_interval_width"])
        ) <= 1e-12
        for item in active_precommits
    )
    package_audit_path = ROOT / "reports" / "submission_package_audit.json"
    package_audit = read_json(package_audit_path) if package_audit_path.exists() else {
        "passes": False, "reason": "clean_git_clone_audit_not_run"
    }
    hop_rates = [item["prefix_rate"] for item in evaluation["hop_decay"]]
    gates = {
        "repository_complete": _gate(all(repository_files.values()), repository_files),
        "isolated_reproduction": _gate(
            (ROOT / "Dockerfile").exists()
            and reproduction["maximum_absolute_delta"] <= float(settings["maximum_reproduction_delta"])
            and bool(package_audit.get("passes")),
            {"three_hop_reproduction": reproduction, "clean_git_clone": package_audit},
        ),
        "per_hop_probability_and_effective_n": _gate(bool(model_run["edge_evidence"]) and all(len(row["p_i"]) == 3 and all(n > 0 for n in row["n_i"]) for row in predictions), {"evidence_rows": len(model_run["edge_evidence"])}),
        "non_naive_model": _gate(scores["latent_conditional_dynamic"] < scores["naive_marginal_product"], {"proposed_brier": scores["latent_conditional_dynamic"], "naive_brier": scores["naive_marginal_product"]}),
        "intrinsic_vs_external_separated": _gate(all("intrinsic_probability" in row and "interruption_probability" in row for row in predictions), {"rows": len(predictions)}),
        "principled_stopping": _gate(all(
            len(row["stop_trace"]) == 3
            and all(item["reason"] and "execution_reached" in item for item in row["stop_trace"])
            and sum(bool(item["is_executed_stop"]) for item in row["stop_trace"]) == 1
            and row["execution_stop"]["state"] != "CONTINUE"
            for row in predictions
        ), {"criteria": ["credible bound", "EVSI", "review cost", "terminal state", "maximum-hop guardrail", "first actionable stop execution"]}),
        "confirmation_n_ge_50": _gate(evaluation["confirmation_events"] >= int(settings["minimum_confirmation_events"]), evaluation["confirmation_events"]),
        "brier_lt_0_15": _gate(scores["latent_conditional_dynamic"] < float(settings["maximum_brier"]), scores["latent_conditional_dynamic"]),
        "terminal_positives_ge_10": _gate(evaluation["terminal_successes"] >= int(settings["minimum_terminal_positives"]), evaluation["terminal_successes"]),
        "positive_skill_vs_climatology": _gate(evaluation["brier_skill_vs_climatology"] > 0, evaluation["brier_skill_vs_climatology"]),
        "root_ablation_improves": _gate(scores["latent_conditional_dynamic"] < scores["no_root_ablation"], {"full": scores["latent_conditional_dynamic"], "no_root": scores["no_root_ablation"]}),
        "reliability_report": _gate(bool(evaluation["reliability"]["bins"]), evaluation["reliability"]),
        "hop_decay_report": _gate(all(left >= right for left, right in zip(hop_rates, hop_rates[1:])), evaluation["hop_decay"]),
        "epistemic_ci": _gate(all(
            row["ci_width"] > 0
            and row["uncertainty_decomposition"]
            and all(item.get("uncertainty_decomposition") for item in row["stop_trace"])
            for row in predictions
        ), {"sources": ["measurement", "link parameters", "regime drift", "external cutoff", "common frailty"], "scope": "each prefix and full chain"}),
        "oracle_90ci_coverage_ge_0_85": _gate(oracle["test_coverage"] >= float(settings["minimum_oracle_coverage"]), oracle["test_coverage"]),
        "ci_width_error_positive_significant": _gate(evaluation["ci_width_error"]["direction_ok"], evaluation["ci_width_error"]),
        "evidence_strength_bayesian_direction": _gate(evidence_update["center_moves_up"] and evidence_update["ci_narrows"], evidence_update),
        "rare_method_calibration_n_ge_20": _gate(
            not evaluation["rare_method_calibration"]["rare_event_clause_applicable"]
            or evaluation["rare_method_calibration"]["minimum_known_outcomes"] >= 20,
            evaluation["rare_method_calibration"],
        ),
        "three_hop_reproduction_within_0_05": _gate(reproduction["maximum_absolute_delta"] <= float(settings["maximum_reproduction_delta"]), reproduction),
        "live_decision_rule_matches_executable": _gate(decision_rules_match, {
            "active_precommits": [item["input"]["event_id"] for item in active_precommits],
            "expected_break_even_probability": expected_break_even,
            "expected_maximum_ci_width": float(config["stopping"]["maximum_interval_width"]),
        }),
        "complete_report": _gate(
            (ROOT / "reports" / "SUBMISSION_REPORT.zh-CN.md").exists()
            and (not live["passes"] or all(
                (ROOT / "demo" / "runs" / f"{item['event_id']}.zh-CN.md").exists()
                for item in live["records"] if item.get("valid") and item.get("eligible_for_submission")
            )),
            {"main": "reports/SUBMISSION_REPORT.zh-CN.md", "live_chinese_report_required_after_seal": True},
        ),
        "prospective_current_macro_demo": _gate(live["passes"], live),
        "six_month_tracking_plan": _gate((ROOT / "demo" / "TRACKING_PLAN.zh-CN.md").exists(), "demo/TRACKING_PLAN.zh-CN.md"),
    }
    required = read_json(ROOT / "preregistration" / "S_GRADE_MATRIX.json")["required"]
    missing = [name for name in required if not gates.get(name, {}).get("passed")]
    return {
        "status": "S_READY" if not missing else "NOT_S_READY",
        "full_s_evidence_complete": not missing,
        "protocol_lock": lock,
        "gates": gates,
        "failed_required_gates": missing,
        "claim_policy": "S_READY means the explicit challenge-aligned machine gates pass. Diagnostic failures, label-access limitations and amendments remain mandatory disclosures and are never tuning prompts.",
    }
