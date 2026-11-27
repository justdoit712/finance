#!/usr/bin/env python3
"""ETHUSDT 专属量化策略 (布林+RSI 均值回归) — 自动生成后可针对该标的独立定制。"""

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
TIMEFRAME = "1h"
DIRECTION = "short_only"
FAMILY = "bb_mean_reversion"

DEFAULT_PARAMS: dict[str, Any] = {
    "bb_len": 16,
    "bb_std": 2.4,
    "rsi_os": 28.0,
    "atr_sl_mult": 2.5
}


def generate_signals(df: pd.DataFrame, params: dict[str, Any] | None = None) -> dict[str, np.ndarray]:
    """返回 {entry_long, entry_short, exit_long, exit_short} 布尔信号数组。"""
    p = {**DEFAULT_PARAMS, **(params or {})}
    close = df["close"].to_numpy(dtype=float)
    rsi_os = float(p["rsi_os"])
    rsi_ob = 100.0 - rsi_os

    mid, upper, lower = bollinger_bands(close, int(p["bb_len"]), float(p["bb_std"]))
    rsi_arr = rsi(close, 14)
    macro_ema = ema(close, int(p.get("trend_ema", 200)))

    entry_long = (close < lower) & (rsi_arr <= rsi_os) & (close >= macro_ema * 0.94)
    entry_short = (close > upper) & (rsi_arr >= rsi_ob) & (close <= macro_ema * 1.06)
    exit_long = close >= mid
    exit_short = close <= mid
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
