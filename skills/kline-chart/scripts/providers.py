"""
providers.py — 国际黄金与白银现货、COMEX 期货多源统一适配器。

提供统一的 ``fetch_ohlcv(...)`` 接口，覆盖：
  - 国际现货：伦敦金 (``XAUUSD``)、伦敦银 (``XAGUSD``) — 经由实时行情流直连（USD 计价）
  - COMEX 期货：黄金主连 (``GC=F`` / ``GC00Y``)、白银主连 (``SI=F`` / ``SI00Y``)、
    微型期货 (``MGC=F`` / ``SIL=F``)、具体月份合约 (``GCZ26.CMX`` / ``GCG27.CMX`` / ``SIH27.CMX``)
  - 国际 ETF 与矿业股：``GLD``、``SLV``、``IAU``、``GDX``、``GDXJ``、``SIL``、``NEM``
  - 24h 链上锚定黄金：``PAXGUSDT`` (Binance)、``XAUT-USDT`` (OKX)
  - 可选辅助：国内沪金/沪银期货 (``SHFE:AU`` / ``SHFE:AG``)、国内黄金 ETF (``518880``) 与本地 CSV

仅依赖 Python 标准库与可选 requests（无 requests 时自动回退 urllib.request）。
"""
from __future__ import annotations

import csv
import json
import math
import re
import threading
import time
import urllib.parse
import urllib.request
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

VALID_PROVIDERS = {"yahoo", "eastmoney", "binance", "okx", "ratio", "csv"}
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
EASTMONEY_URLS = [
    "http://push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
]
OKX_URL = "https://www.okx.com/api/v5/market/candles"

_CN_TZ = timezone(timedelta(hours=8))

# 国际现货 & 期货实时行情别名映射 -> (secid, clean_code, currency, exchange)
_INTL_EM_ALIASES: dict[str, tuple[str, str, str, str]] = {
    "XAUUSD": ("122.XAU", "XAUUSD", "USD", "SPOT"),
    "XAUUSD=X": ("122.XAU", "XAUUSD", "USD", "SPOT"),
    "XAU": ("122.XAU", "XAUUSD", "USD", "SPOT"),
    "SPOT:XAU": ("122.XAU", "XAUUSD", "USD", "SPOT"),
    "XAGUSD": ("122.XAG", "XAGUSD", "USD", "SPOT"),
    "XAGUSD=X": ("122.XAG", "XAGUSD", "USD", "SPOT"),
    "XAG": ("122.XAG", "XAGUSD", "USD", "SPOT"),
    "SPOT:XAG": ("122.XAG", "XAGUSD", "USD", "SPOT"),
    "GC00Y": ("101.GC00Y", "GC00Y", "USD", "COMEX"),
    "COMEX:GC": ("101.GC00Y", "GC00Y", "USD", "COMEX"),
    "SI00Y": ("101.SI00Y", "SI00Y", "USD", "COMEX"),
    "COMEX:SI": ("101.SI00Y", "SI00Y", "USD", "COMEX"),
    "SHFE:AU": ("113.aum", "AU0", "CNY", "SHFE"),
    "AUM": ("113.aum", "AU0", "CNY", "SHFE"),
    "AU0": ("113.aum", "AU0", "CNY", "SHFE"),
    "SHFE:AG": ("113.agm", "AG0", "CNY", "SHFE"),
    "AGM": ("113.agm", "AG0", "CNY", "SHFE"),
    "AG0": ("113.agm", "AG0", "CNY", "SHFE"),
}

_SPOT_YAHOO_FALLBACK_SET = {"XAUUSD", "XAUUSD=X", "XAU", "XAGUSD", "XAGUSD=X", "XAG"}

_INTL_DISPLAY_NAMES = {
    "122.XAU": "伦敦金现货 (XAUUSD)",
    "122.XAG": "伦敦银现货 (XAGUSD)",
    "101.GC00Y": "COMEX 黄金连续 (GC00Y)",
    "101.SI00Y": "COMEX 白银连续 (SI00Y)",
}

# ── TTL 缓存（避免轮询触发限流） ───────────────────────────────────────────────

_CACHE_LOCK = threading.Lock()
_CACHE: dict[tuple[str, str, str, str, str], tuple[float, dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 3.0
_GSR_HIST_CACHE: tuple[float, list[float]] | None = None
_GSR_HIST_TTL_SECONDS = 60.0


def _http_get_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 12,
    direct: bool = False,
) -> dict[str, Any] | list[Any]:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json", "Connection": "close"}
    if headers:
        hdrs.update(headers)
    if requests is not None:
        attempts = [False] if direct else [True, False]
        last_exc: Exception | None = None
        for trust_env in attempts:
            try:
                with requests.Session() as sess:
                    sess.trust_env = trust_env
                    resp = sess.get(url, params=params, headers=hdrs, timeout=timeout)
                    resp.raise_for_status()
                    return resp.json()
            except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError) as exc:
                last_exc = exc
                continue
        if last_exc is not None:
            raise last_exc
    qs = urllib.parse.urlencode(params or {})
    full_url = f"{url}?{qs}" if qs else url
    req = urllib.request.Request(full_url, headers=hdrs)
    if direct:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
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
    """解析 ``provider:SYMBOL`` 或根据贵金属代码特征自动路由数据源。

    路由优先级:
        - ``XAUUSD`` / ``XAUUSD=X`` / ``XAGUSD`` / ``XAGUSD=X`` / ``SPOT:XAU`` -> ``eastmoney`` (122.XAU/XAG，避免 Yahoo 404)
        - ``GC00Y`` / ``SI00Y`` / ``COMEX:GC`` / ``COMEX:SI`` / ``SHFE:AU`` / ``SHFE:AG`` -> ``eastmoney``
        - ``GC=F`` / ``SI=F`` / ``MGC=F`` / ``SIL=F`` / ``*.CMX`` / ``GLD`` / ``SLV`` / ``GDX`` -> ``yahoo``
        - ``PAXGUSDT`` -> ``binance``; ``XAUT-USDT`` -> ``okx``
    """
    s = raw_symbol.strip()
    if not s:
        raise ValueError("标的代码不能为空")

    su = s.upper()
    if su in ("GSR", "XAU/XAG", "XAUXAG", "RATIO:GSR"):
        return "ratio", "GSR"

    if su in _INTL_EM_ALIASES:
        # 避免 Yahoo Finance 对 XAUUSD=X / XAGUSD=X 返回 404
        if explicit_provider and explicit_provider.lower() not in ("", "auto", "yahoo"):
            return explicit_provider.lower(), su
        return "eastmoney", su

    if ":" in s:
        prefix, rest = s.split(":", 1)
        p_low = prefix.strip().lower()
        if p_low in VALID_PROVIDERS:
            sym_val = rest.strip() if p_low == "csv" else rest.strip().upper()
            if p_low == "yahoo" and sym_val in _SPOT_YAHOO_FALLBACK_SET:
                return "eastmoney", sym_val
            if explicit_provider and explicit_provider not in ("", "auto"):
                ep = explicit_provider.lower()
                if ep == "yahoo" and sym_val in _SPOT_YAHOO_FALLBACK_SET:
                    return "eastmoney", sym_val
                return ep, sym_val
            return p_low, sym_val

    if explicit_provider and explicit_provider not in ("", "auto"):
        p_low = explicit_provider.strip().lower()
        if p_low not in VALID_PROVIDERS:
            raise ValueError(f"不支持的数据源 '{explicit_provider}'，可选: {sorted(VALID_PROVIDERS)}")
        if p_low == "yahoo" and su in _SPOT_YAHOO_FALLBACK_SET:
            return "eastmoney", su
        return p_low, s if p_low == "csv" else su

    if re.fullmatch(r"(101|113|122)\.\w+", su):
        return "eastmoney", s
    if su.endswith((".SH", ".SZ", ".BJ")) or re.fullmatch(r"[013568]\d{5}", su):
        return "eastmoney", su
    if re.fullmatch(r"[A-Z0-9]{2,10}(USDT|USDC)", su) and "-" not in su and "=" not in su:
        return "binance", su
    if re.fullmatch(r"[A-Z0-9]{2,10}-(USDT|USDC)", su):
        return "okx", su

    return default_provider, su


# ── 1. Yahoo Finance 适配器（COMEX 主连/微型/月度期货与国际 ETF） ──────────────

def fetch_yahoo_ohlcv(symbol: str, interval: str = "1h", range_str: str | None = "auto") -> dict[str, Any]:
    if interval == "4h":
        raise ValueError("Yahoo Finance 接口不支持 4h 周期，请选用 1h / 1d 或切换至 Binance / OKX 24h 锚定金")
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


# ── 2. 国际现货 / COMEX 连续实时适配器（Eastmoney 国际市场行情流） ──────────────

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
    """将国际现货/期货别名或市场代码转为东方财富 secid，返回 (secid, clean_code, currency, exchange)。"""
    raw = symbol.strip()
    su = raw.upper()

    if su in _INTL_EM_ALIASES:
        return _INTL_EM_ALIASES[su]

    if re.fullmatch(r"\d+\.\w+", raw):
        mkt, code = raw.split(".", 1)
        if mkt == "101":
            return raw, code.upper(), "USD", "COMEX"
        if mkt == "122":
            return raw, code.upper(), "USD", "SPOT"
        if mkt == "113":
            return raw, code.upper(), "CNY", "SHFE"
        if mkt == "116":
            return raw, code, "HKD", "HKEX"
        if mkt == "1":
            return raw, code, "CNY", "SSE"
        if mkt == "0":
            return raw, code, "CNY", "SZSE"
        return raw, code, "USD", "EM"

    if su.endswith(".HK"):
        code = su[:-3].zfill(5)
        return f"116.{code}", code, "HKD", "HKEX"

    if su.endswith((".SH", ".SS")):
        code = su.rsplit(".", 1)[0]
        return f"1.{code}", code, "CNY", "SSE"

    if su.endswith(".SZ"):
        code = su[:-3]
        return f"0.{code}", code, "CNY", "SZSE"

    if su.endswith(".BJ"):
        code = su[:-3]
        return f"0.{code}", code, "CNY", "BSE"

    if re.fullmatch(r"\d{6}", su):
        if su.startswith(("5", "6", "9")):
            return f"1.{su}", su, "CNY", "SSE"
        return f"0.{su}", su, "CNY", "SZSE"

    raise ValueError(
        f"无法识别代码 '{symbol}'，国际现货请用 XAUUSD / XAGUSD，COMEX 连续请用 GC00Y / SI00Y / GC=F / SI=F"
    )


def fetch_eastmoney_ohlcv(
    symbol: str,
    interval: str = "1h",
    range_str: str | None = "auto",
    adjust: str = "qfq",
) -> dict[str, Any]:
    if interval not in _EM_KLT_MAP:
        raise ValueError(f"国际现货/期货实时接口不支持周期 '{interval}'，可选: {sorted(_EM_KLT_MAP)}")

    secid, clean_code, currency, exchange = _to_eastmoney_secid(symbol)
    mkt = secid.split(".", 1)[0]
    is_spot_or_fut = mkt in ("101", "122", "113")

    resolved_range = resolve_range(interval, range_str)
    lmt = _EM_RANGE_LMT.get(resolved_range, 260)
    fqt = "0" if is_spot_or_fut else {"none": "0", "qfq": "1", "hfq": "2"}.get(adjust, "1")

    raw: dict[str, Any] | list[Any] | None = None
    last_err: Exception | None = None
    em_params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "klt": _EM_KLT_MAP[interval],
        "fqt": fqt,
        "end": "20500101",
        "lmt": str(lmt),
    }
    em_headers = {"Referer": "https://quote.eastmoney.com/", "Accept": "*/*"}
    for em_url in EASTMONEY_URLS:
        try:
            raw = _http_get_json(em_url, params=em_params, headers=em_headers, direct=True)
            if isinstance(raw, dict) and raw.get("data"):
                break
        except Exception as exc:
            last_err = exc
    if raw is None and last_err is not None:
        raise RuntimeError(f"请求国际现货/期货行情失败 ({symbol}): {last_err}")
    if not isinstance(raw, dict) or not raw.get("data"):
        raise RuntimeError(f"未获取到 {symbol} (secid={secid}) 的行情数据")

    d = raw["data"]
    klines = d.get("klines") or []
    is_intraday = interval in INTRADAY_INTERVALS
    raw_bars: list[dict[str, Any]] = []

    for line in klines:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        dt_str = parts[0].strip()
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
        raise RuntimeError(f"{symbol} ({interval}) 下无有效 K 线")

    pre_k = d.get("preKPrice")
    prev_close = float(pre_k) if _is_finite(pre_k) and float(pre_k) > 0 else bars[0]["open"]
    name = d.get("name") or clean_code
    display_name = _INTL_DISPLAY_NAMES.get(secid, f"{name} ({clean_code})")

    return {
        "provider": "eastmoney",
        "symbol": clean_code,
        "display_name": display_name,
        "currency": currency,
        "exchange": exchange,
        "interval": interval,
        "range": range_str or "auto",
        "resolved_range": resolved_range,
        "is_intraday": is_intraday,
        "last_price": bars[-1]["close"],
        "prev_close": prev_close,
        "bars": bars,
        "source": f"eastmoney({exchange})" if is_spot_or_fut else f"eastmoney({adjust})",
    }


# ── 3. Binance 适配器（24h 链上锚定黄金代币 PAXGUSDT） ────────────────────────

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

_TOKEN_LIMIT_MAP = {
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


def fetch_binance_ohlcv(symbol: str, interval: str = "1h", range_str: str | None = "auto") -> dict[str, Any]:
    if interval not in _BN_INTERVAL_MAP:
        raise ValueError(f"Binance 不支持周期 '{interval}'，可选: {sorted(_BN_INTERVAL_MAP)}")

    sym = symbol.replace("-", "").replace("/", "").upper()
    resolved_range = resolve_range(interval, range_str)
    limit = min(_TOKEN_LIMIT_MAP.get(resolved_range, 300), 1000)

    rows: list[Any] | None = None
    last_err: Exception | None = None
    for host in BINANCE_HOSTS:
        try:
            raw = _http_get_json(
                f"{host}/api/v3/klines",
                params={"symbol": sym, "interval": _BN_INTERVAL_MAP[interval], "limit": limit},
            )
            if isinstance(raw, list):
                rows = raw
                break
        except Exception as exc:
            last_err = exc

    if rows is None:
        raise RuntimeError(f"请求 Binance 失败 ({sym}): {last_err}")

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
        "display_name": f"{sym} (24h 锚定金)" if sym.startswith("PAXG") else sym,
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


# ── 4. OKX 适配器（24h 链上锚定黄金代币 XAUT-USDT） ───────────────────────────

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
    limit = min(_TOKEN_LIMIT_MAP.get(resolved_range, 240), 300)

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
        "display_name": f"{inst_id} (24h 锚定金)" if inst_id.startswith("XAUT") else inst_id,
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


# ── 5. 本地 CSV 适配器 ────────────────────────────────────────────────────────

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


# ── 5.5 金银比 (GSR) 合成序列与实时统计 ───────────────────────────────────────

def fetch_gsr_ohlcv(interval: str = "1h", range_str: str | None = "auto") -> dict[str, Any]:
    """基于伦敦金 (XAUUSD) 与伦敦银 (XAGUSD) 对齐时间戳合成金银比 K 线序列。"""
    xau = fetch_eastmoney_ohlcv("XAUUSD", interval=interval, range_str=range_str)
    xag = fetch_eastmoney_ohlcv("XAGUSD", interval=interval, range_str=range_str)

    ag_map = {b["time"]: b for b in xag["bars"]}
    bars: list[dict[str, Any]] = []
    for au in xau["bars"]:
        ag = ag_map.get(au["time"])
        if not ag:
            continue
        if ag["open"] <= 0 or ag["high"] <= 0 or ag["low"] <= 0 or ag["close"] <= 0:
            continue
        o = au["open"] / ag["open"]
        c = au["close"] / ag["close"]
        r_hi = au["high"] / ag["high"]
        r_lo = au["low"] / ag["low"]
        bars.append(
            {
                "time": au["time"],
                "open": round(o, 4),
                "high": round(max(o, c, r_hi, r_lo), 4),
                "low": round(min(o, c, r_hi, r_lo), 4),
                "close": round(c, 4),
                "volume": 0.0,
            }
        )

    if not bars:
        raise RuntimeError(f"GSR 在周期={interval} 下无有效对齐 K 线")

    last_price = (xau["last_price"] / xag["last_price"]) if xag["last_price"] > 0 else bars[-1]["close"]
    prev_close = (xau["prev_close"] / xag["prev_close"]) if xag["prev_close"] > 0 else bars[0]["open"]

    return {
        "provider": "ratio",
        "symbol": "GSR",
        "display_name": "金银比 GSR (XAU/XAG)",
        "currency": "XAU/XAG",
        "exchange": "SPOT",
        "interval": interval,
        "range": range_str or "auto",
        "resolved_range": xau["resolved_range"],
        "is_intraday": xau["is_intraday"],
        "last_price": round(last_price, 4),
        "prev_close": round(prev_close, 4),
        "bars": bars,
        "source": "XAUUSD / XAGUSD",
    }


def compute_gsr_snapshot() -> dict[str, Any]:
    """计算实时现货金银比及近 1 年历史均值、分位数与 Z-Score。"""
    global _GSR_HIST_CACHE
    now = time.time()

    with _CACHE_LOCK:
        hist_cached = _GSR_HIST_CACHE
    if hist_cached and (now - hist_cached[0]) < _GSR_HIST_TTL_SECONDS:
        gsr_hist = hist_cached[1]
    else:
        xau_1y = fetch_eastmoney_ohlcv("XAUUSD", interval="1d", range_str="1y")
        xag_1y = fetch_eastmoney_ohlcv("XAGUSD", interval="1d", range_str="1y")
        au_map = {b["time"]: b["close"] for b in xau_1y["bars"]}
        ag_map = {b["time"]: b["close"] for b in xag_1y["bars"]}
        common = sorted(set(au_map) & set(ag_map))
        gsr_hist = [au_map[d] / ag_map[d] for d in common if ag_map[d] > 0]
        if gsr_hist:
            with _CACHE_LOCK:
                _GSR_HIST_CACHE = (now, gsr_hist)

    xau_live = fetch_ohlcv("XAUUSD", interval="1h", range_str="5d", use_cache=True)
    xag_live = fetch_ohlcv("XAGUSD", interval="1h", range_str="5d", use_cache=True)
    xau_px = float(xau_live["last_price"])
    xag_px = float(xag_live["last_price"])
    gsr = (xau_px / xag_px) if xag_px > 0 else 0.0

    n_1y = len(gsr_hist)
    if n_1y >= 2:
        mean_1y = sum(gsr_hist) / n_1y
        var_1y = sum((v - mean_1y) ** 2 for v in gsr_hist) / (n_1y - 1)
        std_1y = math.sqrt(var_1y)
        min_1y = min(gsr_hist)
        max_1y = max(gsr_hist)
        pct_1y = sum(1 for v in gsr_hist if v <= gsr) / n_1y * 100.0
        z_1y = ((gsr - mean_1y) / std_1y) if std_1y > 0 else 0.0
    else:
        mean_1y = gsr
        std_1y = 0.0
        min_1y = gsr
        max_1y = gsr
        pct_1y = 50.0
        z_1y = 0.0

    return {
        "gsr": round(gsr, 2),
        "xau": round(xau_px, 2),
        "xag": round(xag_px, 3),
        "mean_1y": round(mean_1y, 2),
        "std_1y": round(std_1y, 2),
        "min_1y": round(min_1y, 2),
        "max_1y": round(max_1y, 2),
        "pct_1y": round(pct_1y, 1),
        "z_1y": round(z_1y, 2),
        "n_1y": n_1y,
        "updated_at": datetime.now().strftime("%H:%M:%S"),
    }


# ── 统一调度入口 ──────────────────────────────────────────────────────────────

def fetch_ohlcv(
    symbol_spec: str,
    interval: str = "1h",
    range_str: str | None = "auto",
    provider: str | None = None,
    default_provider: str = "yahoo",
    adjust: str = "qfq",
    use_cache: bool = True,
) -> dict[str, Any]:
    """统一多源拉取入口，支持 ``provider:SYMBOL``、自动路由与 3 秒内存缓存。"""
    if interval not in VALID_INTERVALS:
        raise ValueError(f"不支持的周期 '{interval}'，可选: {sorted(VALID_INTERVALS)}")

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
        result = fetch_binance_ohlcv(sym, interval=interval, range_str=range_str)
    elif prov == "okx":
        result = fetch_okx_ohlcv(sym, interval=interval, range_str=range_str)
    elif prov == "ratio":
        result = fetch_gsr_ohlcv(interval=interval, range_str=range_str)
    elif prov == "csv":
        result = load_csv_ohlcv(sym)
    else:
        raise ValueError(f"未知数据源: {prov}")

    if use_cache and prov != "csv":
        with _CACHE_LOCK:
            _CACHE[cache_key] = (now, result)

    return result
