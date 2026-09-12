# Clean TSMOM EXP_V2 accounting semantics R5

R5 is an additive, recoverable preregistration accounting amendment. It does
not change the nine-symbol universe, dates, signals, volatility, funding sign,
cost rates, thresholds, or any frozen V2/R1/R2/R3/R4 file.

The interval ledger is authoritative for accounting. Entry and final
liquidation occur inside scored intervals; no extra liquidation observation is
created. Metrics are reconstructed from serialized ledgers and equity points.
The fixed-quantity benchmark uses additive USD price PnL and causal completed
hourly close references for funding. This amendment is frozen without running
the real source bundle or observing a corrected EXP_V2 result.
