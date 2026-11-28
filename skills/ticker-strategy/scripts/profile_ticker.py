#!/usr/bin/env python3
"""Main-force (主力/庄家) behavior technical profiler & regime diagnostics."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fetch_binance import INTERVAL_MS, fetch_funding_rate, fetch_klines, fetch_metrics

BARS_PER_YEAR = {
    "1m": 365.0 * 1440.0,
    "3m": 365.0 * 480.0,
    "5m": 365.0 * 288.0,
    "15m": 365.0 * 96.0,
    "30m": 365.0 * 48.0,
    "1h": 365.0 * 24.0,
    "2h": 365.0 * 12.0,
    "4h": 365.0 * 6.0,
    "6h": 365.0 * 4.0,
    "8h": 365.0 * 3.0,
    "12h": 365.0 * 2.0,
    "1d": 365.0,
}

PLAYBOOKS = (
    "sweep_fade",
    "ema_defense_pullback",
    "squeeze_ignition",
    "climax_reversal",
    "trend_breakout",
)


def _calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    tr = np.empty(n, dtype=float)
    tr[0] = high[0] - low[0]
    prev_c = close[:-1]
    tr[1:] = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - prev_c), np.abs(low[1:] - prev_c)),
    )
    return pd.Series(tr).ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean().to_numpy()


def _calc_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    if n < period * 2:
        return np.full(n, np.nan)
    up_move = np.diff(high, prepend=high[0])
    down_move = -np.diff(low, prepend=low[0])
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = np.empty(n, dtype=float)
    tr[0] = high[0] - low[0]
    prev_c = close[:-1]
    tr[1:] = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - prev_c), np.abs(low[1:] - prev_c)),
    )

    atr = pd.Series(tr).ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    plus_di = 100.0 * pd.Series(plus_dm).ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr.replace(0.0, np.nan)
    minus_di = 100.0 * pd.Series(minus_dm).ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr.replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx = dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return adx.to_numpy()


def _hurst_rs(log_returns: np.ndarray) -> float:
    r = log_returns[np.isfinite(log_returns)]
    n = len(r)
    if n < 80:
        return 0.5
    lags = [lag for lag in (8, 16, 32, 64, 128, 256) if lag < n // 2]
    if len(lags) < 3:
        return 0.5
    rs_vals = []
    valid_lags = []
    for lag in lags:
        chunks = n // lag
        if chunks < 2:
            continue
        sub = r[: chunks * lag].reshape(chunks, lag)
        means = sub.mean(axis=1, keepdims=True)
        dev = np.cumsum(sub - means, axis=1)
        rng = dev.max(axis=1) - dev.min(axis=1)
        std = sub.std(axis=1, ddof=1)
        valid = std > 1e-12
        if valid.any():
            rs_vals.append(float(np.mean(rng[valid] / std[valid])))
            valid_lags.append(lag)
    if len(valid_lags) < 3:
        return 0.5
    slope = np.polyfit(np.log(valid_lags), np.log(rs_vals), 1)[0]
    return float(np.clip(slope, 0.1, 0.9))


def _efficiency_ratio(close: np.ndarray, window: int = 20) -> float:
    if len(close) <= window:
        return 0.0
    net = np.abs(close[window:] - close[:-window])
    step = np.abs(np.diff(close))
    rolling_path = pd.Series(step).rolling(window).sum().to_numpy()[window - 1 :]
    valid = rolling_path > 1e-12
    if not valid.any():
        return 0.0
    return float(np.nanmedian(net[valid] / rolling_path[valid]))


# ---------------------------------------------------------------------------
# Six-Dimension Main-Force Behavior Dissection
# ---------------------------------------------------------------------------

def _analyze_sweeps(df: pd.DataFrame, lookback: int = 20, fwd_bars: int = 6) -> dict[str, Any]:
    """Measure stop-hunt & pinbar sweep behavior around prior lookback highs/lows."""
    n = len(df)
    if n < lookback + fwd_bars + 5:
        return {
            "lookback": lookback,
            "fwd_bars": fwd_bars,
            "bull_sweep_count": 0,
            "bull_sweep_rate_pct": 0.0,
            "bull_rebound_win_rate": 0.0,
            "bull_avg_fwd_ret": 0.0,
            "bear_sweep_count": 0,
            "bear_sweep_rate_pct": 0.0,
            "bear_dump_win_rate": 0.0,
            "bear_avg_fwd_ret": 0.0,
        }

    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)

    bar_range = np.maximum(h - l, 1e-12)
    lower_wick_ratio = (np.minimum(o, c) - l) / bar_range
    upper_wick_ratio = (h - np.maximum(o, c)) / bar_range

    prev_hi = pd.Series(h).rolling(lookback, min_periods=lookback).max().shift(1).to_numpy()
    prev_lo = pd.Series(l).rolling(lookback, min_periods=lookback).min().shift(1).to_numpy()

    bull_mask = (l < prev_lo) & (c > prev_lo) & (lower_wick_ratio >= 0.40)
    bear_mask = (h > prev_hi) & (c < prev_hi) & (upper_wick_ratio >= 0.40)

    valid_end = n - fwd_bars
    bull_idx = [int(i) for i in np.where(bull_mask[:valid_end])[0] if i >= lookback]
    bear_idx = [int(i) for i in np.where(bear_mask[:valid_end])[0] if i >= lookback]

    bull_rets = [float(c[i + fwd_bars] / max(c[i], 1e-12) - 1.0) for i in bull_idx]
    bear_rets = [float(1.0 - c[i + fwd_bars] / max(c[i], 1e-12)) for i in bear_idx]

    eval_bars = max(valid_end - lookback, 1)
    return {
        "lookback": lookback,
        "fwd_bars": fwd_bars,
        "bull_sweep_count": len(bull_idx),
        "bull_sweep_rate_pct": round(len(bull_idx) / eval_bars * 100.0, 2),
        "bull_rebound_win_rate": round(float(np.mean([r > 0 for r in bull_rets])), 3) if bull_rets else 0.0,
        "bull_avg_fwd_ret": round(float(np.mean(bull_rets)), 5) if bull_rets else 0.0,
        "bear_sweep_count": len(bear_idx),
        "bear_sweep_rate_pct": round(len(bear_idx) / eval_bars * 100.0, 2),
        "bear_dump_win_rate": round(float(np.mean([r > 0 for r in bear_rets])), 3) if bear_rets else 0.0,
        "bear_avg_fwd_ret": round(float(np.mean(bear_rets)), 5) if bear_rets else 0.0,
    }


def _analyze_breakout_honesty(df: pd.DataFrame, atr_arr: np.ndarray, lookback: int = 20) -> dict[str, Any]:
    """Measure whether 20-bar close breakouts genuinely follow through or turn into bull/bear traps."""
    n = len(df)
    fwd = 4
    if n < lookback + fwd + 5:
        return {
            "breakout_count": 0,
            "continuation_rate": 0.0,
            "trap_rate": 0.0,
            "high_vol_continuation_rate": 0.0,
            "low_vol_continuation_rate": 0.0,
        }

    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    prev_hi = pd.Series(h).rolling(lookback, min_periods=lookback).max().shift(1).to_numpy()
    prev_lo = pd.Series(l).rolling(lookback, min_periods=lookback).min().shift(1).to_numpy()
    vol_ma = pd.Series(vol).rolling(20, min_periods=20).mean().to_numpy()

    cont_flags: list[bool] = []
    trap_flags: list[bool] = []
    hv_cont: list[bool] = []
    lv_cont: list[bool] = []

    for i in range(lookback + 1, n - fwd):
        a = atr_arr[i]
        if not np.isfinite(a) or a <= 0 or not np.isfinite(prev_hi[i]) or not np.isfinite(prev_lo[i]):
            continue
        is_up = (c[i] > prev_hi[i]) and (c[i - 1] <= prev_hi[i - 1])
        is_dn = (c[i] < prev_lo[i]) and (c[i - 1] >= prev_lo[i - 1])
        if not (is_up or is_dn):
            continue

        is_hv = np.isfinite(vol_ma[i]) and vol_ma[i] > 0 and vol[i] >= 1.5 * vol_ma[i]
        if is_up:
            lvl = prev_hi[i]
            fav_exc = float(np.max(h[i + 1 : i + 1 + fwd]) - c[i])
            holds = c[i + fwd] > c[i]
            trapped = np.any(c[i + 1 : i + 1 + fwd] < lvl) and fav_exc < 0.8 * a
        else:
            lvl = prev_lo[i]
            fav_exc = float(c[i] - np.min(l[i + 1 : i + 1 + fwd]))
            holds = c[i + fwd] < c[i]
            trapped = np.any(c[i + 1 : i + 1 + fwd] > lvl) and fav_exc < 0.8 * a

        continued = (fav_exc >= 0.8 * a) and holds
        cont_flags.append(bool(continued))
        trap_flags.append(bool(trapped))
        if is_hv:
            hv_cont.append(bool(continued))
        else:
            lv_cont.append(bool(continued))

    return {
        "breakout_count": len(cont_flags),
        "continuation_rate": round(float(np.mean(cont_flags)), 3) if cont_flags else 0.0,
        "trap_rate": round(float(np.mean(trap_flags)), 3) if trap_flags else 0.0,
        "high_vol_continuation_rate": round(float(np.mean(hv_cont)), 3) if hv_cont else 0.0,
        "low_vol_continuation_rate": round(float(np.mean(lv_cont)), 3) if lv_cont else 0.0,
    }


def _analyze_key_emas(
    df: pd.DataFrame,
    atr_arr: np.ndarray,
    candidates: tuple[int, ...] = (21, 34, 55, 120, 200),
) -> dict[str, Any]:
    """Identify which EMA lengths the main force repeatedly defends or suppresses."""
    c = df["close"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    n = len(c)
    fwd = 6

    stats: dict[str, dict[str, Any]] = {}
    best_sup_len = 55
    best_sup_score = -1.0
    best_sup_rate = 0.0
    best_res_len = 55
    best_res_score = -1.0
    best_res_rate = 0.0

    for length in candidates:
        if n < length + fwd + 10:
            continue
        ema_arr = pd.Series(c).ewm(span=length, adjust=False, min_periods=length).mean().to_numpy()
        bull_rets: list[float] = []
        bear_rets: list[float] = []

        i = max(length + 5, 6)
        last_bull = -10
        last_bear = -10
        while i < n - fwd:
            a = atr_arr[i]
            e = ema_arr[i]
            if np.isfinite(a) and a > 0 and np.isfinite(e) and np.isfinite(ema_arr[i - 5]):
                # Bull defense touch in rising EMA
                if (
                    i - last_bull >= 4
                    and e > ema_arr[i - 5]
                    and c[i - 1] > ema_arr[i - 1]
                    and l[i] <= e + 0.35 * a
                    and c[i] >= e - 0.15 * a
                ):
                    bull_rets.append(float(c[i + fwd] / max(c[i], 1e-12) - 1.0))
                    last_bull = i
                # Bear resistance touch in falling EMA
                if (
                    i - last_bear >= 4
                    and e < ema_arr[i - 5]
                    and c[i - 1] < ema_arr[i - 1]
                    and h[i] >= e - 0.35 * a
                    and c[i] <= e + 0.15 * a
                ):
                    bear_rets.append(float(1.0 - c[i + fwd] / max(c[i], 1e-12)))
                    last_bear = i
            i += 1

        b_cnt = len(bull_rets)
        b_rate = float(np.mean([r > 0 for r in bull_rets])) if b_cnt else 0.0
        r_cnt = len(bear_rets)
        r_rate = float(np.mean([r > 0 for r in bear_rets])) if r_cnt else 0.0

        stats[str(length)] = {
            "bull_touches": b_cnt,
            "bull_defense_rate": round(b_rate, 3),
            "bear_touches": r_cnt,
            "bear_reject_rate": round(r_rate, 3),
        }

        if b_cnt >= 5:
            sup_score = b_rate + min(b_cnt, 40) * 0.002
            if sup_score > best_sup_score:
                best_sup_score = sup_score
                best_sup_len = length
                best_sup_rate = b_rate

        if r_cnt >= 5:
            res_score = r_rate + min(r_cnt, 40) * 0.002
            if res_score > best_res_score:
                best_res_score = res_score
                best_res_len = length
                best_res_rate = r_rate

    return {
        "best_support_ema": int(best_sup_len),
        "best_support_rate": round(best_sup_rate, 3),
        "best_resistance_ema": int(best_res_len),
        "best_resistance_rate": round(best_res_rate, 3),
        "ema_details": stats,
    }


def _analyze_squeeze_and_climax(df: pd.DataFrame, atr_arr: np.ndarray) -> tuple[dict[str, Any], dict[str, Any]]:
    """Dissect squeeze accumulation ignition and high-volume climax intent."""
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)
    n = len(c)

    # 1) Squeeze accumulation -> volume ignition
    s_close = pd.Series(c)
    mid = s_close.rolling(20, min_periods=20).mean()
    std = s_close.rolling(20, min_periods=20).std(ddof=0)
    bw = ((2.0 * std * 2.0) / mid.replace(0.0, np.nan)).to_numpy()
    bw_q30 = pd.Series(bw).rolling(100, min_periods=40).quantile(0.30).to_numpy()
    vol_ma = pd.Series(vol).rolling(20, min_periods=20).mean().to_numpy()

    valid_bw = np.isfinite(bw) & np.isfinite(bw_q30)
    squeeze_share = float(np.mean(bw[valid_bw] <= bw_q30[valid_bw])) if valid_bw.any() else 0.0

    ign_wins: list[bool] = []
    ign_atr_moves: list[float] = []
    fwd_ign = 8
    i = 100
    while i < n - fwd_ign:
        a = atr_arr[i]
        if (
            np.isfinite(a)
            and a > 0
            and np.isfinite(bw[i - 1])
            and np.isfinite(bw_q30[i - 1])
            and np.isfinite(vol_ma[i])
            and vol_ma[i] > 0
            and bw[i - 1] <= bw_q30[i - 1] * 1.15
            and vol[i] >= 1.8 * vol_ma[i]
            and abs(c[i] - o[i]) > 0.25 * (h[i] - l[i])
        ):
            direction = 1.0 if c[i] > o[i] else -1.0
            move = direction * (c[i + fwd_ign] - c[i])
            ign_wins.append(move > 0)
            ign_atr_moves.append(float(abs(c[i + fwd_ign] - c[i]) / a))
            i += fwd_ign
            continue
        i += 1

    squeeze_info = {
        "squeeze_share_pct": round(squeeze_share * 100.0, 1),
        "ignition_count": len(ign_wins),
        "ignition_win_rate_8b": round(float(np.mean(ign_wins)), 3) if ign_wins else 0.0,
        "ignition_avg_atr_move_8b": round(float(np.mean(ign_atr_moves)), 2) if ign_atr_moves else 0.0,
    }

    # 2) Climax volume intent (vol >= 2.5 * vol_ma20)
    bar_range = np.maximum(h - l, 1e-12)
    wick_ratio = ((h - np.maximum(o, c)) + (np.minimum(o, c) - l)) / bar_range
    climax_wick_revs: list[bool] = []
    climax_body_conts: list[bool] = []
    fwd_clx = 6

    for j in range(25, n - fwd_clx):
        if not np.isfinite(vol_ma[j]) or vol_ma[j] <= 0 or vol[j] < 2.5 * vol_ma[j]:
            continue
        direction = 1.0 if c[j] >= o[j] else -1.0
        fut_diff = direction * (c[j + fwd_clx] - c[j])
        if wick_ratio[j] >= 0.50:
            climax_wick_revs.append(fut_diff < 0)
        else:
            climax_body_conts.append(fut_diff > 0)

    total_climax = len(climax_wick_revs) + len(climax_body_conts)
    climax_info = {
        "climax_count": total_climax,
        "wick_climax_count": len(climax_wick_revs),
        "climax_wick_reversal_rate_6b": round(float(np.mean(climax_wick_revs)), 3) if climax_wick_revs else 0.0,
        "body_climax_count": len(climax_body_conts),
        "climax_body_continuation_rate_6b": round(float(np.mean(climax_body_conts)), 3) if climax_body_conts else 0.0,
    }
    return squeeze_info, climax_info


def _session_diagnostics(df: pd.DataFrame | None) -> dict[str, Any]:
    if df is None or len(df) < 48:
        return {
            "session_pattern": "unknown",
            "session_label_zh": "样本不足",
            "top_6h_volume_share": None,
            "top_active_utc_hours": [],
            "top_active_bj_hours": [],
            "wick_danger_bj_hours": [],
        }
    work = df.copy()
    dt = pd.to_datetime(work["open_time"], unit="ms", utc=True)
    work["utc_hour"] = dt.dt.hour
    work["bj_hour"] = (work["utc_hour"] + 8) % 24

    bar_range = np.maximum(work["high"] - work["low"], 1e-12)
    wick = (work["high"] - np.maximum(work["open"], work["close"])) + (np.minimum(work["open"], work["close"]) - work["low"])
    work["is_long_wick"] = (wick / bar_range) >= 0.55

    by_utc = work.groupby("utc_hour").agg(qvol=("quote_volume", "sum"))
    total_q = float(by_utc["qvol"].sum())
    if total_q <= 0:
        return {
            "session_pattern": "unknown",
            "session_label_zh": "成交额缺失",
            "top_6h_volume_share": None,
            "top_active_utc_hours": [],
            "top_active_bj_hours": [],
            "wick_danger_bj_hours": [],
        }
    by_utc["vol_share"] = by_utc["qvol"] / total_q
    top6_utc = by_utc.sort_values("vol_share", ascending=False).head(6)
    top6_share = float(top6_utc["vol_share"].sum())
    pattern = "session_biased" if top6_share >= 0.42 else "24x7_uniform"

    by_bj = work.groupby("bj_hour").agg(qvol=("quote_volume", "sum"), wick_rate=("is_long_wick", "mean"))
    top6_bj = [int(h) for h in by_bj.sort_values("qvol", ascending=False).head(6).index.tolist()]
    wick_danger_bj = [int(h) for h in by_bj.sort_values("wick_rate", ascending=False).head(4).index.tolist()]

    # Classify dominant session in Beijing Time
    us_hours = {20, 21, 22, 23, 0, 1, 2, 3}
    asia_eu_hours = set(range(8, 20))
    if pattern == "24x7_uniform":
        session_label_zh = "7×24 全天候均匀交投"
    else:
        us_hits = sum(1 for h in top6_bj if h in us_hours)
        asia_hits = sum(1 for h in top6_bj if h in asia_eu_hours)
        if us_hits >= 4:
            session_label_zh = "美盘时段主导（北京时间 20:00~03:00）"
        elif asia_hits >= 4:
            session_label_zh = "亚欧盘时段主导（北京时间 08:00~20:00）"
        else:
            session_label_zh = "特定时段集中放量"

    return {
        "session_pattern": pattern,
        "session_label_zh": session_label_zh,
        "top_6h_volume_share": round(top6_share, 3),
        "top_active_utc_hours": [int(h) for h in top6_utc.index.tolist()],
        "top_active_bj_hours": top6_bj,
        "wick_danger_bj_hours": wick_danger_bj,
    }


def profile_timeframe(df: pd.DataFrame, interval: str) -> dict[str, Any]:
    if df is None or len(df) < 30:
        return {"bars": 0 if df is None else len(df), "sufficient": False}

    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    qvol = df["quote_volume"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)
    tbvol = df["taker_buy_volume"].to_numpy(dtype=float)

    log_ret = np.diff(np.log(np.maximum(c, 1e-12)))
    ret_std = float(np.std(log_ret, ddof=1)) if len(log_ret) > 1 else 0.0
    ann_factor = BARS_PER_YEAR.get(interval, 365.0 * 24.0)
    ann_vol = ret_std * float(np.sqrt(ann_factor))

    ret_s = pd.Series(log_ret)
    skew = float(ret_s.skew()) if len(log_ret) > 10 else 0.0
    kurt = float(ret_s.kurt()) if len(log_ret) > 10 else 0.0
    lag1_ac = float(ret_s.autocorr(lag=1)) if len(log_ret) > 20 and ret_std > 1e-12 else 0.0
    if not np.isfinite(lag1_ac):
        lag1_ac = 0.0

    atr14 = _calc_atr(h, l, c, 14)
    atr_pct = atr14 / np.maximum(c, 1e-12)
    atr_pct_valid = atr_pct[np.isfinite(atr_pct)]
    atr_med = float(np.median(atr_pct_valid)) if len(atr_pct_valid) else 0.0
    atr_p95 = float(np.percentile(atr_pct_valid, 95)) if len(atr_pct_valid) else 0.0

    adx14 = _calc_adx(h, l, c, 14)
    adx_valid = adx14[np.isfinite(adx14)]
    adx_mean = float(np.mean(adx_valid)) if len(adx_valid) else 0.0
    adx_gt25 = float(np.mean(adx_valid > 25.0)) if len(adx_valid) else 0.0

    bar_range = h - l
    valid_range = bar_range > 1e-12
    body_top = np.maximum(o, c)
    body_bot = np.minimum(o, c)
    wick = (h - body_top) + (body_bot - l)
    wick_ratio = np.where(valid_range, wick / np.where(valid_range, bar_range, 1.0), 0.0)
    wick_mean = float(np.mean(wick_ratio[valid_range])) if valid_range.any() else 0.0
    extreme_wick_pct = float(np.mean(wick_ratio[valid_range] > 0.60)) if valid_range.any() else 0.0

    tail_3s = float(np.mean(np.abs(log_ret - np.mean(log_ret)) > 3.0 * ret_std)) if ret_std > 1e-12 else 0.0

    ms_span = max(int(df["open_time"].iloc[-1] - df["open_time"].iloc[0]), INTERVAL_MS.get(interval, 3_600_000))
    days_covered = ms_span / 86_400_000.0
    avg_daily_qvol = float(np.sum(qvol) / max(days_covered, 1.0))

    total_vol = float(np.sum(vol))
    taker_buy_ratio = float(np.sum(tbvol) / total_vol) if total_vol > 0 else 0.5

    total_return = float(c[-1] / c[0] - 1.0)
    cummax = np.maximum.accumulate(c)
    bh_mdd = float(np.min(c / cummax - 1.0))

    sweeps = _analyze_sweeps(df, lookback=20, fwd_bars=6)
    breakouts = _analyze_breakout_honesty(df, atr14, lookback=20)
    key_emas = _analyze_key_emas(df, atr14)
    squeeze, climax = _analyze_squeeze_and_climax(df, atr14)

    return {
        "bars": int(len(df)),
        "sufficient": len(df) >= 300,
        "start_utc": str(df["datetime"].iloc[0]),
        "end_utc": str(df["datetime"].iloc[-1]),
        "days_covered": round(days_covered, 1),
        "avg_daily_quote_volume_usdt": round(avg_daily_qvol, 2),
        "buy_hold_return": round(total_return, 4),
        "buy_hold_max_drawdown": round(bh_mdd, 4),
        "ann_volatility": round(ann_vol, 4),
        "atr_pct_median": round(atr_med, 5),
        "atr_pct_p95": round(atr_p95, 5),
        "return_skew": round(skew if np.isfinite(skew) else 0.0, 3),
        "excess_kurtosis": round(kurt if np.isfinite(kurt) else 0.0, 3),
        "hurst_rs": round(_hurst_rs(log_ret), 3),
        "adx_mean": round(adx_mean, 2),
        "adx_pct_above_25": round(adx_gt25, 3),
        "lag1_autocorr": round(lag1_ac, 4),
        "efficiency_ratio_20": round(_efficiency_ratio(c, 20), 3),
        "wick_ratio_mean": round(wick_mean, 3),
        "extreme_wick_pct": round(extreme_wick_pct, 3),
        "tail_3sigma_pct": round(tail_3s, 4),
        "taker_buy_ratio": round(taker_buy_ratio, 4),
        "sweep_behavior": sweeps,
        "breakout_honesty": breakouts,
        "key_ema_memory": key_emas,
        "squeeze_accumulation": squeeze,
        "volume_climax": climax,
    }


def _synthesize_whale_diagnosis(
    anchor: dict[str, Any],
    session_info: dict[str, Any],
    regime: str,
    wick_risk: str,
) -> dict[str, Any]:
    """Synthesize concrete Chinese trader insights, taboos, and playbook ranking."""
    sw = anchor.get("sweep_behavior", {})
    bo = anchor.get("breakout_honesty", {})
    emas = anchor.get("key_ema_memory", {})
    sq = anchor.get("squeeze_accumulation", {})
    clx = anchor.get("volume_climax", {})

    bull_win = float(sw.get("bull_rebound_win_rate", 0.0))
    bear_win = float(sw.get("bear_dump_win_rate", 0.0))
    bull_cnt = int(sw.get("bull_sweep_count", 0))
    bear_cnt = int(sw.get("bear_sweep_count", 0))
    trap_rate = float(bo.get("trap_rate", 0.0))
    cont_rate = float(bo.get("continuation_rate", 0.0))
    hv_cont = float(bo.get("high_vol_continuation_rate", 0.0))
    lv_cont = float(bo.get("low_vol_continuation_rate", 0.0))

    sup_ema = int(emas.get("best_support_ema", 55))
    sup_rate = float(emas.get("best_support_rate", 0.0))
    res_ema = int(emas.get("best_resistance_ema", 55))
    res_rate = float(emas.get("best_resistance_rate", 0.0))

    sq_share = float(sq.get("squeeze_share_pct", 0.0))
    ign_win = float(sq.get("ignition_win_rate_8b", 0.0))
    ign_atr = float(sq.get("ignition_avg_atr_move_8b", 0.0))
    clx_wick_rev = float(clx.get("climax_wick_reversal_rate_6b", 0.0))
    clx_body_cont = float(clx.get("climax_body_continuation_rate_6b", 0.0))

    wick_mean = float(anchor.get("wick_ratio_mean", 0.0))
    tbr = float(anchor.get("taker_buy_ratio", 0.5))

    # 1) Style tags
    tags: list[str] = []
    if wick_risk == "high":
        tags.append("高频长影插针")
    if max(bull_win, bear_win) >= 0.55 and (bull_cnt + bear_cnt) >= 8:
        tags.append("插针扫损易反抽")
    if trap_rate >= 0.50:
        tags.append("假突破骗炮偏多")
    elif cont_rate >= 0.45:
        tags.append("真突破延续较好")
    if sup_rate >= 0.55:
        tags.append(f"EMA{sup_ema}多头护盘记忆")
    if res_rate >= 0.55:
        tags.append(f"EMA{res_ema}空头压制记忆")
    if ign_win >= 0.55 and int(sq.get("ignition_count", 0)) >= 4:
        tags.append("缩量吸筹放量点火")
    if clx_wick_rev >= 0.55 and int(clx.get("wick_climax_count", 0)) >= 4:
        tags.append("巨量长影易派发反转")
    if not tags:
        tags.append("常规均衡波动")

    # 2) 5 concrete Chinese bullet points
    bj_active = ", ".join(f"{h:02d}:00" for h in session_info.get("top_active_bj_hours", [])[:4]) or "-"
    bj_wick = ", ".join(f"{h:02d}:00" for h in session_info.get("wick_danger_bj_hours", [])[:3]) or "-"
    summary_lines = [
        (
            f"**插针扫损习性**：平均影线占比 `{wick_mean * 100:.1f}%`（风险 `{wick_risk}`）；"
            f"向下插针前低收回后 6 根反弹胜率 `{bull_win * 100:.1f}%`（{bull_cnt} 次），"
            f"向上诱多收回后回落胜率 `{bear_win * 100:.1f}%`（{bear_cnt} 次）。"
        ),
        (
            f"**突破真假诚实度**：20 根前高低点突破延续率 `{cont_rate * 100:.1f}%` vs 4 根内诱多/诱空骗炮率 `{trap_rate * 100:.1f}%`"
            f"（放量突破延续 `{hv_cont * 100:.1f}%` vs 缩量突破 `{lv_cont * 100:.1f}%`）。"
        ),
        (
            f"**主力均线记忆**：上升期回踩护盘表现最佳为 `EMA{sup_ema}`（6 根反弹胜率 `{sup_rate * 100:.1f}%`）；"
            f"下跌期反抽压制最明显为 `EMA{res_ema}`（6 根回落胜率 `{res_rate * 100:.1f}%`）。"
        ),
        (
            f"**吸筹点火与巨量意图**：布林缩口吸筹期占比 `{sq_share:.1f}%`，缩口放量点火后 8 根顺势胜率 `{ign_win * 100:.1f}%`"
            f"（平均波幅 `{ign_atr:.2f} ATR`）；2.5 倍巨量长影线反转率 `{clx_wick_rev * 100:.1f}%`，巨量实体顺势延续率 `{clx_body_cont * 100:.1f}%`，主动买盘占比 `{tbr * 100:.1f}%`。"
        ),
        (
            f"**主力作息（北京时间）**：{session_info.get('session_label_zh', '-')}；"
            f"成交最活跃时段 `{bj_active}`，长影插针高发时段 `{bj_wick}`。"
        ),
    ]

    # 3) Taboos
    taboos: list[str] = []
    if trap_rate >= 0.48 or lv_cont < 0.35:
        taboos.append(f"20 周期突破骗炮率 `{trap_rate * 100:.0f}%`（缩量突破延续仅 `{lv_cont * 100:.0f}%`），严禁无量追涨杀跌。")
    if wick_risk == "high":
        taboos.append(f"平均影线占比高达 `{wick_mean * 100:.0f}%`，严禁把止损贴在前低/前高 1 倍 ATR 内；重点防备北京时间 `{bj_wick}` 插针。")
    if clx_wick_rev >= 0.55 and int(clx.get("wick_climax_count", 0)) >= 4:
        taboos.append(f"2.5 倍以上巨量长影线后反转率 `{clx_wick_rev * 100:.0f}%`，遇巨量长上/下影切忌反手追单。")
    if not taboos:
        taboos.append("严格遵守底层不追仓上限与止损冷静期，不与主力单边放量结构硬扛。")

    # 4) Dynamic ranking of the 5 playbooks
    scores = {p: 0.0 for p in PLAYBOOKS}
    scores["sweep_fade"] += 1.4 * max(bull_win, bear_win) + 0.6 * trap_rate + (0.25 if wick_risk == "high" else 0.0)
    scores["ema_defense_pullback"] += 1.3 * max(sup_rate, res_rate) + (0.25 if regime == "trending" else 0.0)
    scores["squeeze_ignition"] += 1.2 * ign_win + (0.25 if sq_share >= 25.0 else 0.0) + 0.3 * hv_cont
    scores["climax_reversal"] += 1.2 * clx_wick_rev + (0.25 if regime == "mean_reverting" else 0.0) + 0.3 * trap_rate
    scores["trend_breakout"] += 1.3 * cont_rate + 0.4 * hv_cont + (0.25 if regime == "trending" else -0.15)
    recommended = [k for k, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]

    return {
        "style_tags": tags,
        "summary_lines_zh": summary_lines,
        "taboos_zh": taboos,
        "recommended_playbooks": recommended,
        "best_support_ema": sup_ema,
        "best_resistance_ema": res_ema,
    }


def build_ticker_profile(
    symbol: str,
    klines_by_tf: dict[str, pd.DataFrame],
    funding_df: pd.DataFrame | None = None,
    metrics_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    tf_profiles = {tf: profile_timeframe(df, tf) for tf, df in klines_by_tf.items()}

    finest_df = None
    for tf in ("15m", "1h", "4h", "1d"):
        if tf in klines_by_tf and len(klines_by_tf[tf]) >= 48:
            finest_df = klines_by_tf[tf]
            break
    session_info = _session_diagnostics(finest_df)

    anchor_tf = "1h" if tf_profiles.get("1h", {}).get("sufficient") else next(
        (tf for tf, p in tf_profiles.items() if p.get("sufficient")),
        next(iter(tf_profiles.keys()), None),
    )
    anchor = tf_profiles.get(anchor_tf, {}) if anchor_tf else {}

    hurst = anchor.get("hurst_rs", 0.5)
    adx_mean = anchor.get("adx_mean", 20.0)
    er = anchor.get("efficiency_ratio_20", 0.25)
    ac1 = anchor.get("lag1_autocorr", 0.0)
    kurt = anchor.get("excess_kurtosis", 0.0)
    wick_mean = anchor.get("wick_ratio_mean", 0.4)
    ann_vol = anchor.get("ann_volatility", 0.6)

    if (hurst >= 0.54 and adx_mean >= 23.0) or er >= 0.30:
        regime = "trending"
    elif hurst <= 0.47 or (ac1 <= -0.04 and adx_mean < 22.0):
        regime = "mean_reverting"
    elif kurt >= 6.0 or ann_vol >= 1.1:
        regime = "breakout_volatile"
    else:
        regime = "mixed"

    wick_risk = "high" if wick_mean >= 0.48 else ("medium" if wick_mean >= 0.36 else "low")
    whale_diag = _synthesize_whale_diagnosis(anchor, session_info, regime, wick_risk)

    funding_summary: dict[str, Any] = {"records": 0}
    if funding_df is not None and not funding_df.empty:
        fr = funding_df["last_funding_rate"].to_numpy(dtype=float)
        hrs = float(funding_df["funding_interval_hours"].median()) if "funding_interval_hours" in funding_df.columns else 8.0
        periods_per_year = 365.0 * (24.0 / max(hrs, 1.0))
        funding_summary = {
            "records": int(len(fr)),
            "interval_hours": hrs,
            "mean_rate": round(float(np.mean(fr)), 6),
            "annualized_pct": round(float(np.mean(fr) * periods_per_year * 100.0), 2),
            "positive_ratio": round(float(np.mean(fr > 0)), 3),
            "p05_rate": round(float(np.percentile(fr, 5)), 6),
            "p95_rate": round(float(np.percentile(fr, 95)), 6),
        }

    oi_summary: dict[str, Any] = {"records": 0}
    if metrics_df is not None and not metrics_df.empty and "sum_open_interest_value" in metrics_df.columns:
        oiv = metrics_df["sum_open_interest_value"].dropna().to_numpy(dtype=float)
        if len(oiv) >= 2:
            oi_summary = {
                "records": int(len(metrics_df)),
                "latest_oi_usdt": round(float(oiv[-1]), 2),
                "mean_oi_usdt": round(float(np.mean(oiv)), 2),
                "oi_change_pct": round(float(oiv[-1] / max(oiv[0], 1e-9) - 1.0), 4),
            }

    return {
        "symbol": symbol,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "anchor_timeframe": anchor_tf,
        "diagnosis": {
            "regime": regime,
            "wick_risk": wick_risk,
            "session_pattern": session_info["session_pattern"],
            "session_label_zh": session_info["session_label_zh"],
            "top_6h_volume_share": session_info["top_6h_volume_share"],
            "top_active_utc_hours": session_info["top_active_utc_hours"],
            "top_active_bj_hours": session_info["top_active_bj_hours"],
            "wick_danger_bj_hours": session_info["wick_danger_bj_hours"],
            "recommended_families": whale_diag["recommended_playbooks"],
        },
        "whale_diagnosis": whale_diag,
        "timeframes": tf_profiles,
        "funding": funding_summary,
        "open_interest": oi_summary,
    }


def format_pretty_profile(profile: dict[str, Any]) -> str:
    """Format a human-readable Chinese main-force diagnostic summary."""
    sym = profile["symbol"]
    diag = profile["diagnosis"]
    whale = profile.get("whale_diagnosis", {})
    anchor_tf = profile.get("anchor_timeframe")
    anchor = profile["timeframes"].get(anchor_tf, {})
    lines = [
        f"=== {sym} 主力行为技术体检（基准周期 {anchor_tf}） ===",
        f"体制: {diag.get('regime')} | 插针风险: {diag.get('wick_risk')} | 年化波动: {anchor.get('ann_volatility', 0) * 100:.1f}%",
        f"主力画像标签: {', '.join(whale.get('style_tags', []))}",
        f"推荐战术顺位: {' > '.join(whale.get('recommended_playbooks', []))}",
        "",
        "【六维技术拆解】",
    ]
    for item in whale.get("summary_lines_zh", []):
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("【该币种实战禁忌】")
    for t in whale.get("taboos_zh", []):
        lines.append(f"  ! {t}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile a Binance USDS-M perpetual ticker's main-force behavior.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframes", default="15m,1h,4h")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--pretty", action="store_true", help="Print human-readable Chinese summary instead of raw JSON")
    args = parser.parse_args()

    tfs = [tf.strip() for tf in args.timeframes.split(",") if tf.strip()]
    cdir = Path(args.cache_dir) if args.cache_dir else None
    klines_by_tf = {tf: fetch_klines(args.symbol, tf, args.days, cache_dir=cdir, refresh=args.refresh) for tf in tfs}
    funding = fetch_funding_rate(args.symbol, args.days, cache_dir=cdir, refresh=args.refresh)
    metrics = fetch_metrics(args.symbol, min(args.days, 30), cache_dir=cdir, refresh=args.refresh)
    profile = build_ticker_profile(args.symbol, klines_by_tf, funding, metrics)
    if args.pretty:
        print(format_pretty_profile(profile))
    else:
        print(json.dumps(profile, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
