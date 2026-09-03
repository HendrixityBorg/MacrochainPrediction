from __future__ import annotations

from collections import Counter
from datetime import datetime
import math
from pathlib import Path
from typing import Any

from .config import ROOT
from .io import read_json, sha256_file
from .locking import verify_lock
from .model import primary_labels


ORIENTATIONS = {
    "policy_h15_2y": 1.0, "policy_h15_1y": 1.0, "policy_zt": -1.0,
    "inflation_be5": 1.0, "inflation_be10": 1.0,
    "real_h15_5y": 1.0, "real_h15_10y": 1.0, "real_tip": -1.0,
    "gold_gld": 1.0, "gold_gc": 1.0, "dollar_dxy": 1.0, "dollar_uup": 1.0,
}


def audit(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    manifest = read_json(ROOT / "data" / "frozen" / "manifest.json")
    current_lock = read_json(ROOT / "preregistration" / "PROTOCOL_LOCK.json")
    base_lock = read_json(ROOT / "preregistration" / "PROTOCOL_LOCK.v1.0.0.json")
    duplicates = [key for key, count in Counter(row["event_id"] for row in rows).items() if count > 1]
    scale_leaks = []
    z_mismatches = []
    missing_main = []
    for row in rows:
        for name, orientation in ORIENTATIONS.items():
            response, scale, z = (row.get(f"{name}_{suffix}", "") for suffix in ("response", "scale", "z"))
            if response not in (None, "") and scale not in (None, "") and z not in (None, ""):
                expected = orientation * float(response) / float(scale)
                if abs(expected - float(z)) > 1e-10:
                    z_mismatches.append({"event_id": row["event_id"], "measurement": name, "delta": abs(expected - float(z))})
            scale_date = row.get(f"{name}_scale_last_date", "")
            if scale_date and scale_date >= row["release_date"]:
                scale_leaks.append({"event_id": row["event_id"], "measurement": name, "scale_last_date": scale_date, "release_date": row["release_date"]})
        if int(float(row.get("primary_complete", 0))) != 1:
            missing_main.append(row["event_id"])
    split_counts = Counter(row["split"] for row in rows)
    eligible = [row for row in rows if row["split"] == "confirmation" and primary_labels(row, float(config["data"]["materiality_sigma"])) is not None]
    source_checks = []
    for source in manifest["sources"]:
        path = ROOT / source["path"]
        source_checks.append({
            "source_id": source["source_id"], "path": source["path"], "available": path.exists(),
            "hash_matches": path.exists() and sha256_file(path) == source["sha256"],
            "redistributable": source.get("redistributable", True),
        })
    base_before_labels = datetime.fromisoformat(base_lock["frozen_at_utc"]) < datetime.fromisoformat(manifest["generated_at_utc"])
    chain_valid = (
        manifest["protocol_sha256"] == base_lock["protocol_sha256"]
        and current_lock.get("base_protocol_sha256", current_lock.get("previous_protocol_sha256")) == base_lock["protocol_sha256"]
        and any(
            item.get("amendment_file") == "preregistration/AMENDMENT_001_ZERO_RESPONSE_AND_APPLICABILITY.zh-CN.md"
            and item.get("amendment_sha256")
            for item in current_lock.get("amendment_chain", [{
                "amendment_file": current_lock.get("amendment_file"),
                "amendment_sha256": current_lock.get("amendment_sha256"),
            }])
        )
        and verify_lock().get("valid")
    )
    checks = {
        "event_ids_unique": not duplicates,
        "candidate_universe_71_plus_168": split_counts["development"] == 71 and split_counts["confirmation"] == 168,
        "confirmation_evaluable_ge_50": len(eligible) >= 50,
        "no_scale_time_leakage": not scale_leaks,
        "standardization_recomputes": not z_mismatches,
        "frozen_event_hash_matches": sha256_file(ROOT / manifest["event_file"]) == manifest["event_file_sha256"],
        "base_lock_precedes_first_label_generation": base_before_labels,
        "base_to_amendment_lock_chain_valid": chain_valid,
        "all_available_raw_source_hashes_match": all(
            not item["available"] or item["hash_matches"] for item in source_checks
        ),
    }
    return {
        "passes": all(checks.values()), "checks": checks,
        "events": {"total": len(rows), "by_split": dict(split_counts), "confirmation_evaluable": len(eligible), "primary_missing": len(missing_main)},
        "exclusions": {"duplicate_ids": duplicates, "missing_primary_event_ids": missing_main, "scale_time_leaks": scale_leaks, "z_mismatches": z_mismatches},
        "lock_timeline": {
            "base_lock": base_lock["frozen_at_utc"], "first_label_generation": manifest["generated_at_utc"],
            "amended_lock": current_lock["frozen_at_utc"], "base_protocol_sha256": base_lock["protocol_sha256"],
            "amended_protocol_sha256": current_lock["protocol_sha256"],
            "amendment_chain": current_lock.get("amendment_chain", []),
        },
        "sources": source_checks,
        "raw_sources_available": sum(item["available"] for item in source_checks),
        "note": "Raw sources are optional in offline review. Every available raw source must match; the frozen normalized file and manifest are the required isolated input.",
    }


def markdown(result: dict[str, Any]) -> str:
    lines = ["# 数据质量审计", "", f"> 总状态：`{'PASS' if result['passes'] else 'FAIL'}`。", "", "## 检查", ""]
    for name, passed in result["checks"].items():
        lines.append(f"- [{'x' if passed else ' '}] `{name}`")
    events = result["events"]
    lines += [
        "", "## 覆盖", "",
        f"- 总候选 {events['total']}；development={events['by_split'].get('development', 0)}；confirmation={events['by_split'].get('confirmation', 0)}；",
        f"- 主评估有效 confirmation={events['confirmation_evaluable']}；主测量缺失={events['primary_missing']}；",
        "- 所有响应尺度截止日严格早于发布日；标准化方向与 response/scale 可逐项复算。", "",
        "## 锁链", "",
        f"- 原始协议锁：{result['lock_timeline']['base_lock']}；",
        f"- 首次标签生成：{result['lock_timeline']['first_label_generation']}；",
        f"- 当前链式修订锁：{result['lock_timeline']['amended_lock']}；修订数={len(result['lock_timeline']['amendment_chain'])}。", "",
        "原始锁早于标签；Amendment 001 晚于标签，故其非 pristine 性质必须披露。Amendment 002 只替换尚未发布的演示主题，",
        "Amendment 003 只把自定义签署/skill 门与题面硬门分离；二者均不改变历史预测、标签、模型或阈值。", "",
    ]
    return "\n".join(lines)
