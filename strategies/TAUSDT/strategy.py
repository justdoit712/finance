#!/usr/bin/env python3
"""TAUSDT 专属量化策略 (趋势回踩 RSI 恢复) — 自动生成后可针对该标的独立定制。"""

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
TIMEFRAME = "15m"
DIRECTION = "short_only"
FAMILY = "rsi_momentum_pullback"

DEFAULT_PARAMS: dict[str, Any] = {
    "trend_len": 100,
    "rsi_len": 14,
    "pullback_low": 36.0,
    "atr_sl_mult": 2.6
}


def generate_signals(df: pd.DataFrame, params: dict[str, Any] | None = None) -> dict[str, np.ndarray]:
    """返回 {entry_long, entry_short, exit_long, exit_short} 布尔信号数组。"""
    p = {**DEFAULT_PARAMS, **(params or {})}
    close = df["close"].to_numpy(dtype=float)
    pullback_low = float(p["pullback_low"])
    pullback_high = 100.0 - pullback_low

    trend_ema = ema(close, int(p["trend_len"]))
    rsi_arr = rsi(close, int(p["rsi_len"]))
    prev_rsi = np.roll(rsi_arr, 1)
    prev_rsi[0] = np.nan

    entry_long = (close > trend_ema) & (prev_rsi < pullback_low) & (rsi_arr >= pullback_low)
    entry_short = (close < trend_ema) & (prev_rsi > pullback_high) & (rsi_arr <= pullback_high)
    exit_long = (rsi_arr > 72.0) | (close < trend_ema * 0.99)
    exit_short = (rsi_arr < 28.0) | (close > trend_ema * 1.01)
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
