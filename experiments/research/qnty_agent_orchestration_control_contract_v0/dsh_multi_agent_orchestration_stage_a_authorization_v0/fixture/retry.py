"""Tiny synthetic fixture: retry a callable with bounded backoff.

Stage-A disposable fixture (STAGE_A_BOUNDED_RETRY_V0). Not QntyLab or Qnty
production code.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 0.01,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn`` until it succeeds or ``max_attempts`` attempts are used.

    Sleeps ``base_delay * 2 ** attempt_index`` between attempts (attempt_index
    starting at 0 for the delay after the first failed attempt), but must not
    sleep after the final failed attempt. On exhaustion, re-raises the most
    recent exception raised by ``fn`` (not the first).

    Implement this. The current body is intentionally incomplete.
    """
    raise NotImplementedError("STAGE_A_BOUNDED_RETRY_V0: implement retry_with_backoff")
