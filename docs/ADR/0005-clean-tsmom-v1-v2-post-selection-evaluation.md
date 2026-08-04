# ADR 0005: Clean TSMOM V1/V2 post-selection evaluation

Status: `ACCEPTED_FOR_ONE_CLEAN_POST_SELECTION_EVALUATION`

Historical parity is not claimed and historical results are non-authoritative. This ADR freezes a clean reconstruction: one fixed ten-symbol universe, one 20-bar long/flat signal, two sizing packages, one post-selection evaluation, actual settled funding, explicit base/stress costs, and no tuning or second variant.

Clean rules supersede conflicting historical behavior. The experiment has no paper, shadow, live, QNTY, DVOL, scientific-validation, or trading authority. It is exploratory-only. The evaluation period is not a pristine holdout.

Historical lineage receipt: V1 head `128e01ab4ad97b5b92c4c6c623dff83b79aed0c2`, tree `4327db920d67ef61c3670a265ce0acfbe412fa2d`; V2 head `6c2872fa4487d5d0c063717d7482c93fd7131255`, tree `20b7bcf3bfafdf9e8631f322b4d11dbbd5f755ed`. The receipt preserves `HISTORICAL_PARITY_NOT_CLAIMED`, `HISTORICAL_RESULTS_NON_AUTHORITATIVE`, and `CLEAN_RECONSTRUCTION_REQUIRED`.

Frozen dates: warmup 2026-03-01 through evaluation start 2026-04-23; evaluation end exclusive 2026-08-01; diagnostic tail 2026-06-19 through 2026-08-01. The primary classification and V2 comparison rules are those in the experiment request and are encoded in `evaluation_v0.json` and the run receipt.
