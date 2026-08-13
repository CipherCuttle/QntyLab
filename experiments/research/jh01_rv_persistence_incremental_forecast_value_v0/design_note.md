# JH01 incremental forecast-value preregistration V0

## Scope

This is an outcome-blind preregistration, not a forecast execution. It asks a
different question from the completed JH01 association and temporal replication:
whether an expanding, fitted one-lag representation has material out-of-time
forecast value over literal persistence. It creates no causal, economic-edge,
State Snapshot, Router, Qnty, trading, or promotion authority.

## Forensic finding

The inherited target is unannualized realized volatility, not variance:
`RV24_prior,t = sqrt(sum r_m,h^2)` for returns ending at the 00:00Z decision,
and `RV24_future,t = sqrt(sum r_m,h^2)` for the following 24 hourly returns.
The daily future windows are adjacent and non-overlapping. The market return is
the equal-weighted mean of 20 panel members' hourly log-close returns.

## Methodology review

SOURCE-SUPPORTED FACT: realized-volatility series exhibit persistent dynamics,
which is why association alone is not a forecast-value result ([Andersen,
Bollerslev, Diebold & Labys, 2001](https://public.econ.duke.edu/~boller/Published_Papers/jasa_01.pdf)).

SOURCE-SUPPORTED FACT: HAR-RV is a parsimonious multi-horizon realized-
volatility model, motivating the fixed 1/7/30-day secondary comparator
([Corsi, 2009](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1365738)).

SOURCE-SUPPORTED FACT: predictive-accuracy comparison is based on forecast
loss differentials ([Diebold & Mariano, 1995](https://ink.library.smu.edu.sg/soe_research/347/));
the primary fitted-versus-fixed nested comparison therefore uses the
preregistered Clark-West-style adjusted MSPE direction rather than an
unadjusted nested-model test ([Clark & West, 2007](https://doi.org/10.1016/j.jeconom.2006.05.023)).

SOURCE-SUPPORTED FACT: repeated specification selection risks data snooping
([White, 2000](https://doi.org/10.1111/1468-0262.00152)).

DESIGN DECISION: preserve the exact 24-hour, untransformed-volatility target;
make MSE primary and MAE secondary; use a 5% relative-MSE materiality threshold;
freeze one primary comparison; and prohibit all rescue variants. The 5% is a
decision threshold, not a claimed literature-derived physical constant.

INFERENCE: the exact historical discovery and replication periods are
outcome-seen and cannot be a new confirmatory holdout. No repository artifact
proves an untouched historical interval. The only defensible protocol is the
fixed, post-preregistration-acquired 365-origin interval beginning 2026-07-20.

UNRESOLVED: whether the future protocol can be executed depends on a later,
separately authorised input/materialization phase. This phase accessed neither
those inputs nor their outcomes.

## Termination rule

Failure of the primary gates means JH01 remains valid descriptive persistence
knowledge but is not established as an incremental forecasting primitive. It
does not make volatility persistence false and cannot be repaired by trying
other horizons, targets, losses, panels, windows, or benchmarks here.
