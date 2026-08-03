# ADR 0002: DVOL V0 Phase 1A offline capture core

**Status:** `ACCEPTED_FOR_OFFLINE_CAPTURE_CORE_ONLY`

Phase 0 protocol bytes and hash remain immutable. This decision authorizes only
offline implementation and deterministic fixture replay. It authorizes no live
WebSocket or HTTP request, no scheduled primary observation, and no scientific
evidence from fixture artifacts. No protocol authority boolean is modified.

Live transport and a controlled source-contract smoke require a separate,
reviewed task. Outcome finalization and forecast comparison remain deferred.
QNTY is completely out of scope. This is an experiment-specific boundary, not a
generic authority framework.
