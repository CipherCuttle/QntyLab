# Clean TSMOM V1/V2 v0

This is one fixed, exploratory QntyLab-native post-selection evaluation. Historical Qnty V1/V2 outputs are not accepted as reproducible authority: their code, narratives, inputs and execution semantics conflict. Historical parity is therefore not claimed.

Both packages use the same fixed ten-symbol Binance USD-M perpetual universe, 20 completed 8-hour-bar log momentum, long/flat direction, and causal t+1 execution. V1 gives every active signal 0.10 weight and leaves the remainder in cash. V2 allocates the same active-count gross budget by trailing 90-return inverse volatility and never exceeds gross 1.0. Funding is settled public funding with `-weight * rate`; costs are explicit 7.5 bps base and 15 bps stress per unit turnover.

The dates are labelled `POST_SELECTION_EVALUATION`, not a pristine or scientific holdout, because June 2026 evidence was previously seen. Results are preliminary diagnostics only: they do not authorize tuning, another evaluation, paper/shadow/live trading, QNTY integration, or DVOL changes.
