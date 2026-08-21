"""Small offline CLI for the V1R1 parent request reservation gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dsh_stage_a_v1r1 import ParentLlmBudgetGate, ParentRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    reserve = sub.add_parser("reserve-parent")
    reserve.add_argument("--provider", required=True)
    reserve.add_argument("--model", required=True)
    reserve.add_argument("--max-tokens", required=True, type=int)
    reserve.add_argument("--retry-max", required=True, type=int)
    reserve.add_argument("--agent-loop", required=True)
    reserve.add_argument("--purpose")
    args = parser.parse_args(argv)
    try:
        gate = ParentLlmBudgetGate(Path(args.state))
        attempt = gate.reserve(ParentRequest(
            provider=args.provider,
            model=args.model,
            max_tokens=args.max_tokens,
            retry_max=args.retry_max,
            agent_loop=args.agent_loop == "True",
            purpose=args.purpose,
        ))
        print(json.dumps({"attempt": attempt}, sort_keys=True))
        return 0
    except Exception as exc:  # CLI is a fail-closed process boundary.
        print(f"qntylab parent gate denied: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
