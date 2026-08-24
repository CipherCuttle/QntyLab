# DSH Stage-A V1R3R2 V0R6 one-episode live execution closure

Terminal outcome: `V0R6_LIVE_EPISODE_CLOSED_BLOCKED_NO_REPLAY`.

The exact canonical activation merge was verified from Git topology at
`4195433872140634784c404f88fa0c70a6bcfd11`, with parents
`6a20d9cfb2c485d7f43ccc04141c6365b5add9a0` and
`35d2b49f17733a007a3d1af841ed223262e18636`. The repaired `EpisodeClaim`
implementation identity matched the frozen blob and SHA-256.

The fresh production DSH_HOME materializer and whole-home identity gate passed,
but the shared production preparation path then failed closed at the successor
contract gate with `BLOCK_RUNTIME_IDENTITY`: recomputation produced
`a918ae98a4724d0bfea68b9112358ebf7ab0609d666897558767cd81f0b720d5`, while the
frozen predecessor composite contract is
`a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be`. The
frozen policy digest for the claim source and the current repaired claim source
also differ. This is recorded as `STOP_SOURCE_CONFLICT`.

The episode stopped before disposable fixture preparation, secret read, claim
attempt, DSH invocation, parent/provider I/O, child turns, fixture tests, and
spend. The V0R6 claim ref and local state remained absent. V0R5 was not touched.
No runtime repair, claim repair, replay, second episode, V0R7, or infrastructure
loop is authorized. Full structured evidence is in `execution_evidence.json`.

The project is closed with no Stage B, Qnty, scientific, trading, capital,
promotion, or broader production authority. Any future reconciliation requires
separate explicit Git-backed authority.
