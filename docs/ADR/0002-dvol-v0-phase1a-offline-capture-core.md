# ADR 0002: DVOL V0 Phase 1A offline capture core

**Status:** `ACCEPTED_FOR_OFFLINE_CAPTURE_CORE_ONLY`

Phase 0 protocol bytes and hash remain immutable. This decision authorizes only
offline implementation and deterministic fixture replay. The implementation has
no HTTP adapter, `requests` dependency, WebSocket transport, live command, or
network-capable replay path. It authorizes no scheduled primary observation and
no scientific evidence from fixture artifacts. No protocol authority boolean is
modified.

Replay retains fixture payload bytes through explicit base64 input encoding and
writes a canonical Deribit event index, including local non-payload operational
records. It retains fixture Binance response bytes and request/response metadata
only for captured fixture formations. Outcome retrieval, forecast comparison,
and any real-source behavior remain unimplemented and untested. QNTY is
completely out of scope. This is an experiment-specific boundary, not a generic
authority framework.
