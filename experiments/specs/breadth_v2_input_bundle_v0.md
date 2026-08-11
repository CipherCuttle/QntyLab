# Breadth V2 input bundle V0

`BREADTH_V2_INPUT_BUNDLE_V0` is a pure, fail-closed identity contract. It
binds the ordered evaluation boundaries, fixed instrument identity and panel,
one UTC decision clock, authenticated parent bytes, deterministic admitted
price/funding bytes, and separate source provenance digests. It contains no
strategy, cost, return, benchmark, or campaign result.

Price source bars retain their Binance open timestamp. A close from source open
`t` is admitted at `t + 1h`; therefore a target at `t` cannot see the row opened
at `t`. Funding events retain exact millisecond timestamps and are admitted at
the first hourly UTC boundary greater than or equal to the event time. Multiple
events preserve exact source-time order and settle before target generation.

The required source price clip is `[T0 - N hours, T1 - 1 hour]`, where `N` is
the variant-derived required close count. Funding economics include every
event admitted in `[T0,T1]`; carry warmup includes exactly the last registered
number of events admitted at or before `T0`. Missing, duplicate, gapped,
unauthenticated, mismatched, non-complete, or provenance-incomplete inputs
block the bundle. The fixed cross-sectional panel is never shrunk.

Canonical serialization is sorted-key JSON, compact UTF-8, LF-delimited with a
final newline. The resulting strict asset mapping is the only input to the
existing `evaluation_input_bundle_sha256` seam.
