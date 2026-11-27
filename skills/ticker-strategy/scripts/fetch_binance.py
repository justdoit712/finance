#!/usr/bin/env python3
"""Fetch Binance USDS-M perpetual klines, funding rates, and open-interest metrics.

Primary bulk source: https://data.binance.vision/data/futures/um/
Optional best-effort tail supplement: https://fapi.binance.com/fapi/v1/klines
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import threading
import time
import zipfile

import pandas as pd
import requests

VISION_UM_BASE = "https://data.binance.vision/data/futures/um"
FAPI_BASE = "https://fapi.binance.com"

_THREAD_LOCAL = threading.local()

KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
]

OUTPUT_KLINE_COLUMNS = [
    "open_time",
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
]

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


def _make_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"User-Agent": "CryptoQuant-TickerStrategy/1.0"})
        _THREAD_LOCAL.session = session
    return session


def _download_zip_csv(url: str, timeout: int = 15) -> pd.DataFrame | None:
    session = _make_session()
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                return None
            with zf.open(names[0]) as fh:
                raw = fh.read()
        if not raw.strip():
            return None
        first_line = raw.splitlines()[0].decode("utf-8", errors="ignore").lower()
        has_header = "open_time" in first_line or "calc_time" in first_line or "create_time" in first_line
        buf = io.BytesIO(raw)
        return pd.read_csv(buf, header=0 if has_header else None)
    except requests.RequestException:
        return None
    except zipfile.BadZipFile:
        return None


def _normalize_kline_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=OUTPUT_KLINE_COLUMNS)

    if list(df.columns[:5]) == KLINE_COLUMNS[:5]:
        work = df.copy()
    else:
        work = df.iloc[:, : len(KLINE_COLUMNS)].copy()
        work.columns = KLINE_COLUMNS[: work.shape[1]]

    for col in [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]:
        if col not in work.columns:
            work[col] = 0.0
        work[col] = pd.to_numeric(work[col], errors="coerce")

    work = work.dropna(subset=["open_time", "open", "high", "low", "close"]).copy()
    if work.empty:
        return pd.DataFrame(columns=OUTPUT_KLINE_COLUMNS)

    # Guard against microsecond timestamps if any appear
    open_time = work["open_time"].astype("int64")
    open_time = open_time.where(open_time < 10**14, open_time // 1000)
    work["open_time"] = open_time
    work["count"] = work["count"].fillna(0).astype("int64")
    work["datetime"] = pd.to_datetime(work["open_time"], unit="ms", utc=True)

    work = work[OUTPUT_KLINE_COLUMNS]
    work = work.drop_duplicates(subset=["open_time"], keep="last").sort_values("open_time")
    return work.reset_index(drop=True)


def _iter_months(start_dt: datetime, end_dt: datetime) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    cur_y, cur_m = start_dt.year, start_dt.month
    while (cur_y, cur_m) <= (end_dt.year, end_dt.month):
        months.append((cur_y, cur_m))
        if cur_m == 12:
            cur_y += 1
            cur_m = 1
        else:
            cur_m += 1
    return months


def _month_date_range(year: int, month: int) -> tuple[datetime, datetime]:
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        next_first = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_first = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return first, next_first - timedelta(days=1)


def _fetch_fapi_tail(symbol: str, interval: str, start_ms: int | None) -> pd.DataFrame:
    params: dict[str, str | int] = {"symbol": symbol, "interval": interval, "limit": 500}
    if start_ms is not None:
        params["startTime"] = int(start_ms)
    try:
        resp = requests.get(f"{FAPI_BASE}/fapi/v1/klines", params=params, timeout=3)
        if resp.status_code != 200:
            return pd.DataFrame(columns=OUTPUT_KLINE_COLUMNS)
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            return pd.DataFrame(columns=OUTPUT_KLINE_COLUMNS)
        raw_df = pd.DataFrame(rows)
        return _normalize_kline_df(raw_df)
    except Exception:
        return pd.DataFrame(columns=OUTPUT_KLINE_COLUMNS)


def _cache_is_fresh(path: Path, max_age_hours: float = 12.0) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    age_sec = time.time() - path.stat().st_mtime
    return age_sec < max_age_hours * 3600.0


def fetch_klines(
    symbol: str,
    interval: str = "1h",
    days: int = 180,
    cache_dir: Path | str | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch Binance UM futures klines from data.binance.vision (+ best-effort fapi tail)."""
    symbol = symbol.strip().upper()
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {interval}")

    cache_path: Path | None = None
    if cache_dir is not None:
        cdir = Path(cache_dir)
        cdir.mkdir(parents=True, exist_ok=True)
        cache_path = cdir / f"{symbol}_{interval}_{days}d.csv"
        if not refresh and _cache_is_fresh(cache_path):
            cached = pd.read_csv(cache_path)
            if not cached.empty:
                cached["open_time"] = cached["open_time"].astype("int64")
                cached["datetime"] = pd.to_datetime(cached["open_time"], unit="ms", utc=True)
                return cached

    now_utc = datetime.now(timezone.utc)
    yesterday = (now_utc - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    start_dt = (now_utc - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(start_dt.timestamp() * 1000)

    months = _iter_months(start_dt, yesterday)
    current_ym = (now_utc.year, now_utc.month)

    frames: list[pd.DataFrame] = []
    daily_dates: list[datetime] = []

    past_months = [ym for ym in months if ym < current_ym]
    if past_months:
        month_urls = {
            ym: f"{VISION_UM_BASE}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{ym[0]:04d}-{ym[1]:02d}.zip"
            for ym in past_months
        }
        with ThreadPoolExecutor(max_workers=6) as pool:
            fut_map = {pool.submit(_download_zip_csv, url): ym for ym, url in month_urls.items()}
            for fut in as_completed(fut_map):
                ym = fut_map[fut]
                raw = fut.result()
                if raw is not None and not raw.empty:
                    frames.append(_normalize_kline_df(raw))
                else:
                    m_start, m_end = _month_date_range(*ym)
                    d = max(m_start, start_dt)
                    end_clamp = min(m_end, yesterday)
                    while d <= end_clamp:
                        daily_dates.append(d)
                        d += timedelta(days=1)

    if current_ym in months:
        m_start, m_end = _month_date_range(*current_ym)
        d = max(m_start, start_dt)
        end_clamp = min(m_end, yesterday)
        while d <= end_clamp:
            daily_dates.append(d)
            d += timedelta(days=1)

    if daily_dates:
        daily_dates = sorted(set(daily_dates))
        daily_urls = [
            f"{VISION_UM_BASE}/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{d.strftime('%Y-%m-%d')}.zip"
            for d in daily_dates
        ]
        with ThreadPoolExecutor(max_workers=10) as pool:
            for raw in pool.map(_download_zip_csv, daily_urls):
                if raw is not None and not raw.empty:
                    frames.append(_normalize_kline_df(raw))

    if frames:
        df = pd.concat(frames, ignore_index=True)
        df = df.drop_duplicates(subset=["open_time"], keep="last").sort_values("open_time")
        df = df[df["open_time"] >= start_ms].reset_index(drop=True)
    else:
        df = pd.DataFrame(columns=OUTPUT_KLINE_COLUMNS)

    # Best-effort tail supplement from fapi
    tail_start = int(df["open_time"].max()) + INTERVAL_MS[interval] if not df.empty else start_ms
    tail_df = _fetch_fapi_tail(symbol, interval, tail_start)
    if not tail_df.empty:
        df = pd.concat([df, tail_df], ignore_index=True)
        df = df.drop_duplicates(subset=["open_time"], keep="last").sort_values("open_time")
        df = df[df["open_time"] >= start_ms].reset_index(drop=True)

    if cache_path is not None and not df.empty:
        df.to_csv(cache_path, index=False)

    return df


def fetch_funding_rate(
    symbol: str,
    days: int = 180,
    cache_dir: Path | str | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch historical 8h/4h funding rates from data.binance.vision."""
    symbol = symbol.strip().upper()
    cols = ["calc_time", "datetime", "funding_interval_hours", "last_funding_rate"]

    cache_path: Path | None = None
    if cache_dir is not None:
        cdir = Path(cache_dir)
        cdir.mkdir(parents=True, exist_ok=True)
        cache_path = cdir / f"{symbol}_funding_{days}d.csv"
        if not refresh and _cache_is_fresh(cache_path, max_age_hours=24.0):
            cached = pd.read_csv(cache_path)
            if not cached.empty:
                cached["calc_time"] = cached["calc_time"].astype("int64")
                cached["datetime"] = pd.to_datetime(cached["calc_time"], unit="ms", utc=True)
                return cached

    now_utc = datetime.now(timezone.utc)
    start_dt = (now_utc - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(start_dt.timestamp() * 1000)
    months = _iter_months(start_dt, now_utc)
    urls = [
        f"{VISION_UM_BASE}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{y:04d}-{m:02d}.zip"
        for y, m in months
    ]

    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for raw in pool.map(_download_zip_csv, urls):
            if raw is not None and not raw.empty and "calc_time" in raw.columns:
                frames.append(raw)

    if not frames:
        return pd.DataFrame(columns=cols)

    df = pd.concat(frames, ignore_index=True)
    df["calc_time"] = pd.to_numeric(df["calc_time"], errors="coerce")
    df["funding_interval_hours"] = pd.to_numeric(df.get("funding_interval_hours", 8), errors="coerce").fillna(8)
    df["last_funding_rate"] = pd.to_numeric(df["last_funding_rate"], errors="coerce")
    df = df.dropna(subset=["calc_time", "last_funding_rate"]).copy()
    df["calc_time"] = df["calc_time"].astype("int64")
    df = df[df["calc_time"] >= start_ms]
    df["datetime"] = pd.to_datetime(df["calc_time"], unit="ms", utc=True)
    df = df[cols].drop_duplicates(subset=["calc_time"], keep="last").sort_values("calc_time").reset_index(drop=True)

    if cache_path is not None and not df.empty:
        df.to_csv(cache_path, index=False)
    return df


def fetch_metrics(
    symbol: str,
    days: int = 30,
    cache_dir: Path | str | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch recent daily UM open interest & trader ratio metrics from data.binance.vision."""
    symbol = symbol.strip().upper()
    days = min(int(days), 45)
    cols = [
        "create_time",
        "sum_open_interest",
        "sum_open_interest_value",
        "count_toptrader_long_short_ratio",
        "sum_toptrader_long_short_ratio",
        "count_long_short_ratio",
        "sum_taker_long_short_vol_ratio",
    ]

    cache_path: Path | None = None
    if cache_dir is not None:
        cdir = Path(cache_dir)
        cdir.mkdir(parents=True, exist_ok=True)
        cache_path = cdir / f"{symbol}_metrics_{days}d.csv"
        if not refresh and _cache_is_fresh(cache_path, max_age_hours=24.0):
            cached = pd.read_csv(cache_path)
            if not cached.empty:
                return cached

    now_utc = datetime.now(timezone.utc)
    yesterday = (now_utc - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    urls = [
        f"{VISION_UM_BASE}/daily/metrics/{symbol}/{symbol}-metrics-{(yesterday - timedelta(days=i)).strftime('%Y-%m-%d')}.zip"
        for i in range(days)
    ]

    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for raw in pool.map(_download_zip_csv, urls):
            if raw is not None and not raw.empty and "create_time" in raw.columns:
                frames.append(raw)

    if not frames:
        return pd.DataFrame(columns=cols)

    df = pd.concat(frames, ignore_index=True)
    for col in cols[1:]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = float("nan")
    df = df[cols].drop_duplicates(subset=["create_time"], keep="last").sort_values("create_time").reset_index(drop=True)

    if cache_path is not None and not df.empty:
        df.to_csv(cache_path, index=False)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Binance UM futures data from Binance Vision.")
    parser.add_argument("--symbol", required=True, help="Symbol e.g. ETHUSDT, NIOUSDT")
    parser.add_argument("--interval", default="1h", help="Kline interval (15m, 1h, 4h, 1d)")
    parser.add_argument("--days", type=int, default=180, help="Lookback days")
    parser.add_argument("--cache-dir", default=None, help="Optional cache directory")
    parser.add_argument("--refresh", action="store_true", help="Force refresh bypassing local cache")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    klines = fetch_klines(args.symbol, args.interval, args.days, cache_dir=cache_dir, refresh=args.refresh)
    funding = fetch_funding_rate(args.symbol, args.days, cache_dir=cache_dir, refresh=args.refresh)
    metrics = fetch_metrics(args.symbol, min(args.days, 30), cache_dir=cache_dir, refresh=args.refresh)

    print(
        f"{args.symbol.upper()} {args.interval}: {len(klines)} bars"
        + (f" ({klines['datetime'].iloc[0]} .. {klines['datetime'].iloc[-1]})" if not klines.empty else "")
    )
    print(f"Funding records: {len(funding)} | Metrics records: {len(metrics)}")


if __name__ == "__main__":
    main()
