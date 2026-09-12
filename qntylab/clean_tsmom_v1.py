"""Clean V1's unchanged nine-symbol signal and equal-weight rule."""
from __future__ import annotations

import numpy as np

from .clean_tsmom import SYMBOLS, signal


def weights_v1(closes: np.ndarray) -> np.ndarray:
    if closes.ndim != 2 or closes.shape[1] != len(SYMBOLS):
        raise ValueError(f"expected [bars,{len(SYMBOLS)}] closes")
    return np.column_stack([signal(closes[:, i]) for i in range(len(SYMBOLS))]) / len(SYMBOLS)
