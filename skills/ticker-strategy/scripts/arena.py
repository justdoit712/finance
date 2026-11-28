#!/usr/bin/env python3
"""Main-force playbook arena & perpetual futures backtest engine (pure NumPy/Pandas)."""

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
# Perpetual Futures Backtest Engine (t -> t+1 Open, Base Policy Layer-1 Rules)
# ---------------------------------------------------------------------------

def _align_funding_rates(df: pd.DataFrame, funding_df: pd.DataFrame | None, interval: str) -> tuple[np.ndarray, np.ndarray]:
    n = len(df)
    open_times = df["open_time"].to_numpy(dtype=np.int64)
    bar_ms = INTERVAL_MS.get(interval, 3_600_000)

    is_funding_bar = (open_times // FUNDING_PERIOD_MS) < ((open_times + bar_ms - 1) // FUNDING_PERIOD_MS)
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
    chase_filtered: int = 0,
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
        "chase_filtered": int(chase_filtered),
    }


def _normalize_tranches(raw_tranches: Any) -> list[float]:
    if not isinstance(raw_tranches, (list, tuple)) or not raw_tranches:
        return [1.0]
    vals = [float(x) for x in raw_tranches if float(x) > 0.0]
    if not vals:
        return [1.0]
    s = sum(vals)
    if s > 1.0:
        vals = [x / s for x in vals]
    return vals


def run_perp_backtest(
    df: pd.DataFrame,
    signals: dict[str, np.ndarray],
    config: dict[str, Any],
    funding_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Simulate perpetual futures with no-lookahead execution, fees, slippage, funding, ATR stops & Layer-1 rules."""
    n = len(df)
    if n < 20:
        return {
            "metrics": compute_metrics(np.ones(max(n, 1)), np.ones(max(n, 1)), [], config.get("interval", "1h"), 0, 0.0, 0.0),
            "equity": np.ones(max(n, 1)),
            "trades": [],
        }

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

    # Layer-1 base policy controls
    leverage = max(float(config.get("max_leverage", 1.0)), 0.1)
    tranches = _normalize_tranches(config.get("entry_tranches", [1.0]))
    add_tranche_step = max(float(config.get("add_tranche_atr_step", 0.6)), 0.1)
    max_chase_atr = config.get("max_chase_atr", None)
    max_chase_atr_f = float(max_chase_atr) if max_chase_atr is not None else None

    atr_period = int(config.get("atr_period", 14))
    sl_mult = config.get("atr_sl_mult", 2.0)
    tp_mult = config.get("atr_tp_mult", None)
    trail_mult = config.get("atr_trail_mult", None)
    cooldown_bars = max(
        int(config.get("cooldown_bars", 0)),
        int(config.get("cooldown_bars_after_sl", 0)),
    )
    interval = config.get("interval", "1h")

    atr_arr = atr(highs, lows, closes, atr_period)
    ema20_arr = ema(closes, 20)
    is_funding_bar, funding_rates = _align_funding_rates(df, funding_df, interval)

    equity = np.ones(n, dtype=float)
    trades: list[dict[str, Any]] = []

    pos = 0  # 0 flat, 1 long, -1 short
    pos_weight = 0.0
    next_tranche_idx = 0
    last_tranche_px = 0.0
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
    chase_filtered = 0
    cur_eq = 1.0

    def close_trade(exit_i: int, raw_exit_px: float, reason: str, entered_now: bool) -> None:
        nonlocal pos, pos_weight, next_tranche_idx, cur_eq, total_fees_pct, cooldown_left
        eff_lev = pos_weight * leverage
        if pos == 1:
            fill_px = raw_exit_px * (1.0 - cost_rate)
            gross_ret = (raw_exit_px / entry_px) - 1.0
        else:
            fill_px = raw_exit_px * (1.0 + cost_rate)
            gross_ret = 1.0 - (raw_exit_px / entry_px)

        ref_prev = (entry_px / (1.0 + cost_rate)) if (entered_now and pos == 1) else (
            (entry_px / (1.0 - cost_rate)) if entered_now else closes[exit_i - 1]
        )
        if pos == 1:
            step_ret = (raw_exit_px / max(ref_prev, 1e-12) - 1.0) * eff_lev
        else:
            step_ret = (1.0 - raw_exit_px / max(ref_prev, 1e-12)) * eff_lev

        exit_fee = cost_rate * eff_lev
        cur_eq *= max(1.0 + step_ret, 0.0)
        cur_eq *= max(1.0 - exit_fee, 0.0)
        total_fees_pct += exit_fee

        trades.append({
            "entry_idx": entry_idx,
            "exit_idx": exit_i,
            "side": "long" if pos == 1 else "short",
            "entry_price": round(entry_px, 6),
            "exit_price": round(fill_px, 6),
            "gross_return": float(gross_ret * eff_lev),
            "net_return": float(cur_eq / max(entry_equity, 1e-12) - 1.0),
            "hold_bars": exit_i - entry_idx,
            "exit_reason": reason,
            "tranches_filled": next_tranche_idx,
        })
        pos = 0
        pos_weight = 0.0
        next_tranche_idx = 0
        if reason in ("sl", "trail"):
            cooldown_left = cooldown_bars

    for i in range(1, n):
        sig_i = i - 1
        if cooldown_left > 0 and pos == 0:
            cooldown_left -= 1

        # 1) Signal-driven exits at bar i open
        if pos == 1 and (exit_long[sig_i] or (allow_short and entry_short[sig_i])):
            close_trade(i, opens[i], "signal", entered_now=False)
        elif pos == -1 and (exit_short[sig_i] or (allow_long and entry_long[sig_i])):
            close_trade(i, opens[i], "signal", entered_now=False)

        # 2) Signal-driven initial entry OR staged tranche add at bar i open
        entered_this_bar = False
        added_tranche_this_bar = False
        if pos == 0 and cooldown_left == 0 and np.isfinite(atr_arr[sig_i]) and atr_arr[sig_i] > 0:
            want_long = allow_long and entry_long[sig_i]
            want_short = allow_short and entry_short[sig_i]

            if max_chase_atr_f is not None and np.isfinite(ema20_arr[sig_i]):
                if want_long and closes[sig_i] > ema20_arr[sig_i] + max_chase_atr_f * atr_arr[sig_i]:
                    want_long = False
                    chase_filtered += 1
                if want_short and closes[sig_i] < ema20_arr[sig_i] - max_chase_atr_f * atr_arr[sig_i]:
                    want_short = False
                    chase_filtered += 1

            if want_long and not want_short:
                w0 = tranches[0]
                pos = 1
                pos_weight = w0
                next_tranche_idx = 1
                last_tranche_px = opens[i]
                entry_equity = cur_eq
                entry_px = opens[i] * (1.0 + cost_rate)
                fee0 = cost_rate * pos_weight * leverage
                cur_eq *= max(1.0 - fee0, 0.0)
                total_fees_pct += fee0
                entry_idx = i
                entered_this_bar = True
                best_px = opens[i]
                a = atr_arr[sig_i]
                sl_px = opens[i] - float(sl_mult) * a if sl_mult else 0.0
                tp_px = opens[i] + float(tp_mult) * a if tp_mult else 0.0
                trail_px = opens[i] - float(trail_mult) * a if trail_mult else 0.0
            elif want_short and not want_long:
                w0 = tranches[0]
                pos = -1
                pos_weight = w0
                next_tranche_idx = 1
                last_tranche_px = opens[i]
                entry_equity = cur_eq
                entry_px = opens[i] * (1.0 - cost_rate)
                fee0 = cost_rate * pos_weight * leverage
                cur_eq *= max(1.0 - fee0, 0.0)
                total_fees_pct += fee0
                entry_idx = i
                entered_this_bar = True
                best_px = opens[i]
                a = atr_arr[sig_i]
                sl_px = opens[i] + float(sl_mult) * a if sl_mult else 0.0
                tp_px = opens[i] - float(tp_mult) * a if tp_mult else 0.0
                trail_px = opens[i] + float(trail_mult) * a if trail_mult else 0.0

        elif pos != 0 and next_tranche_idx < len(tranches) and np.isfinite(atr_arr[sig_i]) and atr_arr[sig_i] > 0:
            # First mark existing weight from prev close to bar i open before adding new tranche
            step_open = (opens[i] / max(closes[i - 1], 1e-12) - 1.0) if pos == 1 else (1.0 - opens[i] / max(closes[i - 1], 1e-12))
            a = atr_arr[sig_i]
            should_add = False
            if pos == 1:
                pullback_ok = opens[i] <= last_tranche_px - add_tranche_step * a and (not sl_mult or opens[i] > sl_px)
                confirm_ok = entry_long[sig_i] and opens[i] >= last_tranche_px + 0.3 * a
                should_add = pullback_ok or confirm_ok
            else:
                pullback_ok = opens[i] >= last_tranche_px + add_tranche_step * a and (not sl_mult or opens[i] < sl_px)
                confirm_ok = entry_short[sig_i] and opens[i] <= last_tranche_px - 0.3 * a
                should_add = pullback_ok or confirm_ok

            if should_add:
                cur_eq *= max(1.0 + step_open * pos_weight * leverage, 0.0)
                add_w = tranches[next_tranche_idx]
                fill_tranche = opens[i] * (1.0 + cost_rate if pos == 1 else 1.0 - cost_rate)
                new_w = pos_weight + add_w
                entry_px = (entry_px * pos_weight + fill_tranche * add_w) / max(new_w, 1e-12)
                pos_weight = new_w
                next_tranche_idx += 1
                last_tranche_px = opens[i]
                add_fee = cost_rate * add_w * leverage
                cur_eq *= max(1.0 - add_fee, 0.0)
                total_fees_pct += add_fee
                added_tranche_this_bar = True

        # 3) Intra-bar stop checks (conservative order: SL/Trail before TP)
        use_open_ref = entered_this_bar or added_tranche_this_bar
        if pos == 1:
            eff_stop = max(sl_px if sl_mult else 0.0, trail_px if trail_mult else 0.0)
            if eff_stop > 0.0 and lows[i] <= eff_stop:
                fill = min(opens[i], eff_stop) if not use_open_ref else eff_stop
                reason = "trail" if (trail_mult and trail_px >= sl_px) else "sl"
                close_trade(i, fill, reason, entered_now=use_open_ref)
            elif tp_mult and tp_px > 0.0 and highs[i] >= tp_px:
                fill = max(opens[i], tp_px) if not use_open_ref else tp_px
                close_trade(i, fill, "tp", entered_now=use_open_ref)
        elif pos == -1:
            candidates = [x for x in (sl_px if sl_mult else 0.0, trail_px if trail_mult else 0.0) if x > 0.0]
            eff_stop = min(candidates) if candidates else 0.0
            if eff_stop > 0.0 and highs[i] >= eff_stop:
                fill = max(opens[i], eff_stop) if not use_open_ref else eff_stop
                reason = "trail" if (trail_mult and (not sl_mult or trail_px <= sl_px)) else "sl"
                close_trade(i, fill, reason, entered_now=use_open_ref)
            elif tp_mult and tp_px > 0.0 and lows[i] <= tp_px:
                fill = min(opens[i], tp_px) if not use_open_ref else tp_px
                close_trade(i, fill, "tp", entered_now=use_open_ref)

        # 4) End-of-bar mark-to-market, funding, and trailing stop update for next bar
        if pos != 0:
            exposure_bars += 1
            eff_lev = pos_weight * leverage
            ref_px = opens[i] if use_open_ref else closes[i - 1]
            if pos == 1:
                step_r = (closes[i] / max(ref_px, 1e-12) - 1.0) * eff_lev
                cur_eq *= max(1.0 + step_r, 0.0)
                if trail_mult and np.isfinite(atr_arr[i]):
                    best_px = max(best_px, highs[i])
                    trail_px = max(trail_px, best_px - float(trail_mult) * atr_arr[i])
            else:
                step_r = (1.0 - closes[i] / max(ref_px, 1e-12)) * eff_lev
                cur_eq *= max(1.0 + step_r, 0.0)
                if trail_mult and np.isfinite(atr_arr[i]):
                    best_px = min(best_px, lows[i])
                    new_t = best_px + float(trail_mult) * atr_arr[i]
                    trail_px = new_t if trail_px <= 0.0 else min(trail_px, new_t)

            if is_funding_bar[i]:
                f_cost = pos * funding_rates[i] * eff_lev
                cur_eq *= max(1.0 - f_cost, 0.0)
                total_funding_pct += f_cost

        equity[i] = cur_eq

    metrics = compute_metrics(
        equity,
        closes,
        trades,
        interval,
        exposure_bars,
        total_fees_pct,
        total_funding_pct,
        chase_filtered=chase_filtered,
    )
    return {"metrics": metrics, "equity": equity, "trades": trades}


# ---------------------------------------------------------------------------
# 5 Main-Force Technical Playbooks
# ---------------------------------------------------------------------------

def signals_sweep_fade(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    """主力插针扫损反手：假跌破前低长下影收回做多；假突破前高长上影诱多收回做空。"""
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)

    lookback = int(params["lookback"])
    min_wick = float(params["min_wick"])

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


def signals_ema_defense_pullback(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    """主力护盘均线回踩承接：围绕该币专属护盘/压制 EMA 低吸回踩，拒绝追高。"""
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)

    trend_len = int(params["trend_len"])
    rsi_len = int(params["rsi_len"])
    pullback_low = float(params["pullback_low"])
    pullback_high = 100.0 - pullback_low

    trend_ema = ema(c, trend_len)
    rsi_arr = rsi(c, rsi_len)
    atr_arr = atr(h, l, c, 14)
    prev_rsi = np.roll(rsi_arr, 1)
    prev_rsi[0] = np.nan

    near_sup = (c >= trend_ema * 0.99) & (c <= trend_ema + 2.2 * atr_arr)
    near_res = (c <= trend_ema * 1.01) & (c >= trend_ema - 2.2 * atr_arr)

    entry_long = near_sup & (prev_rsi < pullback_low) & (rsi_arr >= pullback_low)
    entry_short = near_res & (prev_rsi > pullback_high) & (rsi_arr <= pullback_high)
    exit_long = (rsi_arr > 72.0) | (c < trend_ema * 0.985)
    exit_short = (rsi_arr < 28.0) | (c > trend_ema * 1.015)
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }


def signals_squeeze_ignition(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    """主力横盘吸筹放量点火：低波压缩后放量突破首段，剔除单根爆拉透支 K 线。"""
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    bb_len = int(params["bb_len"])
    bb_std = float(params["bb_std"])
    vol_mult = float(params["vol_mult"])

    mid, upper, lower = bollinger_bands(c, bb_len, bb_std)
    bw = (upper - lower) / np.maximum(mid, 1e-12)
    bw_q = pd.Series(bw).rolling(100, min_periods=40).quantile(0.35).to_numpy()
    prev_bw = np.roll(bw, 1)
    prev_bw_q = np.roll(bw_q, 1)
    prev_bw[0] = np.nan
    prev_bw_q[0] = np.nan

    vol_ma = sma(vol, 20)
    atr_arr = atr(h, l, c, 14)
    squeeze_ready = (prev_bw <= prev_bw_q) | (bw <= bw_q * 1.15)
    vol_ok = vol >= (vol_ma * vol_mult)
    not_overextended = (h - l) <= (2.5 * atr_arr)

    entry_long = (c > upper) & squeeze_ready & vol_ok & not_overextended
    entry_short = (c < lower) & squeeze_ready & vol_ok & not_overextended
    exit_long = c < mid
    exit_short = c > mid
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }


def signals_climax_reversal(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    """主力巨量派发/衰竭反转：极端偏离布林带 + RSI 超买超卖 + 放量或长影线衰竭。"""
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    bb_len = int(params["bb_len"])
    bb_std = float(params["bb_std"])
    rsi_os = float(params["rsi_os"])
    rsi_ob = 100.0 - rsi_os
    vol_spike = float(params.get("vol_spike", 1.5))

    mid, upper, lower = bollinger_bands(c, bb_len, bb_std)
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


def signals_trend_breakout(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    """顺庄主升浪结构跟踪：放量确认且 ADX 达标后的趋势波段延续。"""
    c = df["close"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    fast = ema(c, int(params["fast_len"]))
    slow = ema(c, int(params["slow_len"]))
    adx_arr = adx(h, l, c, 14)
    vol_ma = sma(vol, 20)
    adx_min = float(params.get("adx_min", 18.0))
    vol_mult = float(params.get("vol_mult", 1.0))

    prev_fast = np.roll(fast, 1)
    prev_slow = np.roll(slow, 1)
    prev_fast[0] = np.nan
    prev_slow[0] = np.nan

    vol_ok = vol >= (vol_ma * vol_mult)
    entry_long = (fast > slow) & (prev_fast <= prev_slow) & (adx_arr >= adx_min) & vol_ok
    entry_short = (fast < slow) & (prev_fast >= prev_slow) & (adx_arr >= adx_min) & vol_ok
    exit_long = fast < slow
    exit_short = fast > slow
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
    "sweep_fade": StrategyFamilySpec(
        name="sweep_fade",
        label_zh="主力插针扫损反手",
        signal_fn=signals_sweep_fade,
        param_axes={
            "lookback": [15, 24, 36],
            "min_wick": [0.38, 0.48],
            "atr_sl_mult": [1.8, 2.5],
        },
        default_risk={"atr_period": 14, "atr_tp_mult": 3.0, "atr_trail_mult": None, "cooldown_bars": 2},
    ),
    "ema_defense_pullback": StrategyFamilySpec(
        name="ema_defense_pullback",
        label_zh="主力护盘均线回踩承接",
        signal_fn=signals_ema_defense_pullback,
        param_axes={
            "trend_len": [34, 55, 100, 144],
            "rsi_len": [10, 14],
            "pullback_low": [36.0, 44.0],
            "atr_sl_mult": [2.0, 2.6],
        },
        default_risk={"atr_period": 14, "atr_tp_mult": 3.6, "atr_trail_mult": None, "cooldown_bars": 2},
    ),
    "squeeze_ignition": StrategyFamilySpec(
        name="squeeze_ignition",
        label_zh="主力横盘吸筹放量点火",
        signal_fn=signals_squeeze_ignition,
        param_axes={
            "bb_len": [18, 24],
            "bb_std": [1.8, 2.2],
            "vol_mult": [1.3, 1.8],
            "atr_sl_mult": [2.0, 2.8],
        },
        default_risk={"atr_period": 14, "atr_tp_mult": None, "atr_trail_mult": 2.5, "cooldown_bars": 2},
    ),
    "climax_reversal": StrategyFamilySpec(
        name="climax_reversal",
        label_zh="主力巨量派发/衰竭反转",
        signal_fn=signals_climax_reversal,
        param_axes={
            "bb_len": [16, 22],
            "bb_std": [2.1, 2.5],
            "rsi_os": [26.0, 32.0],
            "vol_spike": [1.4, 2.0],
            "atr_sl_mult": [1.8, 2.5],
        },
        default_risk={"atr_period": 14, "atr_tp_mult": 2.8, "atr_trail_mult": None, "cooldown_bars": 3},
    ),
    "trend_breakout": StrategyFamilySpec(
        name="trend_breakout",
        label_zh="顺庄主升浪结构跟踪",
        signal_fn=signals_trend_breakout,
        param_axes={
            "fast_len": [12, 20],
            "slow_len": [48, 80],
            "adx_min": [18.0, 24.0],
            "vol_mult": [1.0, 1.3],
            "atr_sl_mult": [2.2, 3.0],
        },
        default_risk={"atr_period": 14, "atr_tp_mult": None, "atr_trail_mult": 2.6, "cooldown_bars": 2},
    ),
}


def get_param_axes(spec: StrategyFamilySpec, profile: dict[str, Any] | None = None) -> dict[str, list[Any]]:
    """Return effective parameter axes adapted to the ticker's whale diagnosis."""
    axes = {k: list(v) for k, v in spec.param_axes.items()}
    if not profile:
        return axes

    whale = profile.get("whale_diagnosis", {})
    diag = profile.get("diagnosis", {})

    if spec.name == "ema_defense_pullback":
        extra_emas = []
        for key in ("best_support_ema", "best_resistance_ema"):
            val = whale.get(key)
            if isinstance(val, int) and val >= 10:
                extra_emas.append(val)
        if extra_emas:
            merged = sorted(set(axes["trend_len"] + extra_emas))
            axes["trend_len"] = merged

    if diag.get("wick_risk") == "high" and "atr_sl_mult" in axes:
        widened = sorted({max(float(x), 2.2) for x in axes["atr_sl_mult"]})
        if len(widened) == 1:
            widened = [widened[0], round(widened[0] + 0.6, 1)]
        axes["atr_sl_mult"] = widened

    return axes


def expand_param_grid(spec: StrategyFamilySpec, profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    axes = get_param_axes(spec, profile)
    keys = list(axes.keys())
    values = [axes[k] for k in keys]
    combos: list[dict[str, Any]] = []
    for prod in itertools.product(*values):
        p = dict(zip(keys, prod))
        if spec.name == "trend_breakout" and p["fast_len"] >= p["slow_len"]:
            continue
        combos.append(p)
    return combos


def build_backtest_config(
    timeframe: str,
    direction: str,
    spec: StrategyFamilySpec,
    params: dict[str, Any],
    fee_rate: float,
    slippage: float,
    base_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "direction": direction,
        "fee_rate": fee_rate,
        "slippage": slippage,
        "interval": timeframe,
        **spec.default_risk,
        "atr_sl_mult": params.get("atr_sl_mult", 2.0),
    }
    if base_policy:
        cfg["max_leverage"] = base_policy.get("max_leverage", 1.0)
        cfg["entry_tranches"] = base_policy.get("entry_tranches", [1.0])
        cfg["add_tranche_atr_step"] = base_policy.get("add_tranche_atr_step", 0.6)
        cfg["max_chase_atr"] = base_policy.get("max_chase_atr", None)
        cfg["cooldown_bars_after_sl"] = base_policy.get("cooldown_bars_after_sl", 0)
    return cfg


def run_arena(
    klines_by_tf: dict[str, pd.DataFrame],
    funding_df: pd.DataFrame | None = None,
    fee_rate: float = 0.0005,
    slippage: float = 0.0003,
    directions: tuple[str, ...] = ("both", "long_only", "short_only"),
    min_bars: int = 300,
    profile: dict[str, Any] | None = None,
    base_policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run all 5 main-force playbooks across timeframes & directions under Layer-1 base policy."""
    candidates: list[dict[str, Any]] = []
    rec_list: list[str] = []
    if profile:
        rec_list = list(profile.get("whale_diagnosis", {}).get("recommended_playbooks", []))

    for tf, df in klines_by_tf.items():
        if df is None or len(df) < min_bars:
            continue
        for fam_name, spec in FAMILY_SPECS.items():
            align_bonus = 0.0
            if fam_name in rec_list:
                rank_idx = rec_list.index(fam_name)
                if rank_idx <= 1:
                    align_bonus = 0.15
                elif rank_idx == 2:
                    align_bonus = 0.08

            grid = expand_param_grid(spec, profile)
            for params in grid:
                sigs = spec.signal_fn(df, params)
                for direction in directions:
                    cfg = build_backtest_config(tf, direction, spec, params, fee_rate, slippage, base_policy)
                    res = run_perp_backtest(df, sigs, cfg, funding_df=funding_df)
                    m = res["metrics"]
                    if m["trades"] < 12:
                        continue
                    score = (
                        m["sharpe"]
                        + 0.35 * min(m["profit_factor"] - 1.0, 2.0)
                        - 1.2 * max(0.0, abs(m["max_drawdown"]) - 0.25)
                        + align_bonus
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
