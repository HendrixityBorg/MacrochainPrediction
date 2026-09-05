from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .config import ROOT, load_config
from .baselines import add_direct_terminal_baseline
from .audit_ledger import latent_state_rows
from .data import acquire, build_dataset, build_events, load_events
from .demo import precommit, verify_current_demo
from .evaluate import evaluate
from .gates import evaluate_gates
from .io import read_csv, read_json, sha256_file, write_csv, write_json
from .locking import freeze, freeze_amendment, verify_lock
from .model import reproduce_three_hops, run_model
from .oracle import run_oracle
from .quality import audit as audit_quality, markdown as quality_markdown
from .report import (
    chinese_report, plots, reliability_rows, selected_live_demo_payload,
    write_live_demo_report,
)
from .sensitivity import chain_evidence_strength_response


def _flat_predictions(model_run: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for row in model_run["predictions"]:
        hop_outcomes = row["hop_outcomes"] or ["", "", ""]
        output.append({
            "event_id": row["event_id"], "release_date": row["release_date"], "split": row["split"],
            "p_1": row["p_i"][0], "p_2": row["p_i"][1], "p_3": row["p_i"][2],
            "n_1": row["n_i"][0], "n_2": row["n_i"][1], "n_3": row["n_i"][2],
            "intrinsic_probability": row["intrinsic_probability"], "interruption_probability": row["interruption_probability"],
            "chain_probability": row["chain_probability"], "ci_lower": row["ci_lower"], "ci_upper": row["ci_upper"],
            "ci_width": row["ci_width"], "outcome": row["outcome"],
            "hop_1_outcome": hop_outcomes[0], "hop_2_outcome": hop_outcomes[1], "hop_3_outcome": hop_outcomes[2],
            "stop_hop": row["execution_stop"]["hop"],
            "stop_state": row["execution_stop"]["state"], "stop_reason": row["execution_stop"]["reason"],
            "naive_marginal_probability": row["naive_marginal_probability"],
            "conditional_beta_probability": row["conditional_beta_probability"],
            "primary_only_probability": row["primary_only_probability"], "proxy_only_probability": row["proxy_only_probability"],
            "no_root_probability": row["no_root_probability"], "posterior_seed": row["posterior_seed"],
            "direct_terminal_logistic_probability": row.get("direct_terminal_logistic_probability"),
        })
    return output


def _flat_stop_trace(model_run: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for row in model_run["predictions"]:
        for item in row["stop_trace"]:
            output.append({
                "event_id": row["event_id"], "release_date": row["release_date"], "hop": item["hop"],
                "p_i": item["p_i"], "n_i": item["n_i"], "prefix_probability": item["probability"],
                "ci_lower": item["ci_lower"], "ci_upper": item["ci_upper"], "ci_width": item["ci_width"],
                "state": item["state"], "reason": item["reason"], "evsi": item["evsi"],
                "review_cost": item["review_cost"], "break_even_probability": item["break_even_probability"],
                "execution_reached": item["execution_reached"],
                "is_executed_stop": item["is_executed_stop"], "evaluation_mode": item["evaluation_mode"],
                "link_parameter_variance_share": item["uncertainty_decomposition"]["link_parameter_variance_share"],
                "measurement_variance_share": item["uncertainty_decomposition"]["measurement_variance_share"],
                "regime_drift_variance_share": item["uncertainty_decomposition"]["regime_drift_variance_share"],
                "common_frailty_variance_share": item["uncertainty_decomposition"]["common_frailty_variance_share"],
                "external_cutoff_variance_share": item["uncertainty_decomposition"]["external_cutoff_variance_share"],
            })
    return output


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    if args.build_data:
        legacy = Path(args.legacy_source).resolve() if args.legacy_source else None
        frozen_path = ROOT / "data" / "frozen" / "events.csv"
        if frozen_path.exists():
            sources = acquire(legacy_source=legacy, refresh=args.refresh)
            rebuilt = build_events(config, sources)
            existing = read_csv(frozen_path)
            fields = list(existing[0]) if existing else []
            normalized = [{key: str(row.get(key, "")) for key in fields} for row in rebuilt]
            comparison = {
                "mode": "non_destructive_rebuild_audit", "matches_frozen_exactly": existing == normalized,
                "frozen_rows": len(existing), "rebuilt_rows": len(normalized),
                "frozen_sha256": sha256_file(frozen_path),
                "note": "Amended protocol never overwrites confirmation v1; a differing rebuild requires a new dataset version.",
            }
            write_json(ROOT / "reports" / "data_rebuild_audit.json", comparison)
            if not comparison["matches_frozen_exactly"]:
                raise RuntimeError("public-source rebuild differs from frozen v1; overwrite refused")
        else:
            build_dataset(config, legacy_source=legacy, refresh=args.refresh)
    rows = load_events()
    model_run = run_model(rows, config)
    extra_baseline = add_direct_terminal_baseline(model_run, rows, config)
    evaluation = evaluate(model_run, config)
    evaluation["brier"]["direct_terminal_logistic"] = extra_baseline["brier"]
    evaluation["baseline_details"] = {"direct_terminal_logistic": extra_baseline}
    oracle = run_oracle(config)
    reproduction = reproduce_three_hops(model_run, rows, config)
    update = chain_evidence_strength_response()
    quality = audit_quality(rows, config)
    report_dir = ROOT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    write_json(report_dir / "model_run.json", model_run)
    write_json(report_dir / "edge_evidence.json", model_run["edge_evidence"])
    write_csv(report_dir / "latent_state_ledger.csv", latent_state_rows(model_run, rows))
    write_csv(report_dir / "prediction_ledger.csv", _flat_predictions(model_run))
    write_csv(report_dir / "stop_trace.csv", _flat_stop_trace(model_run))
    write_json(report_dir / "evaluation.json", evaluation)
    write_json(report_dir / "baseline_report.json", {**model_run["baselines"], "direct_terminal_logistic": extra_baseline})
    write_csv(report_dir / "reliability_table.csv", reliability_rows(evaluation))
    write_csv(report_dir / "hop_decay.csv", evaluation["hop_decay"])
    write_json(report_dir / "oracle.json", oracle)
    write_json(report_dir / "three_hop_reproduction.json", reproduction)
    write_json(report_dir / "evidence_update.json", update)
    write_json(report_dir / "data_quality.json", quality)
    (report_dir / "DATA_QUALITY_REPORT.md").write_text(quality_markdown(quality), encoding="utf-8")
    plots(evaluation)
    report_path = report_dir / "SUBMISSION_REPORT.md"
    live_payload = selected_live_demo_payload()
    if live_payload:
        write_live_demo_report(live_payload, model_run)
    report_path.write_text(
        chinese_report(model_run, evaluation, oracle, reproduction, update, None, live_payload),
        encoding="utf-8",
    )
    gate = evaluate_gates(model_run, evaluation, oracle, reproduction, update, config)
    gate["supplemental_integrity_gate"] = {"passed": quality["passes"], "evidence": "reports/data_quality.json"}
    if not quality["passes"]:
        gate["status"] = "NOT_S_READY"
        gate["full_s_evidence_complete"] = False
        gate["failed_required_gates"].append("supplemental_data_integrity")
    write_json(report_dir / "s_grade_gate.json", gate)
    report_path.write_text(
        chinese_report(model_run, evaluation, oracle, reproduction, update, gate, live_payload),
        encoding="utf-8",
    )
    write_json(report_dir / "reproduction.json", {
        "command": "python -m macro_gold_latent.cli run --offline",
        "dataset_sha256": sha256_file(ROOT / "data" / "frozen" / "events.csv"),
        "protocol_lock": verify_lock(), "outputs": {
            name: sha256_file(report_dir / name) for name in (
                "evaluation.json", "oracle.json", "prediction_ledger.csv", "three_hop_reproduction.json"
            )
        },
    })
    # Re-evaluate once the reproduction manifest exists; no empirical value changes.
    gate = evaluate_gates(model_run, evaluation, oracle, reproduction, update, config)
    gate["supplemental_integrity_gate"] = {"passed": quality["passes"], "evidence": "reports/data_quality.json"}
    if not quality["passes"]:
        gate["status"] = "NOT_S_READY"
        gate["full_s_evidence_complete"] = False
        gate["failed_required_gates"].append("supplemental_data_integrity")
    write_json(report_dir / "s_grade_gate.json", gate)
    report_path.write_text(
        chinese_report(model_run, evaluation, oracle, reproduction, update, gate, live_payload),
        encoding="utf-8",
    )
    return gate


def command_precommit_demo(args: argparse.Namespace) -> int:
    result = precommit(Path(args.input))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="macro-gold-s")
    root.add_argument("--config", default=str(ROOT / "config" / "default.json"))
    commands = root.add_subparsers(dest="command", required=True)
    freeze_parser = commands.add_parser("freeze-protocol")
    freeze_parser.add_argument("--amendment-file")
    freeze_parser.add_argument("--no-independent-acceptance", action="store_true")
    run = commands.add_parser("run")
    run.add_argument("--offline", action="store_true")
    run.add_argument("--build-data", action="store_true")
    run.add_argument("--legacy-source")
    run.add_argument("--refresh", action="store_true")
    commands.add_parser("oracle")
    commands.add_parser("verify")
    current_parser = commands.add_parser("verify-current-demo")
    current_parser.add_argument("--input", required=True)
    precommit_parser = commands.add_parser("precommit-demo")
    precommit_parser.add_argument("--input", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "freeze-protocol":
        result = freeze_amendment(
            args.amendment_file,
            requires_independent_acceptance=False if args.no_independent_acceptance else None,
        ) if args.amendment_file else freeze()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "oracle":
        print(json.dumps(run_oracle(load_config(args.config)), ensure_ascii=False, indent=2))
        return 0
    if args.command == "verify-current-demo":
        result = verify_current_demo(Path(args.input))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 2
    if args.command == "precommit-demo":
        return command_precommit_demo(args)
    if args.command in {"run", "verify"}:
        if args.command == "verify":
            args.build_data = False
            args.legacy_source = None
            args.refresh = False
            args.offline = True
        gate = run_pipeline(args)
        print(json.dumps({"status": gate["status"], "failed_required_gates": gate["failed_required_gates"], "report": "reports/SUBMISSION_REPORT.md"}, ensure_ascii=False, indent=2))
        return 0 if args.command == "run" or gate["full_s_evidence_complete"] else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
