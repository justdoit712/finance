"""
providers.py — 多市场 K 线数据统一适配器 (Yahoo / 东方财富 / Binance / OKX / Alpaca / CSV)。

提供统一的 ``fetch_ohlcv(...)`` 接口，将各数据源的响应标准化为:
{
    "provider": str,
    "symbol": str,
    "display_name": str,
    "currency": str,
    "exchange": str,
    "interval": str,
    "range": str,
    "resolved_range": str,
    "is_intraday": bool,
    "last_price": float,
    "prev_close": float,
    "bars": [{"time": int|str, "open": float, "high": float, "low": float, "close": float, "volume": float}, ...],
    "source": str,
}

仅依赖 Python 标准库与可选 requests（无 requests 时自动回退 urllib.request）。
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

VALID_PROVIDERS = {"yahoo", "eastmoney", "binance", "gate", "okx", "alpaca", "csv"}
VALID_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"}
INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "1h", "4h"}
VALID_RANGES = {"auto", "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}

DEFAULT_RANGE_BY_INTERVAL = {
    "1m": "1d",
    "2m": "5d",
    "5m": "5d",
    "15m": "5d",
    "30m": "5d",
    "1h": "1mo",
    "4h": "3mo",
    "1d": "1y",
    "1wk": "5y",
    "1mo": "max",
}

YAHOO_HOSTS = [
    "https://query1.finance.yahoo.com",
    "https://query2.finance.yahoo.com",
]
BINANCE_HOSTS = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
]
GATE_BASE_URL = "https://api.gateio.ws/api/v4/spot"
EASTMONEY_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
OKX_URL = "https://www.okx.com/api/v5/market/candles"

_CN_TZ = timezone(timedelta(hours=8))

# ── TTL 缓存（避免轮询触发限流） ───────────────────────────────────────────────

_CACHE_LOCK = threading.Lock()
_CACHE: dict[tuple[str, str, str, str, str], tuple[float, dict[str, Any]]] = {}
_QUOTE_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 3.0


def _http_get_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 12,
) -> dict[str, Any] | list[Any]:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if requests is not None:
        resp = requests.get(url, params=params, headers=hdrs, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    qs = urllib.parse.urlencode(params or {})
    full_url = f"{url}?{qs}" if qs else url
    req = urllib.request.Request(full_url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_range(interval: str, range_str: str | None) -> str:
    if not range_str or range_str == "auto":
        return DEFAULT_RANGE_BY_INTERVAL.get(interval, "1y")
    return range_str


def _is_finite(v: Any) -> bool:
    if v is None or v == "":
        return False
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _sanitize_bars(raw_bars: list[dict[str, Any]], is_intraday: bool) -> list[dict[str, Any]]:
    """过滤缺失值、修正高低价包络、按时间严格升序排列并去重。"""
    dedup: dict[str | int, dict[str, Any]] = {}
    for row in raw_bars:
        ts = row.get("ts")
        o, h, l, c = row.get("open"), row.get("high"), row.get("low"), row.get("close")
        if ts is None or not (_is_finite(o) and _is_finite(h) and _is_finite(l) and _is_finite(c)):
            continue
        ts_int = int(ts)
        vol_raw = row.get("volume")
        vol = float(vol_raw) if _is_finite(vol_raw) and float(vol_raw) >= 0 else 0.0

        o_f, h_f, l_f, c_f = float(o), float(h), float(l), float(c)
        h_f = max(h_f, o_f, c_f)
        l_f = min(l_f, o_f, c_f)

        if is_intraday:
            time_key: str | int = ts_int
        else:
            time_key = row.get("date_str") or datetime.fromtimestamp(ts_int, tz=timezone.utc).strftime("%Y-%m-%d")

        existing = dedup.get(time_key)
        if existing is None or ts_int >= existing["_ts"]:
            dedup[time_key] = {
                "_ts": ts_int,
                "time": time_key,
                "open": round(o_f, 6),
                "high": round(h_f, 6),
                "low": round(l_f, 6),
                "close": round(c_f, 6),
                "volume": vol,
            }

    bars = sorted(dedup.values(), key=lambda x: x["_ts"])
    for b in bars:
        b.pop("_ts", None)
    return bars


# ── 标的路由解析 ──────────────────────────────────────────────────────────────

def parse_symbol(
    raw_symbol: str,
    explicit_provider: str | None = None,
    default_provider: str = "yahoo",
) -> tuple[str, str]:
    """解析 ``provider:SYMBOL`` 或根据代码特征自动推断数据源。"""
    s = raw_symbol.strip()
    if not s:
        raise ValueError("标的代码不能为空")

    # 1. 处理显式前缀 provider:SYMBOL（如 eastmoney:600519 / csv:D:\a.csv）
    if ":" in s:
        prefix, rest = s.split(":", 1)
        p_low = prefix.strip().lower()
        if p_low in VALID_PROVIDERS:
            sym_val = rest.strip() if p_low == "csv" else rest.strip().upper()
            if explicit_provider and explicit_provider not in ("", "auto"):
                return explicit_provider.lower(), sym_val
            return p_low, sym_val

    if explicit_provider and explicit_provider not in ("", "auto"):
        p_low = explicit_provider.strip().lower()
        if p_low not in VALID_PROVIDERS:
            raise ValueError(f"不支持的数据源 '{explicit_provider}'，可选: {sorted(VALID_PROVIDERS)}")
        return p_low, s if p_low == "csv" else s.upper()

    # 2. 自动推断规则
    su = s.upper()
    if su.endswith((".SH", ".SZ", ".BJ")) or re.fullmatch(r"[0368459]\d{5}", su):
        return "eastmoney", su
    if re.fullmatch(r"[A-Z0-9]{2,10}(USDT|USDC|BTC|ETH)", su) and "-" not in su and "=" not in su:
        return "binance", su
    if re.fullmatch(r"[A-Z0-9]{2,10}-(USDT|USDC)", su):
        return "okx", su
    if "/" in su and len(su) <= 12:
        return "alpaca", su

    return default_provider, su


# ── 1. Yahoo Finance 适配器 ───────────────────────────────────────────────────

def fetch_yahoo_ohlcv(symbol: str, interval: str = "1h", range_str: str | None = "auto") -> dict[str, Any]:
    if interval == "4h":
        raise ValueError("Yahoo Finance 接口不支持 4h 周期，请选用 1h / 1d 或切换至 Binance / OKX")
    if interval not in VALID_INTERVALS:
        raise ValueError(f"Yahoo Finance 不支持周期 '{interval}'")

    resolved_range = resolve_range(interval, range_str)
    encoded_sym = urllib.parse.quote(symbol, safe="")
    data: dict[str, Any] | None = None
    last_err: Exception | None = None

    for host in YAHOO_HOSTS:
        url = f"{host}/v8/finance/chart/{encoded_sym}"
        try:
            raw = _http_get_json(
                url,
                params={"interval": interval, "range": resolved_range, "includePrePost": "false"},
            )
            if isinstance(raw, dict):
                data = raw
                break
        except Exception as exc:
            last_err = exc

    if data is None:
        raise RuntimeError(f"请求 Yahoo Finance 失败 ({symbol}): {last_err}")

    chart = data.get("chart") or {}
    if chart.get("error"):
        err_desc = chart["error"].get("description") or str(chart["error"])
        raise RuntimeError(f"Yahoo Finance 返回错误 ({symbol}): {err_desc}")

    results = chart.get("result") or []
    if not results:
        raise RuntimeError(f"Yahoo Finance 未返回 {symbol} 的数据")

    res = results[0]
    meta = res.get("meta") or {}
    timestamps = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0] or {}
    opens, highs, lows, closes, volumes = (
        q.get("open") or [],
        q.get("high") or [],
        q.get("low") or [],
        q.get("close") or [],
        q.get("volume") or [],
    )

    raw_bars = [
        {
            "ts": ts,
            "open": opens[i] if i < len(opens) else None,
            "high": highs[i] if i < len(highs) else None,
            "low": lows[i] if i < len(lows) else None,
            "close": closes[i] if i < len(closes) else None,
            "volume": volumes[i] if i < len(volumes) else 0,
        }
        for i, ts in enumerate(timestamps)
    ]

    is_intraday = interval in INTRADAY_INTERVALS
    bars = _sanitize_bars(raw_bars, is_intraday=is_intraday)
    if not bars:
        raise RuntimeError(f"Yahoo Finance 在 {symbol} ({interval}/{resolved_range}) 下无有效 K 线")

    reg_price = meta.get("regularMarketPrice")
    last_price = float(reg_price) if _is_finite(reg_price) else bars[-1]["close"]
    prev_raw = meta.get("chartPreviousClose") or meta.get("previousClose")
    prev_close = float(prev_raw) if _is_finite(prev_raw) else bars[0]["open"]

    display_name = meta.get("shortName") or meta.get("longName") or meta.get("symbol", symbol)
    return {
        "provider": "yahoo",
        "symbol": meta.get("symbol", symbol),
        "display_name": display_name,
        "currency": meta.get("currency", "USD"),
        "exchange": meta.get("exchangeName", ""),
        "interval": interval,
        "range": range_str or "auto",
        "resolved_range": resolved_range,
        "is_intraday": is_intraday,
        "last_price": last_price,
        "prev_close": prev_close,
        "bars": bars,
        "source": "yahoo",
    }


# ── 2. 东方财富 Eastmoney 适配器（A股 / 港股） ─────────────────────────────────

_EM_KLT_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "1d": "101",
    "1wk": "102",
    "1mo": "103",
}

_EM_RANGE_LMT = {
    "1d": 240,
    "5d": 300,
    "1mo": 240,
    "3mo": 300,
    "6mo": 300,
    "1y": 300,
    "2y": 520,
    "5y": 1250,
    "10y": 2500,
    "ytd": 260,
    "max": 2500,
}


def _to_eastmoney_secid(symbol: str) -> tuple[str, str, str, str]:
    """将常见 A股/港股代码转为东方财富 secid，返回 (secid, clean_code, currency, exchange)。"""
    s = symbol.strip().upper()
    if re.fullmatch(r"\d+\.\w+", s):
        mkt, code = s.split(".", 1)
        if mkt == "116":
            return s, code, "HKD", "HKEX"
        if mkt == "1":
            return s, code, "CNY", "SSE"
        if mkt == "0":
            return s, code, "CNY", "SZSE"
        return s, code, "USD", "EM"

    if s.endswith(".HK"):
        code = s[:-3].zfill(5)
        return f"116.{code}", code, "HKD", "HKEX"

    if s.endswith((".SH", ".SS")):
        code = s.rsplit(".", 1)[0]
        return f"1.{code}", code, "CNY", "SSE"

    if s.endswith(".SZ"):
        code = s[:-3]
        return f"0.{code}", code, "CNY", "SZSE"

    if s.endswith(".BJ"):
        code = s[:-3]
        return f"0.{code}", code, "CNY", "BSE"

    if re.fullmatch(r"\d{6}", s):
        if s.startswith(("5", "6", "9")):
            return f"1.{s}", s, "CNY", "SSE"
        return f"0.{s}", s, "CNY", "SZSE"

    if re.fullmatch(r"\d{4,5}", s):
        code = s.zfill(5)
        return f"116.{code}", code, "HKD", "HKEX"

    raise ValueError(f"东方财富适配器无法识别代码 '{symbol}'，请使用如 600519、600519.SH、300750.SZ 或 00700.HK")


def fetch_eastmoney_ohlcv(
    symbol: str,
    interval: str = "1d",
    range_str: str | None = "auto",
    adjust: str = "qfq",
) -> dict[str, Any]:
    if interval not in _EM_KLT_MAP:
        raise ValueError(f"东方财富接口不支持周期 '{interval}'，可选: {sorted(_EM_KLT_MAP)}")

    secid, clean_code, currency, exchange = _to_eastmoney_secid(symbol)
    resolved_range = resolve_range(interval, range_str)
    lmt = _EM_RANGE_LMT.get(resolved_range, 260)
    fqt_map = {"none": "0", "qfq": "1", "hfq": "2"}
    fqt = fqt_map.get(adjust, "1")

    raw = _http_get_json(
        EASTMONEY_URL,
        params={
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "klt": _EM_KLT_MAP[interval],
            "fqt": fqt,
            "end": "20500101",
            "lmt": str(lmt),
        },
    )
    if not isinstance(raw, dict) or not raw.get("data"):
        raise RuntimeError(f"东方财富未返回 {symbol} (secid={secid}) 的数据")

    d = raw["data"]
    klines = d.get("klines") or []
    is_intraday = interval in INTRADAY_INTERVALS
    raw_bars: list[dict[str, Any]] = []

    for line in klines:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        dt_str = parts[0].strip()
        # f51=date, f52=open, f53=close, f54=high, f55=low, f56=volume
        if len(dt_str) > 10:
            dt = datetime.strptime(dt_str[:16], "%Y-%m-%d %H:%M").replace(tzinfo=_CN_TZ)
            ts = int(dt.timestamp())
            date_str = dt.strftime("%Y-%m-%d")
        else:
            dt = datetime.strptime(dt_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            ts = int(dt.timestamp())
            date_str = dt_str[:10]

        raw_bars.append(
            {
                "ts": ts,
                "date_str": date_str,
                "open": parts[1],
                "close": parts[2],
                "high": parts[3],
                "low": parts[4],
                "volume": parts[5],
            }
        )

    bars = _sanitize_bars(raw_bars, is_intraday=is_intraday)
    if not bars:
        raise RuntimeError(f"东方财富在 {symbol} ({interval}) 下无有效 K 线")

    pre_k = d.get("preKPrice")
    prev_close = float(pre_k) if _is_finite(pre_k) and float(pre_k) > 0 else bars[0]["open"]
    name = d.get("name") or clean_code

    return {
        "provider": "eastmoney",
        "symbol": symbol.upper(),
        "display_name": f"{name} ({clean_code})",
        "currency": currency,
        "exchange": exchange,
        "interval": interval,
        "range": range_str or "auto",
        "resolved_range": resolved_range,
        "is_intraday": is_intraday,
        "last_price": bars[-1]["close"],
        "prev_close": prev_close,
        "bars": bars,
        "source": f"eastmoney({adjust})",
    }


# ── 3. Binance 适配器（加密货币 / 黄金代币 PAXGUSDT） ─────────────────────────

_BN_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1wk": "1w",
    "1mo": "1M",
}

_CRYPTO_LIMIT_MAP = {
    "1d": 288,
    "5d": 300,
    "1mo": 400,
    "3mo": 500,
    "6mo": 600,
    "1y": 500,
    "2y": 730,
    "5y": 1000,
    "max": 1000,
}


def _is_http_4xx(exc: Exception) -> bool:
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) is not None:
        return 400 <= int(resp.status_code) < 500
    code = getattr(exc, "code", None)
    return code is not None and 400 <= int(code) < 500


def _binance_get_json(path: str, params: dict[str, Any], timeout: int = 6) -> dict[str, Any] | list[Any]:
    """优先使用 data-api.binance.vision（遇瞬时 SSL 断流自动重试，遇 4xx 立即终止不等待死节点）。"""
    attempts = [
        ("https://data-api.binance.vision", timeout, None),
        ("https://data-api.binance.vision", timeout, {"Connection": "close"}),
        ("https://data-api.binance.vision", timeout, {"Connection": "close"}),
        ("https://api.binance.com", 4, {"Connection": "close"}),
    ]
    primary_err: Exception | None = None
    for idx, (host, t_sec, extra_hdrs) in enumerate(attempts):
        try:
            return _http_get_json(f"{host}{path}", params=params, headers=extra_hdrs, timeout=t_sec)
        except Exception as exc:
            if primary_err is None:
                primary_err = exc
            if _is_http_4xx(exc):
                raise
            if idx < len(attempts) - 1:
                time.sleep(0.15)
    raise RuntimeError(str(primary_err))


def fetch_binance_ohlcv(symbol: str, interval: str = "1h", range_str: str | None = "auto") -> dict[str, Any]:
    if interval not in _BN_INTERVAL_MAP:
        raise ValueError(f"Binance 不支持周期 '{interval}'，可选: {sorted(_BN_INTERVAL_MAP)}")

    sym = symbol.replace("-", "").replace("/", "").upper()
    resolved_range = resolve_range(interval, range_str)
    limit = min(_CRYPTO_LIMIT_MAP.get(resolved_range, 300), 1000)

    try:
        raw = _binance_get_json(
            "/api/v3/klines",
            params={"symbol": sym, "interval": _BN_INTERVAL_MAP[interval], "limit": limit},
        )
    except Exception as exc:
        raise RuntimeError(f"请求 Binance 失败 ({sym}): {exc}") from exc

    if not isinstance(raw, list):
        raise RuntimeError(f"Binance 返回格式异常 ({sym})")
    rows = raw

    is_intraday = interval in INTRADAY_INTERVALS
    raw_bars = [
        {
            "ts": int(r[0]) // 1000,
            "open": r[1],
            "high": r[2],
            "low": r[3],
            "close": r[4],
            "volume": r[5],
        }
        for r in rows
        if isinstance(r, list) and len(r) >= 6
    ]
    bars = _sanitize_bars(raw_bars, is_intraday=is_intraday)
    if not bars:
        raise RuntimeError(f"Binance 未返回 {sym} 的有效 K 线")

    currency = "USDT" if sym.endswith("USDT") else ("USDC" if sym.endswith("USDC") else "USD")
    return {
        "provider": "binance",
        "symbol": sym,
        "display_name": sym,
        "currency": currency,
        "exchange": "BINANCE",
        "interval": interval,
        "range": range_str or "auto",
        "resolved_range": resolved_range,
        "is_intraday": is_intraday,
        "last_price": bars[-1]["close"],
        "prev_close": bars[0]["open"],
        "bars": bars,
        "source": "binance",
    }


# ── 3b. Gate.io Spot 适配器（长尾山寨与主流现货） ─────────────────────────────

_GATE_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1wk": "7d",
    "1mo": "30d",
}


def _to_gate_pair(symbol: str) -> str:
    """将 TAUSDT / TA-USDT / TA/USDT / TA_USDT 统一标准化为 Gate.io 交易对格式 TA_USDT。"""
    s = symbol.strip().upper().replace("-", "_").replace("/", "_")
    if "_" in s:
        parts = [p for p in s.split("_") if p]
        if len(parts) == 2:
            return f"{parts[0]}_{parts[1]}"
        raise ValueError(f"Gate.io 交易对格式无效: {symbol}")
    for quote in ("USDT", "USDC", "BTC", "ETH"):
        if s.endswith(quote) and len(s) > len(quote):
            return f"{s[:-len(quote)]}_{quote}"
    raise ValueError(f"Gate.io 无法解析交易对 '{symbol}'，请使用如 TA_USDT 或 TAUSDT")


def fetch_gate_ohlcv(symbol: str, interval: str = "1h", range_str: str | None = "auto") -> dict[str, Any]:
    if interval not in _GATE_INTERVAL_MAP:
        raise ValueError(f"Gate.io 不支持周期 '{interval}'，可选: {sorted(_GATE_INTERVAL_MAP)}")

    pair = _to_gate_pair(symbol)
    resolved_range = resolve_range(interval, range_str)
    limit = min(_CRYPTO_LIMIT_MAP.get(resolved_range, 300), 500)

    raw = _http_get_json(
        f"{GATE_BASE_URL}/candlesticks",
        params={"currency_pair": pair, "interval": _GATE_INTERVAL_MAP[interval], "limit": limit},
    )
    if not isinstance(raw, list):
        raise RuntimeError(f"Gate.io 返回格式异常 ({pair}): {raw}")

    is_intraday = interval in INTRADAY_INTERVALS
    raw_bars: list[dict[str, Any]] = []
    for r in raw:
        if not isinstance(r, list) or len(r) < 6:
            continue
        vol_val = r[6] if len(r) >= 7 and _is_finite(r[6]) else r[1]
        raw_bars.append(
            {
                "ts": int(r[0]),
                "quote_vol": r[1],
                "close": r[2],
                "high": r[3],
                "low": r[4],
                "open": r[5],
                "volume": vol_val,
            }
        )

    bars = _sanitize_bars(raw_bars, is_intraday=is_intraday)
    if not bars:
        raise RuntimeError(f"Gate.io 未返回 {pair} 的有效 K 线")

    last_price = bars[-1]["close"]
    prev_close = bars[0]["open"]
    high_24h: float | None = None
    low_24h: float | None = None
    quote_vol_24h: float | None = None

    try:
        tk_raw = _http_get_json(f"{GATE_BASE_URL}/tickers", params={"currency_pair": pair}, timeout=6)
        if isinstance(tk_raw, list) and tk_raw:
            tk = tk_raw[0]
            if _is_finite(tk.get("last")):
                last_price = float(tk["last"])
            if _is_finite(tk.get("change_percentage")):
                pct = float(tk["change_percentage"])
                if 1.0 + pct / 100.0 > 0:
                    prev_close = last_price / (1.0 + pct / 100.0)
            if _is_finite(tk.get("high_24h")):
                high_24h = float(tk["high_24h"])
            if _is_finite(tk.get("low_24h")):
                low_24h = float(tk["low_24h"])
            if _is_finite(tk.get("quote_volume")):
                quote_vol_24h = float(tk["quote_volume"])
    except Exception:
        pass

    currency = pair.split("_")[-1] if "_" in pair else "USDT"
    res: dict[str, Any] = {
        "provider": "gate",
        "symbol": pair,
        "display_name": pair.replace("_", "/"),
        "currency": currency,
        "exchange": "GATE",
        "interval": interval,
        "range": range_str or "auto",
        "resolved_range": resolved_range,
        "is_intraday": is_intraday,
        "last_price": last_price,
        "prev_close": prev_close,
        "bars": bars,
        "source": "gate",
    }
    if high_24h is not None:
        res["high_24h"] = high_24h
    if low_24h is not None:
        res["low_24h"] = low_24h
    if quote_vol_24h is not None:
        res["quote_volume_24h"] = quote_vol_24h
    return res


# ── 4. OKX 适配器（加密货币 / 黄金代币 XAUT-USDT） ────────────────────────────

_OKX_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "4h": "4H",
    "1d": "1D",
    "1wk": "1W",
    "1mo": "1M",
}


def fetch_okx_ohlcv(symbol: str, interval: str = "1h", range_str: str | None = "auto") -> dict[str, Any]:
    if interval not in _OKX_INTERVAL_MAP:
        raise ValueError(f"OKX 不支持周期 '{interval}'，可选: {sorted(_OKX_INTERVAL_MAP)}")

    inst_id = symbol.replace("/", "-").upper()
    if "-" not in inst_id and inst_id.endswith(("USDT", "USDC")):
        quote = "USDT" if inst_id.endswith("USDT") else "USDC"
        inst_id = f"{inst_id[:-len(quote)]}-{quote}"

    resolved_range = resolve_range(interval, range_str)
    limit = min(_CRYPTO_LIMIT_MAP.get(resolved_range, 240), 300)

    raw = _http_get_json(
        OKX_URL,
        params={"instId": inst_id, "bar": _OKX_INTERVAL_MAP[interval], "limit": limit},
    )
    if not isinstance(raw, dict) or raw.get("code") != "0":
        msg = raw.get("msg") if isinstance(raw, dict) else str(raw)
        raise RuntimeError(f"OKX 返回错误 ({inst_id}): {msg}")

    rows = raw.get("data") or []
    is_intraday = interval in INTRADAY_INTERVALS
    raw_bars = [
        {
            "ts": int(r[0]) // 1000,
            "open": r[1],
            "high": r[2],
            "low": r[3],
            "close": r[4],
            "volume": r[5],
        }
        for r in rows
        if isinstance(r, list) and len(r) >= 6
    ]
    bars = _sanitize_bars(raw_bars, is_intraday=is_intraday)
    if not bars:
        raise RuntimeError(f"OKX 未返回 {inst_id} 的有效 K 线")

    currency = inst_id.split("-")[-1] if "-" in inst_id else "USDT"
    return {
        "provider": "okx",
        "symbol": inst_id,
        "display_name": inst_id,
        "currency": currency,
        "exchange": "OKX",
        "interval": interval,
        "range": range_str or "auto",
        "resolved_range": resolved_range,
        "is_intraday": is_intraday,
        "last_price": bars[-1]["close"],
        "prev_close": bars[0]["open"],
        "bars": bars,
        "source": "okx",
    }


# ── 5. Alpaca 适配器（美股 / 加密，需环境变量 Key） ────────────────────────────

_ALPACA_TF_MAP = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "30m": "30Min",
    "1h": "1Hour",
    "4h": "4Hour",
    "1d": "1Day",
    "1wk": "1Week",
    "1mo": "1Month",
}


def fetch_alpaca_ohlcv(symbol: str, interval: str = "1h", range_str: str | None = "auto") -> dict[str, Any]:
    api_key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
    secret_key = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
    if not api_key or not secret_key:
        raise ValueError("Alpaca 数据源需要设置环境变量 ALPACA_API_KEY 与 ALPACA_SECRET_KEY")
    if interval not in _ALPACA_TF_MAP:
        raise ValueError(f"Alpaca 不支持周期 '{interval}'，可选: {sorted(_ALPACA_TF_MAP)}")

    resolved_range = resolve_range(interval, range_str)
    tf = _ALPACA_TF_MAP[interval]
    hdrs = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
    sym = symbol.upper()

    if "/" in sym:
        url = "https://data.alpaca.markets/v1beta3/crypto/us/bars"
        raw = _http_get_json(url, params={"symbols": sym, "timeframe": tf, "limit": 500}, headers=hdrs)
        bar_list = ((raw.get("bars") or {}) if isinstance(raw, dict) else {}).get(sym, [])
    else:
        url = f"https://data.alpaca.markets/v2/stocks/{urllib.parse.quote(sym)}/bars"
        raw = _http_get_json(url, params={"timeframe": tf, "limit": 500, "adjustment": "split"}, headers=hdrs)
        bar_list = (raw.get("bars") or []) if isinstance(raw, dict) else []

    is_intraday = interval in INTRADAY_INTERVALS
    raw_bars = []
    for b in bar_list:
        dt = datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        raw_bars.append(
            {
                "ts": int(dt.timestamp()),
                "open": b.get("o"),
                "high": b.get("h"),
                "low": b.get("l"),
                "close": b.get("c"),
                "volume": b.get("v", 0),
            }
        )
    bars = _sanitize_bars(raw_bars, is_intraday=is_intraday)
    if not bars:
        raise RuntimeError(f"Alpaca 未返回 {sym} 的有效 K 线")

    return {
        "provider": "alpaca",
        "symbol": sym,
        "display_name": sym,
        "currency": "USD",
        "exchange": "ALPACA",
        "interval": interval,
        "range": range_str or "auto",
        "resolved_range": resolved_range,
        "is_intraday": is_intraday,
        "last_price": bars[-1]["close"],
        "prev_close": bars[0]["open"],
        "bars": bars,
        "source": "alpaca",
    }


# ── 6. 本地 CSV 适配器 ────────────────────────────────────────────────────────

def _parse_datetime_token(token: str) -> tuple[int, str, bool]:
    s = token.strip()
    if s.isdigit():
        ts = int(s)
        if ts > 10_000_000_000:
            ts //= 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return ts, dt.strftime("%Y-%m-%d"), True

    for fmt, has_time in (
        ("%Y-%m-%d %H:%M:%S", True),
        ("%Y-%m-%d %H:%M", True),
        ("%Y-%m-%dT%H:%M:%S", True),
        ("%Y-%m-%dT%H:%M:%SZ", True),
        ("%Y/%m/%d %H:%M:%S", True),
        ("%Y-%m-%d", False),
        ("%Y/%m/%d", False),
    ):
        try:
            dt = datetime.strptime(s[:19] if "T" in s and s.endswith("Z") else s, fmt)
            dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp()), dt.strftime("%Y-%m-%d"), has_time
        except ValueError:
            continue

    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    has_time = not (dt.hour == 0 and dt.minute == 0 and dt.second == 0 and len(s) <= 10)
    return int(dt.timestamp()), dt.strftime("%Y-%m-%d"), has_time


def load_csv_ohlcv(csv_path: str, symbol: str | None = None) -> dict[str, Any]:
    """从本地 CSV 读取 OHLCV 行情，兼容大小写列名与可选 Volume/Date 列。"""
    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")

    with open(p, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV 文件为空或缺少表头: {csv_path}")
        col_map = {c.strip().lower(): c for c in reader.fieldnames}

        date_col = next((col_map[k] for k in ("date", "datetime", "timestamp", "time") if k in col_map), None)
        open_col = col_map.get("open")
        high_col = col_map.get("high")
        low_col = col_map.get("low")
        close_col = col_map.get("close") or col_map.get("adjclose") or col_map.get("price")
        vol_col = col_map.get("volume") or col_map.get("vol")
        ticker_col = col_map.get("ticker") or col_map.get("symbol")

        if not close_col:
            raise ValueError(f"CSV 缺少 Close 收盘价列，当前列: {reader.fieldnames}")

        raw_bars: list[dict[str, Any]] = []
        any_intraday = False
        inferred_sym = symbol

        for idx, row in enumerate(reader):
            c_val = row.get(close_col)
            if not _is_finite(c_val):
                continue
            c_num = float(c_val)  # type: ignore[arg-type]
            o_num = float(row[open_col]) if open_col and _is_finite(row.get(open_col)) else c_num
            h_num = float(row[high_col]) if high_col and _is_finite(row.get(high_col)) else max(o_num, c_num)
            l_num = float(row[low_col]) if low_col and _is_finite(row.get(low_col)) else min(o_num, c_num)
            v_num = float(row[vol_col]) if vol_col and _is_finite(row.get(vol_col)) else 0.0

            if not inferred_sym and ticker_col and row.get(ticker_col):
                inferred_sym = row[ticker_col].strip()

            if date_col and row.get(date_col):
                ts, date_str, has_time = _parse_datetime_token(row[date_col])
                any_intraday = any_intraday or has_time
            else:
                ts = 1704067200 + idx * 86400
                date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

            raw_bars.append(
                {
                    "ts": ts,
                    "date_str": date_str,
                    "open": o_num,
                    "high": h_num,
                    "low": l_num,
                    "close": c_num,
                    "volume": v_num,
                }
            )

    bars = _sanitize_bars(raw_bars, is_intraday=any_intraday)
    if not bars:
        raise ValueError(f"CSV 中未解析出有效 OHLCV K 线: {csv_path}")

    sym_name = (inferred_sym or p.stem).upper()
    return {
        "provider": "csv",
        "symbol": sym_name,
        "display_name": sym_name,
        "currency": "USD",
        "exchange": "CSV",
        "interval": "intraday" if any_intraday else "1d",
        "range": "csv",
        "resolved_range": "csv",
        "is_intraday": any_intraday,
        "last_price": bars[-1]["close"],
        "prev_close": bars[0]["open"],
        "bars": bars,
        "source": "csv",
    }


# ── 统一调度入口 ──────────────────────────────────────────────────────────────

def _has_explicit_prefix(symbol_spec: str) -> bool:
    if ":" not in symbol_spec:
        return False
    prefix = symbol_spec.split(":", 1)[0].strip().lower()
    return prefix in VALID_PROVIDERS


def fetch_ohlcv(
    symbol_spec: str,
    interval: str = "1h",
    range_str: str | None = "auto",
    provider: str | None = None,
    default_provider: str = "yahoo",
    adjust: str = "qfq",
    use_cache: bool = True,
) -> dict[str, Any]:
    """统一多源拉取入口，支持 ``provider:SYMBOL``、自动路由、Binance→Gate 自动回退与 3 秒内存缓存。"""
    if interval not in VALID_INTERVALS:
        raise ValueError(f"不支持的周期 '{interval}'，可选: {sorted(VALID_INTERVALS)}")

    has_prefix = _has_explicit_prefix(symbol_spec.strip())
    prov, sym = parse_symbol(symbol_spec, explicit_provider=provider, default_provider=default_provider)
    resolved_range = resolve_range(interval, range_str)
    cache_key = (prov, sym, interval, resolved_range, adjust)
    now = time.time()

    if use_cache and prov != "csv":
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

    if prov == "yahoo":
        result = fetch_yahoo_ohlcv(sym, interval=interval, range_str=range_str)
    elif prov == "eastmoney":
        result = fetch_eastmoney_ohlcv(sym, interval=interval, range_str=range_str, adjust=adjust)
    elif prov == "binance":
        allow_fallback = (not has_prefix) and (not provider or provider == "auto")
        try:
            result = fetch_binance_ohlcv(sym, interval=interval, range_str=range_str)
        except Exception:
            if not allow_fallback:
                raise
            result = fetch_gate_ohlcv(sym, interval=interval, range_str=range_str)
            result["source"] = "gate(auto)"
    elif prov == "gate":
        result = fetch_gate_ohlcv(sym, interval=interval, range_str=range_str)
    elif prov == "okx":
        result = fetch_okx_ohlcv(sym, interval=interval, range_str=range_str)
    elif prov == "alpaca":
        result = fetch_alpaca_ohlcv(sym, interval=interval, range_str=range_str)
    elif prov == "csv":
        result = load_csv_ohlcv(sym)
    else:
        raise ValueError(f"未知数据源: {prov}")

    if use_cache and prov != "csv":
        with _CACHE_LOCK:
            _CACHE[cache_key] = (now, result)

    return result


# ── 轻量级实时报价与自选批量接口 ──────────────────────────────────────────────

def _fetch_binance_quote(sym: str) -> dict[str, Any]:
    clean = sym.replace("-", "").replace("/", "").upper()
    try:
        raw = _binance_get_json("/api/v3/ticker/24hr", params={"symbol": clean}, timeout=6)
    except Exception as exc:
        raise RuntimeError(f"Binance 报价拉取失败 ({clean}): {exc}") from exc
    if isinstance(raw, dict) and _is_finite(raw.get("lastPrice")):
        last_p = float(raw["lastPrice"])
        chg_pct = float(raw.get("priceChangePercent") or 0.0)
        return {
            "provider": "binance",
            "symbol": clean,
            "display_name": clean,
            "currency": "USDT" if clean.endswith("USDT") else "USD",
            "last_price": last_p,
            "change_pct": round(chg_pct, 2),
            "high_24h": float(raw["highPrice"]) if _is_finite(raw.get("highPrice")) else None,
            "low_24h": float(raw["lowPrice"]) if _is_finite(raw.get("lowPrice")) else None,
            "quote_volume_24h": float(raw["quoteVolume"]) if _is_finite(raw.get("quoteVolume")) else None,
        }
    raise RuntimeError(f"Binance 未返回 {clean} 报价")


def _fetch_gate_quote(sym: str) -> dict[str, Any]:
    pair = _to_gate_pair(sym)
    raw = _http_get_json(f"{GATE_BASE_URL}/tickers", params={"currency_pair": pair}, timeout=6)
    if not isinstance(raw, list) or not raw or not _is_finite(raw[0].get("last")):
        raise RuntimeError(f"Gate.io 未返回 {pair} 报价")
    tk = raw[0]
    return {
        "provider": "gate",
        "symbol": pair,
        "display_name": pair.replace("_", "/"),
        "currency": pair.split("_")[-1] if "_" in pair else "USDT",
        "last_price": float(tk["last"]),
        "change_pct": round(float(tk.get("change_percentage") or 0.0), 2),
        "high_24h": float(tk["high_24h"]) if _is_finite(tk.get("high_24h")) else None,
        "low_24h": float(tk["low_24h"]) if _is_finite(tk.get("low_24h")) else None,
        "quote_volume_24h": float(tk["quote_volume"]) if _is_finite(tk.get("quote_volume")) else None,
    }


def _fetch_okx_quote(sym: str) -> dict[str, Any]:
    inst_id = sym.replace("/", "-").upper()
    if "-" not in inst_id and inst_id.endswith(("USDT", "USDC")):
        q = "USDT" if inst_id.endswith("USDT") else "USDC"
        inst_id = f"{inst_id[:-len(q)]}-{q}"
    raw = _http_get_json("https://www.okx.com/api/v5/market/ticker", params={"instId": inst_id}, timeout=6)
    if not isinstance(raw, dict) or raw.get("code") != "0" or not raw.get("data"):
        raise RuntimeError(f"OKX 报价拉取失败 ({inst_id})")
    tk = raw["data"][0]
    last_p = float(tk["last"])
    open_24 = float(tk["open24h"]) if _is_finite(tk.get("open24h")) else last_p
    chg_pct = ((last_p - open_24) / open_24 * 100.0) if open_24 else 0.0
    return {
        "provider": "okx",
        "symbol": inst_id,
        "display_name": inst_id,
        "currency": inst_id.split("-")[-1] if "-" in inst_id else "USDT",
        "last_price": last_p,
        "change_pct": round(chg_pct, 2),
        "high_24h": float(tk["high24h"]) if _is_finite(tk.get("high24h")) else None,
        "low_24h": float(tk["low24h"]) if _is_finite(tk.get("low24h")) else None,
        "quote_volume_24h": float(tk["volCcy24h"]) if _is_finite(tk.get("volCcy24h")) else None,
    }


def _fetch_yahoo_quote(sym: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(sym, safe="")
    last_err: Exception | None = None
    for host in YAHOO_HOSTS:
        try:
            raw = _http_get_json(f"{host}/v8/finance/chart/{encoded}", params={"interval": "1d", "range": "5d"}, timeout=8)
            res = ((raw.get("chart") or {}).get("result") or [None])[0] if isinstance(raw, dict) else None
            if not res:
                continue
            meta = res.get("meta") or {}
            last_p = meta.get("regularMarketPrice")
            if not _is_finite(last_p):
                continue
            last_f = float(last_p)
            prev_raw = meta.get("chartPreviousClose") or meta.get("previousClose")
            prev_f = float(prev_raw) if _is_finite(prev_raw) and float(prev_raw) > 0 else last_f
            chg_pct = ((last_f - prev_f) / prev_f * 100.0) if prev_f else 0.0
            return {
                "provider": "yahoo",
                "symbol": meta.get("symbol", sym),
                "display_name": meta.get("shortName") or meta.get("symbol", sym),
                "currency": meta.get("currency", "USD"),
                "last_price": last_f,
                "change_pct": round(chg_pct, 2),
                "high_24h": float(meta["regularMarketDayHigh"]) if _is_finite(meta.get("regularMarketDayHigh")) else None,
                "low_24h": float(meta["regularMarketDayLow"]) if _is_finite(meta.get("regularMarketDayLow")) else None,
                "quote_volume_24h": None,
            }
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Yahoo 报价拉取失败 ({sym}): {last_err}")


def fetch_quote(
    symbol_spec: str,
    provider: str | None = None,
    default_provider: str = "binance",
    use_cache: bool = True,
) -> dict[str, Any]:
    """拉取单个标的的轻量级实时报价与 24h 涨跌幅（支持 3 秒缓存与 Binance→Gate 自动回退）。"""
    spec = symbol_spec.strip()
    has_prefix = _has_explicit_prefix(spec)
    prov, sym = parse_symbol(spec, explicit_provider=provider, default_provider=default_provider)
    cache_key = (prov, sym)
    now = time.time()

    if use_cache:
        with _CACHE_LOCK:
            cached = _QUOTE_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

    if prov == "binance":
        allow_fallback = (not has_prefix) and (not provider or provider == "auto")
        try:
            q = _fetch_binance_quote(sym)
        except Exception:
            if not allow_fallback:
                raise
            q = _fetch_gate_quote(sym)
    elif prov == "gate":
        q = _fetch_gate_quote(sym)
    elif prov == "okx":
        q = _fetch_okx_quote(sym)
    elif prov == "yahoo":
        q = _fetch_yahoo_quote(sym)
    else:
        ohlcv = fetch_ohlcv(spec, interval="1d", range_str="5d", provider=provider, default_provider=default_provider, use_cache=use_cache)
        last_p = float(ohlcv["last_price"])
        prev_p = float(ohlcv["prev_close"]) or last_p
        q = {
            "provider": ohlcv["provider"],
            "symbol": ohlcv["symbol"],
            "display_name": ohlcv.get("display_name", ohlcv["symbol"]),
            "currency": ohlcv.get("currency", "USD"),
            "last_price": last_p,
            "change_pct": round(((last_p - prev_p) / prev_p * 100.0) if prev_p else 0.0, 2),
            "high_24h": None,
            "low_24h": None,
            "quote_volume_24h": None,
        }

    q["symbol_spec"] = spec
    q["resolved_spec"] = f"{q['provider']}:{q['symbol']}"
    if use_cache:
        with _CACHE_LOCK:
            _QUOTE_CACHE[cache_key] = (now, q)
    return q


def fetch_quotes_batch(
    items: list[dict[str, str] | str],
    default_provider: str = "binance",
) -> list[dict[str, Any]]:
    """并发批量拉取自选列表实时报价，保持输入顺序，单个标的异常不阻断其余标的。"""
    normalized: list[tuple[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            spec = str(item.get("symbol", "")).strip()
            label = str(item.get("label") or spec).strip()
        else:
            spec = str(item).strip()
            label = spec
        if spec:
            normalized.append((spec, label))

    if not normalized:
        return []

    results: list[dict[str, Any] | None] = [None] * len(normalized)

    def _worker(idx: int, spec: str, label: str) -> tuple[int, dict[str, Any]]:
        try:
            q = fetch_quote(spec, default_provider=default_provider)
            q = dict(q)
            q["label"] = label
            return idx, q
        except Exception as exc:
            return idx, {
                "symbol_spec": spec,
                "label": label,
                "error": str(exc),
            }

    with ThreadPoolExecutor(max_workers=min(8, len(normalized))) as pool:
        futures = [pool.submit(_worker, i, spec, label) for i, (spec, label) in enumerate(normalized)]
        for fut in as_completed(futures):
            idx, data = fut.result()
            results[idx] = data

    return [r for r in results if r is not None]
