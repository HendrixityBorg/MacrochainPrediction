# Macro → real rates → gold: latent-chain uncertainty

This is an independent SX-CH-001 submission project. It implements an
event-indexed **multi-measurement latent-variable model** around the auditable
primary chain:

```text
macro surprise → policy-path repricing → real-rate repricing → gold repricing
                         ↘ inflation expectations ↗
                                      ↘ USD / external shocks → gold
```

The primary measurement path is deliberately simple and reproducible:

1. macro first-release innovation;
2. Federal Reserve H.15 2-year nominal yield;
3. H.15 5-year inflation-indexed yield;
4. release-day GLD close-to-close return.

ZT, TIP, GC, 1Y/5Y/10Y nominal and real yields, breakevens and DXY are
measurement-error/sensitivity channels. They never replace a failed primary
label after outcomes are observed.

## Evidence tiers

- `development`: 2005–2010 Employment Situation events. Outcomes were already
  explored and can only fit/choose the method.
- `confirmation`: 2011–2024 events. The protocol must be frozen before the
  event-relative labels are generated. Every member is scored from the same
  development-only model; confirmation labels never cross-feed within batch.
- `live_demo`: a two-stage prospective NFP record. Expectation, scale, model,
  windows and decision rule are precommitted before release; only the official
  root actual is added and sealed before the fixed market window is available.

This repository fails closed. `reports/s_grade_gate.json` can say `S_READY`
only if the explicit challenge-aligned requirements, including a sealed live
demo, are present and empirical gates pass. Diagnostic failures remain
disclosed even when the challenge does not define them as hard gates.

Current locked result: 164 valid confirmation chains, 22 terminal successes,
Brier 0.1193 versus 0.1284 for the required naive marginal product, oracle 90%
CI coverage 0.920. The status remains `NOT_S_READY`: a clean remote-clone
reproduction passed, but A004 missed its 2026-09-04 seal deadline and the code rejected the
post-deadline recovery attempt. It cannot be backfilled; a new prospective macro event is required.
The full model's slight underperformance versus climatology remains a disclosed diagnostic,
not an omitted result. The earlier CPI commitment is retained as
`WITHDRAWN_NOT_USED_FOR_SUBMISSION`. See `docs/S_GRADE_STATUS.zh-CN.md` and
`reports/CURRENT_VS_V2.zh-CN.md`.

## Reproduce

Python 3.11+ is required. The committed normalized records support an offline
review after the first successful build.

```bash
./setup.sh
./run.sh --offline
./test.sh
```

Verify the third-party timestamp on the selected live NFP precommit:

```bash
PYTHONPATH=src .venv/bin/python scripts/verify_live_precommit_timestamp.py \
  NFP_202608_REL_20260904_A004
```

Rebuild the explicitly post-label model-skill audit (it never changes the
locked primary result):

```bash
PYTHONPATH=src .venv/bin/python scripts/build_model_skill_audit.py
```

To rebuild public event records from original/provider caches:

```bash
./run.sh --build-data \
  --legacy-source ../cpi-chain-uncertainty-s
```

Because confirmation v1 is immutable, this command performs a non-destructive
byte/value comparison when `data/frozen/events.csv` already exists and writes
`reports/data_rebuild_audit.json`; it never overwrites the locked file.

The build records URLs, retrieval times, hashes, transformations, missingness,
and the protocol hash. Yahoo-derived raw histories are not redistributed;
normalized event responses and their source hashes are retained for audit.

## Main outputs

- `reports/model_run.json`: chain probability, 90% CI, each `p_i`/`n_i`,
  uncertainty attribution, cutoff probability and stop reason;
- `reports/latent_state_ledger.csv`: every event/state measurement vector,
  loading/covariance and latent posterior mean/SD;
- `reports/stop_trace.csv`: every prefix probability/CI, EVSI, stop state and
  executable reason;
- `reports/evaluation.json`: Brier, reliability, hop decay, baselines,
  ablations and CI-width/error association;
- `reports/model_skill_audit.json`: post-label regime-shift diagnosis,
  development-only prequential model-selection check and year-block bootstrap;
- `reports/oracle.json`: hidden-truth CI coverage over correlated measurement
  error, regime drift, heavy tails and interruptions;
- `reports/s_grade_gate.json`: machine-readable requirement-by-requirement
  status;
- `reports/SUBMISSION_REPORT.zh-CN.md`: consolidated Chinese report.

`data/contracts/external_confirmation/` defines a fail-closed intake for any
new ≥50-event external batch. It rejects reused event IDs, predictions created
after label unlock and any labels file present during the pre-unlock audit.

## Honest current limitation

The public daily confirmation route is weaker causal identification than a
licensed 30-minute event window. It can satisfy calibration-sample engineering
requirements. Raw-label access and the post-label amendment remain disclosed;
the post-release NFP root seal is the remaining machine blocker before the
project may claim challenge-aligned S readiness.
