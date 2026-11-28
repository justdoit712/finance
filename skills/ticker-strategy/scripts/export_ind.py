#!/usr/bin/env python3
"""Generate Flowsurface language(1) .ind overlay scripts for per-ticker main-force playbooks."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any

DEFAULT_RISK_BY_FAMILY: dict[str, dict[str, float | None]] = {
    "sweep_fade": {"atr_tp_mult": 3.0, "atr_trail_mult": None},
    "ema_defense_pullback": {"atr_tp_mult": 3.6, "atr_trail_mult": None},
    "squeeze_ignition": {"atr_tp_mult": None, "atr_trail_mult": 2.5},
    "climax_reversal": {"atr_tp_mult": 2.8, "atr_trail_mult": None},
    "trend_breakout": {"atr_tp_mult": None, "atr_trail_mult": 2.6},
}


def _header(symbol: str, title: str, max_bars_back: int = 5) -> str:
    sym_lower = symbol.lower()
    return "\n".join([
        "language(1)",
        f'indicator("{symbol} {title}", id = "strategy.{sym_lower}", max_bars_back = {max_bars_back})',
        'display(view = "plot", attachment = "overlay")',
        'format(precision = "base_ticker_min_tick")',
        'style("bull", title = "Long Entry", role = "success", shade = "base")',
        'style("bear", title = "Short Entry", role = "danger", shade = "base")',
        'style("mid", title = "Basis / Exit", role = "neutral", shade = "base")',
        'style("band", title = "Band Fill", role = "primary", shade = "faint")',
        'style("stop", title = "ATR Stop", role = "warning", shade = "base")',
        'style("tp", title = "ATR TP", role = "primary", shade = "base")',
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


def _state_machine_and_plots(
    direction: str,
    atr_sl_mult: float,
    atr_tp_mult: float | None = None,
    atr_trail_mult: float | None = None,
    has_atr_already: bool = False,
) -> str:
    allow_long, allow_short = _direction_flags(direction)
    tp_default = float(atr_tp_mult) if atr_tp_mult and float(atr_tp_mult) > 0.0 else 0.0
    trail_default = float(atr_trail_mult) if atr_trail_mult and float(atr_trail_mult) > 0.0 else 0.0
    lines: list[str] = []
    if not has_atr_already:
        lines.extend([
            "tr_val = ta.tr(chart.high, chart.low, chart.close)",
            "atr_val = ta.rma(tr_val, 14)",
        ])
    lines.extend([
        f'atr_sl_mult = input.float({float(atr_sl_mult):.2f}, "ATR Stop Mult", min = 0.5, max = 10.0)',
        f'atr_tp_mult = input.float({tp_default:.2f}, "ATR TP Mult (0=Off)", min = 0.0, max = 15.0)',
        f'atr_trail_mult = input.float({trail_default:.2f}, "ATR Trail Mult (0=Off)", min = 0.0, max = 10.0)',
        f"allow_long = {allow_long}",
        f"allow_short = {allow_short}",
        "raw_long = allow_long && entry_long",
        "raw_short = allow_short && entry_short",
        "raw_exit_long = exit_long || (allow_short && entry_short)",
        "raw_exit_short = exit_short || (allow_long && entry_long)",
        "state pos = 0",
        "state stop_px = 0.0",
        "state tp_px = 0.0",
        "state best_px = 0.0",
        "prev_pos = pos",
        "prev_stop = stop_px",
        "prev_tp = tp_px",
        "prev_best = best_px",
        "stopped_long = prev_pos == 1 && prev_stop > 0.0 && chart.low <= prev_stop",
        "stopped_short = prev_pos == -1 && prev_stop > 0.0 && chart.high >= prev_stop",
        "tp_hit_long = prev_pos == 1 && prev_tp > 0.0 && chart.high >= prev_tp",
        "tp_hit_short = prev_pos == -1 && prev_tp > 0.0 && chart.low <= prev_tp",
        "do_exit_long = prev_pos == 1 && (raw_exit_long || stopped_long || tp_hit_long)",
        "do_exit_short = prev_pos == -1 && (raw_exit_short || stopped_short || tp_hit_short)",
        "pos_after_exit = select(do_exit_long || do_exit_short, 0, prev_pos)",
        "can_enter = pos_after_exit == 0 && !na(atr_val) && atr_val > 0.0",
        "do_enter_long = can_enter && raw_long && !raw_short",
        "do_enter_short = can_enter && raw_short && !raw_long",
        "init_sl_long = chart.close - atr_sl_mult * atr_val",
        "init_trail_long = select(atr_trail_mult > 0.0, chart.close - atr_trail_mult * atr_val, 0.0)",
        "init_stop_long = select(init_trail_long > init_sl_long, init_trail_long, init_sl_long)",
        "init_sl_short = chart.close + atr_sl_mult * atr_val",
        "init_trail_short = select(atr_trail_mult > 0.0, chart.close + atr_trail_mult * atr_val, 0.0)",
        "init_stop_short = select(init_trail_short > 0.0 && init_trail_short < init_sl_short, init_trail_short, init_sl_short)",
        "init_tp_long = select(atr_tp_mult > 0.0, chart.close + atr_tp_mult * atr_val, 0.0)",
        "init_tp_short = select(atr_tp_mult > 0.0, math.max(chart.close - atr_tp_mult * atr_val, 0.0), 0.0)",
        "held_best_long = math.max(prev_best, chart.high)",
        "held_best_short = select(prev_best > 0.0, math.min(prev_best, chart.low), chart.low)",
        "held_trail_long = select(atr_trail_mult > 0.0 && !na(atr_val), math.max(prev_stop, held_best_long - atr_trail_mult * atr_val), prev_stop)",
        "held_trail_short = select(atr_trail_mult > 0.0 && !na(atr_val), select(prev_stop > 0.0, math.min(prev_stop, held_best_short + atr_trail_mult * atr_val), held_best_short + atr_trail_mult * atr_val), prev_stop)",
        "next_pos = select(do_enter_long, 1, select(do_enter_short, -1, select(do_exit_long || do_exit_short, 0, prev_pos)))",
        "next_best = select(do_enter_long, chart.close, select(do_enter_short, chart.close, select(do_exit_long || do_exit_short, 0.0, select(prev_pos == 1, held_best_long, select(prev_pos == -1, held_best_short, 0.0)))))",
        "next_stop = select(do_enter_long, init_stop_long, select(do_enter_short, init_stop_short, select(do_exit_long || do_exit_short, 0.0, select(prev_pos == 1, held_trail_long, select(prev_pos == -1, held_trail_short, 0.0)))))",
        "next_tp = select(do_enter_long, init_tp_long, select(do_enter_short, init_tp_short, select(do_exit_long || do_exit_short, 0.0, prev_tp)))",
        "pos := next_pos",
        "best_px := next_best",
        "stop_px := next_stop",
        "tp_px := next_tp",
        "long_sig = select(do_enter_long, chart.low, na)",
        "short_sig = select(do_enter_short, chart.high, na)",
        "exit_sig = select(do_exit_long || do_exit_short, chart.close, na)",
        "active_stop = select(pos != 0 && stop_px > 0.0, stop_px, na)",
        "active_tp = select(pos != 0 && tp_px > 0.0, tp_px, na)",
        'plot(long_sig, id = "long_entry", title = "Long Entry", precision = "instrument", color_slot = "bull", width = 5, pane = "main")',
        'plot(short_sig, id = "short_entry", title = "Short Entry", precision = "instrument", color_slot = "bear", width = 5, pane = "main")',
        'plot(exit_sig, id = "exit_sig", title = "Exit Signal", precision = "instrument", color_slot = "mid", width = 4, pane = "main")',
        'plot(active_stop, id = "stop_line", title = "ATR Stop", precision = "instrument", color_slot = "stop", width = 1.2, style = "step", pane = "main")',
        'plot(active_tp, id = "tp_line", title = "ATR TP", precision = "instrument", color_slot = "tp", width = 1.0, style = "step", pane = "main")',
        'mark(title = "Long Signal", source = "long_entry", kind = "point", color_slot = "bull")',
        'mark(title = "Short Signal", source = "short_entry", kind = "point", color_slot = "bear")',
        'mark(title = "Exit Mark", source = "exit_sig", kind = "cross", color_slot = "mid")',
    ])
    return "\n".join(lines)


def generate_ind_source(
    symbol: str,
    family: str,
    direction: str,
    params: dict[str, Any],
    risk: dict[str, Any] | None = None,
) -> str:
    symbol = symbol.strip().upper()
    atr_sl_mult = float(params.get("atr_sl_mult", (risk or {}).get("atr_sl_mult", 2.2)))

    alias = {
        "ema_trend": "trend_breakout",
        "bb_squeeze_breakout": "squeeze_ignition",
        "bb_mean_reversion": "climax_reversal",
        "rsi_momentum_pullback": "ema_defense_pullback",
    }
    fam = alias.get(family, family)

    def_risk = DEFAULT_RISK_BY_FAMILY.get(fam, {"atr_tp_mult": None, "atr_trail_mult": None})
    eff_risk = risk if risk is not None else def_risk
    atr_tp_mult = eff_risk.get("atr_tp_mult")
    atr_trail_mult = eff_risk.get("atr_trail_mult")

    if fam == "sweep_fade":
        lookback = int(params.get("lookback", 24))
        min_wick = float(params.get("min_wick", 0.42))
        body = "\n".join([
            _header(symbol, "Sweep Fade", max_bars_back=5),
            f'lookback = input.int({lookback}, "Sweep Lookback", min = 5, max = 200)',
            f'min_wick = input.float({min_wick:.2f}, "Min Wick Ratio", min = 0.1, max = 0.9)',
            "hi_raw = ta.highest(chart.high, lookback)",
            "lo_raw = ta.lowest(chart.low, lookback)",
            "prev_hi = hi_raw[1]",
            "prev_lo = lo_raw[1]",
            "mid_exit = ta.sma(chart.close, lookback)",
            "bar_rng = math.max(chart.high - chart.low, 0.0000001)",
            "lower_wick = (math.min(chart.open, chart.close) - chart.low) / bar_rng",
            "upper_wick = (chart.high - math.max(chart.open, chart.close)) / bar_rng",
            "entry_long = !na(prev_lo) && chart.low < prev_lo && chart.close > prev_lo && lower_wick >= min_wick",
            "entry_short = !na(prev_hi) && chart.high > prev_hi && chart.close < prev_hi && upper_wick >= min_wick",
            "exit_long = !na(mid_exit) && chart.close >= mid_exit",
            "exit_short = !na(mid_exit) && chart.close <= mid_exit",
            'plot(prev_hi, id = "sw_hi", title = "Prior High", precision = "instrument", color_slot = "bear", width = 1.0, pane = "main")',
            'plot(prev_lo, id = "sw_lo", title = "Prior Low", precision = "instrument", color_slot = "bull", width = 1.0, pane = "main")',
            'plot(mid_exit, id = "sw_mid", title = "Mean Exit", precision = "instrument", color_slot = "mid", width = 1.0, pane = "main")',
            _state_machine_and_plots(direction, atr_sl_mult, atr_tp_mult, atr_trail_mult, has_atr_already=False),
        ])
        return body + "\n"

    if fam == "ema_defense_pullback":
        trend_len = int(params.get("trend_len", 55))
        rsi_len = int(params.get("rsi_len", 14))
        pullback_low = float(params.get("pullback_low", 40.0))
        pullback_high = 100.0 - pullback_low
        body = "\n".join([
            _header(symbol, "EMA Defense Pullback", max_bars_back=5),
            f'trend_len = input.int({trend_len}, "Defense EMA", min = 5, max = 500)',
            f'rsi_len = input.int({rsi_len}, "RSI Period", min = 2, max = 50)',
            f'pullback_low = input.float({pullback_low:.1f}, "Pullback RSI", min = 15.0, max = 50.0)',
            "trend_ema = ta.ema(chart.close, trend_len)",
            "rsi_val = ta.rsi(chart.close, rsi_len)",
            "prev_rsi = rsi_val[1]",
            "tr_val = ta.tr(chart.high, chart.low, chart.close)",
            "atr_val = ta.rma(tr_val, 14)",
            "near_sup = !na(trend_ema) && !na(atr_val) && chart.close >= trend_ema * 0.99 && chart.close <= trend_ema + 2.2 * atr_val",
            "near_res = !na(trend_ema) && !na(atr_val) && chart.close <= trend_ema * 1.01 && chart.close >= trend_ema - 2.2 * atr_val",
            "entry_long = near_sup && !na(prev_rsi) && !na(rsi_val) && prev_rsi < pullback_low && rsi_val >= pullback_low",
            f"entry_short = near_res && !na(prev_rsi) && !na(rsi_val) && prev_rsi > {pullback_high:.1f} && rsi_val <= {pullback_high:.1f}",
            "exit_long = (!na(rsi_val) && rsi_val > 72.0) || (!na(trend_ema) && chart.close < trend_ema * 0.985)",
            "exit_short = (!na(rsi_val) && rsi_val < 28.0) || (!na(trend_ema) && chart.close > trend_ema * 1.015)",
            'plot(trend_ema, id = "trend_ema", title = "Defense EMA", precision = "instrument", color_slot = "mid", width = 1.4, pane = "main")',
            _state_machine_and_plots(direction, atr_sl_mult, atr_tp_mult, atr_trail_mult, has_atr_already=True),
        ])
        return body + "\n"

    if fam == "squeeze_ignition":
        bb_len = int(params.get("bb_len", 20))
        bb_std = float(params.get("bb_std", 2.0))
        vol_mult = float(params.get("vol_mult", 1.5))
        body = "\n".join([
            _header(symbol, "Squeeze Ignition", max_bars_back=5),
            f'bb_len = input.int({bb_len}, "BB Period", min = 5, max = 200)',
            f'bb_std = input.float({bb_std:.2f}, "BB Std", min = 0.5, max = 5.0)',
            f'vol_mult = input.float({vol_mult:.2f}, "Volume Mult", min = 0.5, max = 5.0)',
            "basis = ta.sma(chart.close, bb_len)",
            "dev = ta.stdev(chart.close, bb_len) * bb_std",
            "upper = basis + dev",
            "lower = basis - dev",
            "bw = select(!na(basis) && basis > 0.0, (upper - lower) / basis, na)",
            "bw_lo = ta.lowest(bw, 100)",
            "bw_hi = ta.highest(bw, 100)",
            "bw_thresh = bw_lo + (bw_hi - bw_lo) * 0.35",
            "prev_bw = bw[1]",
            "prev_thresh = bw_thresh[1]",
            "vol_ma = ta.sma(chart.volume, 20)",
            "tr_val = ta.tr(chart.high, chart.low, chart.close)",
            "atr_val = ta.rma(tr_val, 14)",
            "squeeze_ready = (!na(prev_bw) && !na(prev_thresh) && prev_bw <= prev_thresh) || (!na(bw) && !na(bw_thresh) && bw <= bw_thresh * 1.15)",
            "vol_ok = !na(vol_ma) && chart.volume >= vol_ma * vol_mult",
            "not_overext = !na(atr_val) && (chart.high - chart.low) <= 2.5 * atr_val",
            "entry_long = !na(upper) && chart.close > upper && squeeze_ready && vol_ok && not_overext",
            "entry_short = !na(lower) && chart.close < lower && squeeze_ready && vol_ok && not_overext",
            "exit_long = !na(basis) && chart.close < basis",
            "exit_short = !na(basis) && chart.close > basis",
            'plot(basis, id = "bb_mid", title = "BB Basis", precision = "instrument", color_slot = "mid", width = 1.0, pane = "main")',
            'plot(upper, id = "bb_upper", title = "BB Upper", precision = "instrument", color_slot = "bull", width = 1.1, pane = "main")',
            'plot(lower, id = "bb_lower", title = "BB Lower", precision = "instrument", color_slot = "bear", width = 1.1, pane = "main")',
            'fill(upper = "bb_upper", lower = "bb_lower", geometry = "series_band", color_slot = "band", opacity = 0.10)',
            _state_machine_and_plots(direction, atr_sl_mult, atr_tp_mult, atr_trail_mult, has_atr_already=True),
        ])
        return body + "\n"

    if fam == "climax_reversal":
        bb_len = int(params.get("bb_len", 20))
        bb_std = float(params.get("bb_std", 2.2))
        rsi_os = float(params.get("rsi_os", 28.0))
        rsi_ob = 100.0 - rsi_os
        vol_spike = float(params.get("vol_spike", 1.5))
        body = "\n".join([
            _header(symbol, "Climax Reversal", max_bars_back=5),
            f'bb_len = input.int({bb_len}, "BB Period", min = 5, max = 200)',
            f'bb_std = input.float({bb_std:.2f}, "BB Std", min = 0.5, max = 5.0)',
            f'rsi_os = input.float({rsi_os:.1f}, "RSI Oversold", min = 10.0, max = 45.0)',
            f'vol_spike = input.float({vol_spike:.2f}, "Volume Spike", min = 0.5, max = 5.0)',
            "basis = ta.sma(chart.close, bb_len)",
            "dev = ta.stdev(chart.close, bb_len) * bb_std",
            "upper = basis + dev",
            "lower = basis - dev",
            "rsi_val = ta.rsi(chart.close, 14)",
            "macro_ema = ta.ema(chart.close, 200)",
            "vol_ma = ta.sma(chart.volume, 20)",
            "bar_rng = math.max(chart.high - chart.low, 0.0000001)",
            "lower_wick = (math.min(chart.open, chart.close) - chart.low) / bar_rng",
            "upper_wick = (chart.high - math.max(chart.open, chart.close)) / bar_rng",
            "exhaust_long = (!na(vol_ma) && chart.volume >= vol_ma * vol_spike) || lower_wick >= 0.35",
            "exhaust_short = (!na(vol_ma) && chart.volume >= vol_ma * vol_spike) || upper_wick >= 0.35",
            "entry_long = !na(lower) && !na(rsi_val) && !na(macro_ema) && chart.close < lower && rsi_val <= rsi_os && exhaust_long && chart.close >= macro_ema * 0.92",
            f"entry_short = !na(upper) && !na(rsi_val) && !na(macro_ema) && chart.close > upper && rsi_val >= {rsi_ob:.1f} && exhaust_short && chart.close <= macro_ema * 1.08",
            "exit_long = !na(basis) && chart.close >= basis",
            "exit_short = !na(basis) && chart.close <= basis",
            'plot(basis, id = "bb_mid", title = "BB Basis", precision = "instrument", color_slot = "mid", width = 1.0, pane = "main")',
            'plot(upper, id = "bb_upper", title = "BB Upper", precision = "instrument", color_slot = "bear", width = 1.1, pane = "main")',
            'plot(lower, id = "bb_lower", title = "BB Lower", precision = "instrument", color_slot = "bull", width = 1.1, pane = "main")',
            'plot(macro_ema, id = "macro_ema", title = "Macro EMA", precision = "instrument", color_slot = "mid", width = 1.2, pane = "main")',
            'fill(upper = "bb_upper", lower = "bb_lower", geometry = "series_band", color_slot = "band", opacity = 0.10)',
            _state_machine_and_plots(direction, atr_sl_mult, atr_tp_mult, atr_trail_mult, has_atr_already=False),
        ])
        return body + "\n"

    # trend_breakout (default)
    fast_len = int(params.get("fast_len", 12))
    slow_len = int(params.get("slow_len", 48))
    adx_min = float(params.get("adx_min", 18.0))
    vol_mult = float(params.get("vol_mult", 1.0))
    body = "\n".join([
        _header(symbol, "Trend Breakout", max_bars_back=5),
        f'fast_len = input.int({fast_len}, "Fast EMA", min = 2, max = 200)',
        f'slow_len = input.int({slow_len}, "Slow EMA", min = 5, max = 500)',
        f'adx_min = input.float({adx_min:.1f}, "Min ADX", min = 5.0, max = 60.0)',
        f'vol_mult = input.float({vol_mult:.2f}, "Volume Mult", min = 0.5, max = 5.0)',
        "fast = ta.ema(chart.close, fast_len)",
        "slow = ta.ema(chart.close, slow_len)",
        "prev_fast = fast[1]",
        "prev_slow = slow[1]",
        "vol_ma = ta.sma(chart.volume, 20)",
        _adx_block(14),
        "vol_ok = !na(vol_ma) && chart.volume >= vol_ma * vol_mult",
        "entry_long = !na(prev_fast) && !na(prev_slow) && fast > slow && prev_fast <= prev_slow && !na(adx_val) && adx_val >= adx_min && vol_ok",
        "entry_short = !na(prev_fast) && !na(prev_slow) && fast < slow && prev_fast >= prev_slow && !na(adx_val) && adx_val >= adx_min && vol_ok",
        "exit_long = !na(fast) && !na(slow) && fast < slow",
        "exit_short = !na(fast) && !na(slow) && fast > slow",
        'plot(fast, id = "fast_ema", title = "Fast EMA", precision = "instrument", color_slot = "bull", width = 1.2, pane = "main")',
        'plot(slow, id = "slow_ema", title = "Slow EMA", precision = "instrument", color_slot = "bear", width = 1.2, pane = "main")',
        _state_machine_and_plots(direction, atr_sl_mult, atr_tp_mult, atr_trail_mult, has_atr_already=True),
    ])
    return body + "\n"


def install_to_flowsurface(ind_path: Path, symbol: str) -> list[Path]:
    """Install .ind file into all Flowsurface user indicator profile directories if present."""
    appdata = os.environ.get("APPDATA", "").strip()
    if not appdata:
        return []
    base = Path(appdata)
    installed: list[Path] = []
    for pdir in sorted(base.glob("flowsurface*")):
        if pdir.is_dir():
            dest = pdir / "indicators" / "strategy" / f"{symbol.lower()}.ind"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ind_path, dest)
            installed.append(dest)
    return installed
