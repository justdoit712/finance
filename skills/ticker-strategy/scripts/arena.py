#!/usr/bin/env python3
"""Multi-family strategy arena & perpetual futures backtest engine (pure NumPy/Pandas)."""

from __future__ import annotations

from dataclasses import dataclass
import itertools
from typing import Any, Callable

import numpy as np
import pandas as pd

from fetch_binance import INTERVAL_MS
from profile_ticker import BARS_PER_YEAR, _calc_adx, _calc_atr

FUNDING_PERIOD_MS = 8 * 3_600_000


# ---------------------------------------------------------------------------
# Pure NumPy / Pandas technical indicators
# ---------------------------------------------------------------------------

def sma(series: np.ndarray | pd.Series, length: int) -> np.ndarray:
    return pd.Series(series, dtype=float).rolling(length, min_periods=length).mean().to_numpy()


def ema(series: np.ndarray | pd.Series, length: int) -> np.ndarray:
    return pd.Series(series, dtype=float).ewm(span=length, adjust=False, min_periods=length).mean().to_numpy()


def rsi(series: np.ndarray | pd.Series, length: int = 14) -> np.ndarray:
    s = pd.Series(series, dtype=float)
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.where(avg_loss > 0.0, 100.0)
    out = out.where(avg_gain > 0.0, 0.0)
    return out.to_numpy()


def bollinger_bands(series: np.ndarray | pd.Series, length: int = 20, num_std: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    s = pd.Series(series, dtype=float)
    mid = s.rolling(length, min_periods=length).mean()
    std = s.rolling(length, min_periods=length).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid.to_numpy(), upper.to_numpy(), lower.to_numpy()


def donchian(high: np.ndarray, low: np.ndarray, length: int) -> tuple[np.ndarray, np.ndarray]:
    hi = pd.Series(high, dtype=float).rolling(length, min_periods=length).max().to_numpy()
    lo = pd.Series(low, dtype=float).rolling(length, min_periods=length).min().to_numpy()
    return hi, lo


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
    return _calc_atr(np.asarray(high, dtype=float), np.asarray(low, dtype=float), np.asarray(close, dtype=float), length)


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
    return _calc_adx(np.asarray(high, dtype=float), np.asarray(low, dtype=float), np.asarray(close, dtype=float), length)


# ---------------------------------------------------------------------------
# Perpetual Futures Backtest Engine (Strict t -> t+1 Open, Fees + Slippage + Funding + ATR Stops)
# ---------------------------------------------------------------------------

def _align_funding_rates(df: pd.DataFrame, funding_df: pd.DataFrame | None, interval: str) -> tuple[np.ndarray, np.ndarray]:
    n = len(df)
    open_times = df["open_time"].to_numpy(dtype=np.int64)
    bar_ms = INTERVAL_MS.get(interval, 3_600_000)

    # Identify bars whose interval [open_time, open_time + bar_ms) crosses an 8h UTC funding mark
    is_funding_bar = (open_times // FUNDING_PERIOD_MS) < ((open_times + bar_ms - 1) // FUNDING_PERIOD_MS)
    # Also include exact 8h boundary bar open (common for 15m/1h/4h)
    is_funding_bar = is_funding_bar | ((open_times % FUNDING_PERIOD_MS) == 0)
    is_funding_bar[0] = False

    rates = np.full(n, 0.0001, dtype=float)
    if funding_df is not None and not funding_df.empty:
        ft = funding_df["calc_time"].to_numpy(dtype=np.int64)
        fr = funding_df["last_funding_rate"].to_numpy(dtype=float)
        idx = np.searchsorted(ft, open_times + bar_ms, side="right") - 1
        valid = idx >= 0
        rates[valid] = fr[idx[valid]]
    return is_funding_bar, rates


def compute_metrics(
    equity: np.ndarray,
    close: np.ndarray,
    trades: list[dict[str, Any]],
    interval: str,
    exposure_bars: int,
    total_fees_pct: float,
    total_funding_pct: float,
) -> dict[str, Any]:
    n = len(equity)
    ann_factor = BARS_PER_YEAR.get(interval, 365.0 * 24.0)
    bar_ret = np.diff(equity) / np.maximum(equity[:-1], 1e-12)
    bar_ret = bar_ret[np.isfinite(bar_ret)]

    total_ret = float(equity[-1] / equity[0] - 1.0) if n > 1 else 0.0
    bh_ret = float(close[-1] / close[0] - 1.0) if n > 1 else 0.0
    excess_ret = total_ret - bh_ret

    years = max(n / ann_factor, 1e-6)
    cagr = float((max(equity[-1], 1e-9) / equity[0]) ** (1.0 / years) - 1.0) if equity[-1] > 0 else -1.0

    std = float(np.std(bar_ret, ddof=1)) if len(bar_ret) > 2 else 0.0
    sharpe = float((np.mean(bar_ret) / std) * np.sqrt(ann_factor)) if std > 1e-12 else 0.0

    down = bar_ret[bar_ret < 0.0]
    down_std = float(np.sqrt(np.mean(down**2))) if len(down) > 0 else 0.0
    sortino = float((np.mean(bar_ret) / down_std) * np.sqrt(ann_factor)) if down_std > 1e-12 else (sharpe if sharpe > 0 else 0.0)

    peak = np.maximum.accumulate(equity)
    dd = equity / np.maximum(peak, 1e-12) - 1.0
    max_dd = float(np.min(dd)) if len(dd) else 0.0
    calmar = float(cagr / abs(max_dd)) if abs(max_dd) > 1e-6 else 0.0

    n_trades = len(trades)
    if n_trades > 0:
        rets = np.array([t["net_return"] for t in trades], dtype=float)
        holds = np.array([t["hold_bars"] for t in trades], dtype=float)
        wins = rets[rets > 0.0]
        losses = rets[rets <= 0.0]
        win_rate = float(len(wins) / n_trades)
        gross_win = float(np.sum(wins))
        gross_loss = float(abs(np.sum(losses)))
        profit_factor = float(gross_win / gross_loss) if gross_loss > 1e-12 else (9.99 if gross_win > 0 else 0.0)
        avg_win = float(np.mean(wins)) if len(wins) else 0.0
        avg_loss = float(abs(np.mean(losses))) if len(losses) else 0.0
        payoff_ratio = float(avg_win / avg_loss) if avg_loss > 1e-12 else (9.99 if avg_win > 0 else 0.0)
        expectancy = float(np.mean(rets))
        avg_hold = float(np.mean(holds))
    else:
        win_rate = 0.0
        profit_factor = 0.0
        payoff_ratio = 0.0
        expectancy = 0.0
        avg_hold = 0.0

    return {
        "total_return": round(total_ret, 4),
        "cagr": round(float(np.clip(cagr, -1.0, 50.0)), 4),
        "buy_hold_return": round(bh_ret, 4),
        "excess_return": round(excess_ret, 4),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "calmar": round(float(np.clip(calmar, -20.0, 50.0)), 3),
        "max_drawdown": round(max_dd, 4),
        "trades": n_trades,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(min(profit_factor, 9.99), 3),
        "payoff_ratio": round(min(payoff_ratio, 9.99), 3),
        "expectancy": round(expectancy, 5),
        "avg_hold_bars": round(avg_hold, 1),
        "exposure_pct": round(exposure_bars / max(n, 1), 4),
        "total_fees_pct": round(total_fees_pct, 4),
        "total_funding_pct": round(total_funding_pct, 4),
    }


def run_perp_backtest(
    df: pd.DataFrame,
    signals: dict[str, np.ndarray],
    config: dict[str, Any],
    funding_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Simulate perpetual futures with no-lookahead execution, fees, slippage, funding, and ATR stops."""
    n = len(df)
    if n < 20:
        return {"metrics": compute_metrics(np.ones(max(n, 1)), np.ones(max(n, 1)), [], config.get("interval", "1h"), 0, 0.0, 0.0), "equity": np.ones(max(n, 1)), "trades": []}

    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)

    entry_long = np.asarray(signals["entry_long"], dtype=bool)
    entry_short = np.asarray(signals["entry_short"], dtype=bool)
    exit_long = np.asarray(signals["exit_long"], dtype=bool)
    exit_short = np.asarray(signals["exit_short"], dtype=bool)

    direction = config.get("direction", "both")
    allow_long = direction in ("both", "long_only")
    allow_short = direction in ("both", "short_only")

    fee_rate = float(config.get("fee_rate", 0.0005))
    slippage = float(config.get("slippage", 0.0003))
    cost_rate = fee_rate + slippage

    atr_period = int(config.get("atr_period", 14))
    sl_mult = config.get("atr_sl_mult", 2.0)
    tp_mult = config.get("atr_tp_mult", None)
    trail_mult = config.get("atr_trail_mult", None)
    cooldown_bars = int(config.get("cooldown_bars", 0))
    interval = config.get("interval", "1h")

    atr_arr = atr(highs, lows, closes, atr_period)
    is_funding_bar, funding_rates = _align_funding_rates(df, funding_df, interval)

    equity = np.ones(n, dtype=float)
    trades: list[dict[str, Any]] = []

    pos = 0  # 0 flat, 1 long, -1 short
    entry_px = 0.0
    entry_idx = 0
    entry_equity = 1.0
    sl_px = 0.0
    tp_px = 0.0
    trail_px = 0.0
    best_px = 0.0
    cooldown_left = 0
    exposure_bars = 0
    total_fees_pct = 0.0
    total_funding_pct = 0.0

    # Mark-to-market equity helper using prev close -> current price
    cur_eq = 1.0

    def close_trade(exit_i: int, raw_exit_px: float, reason: str) -> None:
        nonlocal pos, cur_eq, total_fees_pct, cooldown_left
        if pos == 1:
            fill_px = raw_exit_px * (1.0 - cost_rate)
            gross_ret = (raw_exit_px / entry_px) - 1.0
            net_ret = (fill_px / entry_px) - 1.0
        else:
            fill_px = raw_exit_px * (1.0 + cost_rate)
            gross_ret = 1.0 - (raw_exit_px / entry_px)
            net_ret = 1.0 - (fill_px / entry_px)

        # Update equity from previous close to exit price, then deduct exit cost
        prev_c = closes[exit_i - 1]
        if pos == 1:
            step_ret = raw_exit_px / prev_c - 1.0
        else:
            step_ret = 1.0 - raw_exit_px / prev_c
        # If entered on this exact bar's open, step from entry_px instead of prev_c
        if exit_i == entry_idx:
            if pos == 1:
                step_ret = raw_exit_px / (entry_px / (1.0 + cost_rate)) - 1.0
            else:
                step_ret = 1.0 - raw_exit_px / (entry_px / (1.0 - cost_rate))

        cur_eq *= max(1.0 + step_ret, 0.0)
        cur_eq *= max(1.0 - cost_rate, 0.0)
        total_fees_pct += cost_rate

        trades.append({
            "entry_idx": entry_idx,
            "exit_idx": exit_i,
            "side": "long" if pos == 1 else "short",
            "entry_price": round(entry_px, 6),
            "exit_price": round(fill_px, 6),
            "gross_return": float(gross_ret),
            "net_return": float(cur_eq / max(entry_equity, 1e-12) - 1.0),
            "hold_bars": exit_i - entry_idx,
            "exit_reason": reason,
        })
        pos = 0
        if reason in ("sl", "trail"):
            cooldown_left = cooldown_bars

    for i in range(1, n):
        sig_i = i - 1
        if cooldown_left > 0 and pos == 0:
            cooldown_left -= 1

        # 1) Signal-driven exits at bar i open
        if pos == 1 and (exit_long[sig_i] or (allow_short and entry_short[sig_i])):
            close_trade(i, opens[i], "signal")
        elif pos == -1 and (exit_short[sig_i] or (allow_long and entry_long[sig_i])):
            close_trade(i, opens[i], "signal")

        # 2) Signal-driven entries at bar i open
        entered_this_bar = False
        if pos == 0 and cooldown_left == 0 and np.isfinite(atr_arr[sig_i]) and atr_arr[sig_i] > 0:
            want_long = allow_long and entry_long[sig_i]
            want_short = allow_short and entry_short[sig_i]
            if want_long and not want_short:
                pos = 1
                entry_equity = cur_eq
                entry_px = opens[i] * (1.0 + cost_rate)
                cur_eq *= max(1.0 - cost_rate, 0.0)
                total_fees_pct += cost_rate
                entry_idx = i
                entered_this_bar = True
                best_px = opens[i]
                a = atr_arr[sig_i]
                sl_px = opens[i] - float(sl_mult) * a if sl_mult else 0.0
                tp_px = opens[i] + float(tp_mult) * a if tp_mult else 0.0
                trail_px = opens[i] - float(trail_mult) * a if trail_mult else 0.0
            elif want_short and not want_long:
                pos = -1
                entry_equity = cur_eq
                entry_px = opens[i] * (1.0 - cost_rate)
                cur_eq *= max(1.0 - cost_rate, 0.0)
                total_fees_pct += cost_rate
                entry_idx = i
                entered_this_bar = True
                best_px = opens[i]
                a = atr_arr[sig_i]
                sl_px = opens[i] + float(sl_mult) * a if sl_mult else 0.0
                tp_px = opens[i] - float(tp_mult) * a if tp_mult else 0.0
                trail_px = opens[i] + float(trail_mult) * a if trail_mult else 0.0

        # 3) Intra-bar stop checks (conservative order: SL/Trail before TP)
        if pos == 1:
            eff_stop = max(sl_px if sl_mult else 0.0, trail_px if trail_mult else 0.0)
            if eff_stop > 0.0 and lows[i] <= eff_stop:
                fill = min(opens[i], eff_stop) if not entered_this_bar else eff_stop
                reason = "trail" if (trail_mult and trail_px >= sl_px) else "sl"
                close_trade(i, fill, reason)
            elif tp_mult and tp_px > 0.0 and highs[i] >= tp_px:
                fill = max(opens[i], tp_px) if not entered_this_bar else tp_px
                close_trade(i, fill, "tp")
        elif pos == -1:
            candidates = [x for x in (sl_px if sl_mult else 0.0, trail_px if trail_mult else 0.0) if x > 0.0]
            eff_stop = min(candidates) if candidates else 0.0
            if eff_stop > 0.0 and highs[i] >= eff_stop:
                fill = max(opens[i], eff_stop) if not entered_this_bar else eff_stop
                reason = "trail" if (trail_mult and (not sl_mult or trail_px <= sl_px)) else "sl"
                close_trade(i, fill, reason)
            elif tp_mult and tp_px > 0.0 and lows[i] <= tp_px:
                fill = min(opens[i], tp_px) if not entered_this_bar else tp_px
                close_trade(i, fill, "tp")

        # 4) End-of-bar mark-to-market, funding, and trailing stop update for next bar
        if pos != 0:
            exposure_bars += 1
            ref_px = opens[i] if entered_this_bar else closes[i - 1]
            if pos == 1:
                cur_eq *= max(closes[i] / max(ref_px, 1e-12), 0.0)
                if trail_mult and np.isfinite(atr_arr[i]):
                    best_px = max(best_px, highs[i])
                    trail_px = max(trail_px, best_px - float(trail_mult) * atr_arr[i])
            else:
                cur_eq *= max(1.0 + (1.0 - closes[i] / max(ref_px, 1e-12)), 0.0)
                if trail_mult and np.isfinite(atr_arr[i]):
                    best_px = min(best_px, lows[i])
                    new_t = best_px + float(trail_mult) * atr_arr[i]
                    trail_px = new_t if trail_px <= 0.0 else min(trail_px, new_t)

            if is_funding_bar[i]:
                f_cost = pos * funding_rates[i]
                cur_eq *= max(1.0 - f_cost, 0.0)
                total_funding_pct += f_cost

        equity[i] = cur_eq

    metrics = compute_metrics(equity, closes, trades, interval, exposure_bars, total_fees_pct, total_funding_pct)
    return {"metrics": metrics, "equity": equity, "trades": trades}


# ---------------------------------------------------------------------------
# 5 Strategy Families
# ---------------------------------------------------------------------------

def signals_ema_trend(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)

    fast = ema(close, int(params["fast_len"]))
    slow = ema(close, int(params["slow_len"]))
    adx_arr = adx(high, low, close, 14)
    adx_min = float(params.get("adx_min", 18.0))

    prev_fast = np.roll(fast, 1)
    prev_slow = np.roll(slow, 1)
    prev_fast[0] = np.nan
    prev_slow[0] = np.nan

    cross_up = (fast > slow) & (prev_fast <= prev_slow) & (adx_arr >= adx_min)
    cross_dn = (fast < slow) & (prev_fast >= prev_slow) & (adx_arr >= adx_min)
    exit_long = fast < slow
    exit_short = fast > slow
    return {
        "entry_long": np.nan_to_num(cross_up, nan=False),
        "entry_short": np.nan_to_num(cross_dn, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }


def signals_donchian_breakout(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    entry_len = int(params["entry_len"])
    exit_len = int(params["exit_len"])
    vol_mult = float(params.get("vol_mult", 1.1))

    hi_in, lo_in = donchian(high, low, entry_len)
    hi_out, lo_out = donchian(high, low, exit_len)
    vol_ma = sma(vol, 20)

    prev_hi_in = np.roll(hi_in, 1)
    prev_lo_in = np.roll(lo_in, 1)
    prev_hi_out = np.roll(hi_out, 1)
    prev_lo_out = np.roll(lo_out, 1)
    prev_hi_in[0] = np.nan
    prev_lo_in[0] = np.nan
    prev_hi_out[0] = np.nan
    prev_lo_out[0] = np.nan

    vol_ok = vol >= (vol_ma * vol_mult)
    entry_long = (close > prev_hi_in) & vol_ok
    entry_short = (close < prev_lo_in) & vol_ok
    exit_long = close < prev_lo_out
    exit_short = close > prev_hi_out
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }


def signals_bb_squeeze_breakout(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    close = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    bb_len = int(params["bb_len"])
    bb_std = float(params["bb_std"])
    squeeze_pct = float(params.get("squeeze_pct", 0.40))
    vol_mult = float(params.get("vol_mult", 1.2))

    mid, upper, lower = bollinger_bands(close, bb_len, bb_std)
    bw = (upper - lower) / np.maximum(mid, 1e-12)
    bw_q = pd.Series(bw).rolling(100, min_periods=40).quantile(squeeze_pct).to_numpy()
    prev_bw = np.roll(bw, 1)
    prev_bw_q = np.roll(bw_q, 1)
    prev_bw[0] = np.nan
    prev_bw_q[0] = np.nan

    vol_ma = sma(vol, 20)
    squeeze_ready = (prev_bw <= prev_bw_q) | (bw <= bw_q * 1.15)
    vol_ok = vol >= (vol_ma * vol_mult)

    entry_long = (close > upper) & squeeze_ready & vol_ok
    entry_short = (close < lower) & squeeze_ready & vol_ok
    exit_long = close < mid
    exit_short = close > mid
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }


def signals_bb_mean_reversion(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    close = df["close"].to_numpy(dtype=float)
    bb_len = int(params["bb_len"])
    bb_std = float(params["bb_std"])
    rsi_os = float(params["rsi_os"])
    rsi_ob = float(100.0 - rsi_os)
    trend_ema_len = int(params.get("trend_ema", 200))

    mid, upper, lower = bollinger_bands(close, bb_len, bb_std)
    rsi_arr = rsi(close, 14)
    macro_ema = ema(close, trend_ema_len)

    # Allow reversion with macro trend bias or mild deviation
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


def signals_rsi_momentum_pullback(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    close = df["close"].to_numpy(dtype=float)
    trend_len = int(params["trend_len"])
    rsi_len = int(params["rsi_len"])
    pullback_low = float(params["pullback_low"])
    pullback_high = float(100.0 - pullback_low)

    trend_ema = ema(close, trend_len)
    rsi_arr = rsi(close, rsi_len)
    prev_rsi = np.roll(rsi_arr, 1)
    prev_rsi[0] = np.nan

    # Uptrend pullback recovery; downtrend bounce fade
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


@dataclass(frozen=True)
class StrategyFamilySpec:
    name: str
    label_zh: str
    signal_fn: Callable[[pd.DataFrame, dict[str, Any]], dict[str, np.ndarray]]
    param_axes: dict[str, list[Any]]
    default_risk: dict[str, Any]


FAMILY_SPECS: dict[str, StrategyFamilySpec] = {
    "ema_trend": StrategyFamilySpec(
        name="ema_trend",
        label_zh="EMA 趋势跟踪",
        signal_fn=signals_ema_trend,
        param_axes={
            "fast_len": [9, 14, 21],
            "slow_len": [42, 60, 90],
            "adx_min": [16.0, 22.0],
            "atr_sl_mult": [2.0, 2.8],
        },
        default_risk={"atr_period": 14, "atr_tp_mult": None, "atr_trail_mult": 2.5, "cooldown_bars": 2},
    ),
    "donchian_breakout": StrategyFamilySpec(
        name="donchian_breakout",
        label_zh="Donchian 通道突破",
        signal_fn=signals_donchian_breakout,
        param_axes={
            "entry_len": [16, 24, 36],
            "exit_len": [8, 12],
            "vol_mult": [1.0, 1.3],
            "atr_sl_mult": [2.0, 3.0],
        },
        default_risk={"atr_period": 14, "atr_tp_mult": None, "atr_trail_mult": 2.6, "cooldown_bars": 2},
    ),
    "bb_squeeze_breakout": StrategyFamilySpec(
        name="bb_squeeze_breakout",
        label_zh="布林缩口放量突破",
        signal_fn=signals_bb_squeeze_breakout,
        param_axes={
            "bb_len": [16, 20, 28],
            "bb_std": [1.8, 2.2],
            "vol_mult": [1.1, 1.5],
            "atr_sl_mult": [2.0, 2.8],
        },
        default_risk={"atr_period": 14, "atr_tp_mult": None, "atr_trail_mult": 2.4, "cooldown_bars": 2},
    ),
    "bb_mean_reversion": StrategyFamilySpec(
        name="bb_mean_reversion",
        label_zh="布林+RSI 均值回归",
        signal_fn=signals_bb_mean_reversion,
        param_axes={
            "bb_len": [16, 20, 26],
            "bb_std": [2.0, 2.4],
            "rsi_os": [28.0, 34.0],
            "atr_sl_mult": [1.8, 2.5],
        },
        default_risk={"atr_period": 14, "atr_tp_mult": 3.0, "atr_trail_mult": None, "cooldown_bars": 3},
    ),
    "rsi_momentum_pullback": StrategyFamilySpec(
        name="rsi_momentum_pullback",
        label_zh="趋势回踩 RSI 恢复",
        signal_fn=signals_rsi_momentum_pullback,
        param_axes={
            "trend_len": [100, 160],
            "rsi_len": [10, 14],
            "pullback_low": [36.0, 44.0],
            "atr_sl_mult": [1.8, 2.6],
        },
        default_risk={"atr_period": 14, "atr_tp_mult": 3.6, "atr_trail_mult": None, "cooldown_bars": 2},
    ),
}


def expand_param_grid(spec: StrategyFamilySpec) -> list[dict[str, Any]]:
    keys = list(spec.param_axes.keys())
    values = [spec.param_axes[k] for k in keys]
    combos: list[dict[str, Any]] = []
    for prod in itertools.product(*values):
        p = dict(zip(keys, prod))
        if spec.name == "ema_trend" and p["fast_len"] >= p["slow_len"]:
            continue
        if spec.name == "donchian_breakout" and p["exit_len"] >= p["entry_len"]:
            continue
        combos.append(p)
    return combos


def run_arena(
    klines_by_tf: dict[str, pd.DataFrame],
    funding_df: pd.DataFrame | None = None,
    fee_rate: float = 0.0005,
    slippage: float = 0.0003,
    directions: tuple[str, ...] = ("both", "long_only", "short_only"),
    min_bars: int = 300,
) -> list[dict[str, Any]]:
    """Run all strategy families across available timeframes and directions, returning ranked candidates."""
    candidates: list[dict[str, Any]] = []

    for tf, df in klines_by_tf.items():
        if df is None or len(df) < min_bars:
            continue
        for fam_name, spec in FAMILY_SPECS.items():
            grid = expand_param_grid(spec)
            for params in grid:
                sigs = spec.signal_fn(df, params)
                for direction in directions:
                    cfg = {
                        "direction": direction,
                        "fee_rate": fee_rate,
                        "slippage": slippage,
                        "interval": tf,
                        **spec.default_risk,
                        "atr_sl_mult": params.get("atr_sl_mult", 2.0),
                    }
                    res = run_perp_backtest(df, sigs, cfg, funding_df=funding_df)
                    m = res["metrics"]
                    if m["trades"] < 12:
                        continue
                    score = (
                        m["sharpe"]
                        + 0.35 * min(m["profit_factor"] - 1.0, 2.0)
                        - 1.2 * max(0.0, abs(m["max_drawdown"]) - 0.25)
                    )
                    candidates.append(
                        {
                            "timeframe": tf,
                            "family": fam_name,
                            "family_zh": spec.label_zh,
                            "direction": direction,
                            "params": params,
                            "risk": {**spec.default_risk, "atr_sl_mult": params.get("atr_sl_mult", 2.0)},
                            "metrics": m,
                            "score": round(float(score), 4),
                        }
                    )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates
