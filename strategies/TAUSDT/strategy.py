#!/usr/bin/env python3
"""TAUSDT 专属主力战术策略 (主力插针扫损反手) — 遵循底层基石，可针对该标的独立定制。"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLKIT_SCRIPTS = REPO_ROOT / "skills" / "ticker-strategy" / "scripts"
if str(TOOLKIT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TOOLKIT_SCRIPTS))

from arena import adx, atr, bollinger_bands, donchian, ema, rsi, sma  # noqa: E402

SYMBOL = "TAUSDT"
ASSET_CLASS = "crypto_alt"
TIMEFRAME = "15m"
DIRECTION = "long_only"
FAMILY = "sweep_fade"

DEFAULT_PARAMS: dict[str, Any] = {
    "lookback": 36,
    "min_wick": 0.38,
    "atr_sl_mult": 2.5
}


def generate_signals(df: pd.DataFrame, params: dict[str, Any] | None = None) -> dict[str, np.ndarray]:
    """返回 {entry_long, entry_short, exit_long, exit_short} 布尔信号数组。"""
    p = {**DEFAULT_PARAMS, **(params or {})}
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)

    lookback = int(p["lookback"])
    min_wick = float(p["min_wick"])

    hi, lo = donchian(h, l, lookback)
    prev_hi = np.roll(hi, 1)
    prev_lo = np.roll(lo, 1)
    prev_hi[0] = np.nan
    prev_lo[0] = np.nan

    bar_range = np.maximum(h - l, 1e-12)
    lower_wick = (np.minimum(o, c) - l) / bar_range
    upper_wick = (h - np.maximum(o, c)) / bar_range
    mid_exit = sma(c, lookback)

    entry_long = (l < prev_lo) & (c > prev_lo) & (lower_wick >= min_wick)
    entry_short = (h > prev_hi) & (c < prev_hi) & (upper_wick >= min_wick)
    exit_long = c >= mid_exit
    exit_short = c <= mid_exit
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }


if __name__ == "__main__":
    import subprocess

    cli = TOOLKIT_SCRIPTS / "build_strategy.py"
    subprocess.run([sys.executable, str(cli), "rerun", "--symbol", SYMBOL], check=True)
