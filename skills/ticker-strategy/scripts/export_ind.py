#!/usr/bin/env python3
"""Generate Flowsurface language(1) .ind overlay scripts for per-ticker strategies."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any


def _header(symbol: str, title: str, max_bars_back: int = 2) -> str:
    sym_lower = symbol.lower()
    return "\n".join([
        "language(1)",
        f'indicator("{symbol} {title}", id = "strategy.{sym_lower}", max_bars_back = {max_bars_back})',
        'display(view = "plot", attachment = "overlay")',
        'format(precision = "base_ticker_min_tick")',
        'style("bull", title = "Long / Fast", role = "success", shade = "base")',
        'style("bear", title = "Short / Slow", role = "danger", shade = "base")',
        'style("mid", title = "Basis / Filter", role = "neutral", shade = "base")',
        'style("band", title = "Band Fill", role = "primary", shade = "faint")',
    ])


def _direction_flags(direction: str) -> tuple[str, str]:
    allow_long = "true" if direction in ("both", "long_only") else "false"
    allow_short = "true" if direction in ("both", "short_only") else "false"
    return allow_long, allow_short


def _adx_block(period: int = 14) -> str:
    return "\n".join([
        "prev_high = chart.high[1]",
        "prev_low = chart.low[1]",
        "up_move = chart.high - prev_high",
        "down_move = prev_low - chart.low",
        "plus_dm = select(!na(up_move) && !na(down_move) && up_move > down_move && up_move > 0.0, up_move, 0.0)",
        "minus_dm = select(!na(up_move) && !na(down_move) && down_move > up_move && down_move > 0.0, down_move, 0.0)",
        "tr_val = ta.tr(chart.high, chart.low, chart.close)",
        f"atr_val = ta.rma(tr_val, {period})",
        f"plus_rma = ta.rma(plus_dm, {period})",
        f"minus_rma = ta.rma(minus_dm, {period})",
        "plus_di = select(!na(atr_val) && atr_val > 0.0, 100.0 * plus_rma / atr_val, na)",
        "minus_di = select(!na(atr_val) && atr_val > 0.0, 100.0 * minus_rma / atr_val, na)",
        "di_sum = plus_di + minus_di",
        "dx_val = select(!na(di_sum) && di_sum > 0.0, 100.0 * math.abs(plus_di - minus_di) / di_sum, na)",
        f"adx_val = ta.rma(dx_val, {period})",
    ])


def _signal_plots(direction: str) -> str:
    allow_long, allow_short = _direction_flags(direction)
    return "\n".join([
        f"allow_long = {allow_long}",
        f"allow_short = {allow_short}",
        "long_sig = select(allow_long && entry_long, chart.low, na)",
        "short_sig = select(allow_short && entry_short, chart.high, na)",
        'plot(long_sig, id = "long_entry", title = "Long Entry", precision = "instrument", color_slot = "bull", width = 5, pane = "main")',
        'plot(short_sig, id = "short_entry", title = "Short Entry", precision = "instrument", color_slot = "bear", width = 5, pane = "main")',
        'mark(title = "Long Signal", source = "long_entry", kind = "point", color_slot = "bull")',
        'mark(title = "Short Signal", source = "short_entry", kind = "point", color_slot = "bear")',
    ])


def generate_ind_source(symbol: str, family: str, direction: str, params: dict[str, Any]) -> str:
    symbol = symbol.strip().upper()
    if family == "ema_trend":
        fast_len = int(params["fast_len"])
        slow_len = int(params["slow_len"])
        adx_min = float(params.get("adx_min", 18.0))
        body = "\n".join([
            _header(symbol, "EMA Trend", max_bars_back=2),
            f'fast_len = input.int({fast_len}, "Fast EMA", min = 2, max = 200)',
            f'slow_len = input.int({slow_len}, "Slow EMA", min = 5, max = 500)',
            f'adx_min = input.float({adx_min}, "Min ADX", min = 5.0, max = 60.0)',
            "fast = ta.ema(chart.close, fast_len)",
            "slow = ta.ema(chart.close, slow_len)",
            "prev_fast = fast[1]",
            "prev_slow = slow[1]",
            _adx_block(14),
            "entry_long = !na(prev_fast) && !na(prev_slow) && fast > slow && prev_fast <= prev_slow && !na(adx_val) && adx_val >= adx_min",
            "entry_short = !na(prev_fast) && !na(prev_slow) && fast < slow && prev_fast >= prev_slow && !na(adx_val) && adx_val >= adx_min",
            'plot(fast, id = "fast_ema", title = "Fast EMA", precision = "instrument", color_slot = "bull", width = 1.2, pane = "main")',
            'plot(slow, id = "slow_ema", title = "Slow EMA", precision = "instrument", color_slot = "bear", width = 1.2, pane = "main")',
            _signal_plots(direction),
        ])
        return body + "\n"

    if family == "donchian_breakout":
        entry_len = int(params["entry_len"])
        exit_len = int(params["exit_len"])
        vol_mult = float(params.get("vol_mult", 1.1))
        body = "\n".join([
            _header(symbol, "Donchian Breakout", max_bars_back=2),
            f'entry_len = input.int({entry_len}, "Entry Window", min = 5, max = 200)',
            f'exit_len = input.int({exit_len}, "Exit Window", min = 2, max = 100)',
            f'vol_mult = input.float({vol_mult}, "Volume Mult", min = 0.5, max = 5.0)',
            "hi_in = ta.highest(chart.high, entry_len)",
            "lo_in = ta.lowest(chart.low, entry_len)",
            "prev_hi = hi_in[1]",
            "prev_lo = lo_in[1]",
            "hi_out = ta.highest(chart.high, exit_len)",
            "lo_out = ta.lowest(chart.low, exit_len)",
            "vol_ma = ta.sma(chart.volume, 20)",
            "vol_ok = !na(vol_ma) && chart.volume >= vol_ma * vol_mult",
            "entry_long = !na(prev_hi) && chart.close > prev_hi && vol_ok",
            "entry_short = !na(prev_lo) && chart.close < prev_lo && vol_ok",
            'plot(prev_hi, id = "dc_upper", title = "Channel High", precision = "instrument", color_slot = "bull", width = 1.1, pane = "main")',
            'plot(prev_lo, id = "dc_lower", title = "Channel Low", precision = "instrument", color_slot = "bear", width = 1.1, pane = "main")',
            'plot((hi_out + lo_out) / 2.0, id = "dc_mid", title = "Exit Mid", precision = "instrument", color_slot = "mid", width = 1.0, pane = "main")',
            'fill(upper = "dc_upper", lower = "dc_lower", geometry = "series_band", color_slot = "band", opacity = 0.08)',
            _signal_plots(direction),
        ])
        return body + "\n"

    if family == "bb_squeeze_breakout":
        bb_len = int(params["bb_len"])
        bb_std = float(params["bb_std"])
        squeeze_pct = float(params.get("squeeze_pct", 0.40))
        vol_mult = float(params.get("vol_mult", 1.2))
        body = "\n".join([
            _header(symbol, "BB Squeeze Breakout", max_bars_back=2),
            f'bb_len = input.int({bb_len}, "BB Period", min = 5, max = 200)',
            f'bb_std = input.float({bb_std}, "BB Std", min = 0.5, max = 5.0)',
            f'squeeze_pct = input.float({squeeze_pct}, "Squeeze Threshold", min = 0.1, max = 0.9)',
            f'vol_mult = input.float({vol_mult}, "Volume Mult", min = 0.5, max = 5.0)',
            "basis = ta.sma(chart.close, bb_len)",
            "dev = ta.stdev(chart.close, bb_len) * bb_std",
            "upper = basis + dev",
            "lower = basis - dev",
            "bw = select(!na(basis) && basis > 0.0, (upper - lower) / basis, na)",
            "bw_lo = ta.lowest(bw, 100)",
            "bw_hi = ta.highest(bw, 100)",
            "bw_thresh = bw_lo + (bw_hi - bw_lo) * squeeze_pct",
            "prev_bw = bw[1]",
            "prev_thresh = bw_thresh[1]",
            "vol_ma = ta.sma(chart.volume, 20)",
            "squeeze_ready = (!na(prev_bw) && !na(prev_thresh) && prev_bw <= prev_thresh) || (!na(bw) && !na(bw_thresh) && bw <= bw_thresh * 1.15)",
            "vol_ok = !na(vol_ma) && chart.volume >= vol_ma * vol_mult",
            "entry_long = !na(upper) && chart.close > upper && squeeze_ready && vol_ok",
            "entry_short = !na(lower) && chart.close < lower && squeeze_ready && vol_ok",
            'plot(basis, id = "bb_mid", title = "BB Basis", precision = "instrument", color_slot = "mid", width = 1.0, pane = "main")',
            'plot(upper, id = "bb_upper", title = "BB Upper", precision = "instrument", color_slot = "bull", width = 1.1, pane = "main")',
            'plot(lower, id = "bb_lower", title = "BB Lower", precision = "instrument", color_slot = "bear", width = 1.1, pane = "main")',
            'fill(upper = "bb_upper", lower = "bb_lower", geometry = "series_band", color_slot = "band", opacity = 0.10)',
            _signal_plots(direction),
        ])
        return body + "\n"

    if family == "bb_mean_reversion":
        bb_len = int(params["bb_len"])
        bb_std = float(params["bb_std"])
        rsi_os = float(params["rsi_os"])
        rsi_ob = 100.0 - rsi_os
        trend_ema = int(params.get("trend_ema", 200))
        body = "\n".join([
            _header(symbol, "BB Mean Reversion", max_bars_back=2),
            f'bb_len = input.int({bb_len}, "BB Period", min = 5, max = 200)',
            f'bb_std = input.float({bb_std}, "BB Std", min = 0.5, max = 5.0)',
            f'rsi_os = input.float({rsi_os}, "RSI Oversold", min = 10.0, max = 45.0)',
            f'trend_len = input.int({trend_ema}, "Macro EMA", min = 20, max = 500)',
            "basis = ta.sma(chart.close, bb_len)",
            "dev = ta.stdev(chart.close, bb_len) * bb_std",
            "upper = basis + dev",
            "lower = basis - dev",
            "rsi_val = ta.rsi(chart.close, 14)",
            "macro_ema = ta.ema(chart.close, trend_len)",
            "entry_long = !na(lower) && !na(rsi_val) && !na(macro_ema) && chart.close < lower && rsi_val <= rsi_os && chart.close >= macro_ema * 0.94",
            f"entry_short = !na(upper) && !na(rsi_val) && !na(macro_ema) && chart.close > upper && rsi_val >= {rsi_ob} && chart.close <= macro_ema * 1.06",
            'plot(basis, id = "bb_mid", title = "BB Basis", precision = "instrument", color_slot = "mid", width = 1.0, pane = "main")',
            'plot(upper, id = "bb_upper", title = "BB Upper", precision = "instrument", color_slot = "bear", width = 1.1, pane = "main")',
            'plot(lower, id = "bb_lower", title = "BB Lower", precision = "instrument", color_slot = "bull", width = 1.1, pane = "main")',
            'plot(macro_ema, id = "macro_ema", title = "Macro EMA", precision = "instrument", color_slot = "mid", width = 1.2, pane = "main")',
            'fill(upper = "bb_upper", lower = "bb_lower", geometry = "series_band", color_slot = "band", opacity = 0.10)',
            _signal_plots(direction),
        ])
        return body + "\n"

    # rsi_momentum_pullback (default fallback)
    trend_len = int(params.get("trend_len", 120))
    rsi_len = int(params.get("rsi_len", 14))
    pullback_low = float(params.get("pullback_low", 40.0))
    pullback_high = 100.0 - pullback_low
    body = "\n".join([
        _header(symbol, "RSI Pullback", max_bars_back=2),
        f'trend_len = input.int({trend_len}, "Trend EMA", min = 20, max = 500)',
        f'rsi_len = input.int({rsi_len}, "RSI Period", min = 2, max = 50)',
        f'pullback_low = input.float({pullback_low}, "Pullback RSI", min = 15.0, max = 50.0)',
        "trend_ema = ta.ema(chart.close, trend_len)",
        "rsi_val = ta.rsi(chart.close, rsi_len)",
        "prev_rsi = rsi_val[1]",
        "entry_long = !na(trend_ema) && !na(prev_rsi) && chart.close > trend_ema && prev_rsi < pullback_low && rsi_val >= pullback_low",
        f"entry_short = !na(trend_ema) && !na(prev_rsi) && chart.close < trend_ema && prev_rsi > {pullback_high} && rsi_val <= {pullback_high}",
        'plot(trend_ema, id = "trend_ema", title = "Trend EMA", precision = "instrument", color_slot = "mid", width = 1.3, pane = "main")',
        _signal_plots(direction),
    ])
    return body + "\n"


def install_to_flowsurface(ind_path: Path, symbol: str) -> list[Path]:
    """Install .ind file into Flowsurface user indicator directories if present."""
    appdata = os.environ.get("APPDATA", "").strip()
    if not appdata:
        return []
    base = Path(appdata)
    installed: list[Path] = []
    for profile_dir_name in ("flowsurface", "flowsurface-2"):
        pdir = base / profile_dir_name
        if pdir.exists():
            dest = pdir / "indicators" / "strategy" / f"{symbol.lower()}.ind"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ind_path, dest)
            installed.append(dest)
    return installed
