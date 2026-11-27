#!/usr/bin/env python3
"""Ticker statistical profiling & regime diagnostics (pure NumPy/Pandas)."""

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

    # Moments
    ret_s = pd.Series(log_ret)
    skew = float(ret_s.skew()) if len(log_ret) > 10 else 0.0
    kurt = float(ret_s.kurt()) if len(log_ret) > 10 else 0.0
    lag1_ac = float(ret_s.autocorr(lag=1)) if len(log_ret) > 20 and ret_std > 1e-12 else 0.0
    if not np.isfinite(lag1_ac):
        lag1_ac = 0.0

    # ATR%
    atr14 = _calc_atr(h, l, c, 14)
    atr_pct = atr14 / np.maximum(c, 1e-12)
    atr_pct_valid = atr_pct[np.isfinite(atr_pct)]
    atr_med = float(np.median(atr_pct_valid)) if len(atr_pct_valid) else 0.0
    atr_p95 = float(np.percentile(atr_pct_valid, 95)) if len(atr_pct_valid) else 0.0

    # ADX
    adx14 = _calc_adx(h, l, c, 14)
    adx_valid = adx14[np.isfinite(adx14)]
    adx_mean = float(np.mean(adx_valid)) if len(adx_valid) else 0.0
    adx_gt25 = float(np.mean(adx_valid > 25.0)) if len(adx_valid) else 0.0

    # Wick profile
    bar_range = h - l
    valid_range = bar_range > 1e-12
    body_top = np.maximum(o, c)
    body_bot = np.minimum(o, c)
    wick = (h - body_top) + (body_bot - l)
    wick_ratio = np.where(valid_range, wick / np.where(valid_range, bar_range, 1.0), 0.0)
    wick_mean = float(np.mean(wick_ratio[valid_range])) if valid_range.any() else 0.0
    extreme_wick_pct = float(np.mean(wick_ratio[valid_range] > 0.60)) if valid_range.any() else 0.0

    # Tail 3-sigma rate
    tail_3s = float(np.mean(np.abs(log_ret - np.mean(log_ret)) > 3.0 * ret_std)) if ret_std > 1e-12 else 0.0

    # Daily volume estimate
    ms_span = max(int(df["open_time"].iloc[-1] - df["open_time"].iloc[0]), INTERVAL_MS.get(interval, 3_600_000))
    days_covered = ms_span / 86_400_000.0
    avg_daily_qvol = float(np.sum(qvol) / max(days_covered, 1.0))

    total_vol = float(np.sum(vol))
    taker_buy_ratio = float(np.sum(tbvol) / total_vol) if total_vol > 0 else 0.5

    total_return = float(c[-1] / c[0] - 1.0)
    cummax = np.maximum.accumulate(c)
    bh_mdd = float(np.min(c / cummax - 1.0))

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
    }


def _session_diagnostics(df: pd.DataFrame | None) -> dict[str, Any]:
    if df is None or len(df) < 48:
        return {"session_pattern": "unknown", "top_6h_volume_share": None, "top_active_utc_hours": []}
    work = df.copy()
    work["hour"] = pd.to_datetime(work["open_time"], unit="ms", utc=True).dt.hour
    work["abs_ret"] = work["close"].pct_change().abs().fillna(0.0)
    by_h = work.groupby("hour").agg(qvol=("quote_volume", "sum"), vola=("abs_ret", "mean"))
    total_q = float(by_h["qvol"].sum())
    if total_q <= 0:
        return {"session_pattern": "unknown", "top_6h_volume_share": None, "top_active_utc_hours": []}
    by_h["vol_share"] = by_h["qvol"] / total_q
    top6_hours = by_h.sort_values("vol_share", ascending=False).head(6)
    top6_share = float(top6_hours["vol_share"].sum())
    pattern = "session_biased" if top6_share >= 0.42 else "24x7_uniform"
    return {
        "session_pattern": pattern,
        "top_6h_volume_share": round(top6_share, 3),
        "top_active_utc_hours": [int(h) for h in top6_hours.index.tolist()],
    }


def build_ticker_profile(
    symbol: str,
    klines_by_tf: dict[str, pd.DataFrame],
    funding_df: pd.DataFrame | None = None,
    metrics_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    tf_profiles = {tf: profile_timeframe(df, tf) for tf, df in klines_by_tf.items()}

    # Choose finest non-empty TF with >= 48 bars for session analysis, and prefer 1h for regime tags
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
        recommended = ["ema_trend", "donchian_breakout", "rsi_momentum_pullback", "bb_squeeze_breakout", "bb_mean_reversion"]
    elif hurst <= 0.47 or (ac1 <= -0.04 and adx_mean < 22.0):
        regime = "mean_reverting"
        recommended = ["bb_mean_reversion", "rsi_momentum_pullback", "bb_squeeze_breakout", "ema_trend", "donchian_breakout"]
    elif kurt >= 6.0 or ann_vol >= 1.1:
        regime = "breakout_volatile"
        recommended = ["bb_squeeze_breakout", "donchian_breakout", "ema_trend", "rsi_momentum_pullback", "bb_mean_reversion"]
    else:
        regime = "mixed"
        recommended = ["ema_trend", "bb_squeeze_breakout", "donchian_breakout", "rsi_momentum_pullback", "bb_mean_reversion"]

    wick_risk = "high" if wick_mean >= 0.48 else ("medium" if wick_mean >= 0.36 else "low")

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
            "top_6h_volume_share": session_info["top_6h_volume_share"],
            "top_active_utc_hours": session_info["top_active_utc_hours"],
            "recommended_families": recommended,
        },
        "timeframes": tf_profiles,
        "funding": funding_summary,
        "open_interest": oi_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile a Binance USDS-M perpetual ticker.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframes", default="15m,1h,4h")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    tfs = [tf.strip() for tf in args.timeframes.split(",") if tf.strip()]
    cdir = Path(args.cache_dir) if args.cache_dir else None
    klines_by_tf = {tf: fetch_klines(args.symbol, tf, args.days, cache_dir=cdir, refresh=args.refresh) for tf in tfs}
    funding = fetch_funding_rate(args.symbol, args.days, cache_dir=cdir, refresh=args.refresh)
    metrics = fetch_metrics(args.symbol, min(args.days, 30), cache_dir=cdir, refresh=args.refresh)
    profile = build_ticker_profile(args.symbol, klines_by_tf, funding, metrics)
    print(json.dumps(profile, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
