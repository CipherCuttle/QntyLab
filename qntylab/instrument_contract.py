"""Frozen instrument contracts (Research Factory V2, Seam 2).

``variant_id`` is the *strategy recipe* identity and is deliberately left
unchanged: the same recipe may legitimately be evaluated on spot and on a
perpetual, and that must not read as two different strategies.

What changes is the *evaluation* identity.  Every new trial declares an
``instrument_contract_id`` naming the venue, market, settlement asset, contract
type, price-source contract and funding applicability under which it was run.

The corpus must never pool trials across instrument contracts by accident:
``BTCUSDT`` spot and ``BTCUSDT`` USD-M perpetual are different instruments with
different return series and a funding leg that spot does not have.  Ticker text
matching is not instrument identity.

This module also freezes the perpetual economic boundary.  The funding pipeline
itself is explicitly out of scope for this phase; the invariant that prevents V2
from silently treating perps as spot is not.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

INSTRUMENT_CONTRACT_SCHEMA_VERSION = "INSTRUMENT_CONTRACT_V0"

BINANCE_SPOT_USDT_V1 = "BINANCE_SPOT_USDT_V1"
BINANCE_USDM_PERPETUAL_USDT_V1 = "BINANCE_USDM_PERPETUAL_USDT_V1"

# funding_applicability values
FUNDING_NOT_PART_OF_INSTRUMENT = "FUNDING_NOT_PART_OF_INSTRUMENT"
FUNDING_REQUIRED = "FUNDING_REQUIRED"

# funding_treatment values declared per trial
FUNDING_INCLUDED_PROVENANCE_BOUND = "FUNDING_INCLUDED_PROVENANCE_BOUND"
FUNDING_PROVEN_ZERO_BY_CONTRACT = "FUNDING_PROVEN_ZERO_BY_CONTRACT"
TRIAL_BLOCKED_BY_FUNDING_EVIDENCE = "TRIAL_BLOCKED_BY_FUNDING_EVIDENCE"
FUNDING_NOT_APPLICABLE = "FUNDING_NOT_APPLICABLE"

FUNDING_TREATMENTS = frozenset(
    {
        FUNDING_INCLUDED_PROVENANCE_BOUND,
        FUNDING_PROVEN_ZERO_BY_CONTRACT,
        TRIAL_BLOCKED_BY_FUNDING_EVIDENCE,
        FUNDING_NOT_APPLICABLE,
    }
)

# Treatments a position-bearing trial may declare on a funding-bearing instrument.
# FUNDING_NOT_APPLICABLE is deliberately absent: that is the exact laundering
# this seam exists to prevent.
FUNDING_BEARING_ALLOWED_TREATMENTS = frozenset(
    {
        FUNDING_INCLUDED_PROVENANCE_BOUND,
        FUNDING_PROVEN_ZERO_BY_CONTRACT,
        TRIAL_BLOCKED_BY_FUNDING_EVIDENCE,
    }
)


class InstrumentContractError(RuntimeError):
    """Raised on unknown contracts or forbidden funding declarations."""


_CONTRACT_PAYLOADS: dict[str, dict[str, Any]] = {
    BINANCE_SPOT_USDT_V1: {
        "instrument_contract_id": BINANCE_SPOT_USDT_V1,
        "venue": "BINANCE",
        "market_type": "SPOT",
        "settlement_asset": "USDT",
        "contract_type": "SPOT",
        "price_source_contract": "BINANCE_SPOT_PUBLIC_KLINES_1H_V1",
        "funding_applicability": FUNDING_NOT_PART_OF_INSTRUMENT,
        "schema_version": INSTRUMENT_CONTRACT_SCHEMA_VERSION,
    },
    BINANCE_USDM_PERPETUAL_USDT_V1: {
        "instrument_contract_id": BINANCE_USDM_PERPETUAL_USDT_V1,
        "venue": "BINANCE",
        "market_type": "USD_M_FUTURES",
        "settlement_asset": "USDT",
        "contract_type": "PERPETUAL",
        "price_source_contract": "BINANCE_USD_M_PERPETUAL_1H_MATERIALIZER_V0",
        "funding_applicability": FUNDING_REQUIRED,
        "schema_version": INSTRUMENT_CONTRACT_SCHEMA_VERSION,
    },
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def known_contract_ids() -> list[str]:
    return sorted(_CONTRACT_PAYLOADS)


def contract_payload(instrument_contract_id: str) -> dict[str, Any]:
    """Immutable canonical payload for a frozen instrument contract."""
    if not isinstance(instrument_contract_id, str) or not instrument_contract_id.strip():
        raise InstrumentContractError("instrument_contract_id must be a non-empty string")
    payload = _CONTRACT_PAYLOADS.get(instrument_contract_id)
    if payload is None:
        raise InstrumentContractError(
            f"unknown instrument_contract_id {instrument_contract_id!r}; known: {known_contract_ids()}"
        )
    return dict(sorted(payload.items()))


def contract_digest(instrument_contract_id: str) -> str:
    return hashlib.sha256(_canonical_bytes(contract_payload(instrument_contract_id))).hexdigest()


def is_funding_bearing(instrument_contract_id: str) -> bool:
    return contract_payload(instrument_contract_id)["funding_applicability"] == FUNDING_REQUIRED


def validate_funding_treatment(
    *,
    instrument_contract_id: str,
    funding_treatment: str,
    has_position_exposure: bool,
) -> str:
    """Enforce the frozen perpetual economic boundary.

    A position-bearing trial on a funding-bearing instrument must declare an
    explicit funding-cost treatment.  ``FUNDING_NOT_APPLICABLE`` is forbidden
    there -- it is true of spot and false of a perpetual, and accepting it is
    how a perp corpus silently becomes a spot corpus.

    ``TRIAL_BLOCKED_BY_FUNDING_EVIDENCE`` is a legal declaration but not a legal
    completion; the runner refuses to emit a completed trial under it.
    """
    if funding_treatment not in FUNDING_TREATMENTS:
        raise InstrumentContractError(
            f"unknown funding_treatment {funding_treatment!r}; known: {sorted(FUNDING_TREATMENTS)}"
        )
    if is_funding_bearing(instrument_contract_id) and has_position_exposure:
        if funding_treatment not in FUNDING_BEARING_ALLOWED_TREATMENTS:
            raise InstrumentContractError(
                f"{funding_treatment} is forbidden for a position-bearing trial on "
                f"{instrument_contract_id}: a perpetual position bears funding. Declare one of "
                f"{sorted(FUNDING_BEARING_ALLOWED_TREATMENTS)}."
            )
    return funding_treatment


def assert_single_instrument_contract(instrument_contract_ids: list[str], *, allow_cross_instrument: bool = False) -> str | None:
    """Default corpus rule: FAIL_CLOSED_ON_MIXED_INSTRUMENT_CORPUS."""
    distinct = sorted({value for value in instrument_contract_ids})
    if not distinct:
        return None
    if len(distinct) > 1 and not allow_cross_instrument:
        raise InstrumentContractError(
            "FAIL_CLOSED_ON_MIXED_INSTRUMENT_CORPUS: refusing to pool trials across instrument "
            f"contracts {distinct}; pass allow_cross_instrument=True to declare an explicit "
            "cross-instrument comparison"
        )
    return distinct[0] if len(distinct) == 1 else None


def contracts_payload() -> dict[str, Any]:
    return {
        "contracts": {key: contract_payload(key) for key in known_contract_ids()},
        "digests": {key: contract_digest(key) for key in known_contract_ids()},
        "schema_version": INSTRUMENT_CONTRACT_SCHEMA_VERSION,
    }
