from __future__ import annotations

from bisect import bisect_left
from calendar import monthrange
import csv
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
import time
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .config import ROOT
from .io import read_csv, read_json, sha256_file, write_csv, write_json
from .locking import verify_lock
from .xlsx import rows as xlsx_rows


PHILLY_EMPLOY = (
    "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/"
    "real-time-data/data-files/xlsx/employ_level_first_second_third.xlsx"
)
ALFRED_DATES = "https://alfred.stlouisfed.org/release/downloaddates?ff=txt&rid=50"
H15_NOMINAL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?filetype=csv&from=&label=include&lastobs="
    "&layout=seriescolumn&rel=H15&series=bf17364827e38702b42a58cf8eaa3f78&to=&type=package"
)
H15_REAL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H15&series="
    "0b98a66d3ff5e1ea0fbf88adc59b387f&lastobs=&from=&to=&filetype=csv&label=include&layout=seriescolumn&type=package"
)
YAHOO = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_START = 1072915200
YAHOO_END = 1893456000
SYMBOLS = {"zt": "ZT=F", "tip": "TIP", "gld": "GLD", "gc": "GC=F", "dxy": "DX-Y.NYB", "uup": "UUP"}
USER_AGENT = "Mozilla/5.0 macro-gold-latent-s/0.1 reproducibility-research"


def _fetch(url: str, target: Path, refresh: bool = False) -> dict[str, Any]:
    if target.exists() and not refresh:
        return {"url": url, "path": str(target.relative_to(ROOT)), "sha256": sha256_file(target), "cached": True}
    target.parent.mkdir(parents=True, exist_ok=True)
    error: Exception | None = None
    for attempt in range(4):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urlopen(request, timeout=90) as response, tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                shutil.copyfileobj(response, handle)
                temporary = Path(handle.name)
            temporary.replace(target)
            return {"url": url, "path": str(target.relative_to(ROOT)), "sha256": sha256_file(target), "cached": False}
        except Exception as exc:  # keep provider errors in one actionable message
            error = exc
            time.sleep(1.0 + attempt)
    curl = shutil.which("curl")
    if curl:
        temporary = target.with_suffix(target.suffix + ".download")
        completed = subprocess.run(
            [curl, "-L", "--fail", "--silent", "--show-error", "--retry", "3", "--output", str(temporary), url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if completed.returncode == 0 and temporary.exists():
            temporary.replace(target)
            return {"url": url, "path": str(target.relative_to(ROOT)), "sha256": sha256_file(target), "cached": False, "transport": "curl_fallback"}
        temporary.unlink(missing_ok=True)
        error = RuntimeError(completed.stderr.strip() or f"curl exit {completed.returncode}")
    raise RuntimeError(f"failed to fetch {url}: {error}")


def _yahoo_url(symbol: str) -> str:
    query = urlencode({"period1": YAHOO_START, "period2": YAHOO_END, "interval": "1d", "events": "history"})
    return YAHOO.format(symbol=quote(symbol, safe="")) + "?" + query


def _import_legacy(raw: Path, legacy: Path) -> None:
    candidates = {
        "employ.xlsx": legacy / "experiments/public_macro_screen/cache/employ_level_first_second_third.xlsx",
        "h15_nominal.csv": legacy / "data/raw/h15_nominal.csv",
        "h15_real.csv": legacy / "data/raw/h15_real.csv",
        "yahoo_zt.json": legacy / "experiments/public_macro_screen/cache/ZT_F.json",
        "yahoo_tip.json": legacy / "experiments/public_macro_screen/cache/TIP.json",
        "yahoo_gld.json": legacy / "experiments/public_macro_screen/cache/GLD.json",
        "yahoo_gc.json": legacy / "experiments/public_macro_screen/cache/GC_F.json",
    }
    raw.mkdir(parents=True, exist_ok=True)
    for name, source in candidates.items():
        target = raw / name
        if source.exists() and not target.exists():
            shutil.copy2(source, target)


def acquire(*, legacy_source: Path | None = None, refresh: bool = False) -> list[dict[str, Any]]:
    raw = ROOT / "data" / "raw"
    if legacy_source:
        _import_legacy(raw, legacy_source)
    sources = [
        {"source_id": "philadelphia_fed_employ_first_releases", **_fetch(PHILLY_EMPLOY, raw / "employ.xlsx", refresh)},
        {"source_id": "alfred_employment_situation_release_dates", **_fetch(ALFRED_DATES, raw / "release_dates_50.txt", refresh)},
        {"source_id": "federal_reserve_h15_nominal", **_fetch(H15_NOMINAL, raw / "h15_nominal.csv", refresh)},
        {"source_id": "federal_reserve_h15_real", **_fetch(H15_REAL, raw / "h15_real.csv", refresh)},
    ]
    for name, symbol in SYMBOLS.items():
        sources.append({
            "source_id": f"yahoo_{symbol}",
            "redistributable": False,
            **_fetch(_yahoo_url(symbol), raw / f"yahoo_{name}.json", refresh),
        })
    return sources


def _h15(path: Path, identifier: str) -> dict[date, float]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.reader(handle))
    header = next(index for index, row in enumerate(records) if row and row[0].strip() == "Time Period")
    column = records[header].index(identifier)
    output: dict[date, float] = {}
    for row in records[header + 1:]:
        try:
            output[date.fromisoformat(row[0])] = float(row[column])
        except (ValueError, IndexError):
            continue
    return output


def _yahoo(path: Path) -> dict[date, float]:
    payload = read_json(path)
    result = payload["chart"]["result"][0]
    values = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
    if values is None:
        values = result["indicators"]["quote"][0]["close"]
    return {
        datetime.fromtimestamp(stamp, tz=timezone.utc).date(): float(value)
        for stamp, value in zip(result["timestamp"], values)
        if value is not None and float(value) > 0
    }


def _spread(left: dict[date, float], right: dict[date, float]) -> dict[date, float]:
    return {point: left[point] - right[point] for point in left.keys() & right.keys()}


def _change(series: dict[date, float], point: date, *, log_return: bool) -> tuple[float, date] | None:
    dates = sorted(series)
    index = bisect_left(dates, point)
    if index <= 0 or index >= len(dates) or dates[index] != point:
        return None
    before, after = series[dates[index - 1]], series[dates[index]]
    value = 100.0 * math.log(after / before) if log_return else after - before
    return value, dates[index - 1]


def _scale(series: dict[date, float], point: date, *, log_return: bool, lookback: int, minimum: int) -> tuple[float, date] | None:
    dates = sorted(series)
    end = bisect_left(dates, point)
    changes: list[float] = []
    start = max(1, end - lookback)
    for index in range(start, end):
        before, after = series[dates[index - 1]], series[dates[index]]
        changes.append(100.0 * math.log(after / before) if log_return else after - before)
    if len(changes) < minimum:
        return None
    value = statistics.stdev(changes)
    return (value, dates[end - 1]) if value > 0 else None


def _first_releases(path: Path) -> dict[str, float]:
    records = xlsx_rows(path, "DATA")
    header = next(index for index, row in enumerate(records) if row and str(row[0]).strip() == "Date")
    output = {}
    for row in records[header + 1:]:
        if len(row) < 2 or row[0] is None or row[1] is None:
            continue
        try:
            output[str(row[0]).strip()] = float(row[1])
        except (ValueError, TypeError):
            continue
    return output


def _release_dates(path: Path, references: list[str]) -> dict[str, date]:
    candidates = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            candidates.append(date.fromisoformat(line.strip()))
        except ValueError:
            continue
    output: dict[str, date] = {}
    for reference in references:
        year, month = (int(value) for value in reference.split(":"))
        end = date(year, month, monthrange(year, month)[1])
        eligible = [point for point in candidates if end < point <= end + timedelta(days=25)]
        if eligible:
            output[reference] = min(eligible)
    return output


def _root_innovations(first: dict[str, float]) -> dict[str, dict[str, float]]:
    ordered = sorted(first)
    innovations: list[float] = []
    output: dict[str, dict[str, float]] = {}
    for index, reference in enumerate(ordered):
        if index < 12:
            innovations.append(0.0)
            continue
        expected = statistics.median(first[item] for item in ordered[index - 12:index])
        innovation = first[reference] - expected
        history = [value for value in innovations[max(12, len(innovations) - 60):] if math.isfinite(value)]
        scale = statistics.stdev(history) if len(history) >= 24 else statistics.stdev([first[item] for item in ordered[max(0, index - 60):index]])
        output[reference] = {"actual": first[reference], "expected": expected, "response": innovation, "scale": scale, "z": innovation / scale if scale > 0 else 0.0}
        innovations.append(innovation)
    return output


def _measurement(
    row: dict[str, Any], name: str, series: dict[date, float], point: date, *,
    log_return: bool, orientation: float, source_id: str, lookback: int, minimum: int,
) -> bool:
    changed = _change(series, point, log_return=log_return)
    scaled = _scale(series, point, log_return=log_return, lookback=lookback, minimum=minimum)
    if changed is None or scaled is None:
        row.update({f"{name}_response": "", f"{name}_scale": "", f"{name}_z": "", f"{name}_scale_last_date": "", f"{name}_source_id": source_id})
        return False
    response, previous = changed
    scale, scale_last = scaled
    row.update({
        f"{name}_response": response,
        f"{name}_scale": scale,
        f"{name}_z": orientation * response / scale,
        f"{name}_previous_date": previous.isoformat(),
        f"{name}_scale_last_date": scale_last.isoformat(),
        f"{name}_source_id": source_id,
    })
    return True


def build_events(config: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw = ROOT / "data" / "raw"
    first = _first_releases(raw / "employ.xlsx")
    roots = _root_innovations(first)
    references = [
        item for item in sorted(first)
        if (
            config["data"]["development_start"] <= item <= config["data"]["development_end"]
            or config["data"]["confirmation_start"] <= item <= config["data"]["confirmation_end"]
        )
    ]
    releases = _release_dates(raw / "release_dates_50.txt", references)
    nominal = {name: _h15(raw / "h15_nominal.csv", identifier) for name, identifier in {
        "n1": "RIFLGFCY01_N.B", "n2": "RIFLGFCY02_N.B", "n5": "RIFLGFCY05_N.B", "n10": "RIFLGFCY10_N.B",
    }.items()}
    real = {name: _h15(raw / "h15_real.csv", identifier) for name, identifier in {
        "r5": "RIFLGFCY05_XII_N.B", "r10": "RIFLGFCY10_XII_N.B",
    }.items()}
    market = {name: _yahoo(raw / f"yahoo_{name}.json") for name in SYMBOLS}
    series = {
        "policy_h15_2y": (nominal["n2"], False, 1.0, "federal_reserve_h15_nominal:RIFLGFCY02_N.B"),
        "policy_h15_1y": (nominal["n1"], False, 1.0, "federal_reserve_h15_nominal:RIFLGFCY01_N.B"),
        "policy_zt": (market["zt"], True, -1.0, "yahoo:ZT=F"),
        "inflation_be5": (_spread(nominal["n5"], real["r5"]), False, 1.0, "derived:H15_5Y_nominal_minus_5Y_real"),
        "inflation_be10": (_spread(nominal["n10"], real["r10"]), False, 1.0, "derived:H15_10Y_nominal_minus_10Y_real"),
        "real_h15_5y": (real["r5"], False, 1.0, "federal_reserve_h15_real:RIFLGFCY05_XII_N.B"),
        "real_h15_10y": (real["r10"], False, 1.0, "federal_reserve_h15_real:RIFLGFCY10_XII_N.B"),
        "real_tip": (market["tip"], True, -1.0, "yahoo:TIP"),
        "gold_gld": (market["gld"], True, 1.0, "yahoo:GLD"),
        "gold_gc": (market["gc"], True, 1.0, "yahoo:GC=F"),
        "dollar_dxy": (market["dxy"], True, 1.0, "yahoo:DX-Y.NYB"),
        "dollar_uup": (market["uup"], True, 1.0, "yahoo:UUP"),
    }
    lookback = int(config["data"]["volatility_lookback_sessions"])
    minimum = int(config["data"]["minimum_scale_sessions"])
    rows: list[dict[str, Any]] = []
    source_hashes = {item["source_id"]: item["sha256"] for item in sources}
    for reference in references:
        if reference not in releases or reference not in roots:
            continue
        split = "development" if reference <= config["data"]["development_end"] else "confirmation"
        point = releases[reference]
        root = roots[reference]
        row: dict[str, Any] = {
            "event_id": f"NFP_{reference.replace(':', '')}_REL_{point.strftime('%Y%m%d')}",
            "topic": "nfp", "reference_period": reference, "release_date": point.isoformat(),
            "release_time_local": f"{point.isoformat()}T08:30:00 America/New_York",
            "split": split,
            "evidence_status": "development_seen" if split == "development" else "confirmation_protocol_locked",
            "root_actual": root["actual"], "root_expected": root["expected"],
            "root_response": root["response"], "root_scale": root["scale"], "root_z": root["z"],
            "root_source_id": "philadelphia_fed_employ_first_releases",
            "external_cutoff": 0, "scheduled_cutoff": 0, "cutoff_reason": "",
        }
        available = {name: _measurement(row, name, values, point, log_return=is_log, orientation=orientation,
                                         source_id=source_id, lookback=lookback, minimum=minimum)
                     for name, (values, is_log, orientation, source_id) in series.items()}
        main_available = all(available[name] for name in ("policy_h15_2y", "real_h15_5y", "gold_gld"))
        row["primary_complete"] = int(main_available)
        row["source_bundle_sha256"] = json.dumps(source_hashes, sort_keys=True, separators=(",", ":"))
        rows.append(row)
    return rows


def build_dataset(config: dict[str, Any], *, legacy_source: Path | None = None, refresh: bool = False) -> dict[str, Any]:
    lock = verify_lock()
    if not lock.get("valid"):
        raise RuntimeError(f"refusing label generation without valid protocol lock: {lock.get('reason')}")
    sources = acquire(legacy_source=legacy_source, refresh=refresh)
    rows = build_events(config, sources)
    target = ROOT / "data" / "frozen" / "events.csv"
    if target.exists():
        old = read_csv(target)
        if old != [{key: str(value) for key, value in row.items()} for row in rows]:
            raise RuntimeError("frozen dataset exists and differs; create a new dataset version instead of overwriting")
    else:
        write_csv(target, rows)
    split_counts = {split: sum(row["split"] == split and int(row["primary_complete"]) == 1 for row in rows) for split in ("development", "confirmation")}
    manifest = {
        "dataset_version": "nfp_gold_confirmation_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": lock["protocol_sha256"],
        "event_file": str(target.relative_to(ROOT)),
        "event_file_sha256": sha256_file(target),
        "events_total": len(rows), "primary_complete": split_counts,
        "confirmation_label_access_warning": "Raw price histories were locally accessible. This limitation must be disclosed; the challenge does not prescribe a third-party signature artifact.",
        "sources": sources,
    }
    manifest_path = ROOT / "data" / "frozen" / "manifest.json"
    if manifest_path.exists():
        prior = read_json(manifest_path)
        stable = {key: value for key, value in manifest.items() if key != "generated_at_utc"}
        old_stable = {key: value for key, value in prior.items() if key != "generated_at_utc"}
        for collection in (stable.get("sources", []), old_stable.get("sources", [])):
            for source in collection:
                source.pop("cached", None)
                source.pop("transport", None)
        if stable != old_stable:
            raise RuntimeError("frozen manifest differs; refuse overwrite")
    else:
        write_json(manifest_path, manifest)
    return manifest


def load_events() -> list[dict[str, Any]]:
    path = ROOT / "data" / "frozen" / "events.csv"
    if not path.exists():
        raise FileNotFoundError("frozen event data missing; run with --build-data after freezing protocol")
    rows = read_csv(path)
    rows.sort(key=lambda row: row["release_date"])
    return rows
