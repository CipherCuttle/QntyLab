"""Constrained HTTP wrapper for the Order Flow V1 Frankfurt execution relay.

This is not a generic proxy. It exposes only health, non-scientific smoke, and
one frozen-panel/current-window kline route. Historical windows, arbitrary
symbols, arbitrary URLs, persistence, and scheduling are not available.
"""
from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from urllib.parse import parse_qs, urlparse

from .order_flow_prospective_v1_relay import RelayBlocked, fetch_current_scientific_row, run_non_scientific_smoke


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "QntyLabOrderFlowRelay/1"

    def _send(self, status: int, payload: object) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(HTTPStatus.OK, {"status": "ok", "mode": "ORDER_FLOW_V1_EXECUTION_RELAY"})
            return
        try:
            if parsed.path == "/v1/smoke":
                self._send(HTTPStatus.OK, run_non_scientific_smoke())
                return
            if parsed.path == "/v1/row":
                query = parse_qs(parsed.query, strict_parsing=True)
                if set(query) != {"symbol", "logical_close_utc"}:
                    raise RelayBlocked("exact symbol and logical_close_utc query required")
                symbol_values = query["symbol"]
                close_values = query["logical_close_utc"]
                if len(symbol_values) != 1 or len(close_values) != 1:
                    raise RelayBlocked("query parameters must be singular")
                payload = fetch_current_scientific_row(
                    symbol=symbol_values[0], logical_close=close_values[0]
                )
                self._send(HTTPStatus.OK, payload)
                return
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except (RelayBlocked, ValueError) as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            self._send(HTTPStatus.BAD_GATEWAY, {"error": "provider_unavailable"})


def main() -> None:
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
