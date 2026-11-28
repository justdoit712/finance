#!/usr/bin/env python3
"""ETHUSDT 专属主力战术策略 (主力巨量派发/衰竭反转) — 遵循底层基石，可针对该标的独立定制。"""

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

SYMBOL = "ETHUSDT"
ASSET_CLASS = "crypto_major"
TIMEFRAME = "1h"
DIRECTION = "short_only"
FAMILY = "climax_reversal"

DEFAULT_PARAMS: dict[str, Any] = {
    "bb_len": 16,
    "bb_std": 2.5,
    "rsi_os": 32.0,
    "vol_spike": 2.0,
    "atr_sl_mult": 2.5
}


def generate_signals(df: pd.DataFrame, params: dict[str, Any] | None = None) -> dict[str, np.ndarray]:
    """返回 {entry_long, entry_short, exit_long, exit_short} 布尔信号数组。"""
    p = {**DEFAULT_PARAMS, **(params or {})}
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    rsi_os = float(p["rsi_os"])
    rsi_ob = 100.0 - rsi_os
    vol_spike = float(p.get("vol_spike", 1.5))

    mid, upper, lower = bollinger_bands(c, int(p["bb_len"]), float(p["bb_std"]))
    rsi_arr = rsi(c, 14)
    macro_ema = ema(c, 200)
    vol_ma = sma(vol, 20)

    bar_range = np.maximum(h - l, 1e-12)
    lower_wick = (np.minimum(o, c) - l) / bar_range
    upper_wick = (h - np.maximum(o, c)) / bar_range

    exhaust_long = (vol >= vol_ma * vol_spike) | (lower_wick >= 0.35)
    exhaust_short = (vol >= vol_ma * vol_spike) | (upper_wick >= 0.35)

    entry_long = (c < lower) & (rsi_arr <= rsi_os) & exhaust_long & (c >= macro_ema * 0.92)
    entry_short = (c > upper) & (rsi_arr >= rsi_ob) & exhaust_short & (c <= macro_ema * 1.08)
    exit_long = c >= mid
    exit_short = c <= mid
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
