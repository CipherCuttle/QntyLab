# ADR 0003: DVOL V0 Phase 1B non-primary live smoke

**Status:** `ACCEPTED_FOR_ONE_NON_PRIMARY_LIVE_SOURCE_SMOKE_ONLY`

The Phase 0 protocol and Phase 1A offline core remain immutable. This decision
authorizes one bounded public-source smoke, outside a protocol primary formation
window, solely to exercise the frozen Deribit and Binance source contracts.

The smoke creates no scheduled-week artifact, primary observation, predictor,
outcome, forecast error, or scientific evidence. Raw application and HTTP bytes
remain under a new `/tmp` artifact root and outside Git; Git receives only a
non-sensitive receipt. Credentials are neither needed nor permitted.

Only the frozen Deribit hostname, channels and subscription method, and the
frozen Binance hostname, symbols and endpoint may be used. There is no fallback
venue, hostname, symbol, channel, endpoint, scheduler, service, or recurrence.
Re-running the smoke requires separate authority. Scheduled collection remains
separately gated.
