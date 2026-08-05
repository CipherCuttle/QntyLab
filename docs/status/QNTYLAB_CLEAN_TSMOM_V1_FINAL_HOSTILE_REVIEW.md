# QntyLab Clean TSMOM V1 Final Hostile Review

## Classification

`CLEAN_TSMOM_RUN_INVALID_REQUIRES_NEW_VERSION`

PR #5 (`https://github.com/CipherCuttle/QntyLab/pull/5`) is an open draft PR. Its contract is the `research/clean-tsmom-v1-v2-source-resolved-v1` head at `1a6e70ff4849fcb067e00d84705d7b70d3458b4e`, against `master`. It must not merge. This closeout preserves the invalid run; it does not authorize a corrected experiment, trading, deployment, tuning, Qnty integration, or DVOL change.

## Confirmed valid evidence retained

The hostile review established the following evidence before the invalidity finding:

- The frozen contract predates result computation, and the frozen sidecars passed.
- All nine retained source pairs passed their manifests: 3,672 hourly rows and 459 funding events per symbol.
- The source manifest digest matched: `8605c6675be20510691f9ed840455de59acb0536c19b1a8fc7386606b3e2470a`.
- The independently reconstructed 8-hour panel matched; the panel manifest digest was `f423b21d1e7fa5d696021ce3a13889a4a0894a8a85de02db2e02128bd8cccd5f`.
- The original result artifact existed and matched SHA-256 `19196a8d40d2cde7ca362289d2c5368737d9ef7067cef6b78592fcdb5e3dd9aa`.
- Clean V1 independently matched within approximately `2.22e-16`.
- Required controls and diagnostic-tail outputs existed.
- No raw hourly source data was committed.
- `market_data_network_attempts_during_closeout=0`. No market-data network request was made during this closeout.

The pre-existing untracked review tooling was preserved, not newly authored in this session:

```text
tests/test_clean_tsmom_independent_verify.py
sha256=2dba67ebd633abb6e52b1d2b16855cfa90c579f7d7746e9773426c61aaad5d0e

tools/verify_clean_tsmom_v1_results.py
sha256=7649d94e6775d546bf2c15a3ccf9023ebf0f0245b19da0d675bd4750e93b8813
```

The external preservation snapshot was `/tmp/qntylab_clean_tsmom_untracked_audit_20260805T111109Z`; its archive SHA-256 was `1959dbc7a2970a38e7ce67c57477c014a37ae8684d8ab4ba012a2ce77168881c`.

## Material invalidating defect

The producer's Clean V2 volatility estimator consumed information unavailable at the decision timestamp. This is future-volatility leakage. An independently causal V2 recomputation disagreed beyond the frozen `1e-12` tolerance:

```text
net_return=0.0002859125
sharpe=0.0044647193
max_drawdown=0.0002845819
turnover=0.0129038965
net_funding=0.0050040350
```

Therefore the submitted Clean V2 metrics are invalid, and the submitted V2-versus-V1 packaging comparison is invalid. This cannot be repaired by modifying and rerunning the frozen experiment version. A new experiment version must freeze corrected causal V2 semantics before any new evaluation. No corrected V2 metrics were calculated during this closeout.

## Additional defects and evidence-retention issue

- The documentation falsely claimed that V2 worsened Sharpe, despite `-0.868534 > -0.921987`.
- The independent verifier did not initially enforce every frozen sidecar and original-result identity internally; this closeout hardens those checks and adds hostile rejection tests.
- `results_v1.json` contains approximately 34,683 generated lines and is not a compact summary.
- `deterministic_run_root_count=0`: deterministic run roots were not located during review. This is an additional evidence-retention defect, not independently invalidating of the already-invalid V2 result because the causal mismatch independently establishes invalidity. Run-root command output is unavailable; no run root is invented here.

## Preservation and verifier commands

The preservation gate was run against `/home/swirky/DevHub/worktrees/QntyLab-clean-tsmom-v1-v2-v1`:

```bash
gh pr view 5 --repo CipherCuttle/QntyLab --json state,isDraft,mergeable,headRefName,headRefOid,baseRefName,url
git -C "$WT" status --short --branch
git -C "$WT" rev-parse HEAD
```

The closeout verification commands are recorded exactly as required:

```bash
python -m pytest -q tests/test_clean_tsmom_independent_verify.py
python -m pytest tests/test_clean_tsmom_independent_verify.py -W error
python -m pytest -q tests/test_clean_tsmom.py tests/test_clean_tsmom_source.py tests/test_strategy_test.py tests/test_research_ledger.py
python -m compileall -q qntylab tools tests
find experiments/clean_tsmom -name '*.json' -type f -print0 | xargs -0 -n1 python -m json.tool >/dev/null
git diff --check
```

The independent verifier is intentionally expected to fail overall: all identity, source, panel, Clean V1, control, and tail gates pass, while the causal V2 mismatch remains exposed as a failure. It must not reinterpret that mismatch as success.

Frozen experiment files remain byte-identical to pre-closeout HEAD `1a6e70ff4849fcb067e00d84705d7b70d3458b4e`; the required scoped diff is empty. No V0/V1 specification, source CSV, manifest, original result artifact, date, universe, Qnty, or DVOL file was changed. No in-place corrected rerun was performed, and PR #5 was not merged or force-pushed.

## Closeout decision

PR #5 must remain unmerged and is ready for the human owner to close as superseded if desired. Clean V1's independently matching result may be retained as evidence. The invalid run itself remains preserved. Any corrected Clean V2 work requires a new frozen experiment version and a separate review.
