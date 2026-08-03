# ADR 0004: DVOL V0 Phase 1B evidence-retention repair

**Status:** `ACCEPTED_FOR_OFFLINE_EVIDENCE_REPAIR_ONLY`

The first Phase 1B smoke and its receipt remain immutable. Its acknowledgement
mismatch is `ACK_UNRESOLVED`: the offending payload was not retained, so the
historical result is not reclassified or inferred.

This decision authorizes offline code repair and fake-transport tests only. For
every future source message, exact payload bytes are retained and indexed before
strict decoding, parsing, validation, or classification. The receive invariant
is `RECEIVE -> TIMESTAMP -> HASH -> RETAIN -> INDEX -> PARSE -> CLASSIFY`.

Current first-party Deribit documentation defines `public/subscribe` success
`result` as the subscribed-channel list but gives no response-order guarantee.
Acknowledgement validation therefore requires exactly the requested two unique
string channels as a set; requested and returned order remain diagnostics.

Deribit, Binance BTC, and Binance ETH probes are independent, have one attempt
each, and retain successful source evidence even when another source blocks.
The 90-second Deribit receive deadline begins immediately after subscription
send and is absolute: unrelated or intermittent messages cannot renew it.
Pre-acknowledgement notifications are retained and classified but not counted.
Any sequential UTC or monotonic-clock regression is a global integrity failure
which stops later probes while retaining earlier evidence. The live command
fail-closes on repository root, branch, clean worktree, exact commit, and mode.
Non-200 HTTP responses retain status, selected headers, body bytes, digest, and
byte count. Publication uses Linux no-replace rename semantics; manifest and
status bind protocol hash, commit, mode, run bounds, verdict, and source results.
This does not authorize a network call, rerun, scheduled collection, primary
observation, Phase 0/Phase 1A change, or QNTY work. Another independent hostile
review is required; a separate ADR is required before exactly one rerun.
