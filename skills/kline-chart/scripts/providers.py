"""
providers.py — 加密货币 K 线与实时行情适配器 (Gate.io Spot + 本地 CSV)。

提供统一的 ``fetch_ohlcv(...)``、``fetch_quote(...)`` 与 ``fetch_quotes_batch(...)`` 接口，
将响应标准化为 Lightweight Charts 所需格式，仅依赖 Python 标准库与可选 requests。
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
    from requests.adapters import HTTPAdapter
except ImportError:
    requests = None  # type: ignore[assignment]
    HTTPAdapter = None  # type: ignore[assignment,misc]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

VALID_PROVIDERS = {"gate", "csv"}
VALID_INTERVALS = {"5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"}
INTRADAY_INTERVALS = {"5m", "15m", "30m", "1h", "4h"}
VALID_RANGES = {"auto", "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}

DEFAULT_RANGE_BY_INTERVAL = {
    "5m": "5d",
    "15m": "5d",
    "30m": "5d",
    "1h": "1mo",
    "4h": "3mo",
    "1d": "1y",
    "1wk": "5y",
    "1mo": "max",
}

GATE_BASE_URL = "https://api.gateio.ws/api/v4/spot"

_GATE_INTERVAL_MAP = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1wk": "7d",
    "1mo": "30d",
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

_CACHE_LOCK = threading.Lock()
_CACHE: dict[tuple[str, str, str, str], tuple[float, dict[str, Any]]] = {}
_QUOTE_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_ALL_TICKERS_LOCK = threading.Lock()
_ALL_TICKERS_CACHE: tuple[float, dict[str, dict[str, Any]]] | None = None
_SESSION_LOCK = threading.Lock()
_SHARED_SESSION: Any = None
CACHE_TTL_SECONDS = 4.0


def _get_session() -> Any:
    global _SHARED_SESSION
    if requests is None:
        return None
    if _SHARED_SESSION is None:
        with _SESSION_LOCK:
            if _SHARED_SESSION is None:
                sess = requests.Session()
                sess.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
                if HTTPAdapter is not None:
                    sess.mount("https://", HTTPAdapter(pool_connections=8, pool_maxsize=16))
                _SHARED_SESSION = sess
    return _SHARED_SESSION


def _reset_session() -> None:
    global _SHARED_SESSION
    with _SESSION_LOCK:
        if _SHARED_SESSION is not None:
            try:
                _SHARED_SESSION.close()
            except Exception:
                pass
            _SHARED_SESSION = None


def _http_get_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 8,
    use_session: bool = True,
) -> dict[str, Any] | list[Any]:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if requests is not None:
        sess = _get_session() if use_session else None
        if sess is not None:
            resp = sess.get(url, params=params, headers=headers, timeout=timeout)
        else:
            resp = requests.get(url, params=params, headers=hdrs, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    qs = urllib.parse.urlencode(params or {})
    full_url = f"{url}?{qs}" if qs else url
    req = urllib.request.Request(full_url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _is_http_4xx(exc: Exception) -> bool:
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) is not None:
        return 400 <= int(resp.status_code) < 500
    code = getattr(exc, "code", None)
    return code is not None and 400 <= int(code) < 500


def _gate_get_json(path: str, params: dict[str, Any] | None = None, timeout: int = 8) -> dict[str, Any] | list[Any]:
    """优先复用 HTTP Keep-Alive 长连接请求 Gate.io；若长连接失效则重建连接重试，遇 4xx 立即报错。"""
    url = f"{GATE_BASE_URL}{path}"
    attempts = [
        (True, None),
        (True, None),
        (False, {"Connection": "close"}),
    ]
    last_err: Exception | None = None
    for idx, (use_sess, extra_hdrs) in enumerate(attempts):
        try:
            return _http_get_json(url, params=params, headers=extra_hdrs, timeout=timeout, use_session=use_sess)
        except Exception as exc:
            last_err = exc
            if _is_http_4xx(exc):
                raise
            _reset_session()
            if idx < len(attempts) - 1:
                time.sleep(0.1)
    raise RuntimeError(str(last_err))


def _get_all_gate_tickers(use_cache: bool = True) -> dict[str, dict[str, Any]]:
    """一次性拉取并缓存 Gate.io 全市场现货 24h 行情映射，大幅减少批量握手开销。"""
    global _ALL_TICKERS_CACHE
    now = time.time()
    if use_cache and _ALL_TICKERS_CACHE and (now - _ALL_TICKERS_CACHE[0]) < CACHE_TTL_SECONDS:
        return _ALL_TICKERS_CACHE[1]

    with _ALL_TICKERS_LOCK:
        now = time.time()
        if use_cache and _ALL_TICKERS_CACHE and (now - _ALL_TICKERS_CACHE[0]) < CACHE_TTL_SECONDS:
            return _ALL_TICKERS_CACHE[1]
        raw = _gate_get_json("/tickers", timeout=8)
        if not isinstance(raw, list):
            raise RuntimeError("Gate.io 全量报价返回格式异常")
        mapping: dict[str, dict[str, Any]] = {}
        for item in raw:
            if isinstance(item, dict) and item.get("currency_pair"):
                mapping[str(item["currency_pair"]).upper()] = item
        _ALL_TICKERS_CACHE = (time.time(), mapping)
        return mapping


def warmup() -> None:
    """后台预热 Gate.io HTTPS 长连接与全量行情缓存。"""
    try:
        _get_all_gate_tickers(use_cache=False)
    except Exception:
        pass


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


# ── 标的解析与交易对标准化 ────────────────────────────────────────────────────

def _to_gate_pair(symbol: str) -> str:
    """将 BTC / BTCUSDT / BTC-USDT / BTC/USDT / TA_USDT 统一转为 Gate.io 格式 XXX_USDT。"""
    s = symbol.strip()
    if ":" in s:
        _, s = s.split(":", 1)
    s = s.strip().upper().replace("-", "_").replace("/", "_")
    if not s:
        raise ValueError("标的代码不能为空")
    if "_" in s:
        parts = [p for p in s.split("_") if p]
        if len(parts) == 2:
            return f"{parts[0]}_{parts[1]}"
        raise ValueError(f"交易对格式无效: {symbol}")
    for quote in ("USDT", "USDC", "BTC", "ETH"):
        if s.endswith(quote) and len(s) > len(quote):
            return f"{s[:-len(quote)]}_{quote}"
    if re.fullmatch(r"[A-Z0-9]{1,12}", s):
        return f"{s}_USDT"
    raise ValueError(f"无法解析交易对 '{symbol}'，请使用如 BTC、BTCUSDT 或 TA_USDT")


def parse_symbol(
    raw_symbol: str,
    explicit_provider: str | None = None,
    default_provider: str = "gate",
) -> tuple[str, str]:
    """解析标的代码，在线行情统一归口到 Gate.io 现货。"""
    s = raw_symbol.strip()
    if not s:
        raise ValueError("标的代码不能为空")

    if explicit_provider and explicit_provider.lower() == "csv":
        if s.lower().startswith("csv:"):
            s = s.split(":", 1)[1].strip()
        return "csv", s

    if s.lower().startswith("csv:"):
        return "csv", s.split(":", 1)[1].strip()

    if ":" in s:
        _, rest = s.split(":", 1)
        s = rest.strip()

    return "gate", _to_gate_pair(s)


# ── Gate.io Spot 适配器 ───────────────────────────────────────────────────────

def fetch_gate_ohlcv(symbol: str, interval: str = "1h", range_str: str | None = "auto") -> dict[str, Any]:
    if interval not in _GATE_INTERVAL_MAP:
        raise ValueError(f"Gate.io 不支持周期 '{interval}'，可选: {sorted(_GATE_INTERVAL_MAP)}")

    pair = _to_gate_pair(symbol)
    resolved_range = resolve_range(interval, range_str)
    limit = min(_CRYPTO_LIMIT_MAP.get(resolved_range, 300), 1000)

    try:
        raw = _gate_get_json(
            "/candlesticks",
            params={"currency_pair": pair, "interval": _GATE_INTERVAL_MAP[interval], "limit": limit},
        )
    except Exception as exc:
        if _is_http_4xx(exc):
            raise ValueError(f"Gate.io 现货未找到交易对 {pair}") from exc
        raise RuntimeError(f"请求 Gate.io 失败 ({pair}): {exc}") from exc

    tk_raw: Any = None
    now_t = time.time()
    if _ALL_TICKERS_CACHE and (now_t - _ALL_TICKERS_CACHE[0]) < 30.0:
        hit = _ALL_TICKERS_CACHE[1].get(pair)
        if hit:
            tk_raw = [hit]
    if tk_raw is None:
        try:
            tk_raw = _http_get_json(f"{GATE_BASE_URL}/tickers", params={"currency_pair": pair}, timeout=4)
        except Exception:
            tk_raw = None

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


# ── 本地 CSV 适配器（离线导出使用） ──────────────────────────────────────────

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

def fetch_ohlcv(
    symbol_spec: str,
    interval: str = "1h",
    range_str: str | None = "auto",
    provider: str | None = None,
    default_provider: str = "gate",
    use_cache: bool = True,
) -> dict[str, Any]:
    """统一行情拉取入口（Gate.io 现货实时 + 本地 CSV，带 3 秒内存缓存）。"""
    if interval not in VALID_INTERVALS:
        raise ValueError(f"不支持的周期 '{interval}'，可选: {sorted(VALID_INTERVALS)}")

    prov, sym = parse_symbol(symbol_spec, explicit_provider=provider, default_provider=default_provider)
    resolved_range = resolve_range(interval, range_str)
    cache_key = (prov, sym, interval, resolved_range)
    now = time.time()

    if use_cache and prov != "csv":
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

    if prov == "csv":
        result = load_csv_ohlcv(sym)
    else:
        result = fetch_gate_ohlcv(sym, interval=interval, range_str=range_str)

    if use_cache and prov != "csv":
        with _CACHE_LOCK:
            _CACHE[cache_key] = (now, result)

    return result


# ── 轻量级实时报价与自选批量接口 ──────────────────────────────────────────────

def _ticker_to_quote(tk: dict[str, Any], pair: str, spec: str) -> dict[str, Any]:
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
        "symbol_spec": spec,
        "resolved_spec": f"gate:{pair}",
    }


def fetch_quote(
    symbol_spec: str,
    provider: str | None = None,
    default_provider: str = "gate",
    use_cache: bool = True,
) -> dict[str, Any]:
    """拉取单个交易对的 Gate.io 实时报价与 24h 涨跌幅（3 秒 TTL 缓存）。"""
    spec = symbol_spec.strip()
    prov, pair = parse_symbol(spec, explicit_provider=provider, default_provider=default_provider)
    if prov == "csv":
        raise ValueError("CSV 模式不支持实时报价")

    cache_key = ("gate", pair)
    now = time.time()
    if use_cache:
        with _CACHE_LOCK:
            cached = _QUOTE_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]
        if _ALL_TICKERS_CACHE and (now - _ALL_TICKERS_CACHE[0]) < CACHE_TTL_SECONDS:
            hit = _ALL_TICKERS_CACHE[1].get(pair)
            if hit and _is_finite(hit.get("last")):
                return _ticker_to_quote(hit, pair, spec)

    try:
        raw = _gate_get_json("/tickers", params={"currency_pair": pair}, timeout=6)
    except Exception as exc:
        if _is_http_4xx(exc):
            raise ValueError(f"Gate.io 现货未找到交易对 {pair}") from exc
        raise RuntimeError(f"Gate.io 报价拉取失败 ({pair}): {exc}") from exc

    if not isinstance(raw, list) or not raw or not _is_finite(raw[0].get("last")):
        raise RuntimeError(f"Gate.io 未返回 {pair} 报价")

    q = _ticker_to_quote(raw[0], pair, spec)

    if use_cache:
        with _CACHE_LOCK:
            _QUOTE_CACHE[cache_key] = (now, q)
    return q


def fetch_quotes_batch(
    items: list[dict[str, str] | str],
    default_provider: str = "gate",
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """通过单次全量缓存拉取自选列表 Gate.io 实时报价，避免并发多次握手。"""
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

    if len(normalized) > 1:
        try:
            all_tk = _get_all_gate_tickers(use_cache=use_cache)
            out: list[dict[str, Any]] = []
            for spec, label in normalized:
                try:
                    _, pair = parse_symbol(spec, default_provider=default_provider)
                    tk = all_tk.get(pair)
                    if tk and _is_finite(tk.get("last")):
                        q = _ticker_to_quote(tk, pair, spec)
                        q["label"] = label
                        out.append(q)
                    else:
                        out.append({"symbol_spec": spec, "label": label, "error": f"Gate.io 现货未找到交易对 {pair}"})
                except Exception as exc:
                    out.append({"symbol_spec": spec, "label": label, "error": str(exc)})
            return out
        except Exception:
            pass

    results: list[dict[str, Any] | None] = [None] * len(normalized)

    def _worker(idx: int, spec: str, label: str) -> tuple[int, dict[str, Any]]:
        try:
            q = dict(fetch_quote(spec, default_provider=default_provider, use_cache=use_cache))
            q["label"] = label
            return idx, q
        except Exception as exc:
            return idx, {
                "symbol_spec": spec,
                "label": label,
                "error": str(exc),
            }

    with ThreadPoolExecutor(max_workers=min(4, len(normalized))) as pool:
        futures = [pool.submit(_worker, i, spec, label) for i, (spec, label) in enumerate(normalized)]
        for fut in as_completed(futures):
            idx, data = fut.result()
            results[idx] = data

    return [r for r in results if r is not None]
