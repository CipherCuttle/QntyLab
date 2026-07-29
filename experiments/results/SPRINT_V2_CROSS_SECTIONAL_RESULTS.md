# Sprint v2 cross-sectional results

> **EXPLORATORY ONLY**
> **NONAUTHORITATIVE**
> **NO SCIENTIFIC VALIDATION**
> **NO HOLDOUT**
> **NO PAPER/LIVE TRADING AUTHORITY**

This is a compact derivative of the completed canonical result, not a new run.
It introduces no new variant, simulation, threshold, exclusion, or classification
semantic. Exact machine-readable headline values are in sprint_v2_summary.json.

## Canonical source and scope

- Source: experiments/results/sprint_v2_results.json
- Source size: 531151382 bytes
- Source SHA-256: 01868090cb77068e8524da67976121152a62034c7fa4ea4c9993366bcce4844d
- Source provenance verdict: COMPLETED_EXECUTION_PROVEN_BY_ATOMIC_ARTIFACT
- Eight primary result records; seven weekday anchors and 100 seeded (20260728)
  random-rank draws per variant.

The displayed figures below are decimal cumulative-return/PnL fields from the
canonical object; table displays are rounded for readability. The summary JSON
retains the exact extracted headline values.

## Headline table

| Variant | Gross | Net 5 | Net 10 | Net 20 | Turnover | IC mean | Long / short contribution | 2021-23 net 10 | 2024+ net 10 | Weekly +/7 | Null draws >= observed | Largest total contributor | Frozen status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| H012 momentum 7d | 15.249036 | 2.706510 | -0.155524 | -0.956320 | 2951.833333 | -0.018105 | 6.258232 / -0.292957 | -0.333790 | -0.805897 | 3 | 0 | RIVERUSDT, 15.743% | OBJECTIVE_KILL |
| H012 momentum 30d | 35.721489 | 16.251073 | 7.101091 | 0.784399 | 1509.500000 | -0.017584 | 7.673576 / -0.803801 | 0.386027 | -0.021122 | 7 | 0 | PIPPINUSDT, 12.219% | UNRESOLVED_SURVIVOR_CANDIDATE |
| H012 momentum 90d | 31.863476 | 18.518151 | 10.589526 | 3.083427 | 1041.833333 | -0.024658 | 6.496166 / -0.525065 | 0.145193 | 5.141726 | 7 | 0 | SIRENUSDT, 24.700% | UNRESOLVED_SURVIVOR_CANDIDATE |
| H013 reversal 1d | -0.967472 | -0.999004 | -0.999970 | -1.000000 | 6945.500000 | -0.024988 | 1.789718 / -2.499729 | -0.990986 | -0.985864 | 0 | 84 | LUNAUSDT, 137.148% | OBJECTIVE_KILL |
| H013 reversal 3d | -0.998763 | -0.999853 | -0.999982 | -1.000000 | 4237.000000 | -0.026835 | 1.704002 / -5.559600 | -0.997419 | -0.926655 | 0 | 89 | LUNAUSDT, 25.319% | OBJECTIVE_KILL |
| H014 funding 24h | 216.165523 | 28.880570 | 3.103099 | -0.923100 | 3971.000000 | -0.022532 | 6.166513 / 1.301762 | 0.491835 | 0.018945 | 7 | 0 | SIRENUSDT, -10.973% | UNRESOLVED_SURVIVOR_CANDIDATE |
| H014 funding 7d | 237.284441 | 115.415839 | 55.855831 | 12.546897 | 1434.666667 | -0.020196 | 5.410206 / 2.188850 | 0.505662 | 11.639389 | 7 | 0 | SIRENUSDT, 17.417% | UNRESOLVED_SURVIVOR_CANDIDATE |
| H015 premium | 10.996035 | -0.397739 | -0.969891 | -0.999926 | 5977.666667 | -0.019391 | 4.574378 / 0.473630 | 0.913783 | -0.985199 | 4 | 0 | RIVERUSDT, 16.097% | OBJECTIVE_KILL |

## Frozen objective classification

The implementation’s frozen status is OBJECTIVE_KILL when the
net_10bps_nonpositive predicate is true. It separately records
uninterpretable_delisting=true for all eight variants; that field does not
change the frozen status, so it is reported rather than reinterpreted.

| Frozen status | Variants | Triggered status predicate |
|---|---|---|
| OBJECTIVE_KILL | H012 7d; H013 1d; H013 3d; H015 | net_10bps_nonpositive=true |
| UNRESOLVED_SURVIVOR_CANDIDATE | H012 30d; H012 90d; H014 24h; H014 7d | net_10bps_nonpositive=false |

All variants also record uninterpretable_delisting=true. No qualitative
classification threshold was added.

## Costs, IC, and attribution

Costs turn H012 7d from positive at 5bps to negative at 10bps, and H014 24h
from positive at 10bps to negative at 20bps. Both H013 variants and H015 are
negative at all three cost levels. H012 30d, H012 90d, and H014 7d remain
positive through 20bps in this frozen output.

Raw-score IC means are negative for every variant. That is directionally
inconsistent with the positive-direction H012 momentum family, while it is
directionally consistent with the inverse-direction H013, H014, and H015
families. No IC magnitude threshold is frozen, so this is descriptive only.

The main books are long-dominated for H012 and H015. H013 has negative short
contribution dominating the gross attribution. Both H014 books have positive
long and short contribution. For H014 24h, price PnL is 2.693254338242277,
funding PnL is 4.775020785, and 10bps fees are 3.971: descriptively
carry-driven. For H014 7d, price PnL is 3.279040230545213, funding PnL is
4.32001567, and 10bps fees are 1.4346666666666668: mixed, funding-heavy.
Funding cashflow remains the frozen -position * funding_rate convention.

## Temporal and rolling-180 diagnostics

The headline table gives the required 2021-23 and 2024+ net-10 results. The
2020 net-10 results are respectively: H012 7d 5.530450376634181; H012 30d
4.970945932235458; H012 90d 0.6477705736091233; H013 1d
-0.761854617110318; H013 3d -0.9074218460087113; H014 24h
1.6992349858682774; H014 7d 1.9875936421192377; H015
0.06294505590390598.

H012 7d, both H013 variants, and H015 do not survive 2024+ at net 10. H012
30d is slightly negative in 2024+; H012 90d and both H014 variants remain
positive, though H014 24h is only 0.018944696443733422.

**POST-RUN DESCRIPTIVE DIAGNOSTIC:** frozen rolling-180 net-10 windows:

| Variant | Windows | Min | Max | Positive windows |
|---|---:|---:|---:|---:|
| H012 7d | 2085 | -0.804496 | 5.478208 | 809 |
| H012 30d | 2085 | -0.632215 | 3.505567 | 1109 |
| H012 90d | 2084 | -0.701734 | 12.510949 | 978 |
| H013 1d | 2085 | -0.842228 | 0.053652 | 2 |
| H013 3d | 2085 | -0.947609 | 0.931475 | 237 |
| H014 24h | 2085 | -0.673963 | 2.424364 | 1186 |
| H014 7d | 2085 | -0.789230 | 6.710751 | 1167 |
| H015 | 2077 | -0.779256 | 4.629161 | 668 |

## Weekly robustness

All values are canonical net-10 results; no weekday is selected or promoted.

| Variant | Mon | Tue | Wed | Thu | Fri | Sat | Sun | Median / min / max / dispersion |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| H012 7d | -0.545222 | 0.204438 | 0.700972 | -0.021332 | -0.914626 | -0.180263 | 2.198872 | -0.021332 / -0.914626 / 2.198872 / 3.113498 |
| H012 30d | 68.707024 | 169.046325 | 7.135029 | 35.116563 | 6.077438 | 13.332199 | 41.237532 | 35.116563 / 6.077438 / 169.046325 / 162.968887 |
| H012 90d | 24.134926 | 255.411000 | 4.997831 | 2.763901 | 9.320725 | 3.653110 | 1.964382 | 4.997831 / 1.964382 / 255.411000 / 253.446618 |
| H013 1d | -0.973799 | -0.977241 | -0.962459 | -0.993466 | -0.999576 | -0.996462 | -0.999473 | -0.993466 / -0.999576 / -0.962459 / 0.037117 |
| H013 3d | -0.999758 | -0.998322 | -0.998169 | -0.998640 | -0.998402 | -0.998620 | -0.999986 | -0.998620 / -0.999986 / -0.998169 / 0.001818 |
| H014 24h | 156.294522 | 13.515981 | 2.955577 | 2.607085 | 5.890802 | 35.399518 | 15.802374 | 13.515981 / 2.607085 / 156.294522 / 153.687436 |
| H014 7d | 6.254558 | 119.026922 | 130.905613 | 20.182507 | 54.031805 | 43.634318 | 7.010741 | 43.634318 / 6.254558 / 130.905613 / 124.651055 |
| H015 | -0.930145 | 0.225470 | 0.146197 | -0.577889 | -0.975504 | 1.715823 | 20.441726 | 0.146197 / -0.975504 / 20.441726 / 21.417230 |

The surviving four variants have seven positive anchors, but their very wide
dispersions are a timing-fragility warning, not a selection license.

## Random-rank null, breadth, missingness, gaps, and concentration

**POST-RUN DESCRIPTIVE DIAGNOSTIC:** at net 10, the four survivors each exceed
all 100 existing random-rank draws (empirical percentile 1.0); H012 7d and
H015 also do so despite being killed by costs. H013 1d and 3d have 84 and 89
null draws respectively at least as large as observed. This is descriptive,
not a new survival threshold.

Each main record series has 2372 dates and 2256--2264 valid-portfolio dates.
The held-leg eligible_return_count ranges from 0 to 8 (median 8). Forced
close events range from 5 to 10 by variant and the frozen classification
records a delisting concern for every variant. Missing-funding position events
range from 1 (H014 24h) to 51 (H012 90d), involving the already-recorded source
gaps; no assets were removed.

Largest total-contributor shares are in the headline table. H012 90d has the
largest survivor single-asset share (SIRENUSDT, 24.700%), H014 7d has
SIRENUSDT at 17.417%, H012 30d has PIPPINUSDT at 12.219%, and H014 24h has a
negative SIRENUSDT share of -10.973%. These diagnostics weaken causal or
generalized interpretation; no concentration threshold is frozen.

## Survivor red team and evidence triage

All survivors are still UNRESOLVED_SURVIVOR_CANDIDATE, never validated edge,
alpha, or trading strategy.

| Candidate | Supports from existing output | Weakens / ambiguous from existing output | Strongest skeptical explanation |
|---|---|---|---|
| H014 7d | net 10 and 20 positive; 2024+ positive; seven positive anchors; inverse-direction IC sign; all null draws lower | very wide weekday spread; 17.417% SIREN share; gaps/delistings; carry contribution exceeds price contribution | frozen carry economics plus timing and asset exposure may dominate rather than a stable generalized signal |
| H012 90d | net 10 and 20 positive; 2024+ positive; seven positive anchors; all null draws lower | momentum IC sign is negative; 24.700% SIREN share; wide weekday spread; gaps/delistings | an asset/timing-heavy return pattern with IC inconsistency |
| H012 30d | net 10 and 20 positive; seven positive anchors; all null draws lower | 2024+ slightly negative; momentum IC sign is negative; large weekday spread; gaps/delistings | earlier-period/timing performance without contemporaneous IC support |
| H014 24h | net 10 positive; seven positive anchors; inverse-direction IC sign; all null draws lower | net 20 negative; 2024+ nearly flat; very wide weekday spread; carry-driven; gaps/delistings | cost-sensitive funding carry rather than durable cross-sectional evidence |

This ordering is **EVIDENCE TRIAGE**, not a composite score, selection, or
authorization.

## Family coherence and multiple-testing context

H012 is mixed: 7d is killed, while 30d and 90d survive mechanically; the two
survivors retain negative raw momentum IC. H013 is coherently negative and
killed at both horizons. H014 has two mechanical survivors, but only 7d
survives 20bps and both have large weekday dispersion. H015 is cost-destroyed
and killed.

Search context remains Sprint v0: 15 variants / 45 result records; Sprint v1:
17 variants / 51 result records; Sprint v2: 8 primary result records. Any
survivor is discovery evidence in that broader research search and requires an
independent, predeclared replication.

## What this does not establish

It does not establish scientific validation, a holdout result, a validated
edge, an alpha, profitability beyond this frozen experiment, causal mechanism,
or any paper/live trading authority. The next scientific action, if separately
authorized, is an independently specified replication protocol; this artifact
does not authorize one.
