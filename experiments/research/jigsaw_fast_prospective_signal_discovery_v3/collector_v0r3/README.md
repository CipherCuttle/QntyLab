# JFPV3 PR-B R3 — transport-window repair

This bounded repair corrects only the Binance USD-M kline request boundary used by the JFPV3 prospective collector.

The frozen scientific contracts define logical hourly close timestamps. Binance kline REST parameters select candles by open time. R2 passed logical close bounds directly as `startTime`/`endTime` and then translated each returned row to `open_time + 1h`, shifting the logical window one hour forward.

R3 preserves R2 history and scientific contracts, introduces a new implementation identity, and translates both provider bounds by exactly `-1h`. No activation, network access, market-data access, prospective feature/outcome computation, inference, or classification occurs in this repair phase.

The canonical R2 activation authorization remains unused (`valid_activation_count = 0`) and must not be used for R3. After this repair is canonical, issue a fresh activation authorization bound to the R3 implementation identity.
