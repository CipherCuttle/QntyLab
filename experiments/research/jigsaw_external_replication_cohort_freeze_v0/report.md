# Jigsaw Drawdown Piece — External Replication Cohort Freeze V0

## Repository reconciliation

The declaration is based on Jigsaw commit `2320de3` and the committed
Catalog-48 receipt at `1cfa2d5`.  The source receipt records 43 exact,
title-level Binance USD-M perpetual launch matches in a frozen 60-target set;
`BNXUSDT` is its one explicit relaunch ambiguity.  No network request, live
roster, source re-enumeration, price download, state calculation, H003 run, or
replication outcome inspection occurred in this phase.

## Source evidence used

`docs/forensics/QNTYLAB_LIFECYCLE_OFFICIAL_SOURCE_COVERAGE_V1.md`
(`sha256: 1780cb646751bb22fd08bace96d76124233d09b155dc7d4a804546103cc05b3b`)
is the sole cohort-membership source.  The Jigsaw preregistration and result
are bound by the declaration for the unchanged piece contract and previously
earned replication authorization, respectively.

## Frozen selection rule

Use only the retained unambiguous Catalog-48 exact Binance USD-M perpetual
launch records with a positive release-date fact no later than `2024-01-01`;
exclude BTCUSDT, ETHUSDT, and SOLUSDT; sort by launch/start date, symbol, then
instance id; take the first 20.  Catalog article code is part of every instance
id, so it binds the lifecycle episode.  The record is a potential-history fact,
not a data-usability or continuity assertion.

## Candidate enumeration

| Order | InstrumentIdentity | Launch/start evidence | Identity status | Decision | Reason |
|---:|---|---|---|---|---|
| — | ETHUSDT / `catalog48:360036964392` | 2019-11-29 | resolvable | excluded | discovery asset |
| 1 | BCHUSDT / `catalog48:360037742632` | 2019-12-19 | resolvable | included | first qualifying identity |
| 2 | XRPUSDT / `catalog48:360038497311` | 2020-01-06 | resolvable | included | first qualifying identity |
| 3 | LTCUSDT / `catalog48:360038585151` | 2020-01-08 | resolvable | included | first qualifying identity |
| 4 | TRXUSDT / `catalog48:360038407872` | 2020-01-14 | resolvable | included | first qualifying identity |
| 5 | ETCUSDT / `catalog48:360038833831` | 2020-01-15 | resolvable | included | first qualifying identity |
| 6 | LINKUSDT / `catalog48:360038885371` | 2020-01-16 | resolvable | included | first qualifying identity |
| 7 | XLMUSDT / `catalog48:360038969011` | 2020-01-19 | resolvable | included | first qualifying identity |
| 8 | CHZUSDT / `catalog48:e95ce5d56cfe4ef4acfb02a0769e6fd8` | 2021-01-21 | resolvable | included | first qualifying identity |
| 9 | SANDUSDT / `catalog48:df96728782084fd2ab2ba51b6201b462` | 2021-01-25 | resolvable | included | first qualifying identity |
| 10 | REEFUSDT / `catalog48:02895f23b535433e8563175cfb64d1cd` | 2021-02-22 | resolvable | included | first qualifying identity |
| 11 | CHRUSDT / `catalog48:86f5ef4c343c4acda8358918e3f77698` | 2021-03-12 | resolvable | included | first qualifying identity |
| 12 | ALICEUSDT / `catalog48:09e302f8a778456aa42e0df634cc4e8f` | 2021-03-16 | resolvable | included | first qualifying identity |
| 13 | ONEUSDT / `catalog48:45cb73bba8254e52b9c0d7ad597d0402` | 2021-03-17 | resolvable | included | first qualifying identity |
| 14 | API3USDT / `catalog48:3e091344eaaa4632bbdc1e5ded1237e1` | 2022-02-21 | resolvable | included | first qualifying identity |
| 15 | GMTUSDT / `catalog48:b76223a20c604f718b1e124d1d049d0d` | 2022-03-14 | resolvable | included | first qualifying identity |
| 16 | APEUSDT / `catalog48:bb98f3f2625143fc9d5d98c3aae55b1a` | 2022-03-17 | resolvable | included | first qualifying identity |
| 17 | OPUSDT / `catalog48:ce9176af28a148d4993972a1caeffda0` | 2022-06-01 | resolvable | included | first qualifying identity |
| 18 | INJUSDT / `catalog48:c562f0d46b0e404c89d9eb8e56a70a2c` | 2022-08-16 | resolvable | included | first qualifying identity |
| 19 | LDOUSDT / `catalog48:d6c6c06ddb074c829d90155b0aba661b` | 2022-09-21 | resolvable | included | first qualifying identity |
| 20 | APTUSDT / `catalog48:f9df5bba5e1c4f1e9289240d0f9344e2` | 2022-10-18 | resolvable | included; stop | TARGET_N reached |

`BNXUSDT` is excluded before ordering by the existing retained relaunch
ambiguity, but is not encountered before the cohort freezes.

## Frozen cohort and size

The exact identities, `cohort_digest`, and `piece_contract_digest` are in
`declaration.json`.  `TARGET_N=20`, `ACTUAL_N=20`, and
`MIN_ACCEPTABLE_N=10`.

The launch-date composition is 1 (2019), 6 (2020), 6 (2021), and 7 (2022).
All twenty selected symbols have `PRIOR_OUTCOME_EXPOSURE=NO`: this was checked
only by symbol presence in committed strategy-result artifacts, without reading
their metrics.  This selection is therefore externally untested in the
QntyLab strategy-result record.

## Missingness contract

Membership is immutable and distinct from availability, usability, and outcome
availability.  Each member × scheduled decision must later retain a usable or
declared-missing state.  A delist, source gap, absent archive, failed strategy
path, insufficient state history, or post-freeze identity conflict remains
denominator telemetry and cannot cause replacement.

## Selection falsifiers

| Check | Status | Basis |
|---|---|---|
| F1 current-survivor leakage | PASS | no live-roster input exists in the declaration |
| F2 future-data leakage | PASS | availability and future rows are absent from ordering |
| F3 outcome leakage | PASS | outcomes are absent from source and declaration inputs |
| F4 relaunch ambiguity | PASS | BNXUSDT excluded before ordering |
| F5 post-freeze data failure | PASS | immutable membership/missingness contract |
| F6 delist | PASS | immutable membership/missingness contract |
| F7 twenty-one qualifies | PASS | stop at exact first 20 |
| F8 twelve qualify | PASS | rule freezes all 10–19 qualifiers |
| F9 nine qualify | PASS | rule declares cohort not earned below 10 |
| F10 insufficient evidence | PASS | the retained receipt supplies 20 unambiguous pre-cutoff identities; no archaeology reopened |

## Claim boundary and ten-stack verdict

This is source-conditioned cross-sectional falsification, not an exchange-wide
or pristine-OOS sample.  It keeps common BTC/ETH/SOL market state separate from
new-asset outcomes, makes source provenance and survivorship risk explicit,
uses a minimal deterministic design, and prevents cybernetic replacement after
missingness.  It can update the weak V0 result but cannot promote it to trading
authority or a universal trend-regime claim.

## Primary decision and next action

`EXTERNAL_REPLICATION_COHORT_FROZEN`

`EXECUTE_FROZEN_DRAWDOWN_PIECE_EXTERNAL_REPLICATION`
