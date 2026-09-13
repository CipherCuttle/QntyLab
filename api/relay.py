from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from qntylab.order_flow_prospective_v1_relay import (
    RelayBlocked,
    fetch_current_scientific_row,
    run_non_scientific_smoke,
)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: object) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query, keep_blank_values=False)
        mode = (params.get("mode") or ["health"])[0]

        try:
            if mode == "health":
                self._send(
                    200,
                    {
                        "mode": "ORDER_FLOW_V1_EXECUTION_RELAY_HEALTH",
                        "region": os.environ.get("VERCEL_REGION"),
                        "status": "PASS",
                    },
                )
                return

            if mode == "smoke":
                self._send(200, run_non_scientific_smoke())
                return

            if mode == "row":
                symbol = (params.get("symbol") or [None])[0]
                logical_close = (params.get("logical_close") or [None])[0]
                if not symbol or not logical_close:
                    self._send(400, {"error": "symbol and logical_close are required"})
                    return
                self._send(
                    200,
                    fetch_current_scientific_row(
                        symbol=symbol,
                        logical_close=logical_close,
                    ),
                )
                return

            self._send(404, {"error": "unsupported mode"})
        except RelayBlocked as exc:
            self._send(422, {"error": str(exc)})
        except Exception:
            self._send(502, {"error": "relay execution failed closed"})

    def log_message(self, format: str, *args: object) -> None:
        return
