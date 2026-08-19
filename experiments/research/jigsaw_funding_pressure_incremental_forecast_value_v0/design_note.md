# Funding-pressure incremental forecast-value preregistration V0

## Decision

Select `A_EXPLORATORY_610_INCREMENTAL_FORECAST_TEST`. The 610 historical
funding decisions are already outcome-exposed because the old aggregate result
is immutable and known. They may support a causal rolling forecast comparison
as exploratory development/evidence only; they are not sealed, unseen,
prospective, or independent confirmation.

The fixed test uses the existing continuous funding-pressure ECDF percentile
and one expanding OLS HAR-RV-style baseline with daily, weekly, and monthly
components. M1 adds exactly one linear funding predictor to M0. Literal RV24
persistence is retained as a descriptive context benchmark only.

## Why not B, C, or D?

The canonical funding materialization ends on 2025-06-19, and REEF lifecycle
evidence terminates within the later candidate period. No later complete
20-member funding/OHLCV input and warm-up is Git-bound, so a disjoint sealed
evaluation cannot be outcome-blind feasibility-certified without new
acquisition. Current-listing substitution and survivor-panel selection are
prohibited.

A prospective campaign would require a new long-lived funding recorder and
would duplicate the calendar and operational burden of the separate JH01 V1
campaign, which remains `ARMED_BUT_INACTIVE` and has had no scientific
evaluation here. A is therefore the highest-information bounded discriminator
per cost. D is not selected because this narrow exploratory question can be
answered without laundering the old sample into confirmation.

## Frozen statistical contract

The development labels are origins `2023-10-19` through `2024-10-17` (365
origins whose target completion is strictly before the first forecast origin).
The exploratory forecast range is `2024-10-19` through `2025-06-19` (244 daily
origins). The boundary origin `2024-10-18` is not used because its target is
not complete strictly before `2024-10-19`.

At each origin, fit only on completed target rows from the expanding history.
Use MSE on the exact untransformed future market-wide RV24 target. The primary
comparison is the nested M1-versus-M0 Clark-West adjusted MSPE test with
Bartlett Newey-West HAC bandwidth fixed at 5 and one-sided alpha 0.05.

No defensible deployment-specific practical threshold exists for this
prior-exposed exploratory discriminator, so `MATERIALITY_GATE =
NONE_JUSTIFIABLE`. A positive classification is consequently limited to
exploratory incremental predictive information; it cannot be called material,
economic, actionable, causal, or confirmatory.

## Absolute boundary

This artifact freezes design only. It grants no execution, data acquisition,
outcome access, model fitting, forecast persistence, result recording, Router,
Qnty, trading, capital, or promotion authority.
