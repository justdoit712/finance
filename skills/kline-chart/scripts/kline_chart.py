"""
kline_chart.py — 全市场多源交互式 K 线看板 & 离线静态 HTML 导出器。

基于本地打包的 TradingView Lightweight Charts v4.2.3，通过 providers.py 统一支持
美股/港股/A股（Yahoo / 东方财富）、贵金属、加密货币（Binance / OKX / Alpaca）与本地 CSV。

用法:
    # 启动本地实时交互看板（默认配置从 assets/defaults.json 加载）
    python skills/kline-chart/scripts/kline_chart.py serve

    # 指定数据源与标的（A股前复权 / 加密货币 / 美股 / 贵金属）
    python skills/kline-chart/scripts/kline_chart.py serve --symbol eastmoney:600519 --interval 1d --color-scheme red_up
    python skills/kline-chart/scripts/kline_chart.py serve --symbol binance:BTCUSDT --interval 15m --refresh 5

    # 导出单文件交互式静态 HTML（内嵌 Lightweight Charts 与数据，可离线分享）
    python skills/kline-chart/scripts/kline_chart.py export --symbol yahoo:AAPL --interval 1d --range 1y -o D:/empty/aapl.html
    python skills/kline-chart/scripts/kline_chart.py export --csv data/my_ohlcv.csv -o D:/empty/local.html
"""
from __future__ import annotations

import argparse
import json
import math
import os
import queue
import sys
import threading
import urllib.parse
import webbrowser
from collections.abc import Callable
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from . import providers, ws_stream
except (ImportError, ValueError):
    import providers
    import ws_stream

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, Exception):
    pass

SKILL_DIR = SCRIPT_DIR.parent
ASSETS_DIR = SKILL_DIR / "assets"
LWC_JS_PATH = ASSETS_DIR / "lightweight-charts.standalone.production.js"
ICON_PATH = ASSETS_DIR / "crypto_client.ico"
DEFAULTS_PATH = ASSETS_DIR / "defaults.json"
WATCHLIST_PATH = Path.home() / ".crypto_quant_watchlist.json"

VALID_STRATEGIES = {
    "none",
    "sma_crossover",
    "bbands_contrarian",
    "rsi_meanrev",
    "macd_crossover",
}


def _infer_price_precision(price: float) -> int:
    ap = abs(price)
    if 0 < ap < 0.05:
        return 6
    if 0 < ap < 1.0:
        return 5
    if 0 < ap < 100.0:
        return 4
    return 2


def _normalize_watchlist_items(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        raise ValueError("symbols 必须是列表")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            sym = str(item.get("symbol", "")).strip()
            label = str(item.get("label") or sym).strip()
        else:
            sym = str(item).strip()
            label = sym
        if not sym:
            continue
        key = sym.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append({"symbol": sym, "label": label or sym})
    return out


def load_watchlist(defaults: dict[str, Any] | None = None) -> list[dict[str, str]]:
    if WATCHLIST_PATH.exists():
        try:
            raw = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
            items = _normalize_watchlist_items(raw.get("symbols") if isinstance(raw, dict) else raw)
            if items:
                return items
        except Exception:
            pass
    cfg = defaults or load_defaults()
    return _normalize_watchlist_items(cfg.get("symbols", []))


def save_watchlist(items: Any) -> list[dict[str, str]]:
    normalized = _normalize_watchlist_items(items)
    if not normalized:
        raise ValueError("自选列表不能为空")
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = WATCHLIST_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps({"symbols": normalized}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, WATCHLIST_PATH)
    return normalized


def load_defaults() -> dict[str, Any]:
    if DEFAULTS_PATH.exists():
        with open(DEFAULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "title": "全市场交互式 K 线看板",
        "default_symbol": "yahoo:SPY",
        "default_provider": "yahoo",
        "default_interval": "1d",
        "default_range": "auto",
        "default_strategy": "sma_crossover",
        "default_refresh_seconds": 15,
        "color_scheme": "green_up",
        "default_host": "127.0.0.1",
        "default_port": 8765,
        "symbols": [
            {"symbol": "yahoo:SPY", "label": "标普500"},
            {"symbol": "yahoo:AAPL", "label": "苹果"},
            {"symbol": "eastmoney:600519", "label": "贵州茅台"},
            {"symbol": "eastmoney:00700.HK", "label": "腾讯控股"},
            {"symbol": "yahoo:GC=F", "label": "COMEX黄金"},
            {"symbol": "binance:BTCUSDT", "label": "BTC/USDT"},
        ],
        "indicators": {
            "sma_fast": 20,
            "sma_slow": 60,
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_period": 14,
        },
    }


# ── 纯 Python 技术指标与策略信号计算 ───────────────────────────────────────────

def compute_sma(closes: list[float], period: int) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return out
    window_sum = sum(closes[:period])
    out[period - 1] = window_sum / period
    for i in range(period, n):
        window_sum += closes[i] - closes[i - period]
        out[i] = window_sum / period
    return out


def compute_ema(closes: list[float], period: int) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if period <= 0 or n == 0:
        return out
    alpha = 2.0 / (period + 1.0)
    ema = closes[0]
    out[0] = ema
    for i in range(1, n):
        ema = alpha * closes[i] + (1.0 - alpha) * ema
        out[i] = ema
    return out


def compute_bollinger(
    closes: list[float], period: int = 20, k: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    n = len(closes)
    mid = compute_sma(closes, period)
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return upper, mid, lower
    for i in range(period - 1, n):
        m = mid[i]
        assert m is not None
        window = closes[i - period + 1 : i + 1]
        var = sum((x - m) ** 2 for x in window) / period
        sd = math.sqrt(var)
        upper[i] = m + k * sd
        lower[i] = m - k * sd
    return upper, mid, lower


def compute_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < 2 or period <= 0:
        return out
    alpha = 1.0 / period
    ema_gain = 0.0
    ema_loss = 0.0
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gain = diff if diff > 0 else 0.0
        loss = -diff if diff < 0 else 0.0
        if i == 1:
            ema_gain = gain
            ema_loss = loss
        else:
            ema_gain = alpha * gain + (1.0 - alpha) * ema_gain
            ema_loss = alpha * loss + (1.0 - alpha) * ema_loss
        if i >= period:
            if ema_loss == 0:
                out[i] = 100.0 if ema_gain > 0 else 50.0
            else:
                rs = ema_gain / ema_loss
                out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def compute_macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float | None], list[float | None]]:
    ema_f = compute_ema(closes, fast)
    ema_s = compute_ema(closes, slow)
    n = len(closes)
    macd_vals: list[float] = []
    for i in range(n):
        f_v = ema_f[i]
        s_v = ema_s[i]
        macd_vals.append((f_v - s_v) if (f_v is not None and s_v is not None) else 0.0)
    sig_vals = compute_ema(macd_vals, signal)
    macd_out: list[float | None] = [macd_vals[i] if i >= slow - 1 else None for i in range(n)]
    sig_out: list[float | None] = [sig_vals[i] if i >= slow - 1 else None for i in range(n)]
    return macd_out, sig_out


def compute_strategy_markers(
    times: list[str | int],
    closes: list[float],
    strategy: str,
    sma_fast: int = 20,
    sma_slow: int = 60,
    bb_period: int = 20,
    bb_std: float = 2.0,
    rsi_period: int = 14,
) -> list[dict[str, Any]]:
    """计算严格交替的多头买卖点标记。"""
    if strategy not in VALID_STRATEGIES or strategy == "none":
        return []

    n = len(closes)
    if n < 3:
        return []

    raw_actions: list[str] = ["hold"] * n

    if strategy == "sma_crossover":
        sf = compute_sma(closes, sma_fast)
        ss = compute_sma(closes, sma_slow)
        prev_state: bool | None = None
        for i in range(n):
            if sf[i] is None or ss[i] is None:
                continue
            cur_state = sf[i] > ss[i]  # type: ignore[operator]
            if prev_state is not None:
                if not prev_state and cur_state:
                    raw_actions[i] = "buy"
                elif prev_state and not cur_state:
                    raw_actions[i] = "sell"
            prev_state = cur_state

    elif strategy == "bbands_contrarian":
        _, mid, lower = compute_bollinger(closes, bb_period, bb_std)
        for i in range(n):
            if mid[i] is None or lower[i] is None:
                continue
            if closes[i] < lower[i]:  # type: ignore[operator]
                raw_actions[i] = "buy"
            elif closes[i] > mid[i]:  # type: ignore[operator]
                raw_actions[i] = "sell"

    elif strategy == "rsi_meanrev":
        rsi_vals = compute_rsi(closes, rsi_period)
        for i in range(1, n):
            prev_r, cur_r = rsi_vals[i - 1], rsi_vals[i]
            if prev_r is None or cur_r is None:
                continue
            if prev_r <= 30.0 < cur_r:
                raw_actions[i] = "buy"
            elif prev_r >= 70.0 > cur_r:
                raw_actions[i] = "sell"

    elif strategy == "macd_crossover":
        macd_l, sig_l = compute_macd(closes)
        for i in range(1, n):
            pm, ps = macd_l[i - 1], sig_l[i - 1]
            cm, cs = macd_l[i], sig_l[i]
            if pm is None or ps is None or cm is None or cs is None:
                continue
            if (pm - ps) <= 0.0 < (cm - cs):
                raw_actions[i] = "buy"
            elif (pm - ps) >= 0.0 > (cm - cs):
                raw_actions[i] = "sell"

    markers: list[dict[str, Any]] = []
    in_pos = False
    for i, action in enumerate(raw_actions):
        if not in_pos and action == "buy":
            in_pos = True
            markers.append(
                {
                    "time": times[i],
                    "position": "belowBar",
                    "color": "#26a69a",
                    "shape": "arrowUp",
                    "text": "BUY",
                }
            )
        elif in_pos and action == "sell":
            in_pos = False
            markers.append(
                {
                    "time": times[i],
                    "position": "aboveBar",
                    "color": "#ef5350",
                    "shape": "arrowDown",
                    "text": "SELL",
                }
            )
    return markers


def _to_line_series(times: list[str | int], vals: list[float | None]) -> list[dict[str, Any]]:
    return [
        {"time": t, "value": round(v, 6)}
        for t, v in zip(times, vals)
        if v is not None and math.isfinite(v)
    ]


def build_kline_payload(
    raw_data: dict[str, Any],
    strategy: str = "sma_crossover",
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建前端 Lightweight Charts 所需的完整 JSON 载荷。"""
    if strategy not in VALID_STRATEGIES:
        raise ValueError(f"不支持的策略 '{strategy}'，可选: {sorted(VALID_STRATEGIES)}")

    cfg = (defaults or load_defaults()).get("indicators", {})
    sma_fast = int(cfg.get("sma_fast", 20))
    sma_slow = int(cfg.get("sma_slow", 60))
    bb_period = int(cfg.get("bb_period", 20))
    bb_std = float(cfg.get("bb_std", 2.0))
    rsi_period = int(cfg.get("rsi_period", 14))

    bars = raw_data["bars"]
    times = [b["time"] for b in bars]
    closes = [b["close"] for b in bars]

    candles = [
        {
            "time": b["time"],
            "open": b["open"],
            "high": b["high"],
            "low": b["low"],
            "close": b["close"],
        }
        for b in bars
    ]
    volume = [
        {
            "time": b["time"],
            "value": b["volume"],
            "color": "rgba(38, 166, 154, 0.45)" if b["close"] >= b["open"] else "rgba(239, 83, 80, 0.45)",
        }
        for b in bars
    ]

    sma20_vals = compute_sma(closes, sma_fast)
    sma60_vals = compute_sma(closes, sma_slow)
    bb_u, bb_m, bb_l = compute_bollinger(closes, bb_period, bb_std)
    markers = compute_strategy_markers(
        times,
        closes,
        strategy=strategy,
        sma_fast=sma_fast,
        sma_slow=sma_slow,
        bb_period=bb_period,
        bb_std=bb_std,
        rsi_period=rsi_period,
    )

    last_price = float(raw_data["last_price"])
    prev_close = float(raw_data["prev_close"])
    change = last_price - prev_close
    change_pct = (change / prev_close * 100.0) if prev_close else 0.0
    precision = _infer_price_precision(last_price)

    meta: dict[str, Any] = {
        "provider": raw_data.get("provider", "yahoo"),
        "symbol": raw_data["symbol"],
        "display_name": raw_data.get("display_name", raw_data["symbol"]),
        "currency": raw_data.get("currency", "USD"),
        "exchange": raw_data.get("exchange", ""),
        "interval": raw_data["interval"],
        "range": raw_data["range"],
        "resolved_range": raw_data["resolved_range"],
        "strategy": strategy,
        "is_intraday": raw_data["is_intraday"],
        "price_precision": precision,
        "last_price": round(last_price, precision),
        "prev_close": round(prev_close, precision),
        "change": round(change, precision),
        "change_pct": round(change_pct, 2),
        "bar_count": len(bars),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": raw_data.get("source", raw_data.get("provider", "yahoo")),
    }
    for extra_key in ("high_24h", "low_24h", "quote_volume_24h"):
        if extra_key in raw_data and raw_data[extra_key] is not None:
            meta[extra_key] = raw_data[extra_key]

    return {
        "meta": meta,
        "candles": candles,
        "volume": volume,
        "indicators": {
            "sma20": _to_line_series(times, sma20_vals),
            "sma60": _to_line_series(times, sma60_vals),
            "bb_upper": _to_line_series(times, bb_u),
            "bb_mid": _to_line_series(times, bb_m),
            "bb_lower": _to_line_series(times, bb_l),
        },
        "markers": markers,
    }


def compute_tail_indicators(
    closes: list[float],
    time_val: int | str,
    defaults: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any] | None]:
    """仅增量计算最后一根 K 线的技术指标点，供 WebSocket/SSE 实时推送使用。"""
    cfg = (defaults or load_defaults()).get("indicators", {})
    sma_fast = int(cfg.get("sma_fast", 20))
    sma_slow = int(cfg.get("sma_slow", 60))
    bb_period = int(cfg.get("bb_period", 20))
    bb_std = float(cfg.get("bb_std", 2.0))

    def _pt(val: float | None) -> dict[str, Any] | None:
        if val is None or not math.isfinite(val):
            return None
        return {"time": time_val, "value": round(val, 6)}

    s20 = compute_sma(closes[-sma_fast:], sma_fast)[-1] if len(closes) >= sma_fast else None
    s60 = compute_sma(closes[-sma_slow:], sma_slow)[-1] if len(closes) >= sma_slow else None
    if len(closes) >= bb_period:
        bu_l, bm_l, bl_l = compute_bollinger(closes[-bb_period:], bb_period, bb_std)
        bu, bm, bl = bu_l[-1], bm_l[-1], bl_l[-1]
    else:
        bu = bm = bl = None

    return {
        "sma20": _pt(s20),
        "sma60": _pt(s60),
        "bb_upper": _pt(bu),
        "bb_mid": _pt(bm),
        "bb_lower": _pt(bl),
    }


# ── 前端交互页面 HTML 模板 ────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>__PAGE_TITLE__</title>
  <link rel="icon" type="image/x-icon" href="/favicon.ico" />
  <style>
    :root {
      --bg: #131722;
      --panel: #1e222d;
      --border: #2a2e39;
      --text: #d1d4dc;
      --muted: #787b86;
      --accent: #f0b90b;
      --up: #26a69a;
      --down: #ef5350;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0; padding: 0; height: 100%; width: 100%;
      background: var(--bg); color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
      font-size: 13px; overflow: hidden;
    }
    .app { display: flex; flex-direction: column; height: 100vh; width: 100vw; }
    .toolbar {
      display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px;
      padding: 8px 14px; background: var(--panel); border-bottom: 1px solid var(--border); z-index: 10;
    }
    .group { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
    .divider { width: 1px; height: 20px; background: var(--border); }
    button, select, input[type="text"] {
      background: #2a2e39; color: var(--text); border: 1px solid #363a45;
      border-radius: 4px; padding: 4px 8px; font-size: 12px; outline: none;
    }
    button { cursor: pointer; transition: background 0.15s, border-color 0.15s; white-space: nowrap; }
    button:hover:not(:disabled) { background: #363a45; }
    button.active {
      background: rgba(240, 185, 11, 0.16); border-color: var(--accent);
      color: var(--accent); font-weight: 600;
    }
    button:disabled, select:disabled, input:disabled { opacity: 0.45; cursor: not-allowed; }
    input[type="text"] { width: 125px; }
    label.chk {
      display: inline-flex; align-items: center; gap: 4px; cursor: pointer;
      padding: 2px 6px; border-radius: 4px; user-select: none;
    }
    label.chk:hover { background: #2a2e39; }
    .workspace { display: flex; flex: 1 1 auto; min-height: 0; width: 100%; }
    .sidebar {
      width: 262px; flex-shrink: 0; background: #161a25;
      border-right: 1px solid var(--border);
      display: flex; flex-direction: column; min-height: 0;
    }
    .sidebar.hidden { display: none; }
    .wl-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 8px 12px; border-bottom: 1px solid var(--border); font-weight: 600;
    }
    .wl-title { display: flex; align-items: center; gap: 6px; color: #fff; font-size: 12px; }
    .wl-badge {
      background: #2a2e39; color: var(--muted); border-radius: 10px;
      padding: 1px 7px; font-size: 11px; font-weight: 500;
    }
    .wl-add-row {
      display: flex; gap: 6px; padding: 8px 10px;
      border-bottom: 1px solid var(--border); background: #1a1e2b;
    }
    .wl-add-row input { flex: 1 1 auto; width: auto; min-width: 0; }
    .wl-list { flex: 1 1 auto; overflow-y: auto; padding: 4px 0; }
    .wl-list::-webkit-scrollbar { width: 6px; }
    .wl-list::-webkit-scrollbar-thumb { background: #2a2e39; border-radius: 3px; }
    .wl-item {
      display: flex; flex-direction: column; gap: 3px;
      padding: 8px 12px; cursor: pointer; border-left: 3px solid transparent;
      border-bottom: 1px solid rgba(42, 46, 57, 0.45);
      transition: background 0.12s, border-color 0.12s;
    }
    .wl-item:hover { background: rgba(42, 46, 57, 0.55); }
    .wl-item.active {
      background: rgba(240, 185, 11, 0.09);
      border-left-color: var(--accent);
    }
    .wl-row-top, .wl-row-bot {
      display: flex; align-items: center; justify-content: space-between; gap: 6px;
    }
    .wl-label-wrap { display: flex; align-items: center; gap: 6px; min-width: 0; }
    .wl-label { font-weight: 600; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .wl-prov {
      font-size: 10px; padding: 0 4px; border-radius: 3px;
      background: #2a2e39; color: var(--muted); text-transform: uppercase; flex-shrink: 0;
    }
    .wl-price { font-weight: 600; font-variant-numeric: tabular-nums; font-size: 12px; color: var(--text); }
    .wl-sym { font-size: 11px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .wl-right-bot { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
    .wl-chg {
      font-size: 11px; font-variant-numeric: tabular-nums; font-weight: 600;
      padding: 1px 5px; border-radius: 3px;
    }
    .wl-chg.up { background: rgba(38, 166, 154, 0.14); color: var(--up); }
    .wl-chg.down { background: rgba(239, 83, 80, 0.14); color: var(--down); }
    .wl-del {
      opacity: 0; background: transparent; border: none; color: var(--muted);
      padding: 0 4px; font-size: 14px; line-height: 1;
    }
    .wl-item:hover .wl-del { opacity: 1; }
    .wl-del:hover { color: var(--down); background: transparent !important; }
    .main-pane { display: flex; flex-direction: column; flex: 1 1 auto; min-width: 0; min-height: 0; }
    .status-bar {
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
      gap: 8px; padding: 6px 14px; background: #161a25;
      border-bottom: 1px solid var(--border); font-size: 12px;
    }
    .quote-info { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .provider-tag {
      background: rgba(240, 185, 11, 0.14); color: var(--accent);
      border: 1px solid rgba(240, 185, 11, 0.35); border-radius: 4px;
      padding: 1px 6px; font-size: 11px; text-transform: uppercase;
    }
    .sym-title { font-size: 15px; font-weight: 700; color: #ffffff; }
    .price-big { font-size: 15px; font-weight: 700; font-variant-numeric: tabular-nums; }
    .up { color: var(--up); }
    .down { color: var(--down); }
    .ohlcv-legend { color: var(--muted); font-variant-numeric: tabular-nums; }
    .ohlcv-legend span { margin-right: 10px; color: var(--text); }
    .ohlcv-legend b { color: var(--muted); font-weight: 500; margin-right: 3px; }
    .live-badge { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--up); display: inline-block; }
    .dot.paused { background: var(--muted); }
    .dot.error { background: var(--down); }
    .dot.static { background: var(--accent); }
    .dot.loading { background: var(--accent); animation: kpulse 1s ease-in-out infinite; }
    @keyframes kpulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
    .chart-wrap { position: relative; flex: 1 1 auto; min-height: 0; width: 100%; }
    #chart { width: 100%; height: 100%; }
    .error-banner {
      display: none; position: absolute; top: 10px; right: 14px; z-index: 20;
      background: rgba(239, 83, 80, 0.92); color: #fff; padding: 8px 12px;
      border-radius: 6px; max-width: 440px; box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }
    .hint-footer {
      padding: 4px 14px; background: var(--panel); border-top: 1px solid var(--border);
      color: var(--muted); font-size: 11px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
    }
  </style>
</head>
<body>
  <div class="app">
    <div class="toolbar">
      <div class="group">
        <input type="text" id="custom-symbol" placeholder="输入币种如 BTC / TAUSDT" />
        <button id="btn-load-symbol">加载</button>
      </div>
      <div class="divider"></div>
      <div class="group" id="interval-buttons"></div>
      <div class="group">
        <select id="range-select" title="时间区间">
          <option value="auto">区间: 自动</option>
          <option value="1d">1D</option>
          <option value="5d">5D</option>
          <option value="1mo">1M</option>
          <option value="3mo">3M</option>
          <option value="6mo">6M</option>
          <option value="1y">1Y</option>
          <option value="5y">5Y</option>
          <option value="max">MAX</option>
        </select>
      </div>
      <div class="divider"></div>
      <div class="group">
        <label class="chk"><input type="checkbox" id="chk-sma20" checked /> <span style="color:#f0b90b">SMA20</span></label>
        <label class="chk"><input type="checkbox" id="chk-sma60" checked /> <span style="color:#42a5f5">SMA60</span></label>
        <label class="chk"><input type="checkbox" id="chk-bb" /> <span style="color:#ab47bc">布林带</span></label>
        <label class="chk"><input type="checkbox" id="chk-vol" checked /> 成交量</label>
      </div>
      <div class="divider"></div>
      <div class="group">
        <select id="strategy-select" title="策略买卖点标记">
          <option value="none">信号: 无</option>
          <option value="sma_crossover">信号: 双均线交叉</option>
          <option value="bbands_contrarian">信号: 布林带反转</option>
          <option value="rsi_meanrev">信号: RSI均值回归</option>
          <option value="macd_crossover">信号: MACD金叉死叉</option>
        </select>
        <select id="refresh-select" title="实时推送 / 轮询间隔">
          <option value="live">实时: WS推送</option>
          <option value="1">刷新: 1s</option>
          <option value="5">刷新: 5s</option>
          <option value="15">刷新: 15s</option>
          <option value="30">刷新: 30s</option>
          <option value="60">刷新: 60s</option>
          <option value="0">刷新: 暂停</option>
        </select>
        <button id="btn-refresh">立即刷新</button>
        <button id="btn-color-scheme" title="切换绿涨红跌 / 红涨绿跌">绿涨红跌</button>
        <button id="btn-fit" title="重置缩放适应全屏">适应屏幕</button>
      </div>
    </div>

    <div class="workspace">
      <aside class="sidebar" id="sidebar">
        <div class="wl-header">
          <span class="wl-title">自选标的 <span class="wl-badge" id="wl-count">0</span></span>
          <button id="wl-refresh-btn" title="刷新自选行情" style="padding:2px 6px;font-size:11px;">刷新行情</button>
        </div>
        <div class="wl-add-row">
          <input type="text" id="wl-add-input" placeholder="添加代码如 TAUSDT" />
          <button id="wl-add-btn">+ 添加</button>
        </div>
        <div class="wl-list" id="watchlist-items"></div>
      </aside>

      <div class="main-pane">
        <div class="status-bar">
          <div class="quote-info">
            <span class="provider-tag" id="hdr-provider">--</span>
            <span class="sym-title" id="hdr-symbol">--</span>
            <span class="price-big" id="hdr-price">--</span>
            <span id="hdr-change">--</span>
            <div class="ohlcv-legend" id="ohlcv-legend"></div>
          </div>
          <div class="live-badge">
            <span class="dot" id="live-dot"></span>
            <span id="live-text">初始化中...</span>
          </div>
        </div>

        <div class="chart-wrap">
          <div id="chart"></div>
          <div class="error-banner" id="error-banner"></div>
        </div>
      </div>
    </div>

    <div class="hint-footer">
      <span>数据源: Gate.io 现货 · 支持输入 BTC / BTCUSDT / TAUSDT / TA_USDT | 滚轮缩放 & 拖拽平移</span>
      <span id="meta-summary">--</span>
    </div>
  </div>

  __LWC_SCRIPT_TAG__
  <script>
    const APP_CONFIG = __APP_CONFIG_JSON__;
    const INITIAL_PAYLOAD = __INITIAL_PAYLOAD_JSON__;

    const INTERVALS = ["5m", "15m", "1h", "4h", "1d", "1wk"];
    const state = {
      symbol: APP_CONFIG.symbol,
      provider: APP_CONFIG.provider || "gate",
      interval: APP_CONFIG.interval,
      range: APP_CONFIG.range,
      strategy: APP_CONFIG.strategy,
      wsEnabled: Boolean(APP_CONFIG.ws_enabled),
      refreshMode: APP_CONFIG.mode === "static"
        ? "0"
        : (APP_CONFIG.ws_enabled ? "live" : String(APP_CONFIG.refresh || 1)),
      refreshSec: Number(APP_CONFIG.refresh || 1),
      colorScheme: APP_CONFIG.color_scheme || "green_up",
      isStatic: APP_CONFIG.mode === "static",
      watchlist: Array.isArray(APP_CONFIG.symbols) ? [...APP_CONFIG.symbols] : [],
      quotesBySpec: {},
      sidebarVisible: APP_CONFIG.mode !== "static",
      pricePrecision: 2,
      activeCanonicalSymbol: "",
      lastBarTime: null,
      lastKey: "",
      lastPayload: null,
      payloadCache: new Map(),
      lastCrosshairBar: null,
      lastCrosshairVol: null,
      timerId: null,
      fallbackTimerId: null,
      eventSource: null,
      streamToken: 0,
      pendingTick: null,
      rafScheduled: false,
      lastRafTime: 0,
      activeRequestId: 0,
      abortCtrl: null,
      quotesLoading: false,
    };

    const chartEl = document.getElementById("chart");
    const chart = LightweightCharts.createChart(chartEl, {
      layout: { background: { type: "solid", color: "#131722" }, textColor: "#d1d4dc" },
      grid: { vertLines: { color: "#1f2430" }, horzLines: { color: "#1f2430" } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#2a2e39", scaleMargins: { top: 0.08, bottom: 0.22 } },
      timeScale: { borderColor: "#2a2e39", timeVisible: true, secondsVisible: false },
      localization: { locale: "zh-CN" },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#26a69a", downColor: "#ef5350",
      borderVisible: false, wickUpColor: "#26a69a", wickDownColor: "#ef5350",
    });

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.80, bottom: 0.0 } });

    const sma20Series = chart.addLineSeries({ color: "#f0b90b", lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false });
    const sma60Series = chart.addLineSeries({ color: "#42a5f5", lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false });
    const bbUpperSeries = chart.addLineSeries({ color: "rgba(171, 71, 188, 0.8)", lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
    const bbMidSeries = chart.addLineSeries({ color: "rgba(171, 71, 188, 0.5)", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    const bbLowerSeries = chart.addLineSeries({ color: "rgba(171, 71, 188, 0.8)", lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });

    new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) chart.resize(Math.floor(width), Math.floor(height));
      }
    }).observe(chartEl);

    function getColors() {
      if (state.colorScheme === "red_up") {
        return { up: "#ef5350", down: "#26a69a", upVol: "rgba(239, 83, 80, 0.45)", downVol: "rgba(38, 166, 154, 0.45)", label: "红涨绿跌" };
      }
      return { up: "#26a69a", down: "#ef5350", upVol: "rgba(38, 166, 154, 0.45)", downVol: "rgba(239, 83, 80, 0.45)", label: "绿涨红跌" };
    }

    function colorizeVolume(candles, volumes) {
      const c = getColors();
      return volumes.map((v, idx) => {
        const bar = candles[idx];
        const isUp = bar ? bar.close >= bar.open : true;
        return { time: v.time, value: v.value, color: isUp ? c.upVol : c.downVol };
      });
    }

    function inferPrecision(val) {
      const av = Math.abs(Number(val));
      if (!Number.isFinite(av) || av === 0) return 4;
      if (av < 0.05) return 6;
      if (av < 1) return 5;
      if (av < 100) return 4;
      return 2;
    }

    function fmtNum(val, prec) {
      const n = Number(val);
      if (!Number.isFinite(n)) return "--";
      return n.toFixed(prec != null ? prec : inferPrecision(n));
    }

    function applyColorScheme(recolorExisting) {
      const c = getColors();
      document.documentElement.style.setProperty("--up", c.up);
      document.documentElement.style.setProperty("--down", c.down);
      document.getElementById("btn-color-scheme").textContent = c.label;
      candleSeries.applyOptions({
        upColor: c.up, downColor: c.down, wickUpColor: c.up, wickDownColor: c.down,
      });
      if (recolorExisting && state.lastPayload) {
        const volColored = colorizeVolume(state.lastPayload.candles, state.lastPayload.volume);
        state.lastPayload.volume = volColored;
        const lr = chart.timeScale().getVisibleLogicalRange();
        volumeSeries.setData(volColored);
        if (lr) chart.timeScale().setVisibleLogicalRange(lr);
        const bars = state.lastPayload.candles;
        const vols = state.lastPayload.volume;
        updateLegend(state.lastCrosshairBar || bars[bars.length - 1], state.lastCrosshairVol || vols[vols.length - 1]);
      }
      renderWatchlist();
    }

    function syncSidebarVisibility() {
      const sb = document.getElementById("sidebar");
      if (state.isStatic || !state.sidebarVisible) {
        sb.classList.add("hidden");
      } else {
        sb.classList.remove("hidden");
      }
    }

    function renderWatchlist() {
      const box = document.getElementById("watchlist-items");
      document.getElementById("wl-count").textContent = String(state.watchlist.length);
      box.innerHTML = "";
      state.watchlist.forEach((item, idx) => {
        const pairGuess = item.symbol.replace(/^gate:/i, "").toUpperCase();
        const q = state.quotesBySpec[item.symbol]
          || state.quotesBySpec[item.symbol.toUpperCase()]
          || state.quotesBySpec[pairGuess];
        const isActive = item.symbol.toUpperCase() === state.symbol.toUpperCase();
        const row = document.createElement("div");
        row.className = "wl-item" + (isActive ? " active" : "");
        row.dataset.spec = item.symbol.toUpperCase();
        row.dataset.pair = (q && q.symbol) ? String(q.symbol).toUpperCase() : pairGuess;

        const provText = (q && q.provider) ? q.provider : "gate";
        const priceStr = (q && q.last_price != null) ? fmtNum(q.last_price) : "--";
        const chgVal = (q && q.change_pct != null) ? Number(q.change_pct) : null;
        const chgCls = chgVal == null ? "" : (chgVal >= 0 ? "up" : "down");
        const chgStr = chgVal == null ? "--" : `${chgVal >= 0 ? "+" : ""}${chgVal.toFixed(2)}%`;

        row.innerHTML =
          `<div class="wl-row-top">` +
            `<div class="wl-label-wrap">` +
              `<span class="wl-label"></span>` +
              `<span class="wl-prov">${provText}</span>` +
            `</div>` +
            `<span class="wl-price">${priceStr}</span>` +
          `</div>` +
          `<div class="wl-row-bot">` +
            `<span class="wl-sym"></span>` +
            `<div class="wl-right-bot">` +
              `<span class="wl-chg ${chgCls}">${chgStr}</span>` +
              `<button class="wl-del" title="移除">×</button>` +
            `</div>` +
          `</div>`;

        row.querySelector(".wl-label").textContent = item.label || item.symbol;
        row.querySelector(".wl-sym").textContent = item.symbol;

        row.onclick = () => {
          state.symbol = item.symbol;
          state.provider = "auto";
          document.getElementById("custom-symbol").value = "";
          renderToolbar();
          renderWatchlist();
          fetchAndRender(false);
        };

        row.querySelector(".wl-del").onclick = async (ev) => {
          ev.stopPropagation();
          if (state.watchlist.length <= 1) {
            showError("自选列表至少保留 1 个标的");
            return;
          }
          const next = state.watchlist.filter((_, i) => i !== idx);
          state.watchlist = next;
          if (isActive && next.length) {
            state.symbol = next[0].symbol;
            state.provider = "auto";
            fetchAndRender(false);
          }
          renderWatchlist();
          await saveWatchlistRemote(next);
        };

        box.appendChild(row);
      });
    }

    async function saveWatchlistRemote(items) {
      try {
        const resp = await fetch("/api/watchlist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbols: items }),
        });
        const data = await resp.json();
        if (resp.ok && Array.isArray(data.symbols)) {
          state.watchlist = data.symbols;
        }
      } catch (_) {}
    }

    function patchWatchlistQuote(q) {
      if (!q || q.error) return;
      const pair = String(q.symbol || "").toUpperCase();
      if (q.symbol_spec) {
        state.quotesBySpec[q.symbol_spec] = q;
        state.quotesBySpec[q.symbol_spec.toUpperCase()] = q;
      }
      if (q.resolved_spec) {
        state.quotesBySpec[q.resolved_spec] = q;
        state.quotesBySpec[q.resolved_spec.toUpperCase()] = q;
      }
      if (pair) state.quotesBySpec[pair] = q;

      const box = document.getElementById("watchlist-items");
      if (!box) return;
      const rows = box.querySelectorAll(".wl-item");
      rows.forEach((row) => {
        const rowPair = (row.dataset.pair || "").toUpperCase();
        const rowSpec = (row.dataset.spec || "").toUpperCase();
        if ((pair && rowPair === pair) || (q.resolved_spec && rowSpec === q.resolved_spec.toUpperCase())) {
          const pEl = row.querySelector(".wl-price");
          if (pEl && q.last_price != null) pEl.textContent = fmtNum(q.last_price);
          const cEl = row.querySelector(".wl-chg");
          if (cEl && q.change_pct != null) {
            const chgVal = Number(q.change_pct);
            cEl.className = "wl-chg " + (chgVal >= 0 ? "up" : "down");
            cEl.textContent = `${chgVal >= 0 ? "+" : ""}${chgVal.toFixed(2)}%`;
          }
        }
      });
    }

    async function fetchWatchlistQuotes(useNocache) {
      if (state.isStatic || state.quotesLoading || !state.watchlist.length) return;
      state.quotesLoading = true;
      try {
        const syms = state.watchlist.map((it) => it.symbol).join(",");
        const nocacheFlag = useNocache || state.refreshMode === "1" || Boolean(state.fallbackTimerId);
        const qUrl = `/api/quotes?symbols=${encodeURIComponent(syms)}${nocacheFlag ? "&nocache=1" : ""}`;
        const resp = await fetch(qUrl);
        const data = await resp.json();
        if (resp.ok && Array.isArray(data.quotes)) {
          let rebuilt = false;
          data.quotes.forEach((q) => {
            if (q && !q.error) {
              if (q.symbol_spec) {
                state.quotesBySpec[q.symbol_spec] = q;
                state.quotesBySpec[q.symbol_spec.toUpperCase()] = q;
              }
              if (q.resolved_spec) state.quotesBySpec[q.resolved_spec.toUpperCase()] = q;
              if (q.symbol) state.quotesBySpec[String(q.symbol).toUpperCase()] = q;
              rebuilt = true;
            }
          });
          if (rebuilt) renderWatchlist();
        }
      } catch (_) {
      } finally {
        state.quotesLoading = false;
      }
    }

    async function addSymbolToWatchlist(rawInput) {
      const raw = rawInput.trim();
      if (!raw) return;
      const btn = document.getElementById("wl-add-btn");
      btn.disabled = true;
      btn.textContent = "...";
      try {
        const spec = raw;
        const resp = await fetch(`/api/quotes?symbols=${encodeURIComponent(spec)}`);
        const data = await resp.json();
        const q = (data.quotes && data.quotes[0]) ? data.quotes[0] : null;
        if (!resp.ok || !q || q.error) {
          throw new Error((q && q.error) || data.error || `无法识别标的 ${raw}`);
        }
        const canonical = q.resolved_spec || spec;
        const label = q.display_name || raw.toUpperCase();
        state.quotesBySpec[canonical] = q;
        state.quotesBySpec[canonical.toUpperCase()] = q;
        const exists = state.watchlist.find((it) => it.symbol.toUpperCase() === canonical.toUpperCase());
        if (!exists) {
          state.watchlist = [...state.watchlist, { symbol: canonical, label }];
          await saveWatchlistRemote(state.watchlist);
        }
        state.symbol = canonical;
        state.provider = "gate";
        document.getElementById("wl-add-input").value = "";
        renderToolbar();
        renderWatchlist();
        await fetchAndRender(false);
      } catch (err) {
        showError(`添加自选失败: ${err.message}`);
      } finally {
        btn.disabled = false;
        btn.textContent = "+ 添加";
      }
    }

    function renderToolbar() {
      syncSidebarVisibility();

      const intBox = document.getElementById("interval-buttons");
      intBox.innerHTML = "";
      INTERVALS.forEach((iv) => {
        const btn = document.createElement("button");
        btn.textContent = iv;
        if (iv === state.interval) btn.classList.add("active");
        if (state.isStatic) btn.disabled = true;
        btn.onclick = () => {
          state.interval = iv;
          renderToolbar();
          fetchAndRender(false);
        };
        intBox.appendChild(btn);
      });

      document.getElementById("range-select").value = state.range;
      document.getElementById("range-select").disabled = state.isStatic;
      document.getElementById("strategy-select").value = state.strategy;
      document.getElementById("strategy-select").disabled = state.isStatic;
      const refreshSel = document.getElementById("refresh-select");
      if (refreshSel) {
        const liveOpt = refreshSel.querySelector('option[value="live"]');
        if (liveOpt) liveOpt.disabled = !state.wsEnabled;
        if (!state.wsEnabled && state.refreshMode === "live") {
          state.refreshMode = String(state.refreshSec > 0 ? state.refreshSec : 1);
        }
        refreshSel.value = state.refreshMode;
        refreshSel.disabled = state.isStatic;
      }
      document.getElementById("custom-symbol").disabled = state.isStatic;
      document.getElementById("btn-load-symbol").disabled = state.isStatic;
      document.getElementById("btn-refresh").disabled = state.isStatic;
    }

    function updateLegend(bar, volBar) {
      if (!bar) return;
      const cls = bar.close >= bar.open ? "up" : "down";
      const p = state.pricePrecision;
      const volTxt = volBar && volBar.value ? Number(volBar.value).toLocaleString() : "-";
      document.getElementById("ohlcv-legend").innerHTML =
        `<span><b>O</b><span class="${cls}">${fmtNum(bar.open, p)}</span></span>` +
        `<span><b>H</b><span class="${cls}">${fmtNum(bar.high, p)}</span></span>` +
        `<span><b>L</b><span class="${cls}">${fmtNum(bar.low, p)}</span></span>` +
        `<span><b>C</b><span class="${cls}">${fmtNum(bar.close, p)}</span></span>` +
        `<span><b>V</b>${volTxt}</span>`;
    }

    chart.subscribeCrosshairMove((param) => {
      if (!state.lastPayload) return;
      if (!param || !param.time) {
        state.lastCrosshairBar = null;
        state.lastCrosshairVol = null;
        const candles = state.lastPayload.candles;
        const vols = state.lastPayload.volume;
        updateLegend(candles[candles.length - 1], vols[vols.length - 1]);
        return;
      }
      const c = param.seriesData.get(candleSeries);
      const v = param.seriesData.get(volumeSeries);
      if (c) {
        state.lastCrosshairBar = c;
        state.lastCrosshairVol = v;
        updateLegend(c, v);
      }
    });

    function applyVisibility() {
      sma20Series.applyOptions({ visible: document.getElementById("chk-sma20").checked });
      sma60Series.applyOptions({ visible: document.getElementById("chk-sma60").checked });
      const showBb = document.getElementById("chk-bb").checked;
      bbUpperSeries.applyOptions({ visible: showBb });
      bbMidSeries.applyOptions({ visible: showBb });
      bbLowerSeries.applyOptions({ visible: showBb });
      volumeSeries.applyOptions({ visible: document.getElementById("chk-vol").checked });
    }

    function showError(msg) {
      const el = document.getElementById("error-banner");
      if (!msg) { el.style.display = "none"; el.textContent = ""; return; }
      el.textContent = msg;
      el.style.display = "block";
    }

    function setLiveStatus(kind, text) {
      document.getElementById("live-dot").className = "dot " + kind;
      document.getElementById("live-text").textContent = text;
    }

    function applyPayload(payload, isTimerRefresh) {
      showError("");
      const meta = payload.meta;
      const key = `${meta.provider}|${meta.symbol}|${meta.interval}|${meta.range}|${meta.strategy}`;
      const sameSeries = isTimerRefresh && key === state.lastKey && state.lastPayload;

      document.getElementById("hdr-provider").textContent = meta.provider || "auto";
      const titleText = meta.display_name && meta.display_name !== meta.symbol
        ? `${meta.display_name} · ${meta.interval} (${meta.resolved_range})`
        : `${meta.symbol} · ${meta.interval} (${meta.resolved_range})`;
      document.getElementById("hdr-symbol").textContent = titleText;

      const p = Number(meta.price_precision || inferPrecision(meta.last_price));
      state.pricePrecision = p;
      const minMove = Number(Math.pow(10, -p).toFixed(p));
      candleSeries.applyOptions({
        priceFormat: { type: "price", precision: p, minMove },
      });

      const priceEl = document.getElementById("hdr-price");
      const chgEl = document.getElementById("hdr-change");
      const upDown = meta.change >= 0 ? "up" : "down";
      const sign = meta.change >= 0 ? "+" : "";
      priceEl.textContent = `${fmtNum(meta.last_price, p)} ${meta.currency || ""}`.trim();
      priceEl.className = `price-big ${upDown}`;
      chgEl.textContent = `${sign}${fmtNum(meta.change, p)} (${sign}${meta.change_pct}%)`;
      chgEl.className = upDown;

      const hiLoStr = (meta.high_24h != null && meta.low_24h != null)
        ? ` | 24h高低: ${fmtNum(meta.high_24h, p)} / ${fmtNum(meta.low_24h, p)}`
        : "";
      document.getElementById("meta-summary").textContent =
        `K线: ${meta.bar_count} 根 | 信号: ${payload.markers.length} 次${hiLoStr} | 数据源: ${meta.source} | 更新于: ${meta.updated_at}`;

      const prevCandles = state.lastPayload ? state.lastPayload.candles : [];
      const newCandles = payload.candles;
      const volColored = colorizeVolume(newCandles, payload.volume);
      payload.volume = volColored;

      const canIncrementalUpdate =
        sameSeries &&
        prevCandles.length > 0 &&
        newCandles.length === prevCandles.length &&
        newCandles[newCandles.length - 1].time === prevCandles[prevCandles.length - 1].time;

      if (canIncrementalUpdate) {
        candleSeries.update(newCandles[newCandles.length - 1]);
        volumeSeries.update(volColored[volColored.length - 1]);
        const ind = payload.indicators;
        if (ind.sma20.length) sma20Series.update(ind.sma20[ind.sma20.length - 1]);
        if (ind.sma60.length) sma60Series.update(ind.sma60[ind.sma60.length - 1]);
        if (ind.bb_upper.length) bbUpperSeries.update(ind.bb_upper[ind.bb_upper.length - 1]);
        if (ind.bb_mid.length) bbMidSeries.update(ind.bb_mid[ind.bb_mid.length - 1]);
        if (ind.bb_lower.length) bbLowerSeries.update(ind.bb_lower[ind.bb_lower.length - 1]);
        candleSeries.setMarkers(payload.markers || []);
      } else {
        const logicalRange = sameSeries ? chart.timeScale().getVisibleLogicalRange() : null;
        chart.timeScale().applyOptions({ timeVisible: Boolean(meta.is_intraday) });
        candleSeries.setData(newCandles);
        volumeSeries.setData(volColored);
        sma20Series.setData(payload.indicators.sma20 || []);
        sma60Series.setData(payload.indicators.sma60 || []);
        bbUpperSeries.setData(payload.indicators.bb_upper || []);
        bbMidSeries.setData(payload.indicators.bb_mid || []);
        bbLowerSeries.setData(payload.indicators.bb_lower || []);
        candleSeries.setMarkers(payload.markers || []);

        if (logicalRange) chart.timeScale().setVisibleLogicalRange(logicalRange);
        else chart.timeScale().fitContent();
      }

      state.lastKey = key;
      state.lastPayload = payload;
      state.activeCanonicalSymbol = String(meta.symbol || "").toUpperCase();
      state.lastBarTime = newCandles.length ? newCandles[newCandles.length - 1].time : null;
      updateLegend(newCandles[newCandles.length - 1], volColored[volColored.length - 1]);
      applyVisibility();

      if (state.isStatic) {
        setLiveStatus("static", `静态快照 (${meta.updated_at})`);
      } else if (state.refreshMode === "live" && state.wsEnabled) {
        if (state.fallbackTimerId) {
          setLiveStatus("loading", `WS 重连中 · 1s 轮询兜底 (${meta.updated_at})`);
        } else if (state.eventSource && state.eventSource.readyState === 1) {
          setLiveStatus("", `WS 实时推送中 · ${meta.updated_at}`);
        } else {
          setLiveStatus("loading", `接入实时流中 · ${meta.updated_at}`);
        }
      } else {
        const sec = Number(state.refreshMode);
        if (sec > 0) setLiveStatus("", `实时轮询中 · 每 ${sec}s · ${meta.updated_at}`);
        else setLiveStatus("paused", `已暂停自动刷新 · ${meta.updated_at}`);
      }
    }

    function stopFallbackPolling() {
      if (state.fallbackTimerId) {
        clearInterval(state.fallbackTimerId);
        state.fallbackTimerId = null;
      }
    }

    function startFallbackPolling() {
      if (state.isStatic || state.fallbackTimerId || state.refreshMode !== "live") return;
      state.fallbackTimerId = setInterval(() => {
        fetchAndRender(true);
        fetchWatchlistQuotes(true);
      }, 1000);
    }

    function closeStream() {
      state.streamToken += 1;
      if (state.eventSource) {
        try { state.eventSource.close(); } catch (_) {}
        state.eventSource = null;
      }
      state.pendingTick = null;
      state.rafScheduled = false;
      stopFallbackPolling();
    }

    function syncSeriesPoint(arr, pt) {
      if (!Array.isArray(arr) || !pt || pt.time == null) return;
      if (arr.length && arr[arr.length - 1].time === pt.time) {
        arr[arr.length - 1] = pt;
      } else if (!arr.length || pt.time > arr[arr.length - 1].time) {
        arr.push(pt);
      }
    }

    function flushPendingTick() {
      state.rafScheduled = false;
      const tick = state.pendingTick;
      if (!tick || state.isStatic || state.refreshMode !== "live") return;
      const now = performance.now();
      if (now - state.lastRafTime < 60) {
        state.rafScheduled = true;
        requestAnimationFrame(flushPendingTick);
        return;
      }
      state.pendingTick = null;
      state.lastRafTime = now;

      if (String(tick.symbol || "").toUpperCase() !== state.activeCanonicalSymbol || tick.interval !== state.interval) {
        return;
      }
      const candle = tick.candle;
      if (!candle || candle.time == null) return;
      if (state.lastBarTime != null && candle.time < state.lastBarTime) return;
      state.lastBarTime = candle.time;

      const cols = getColors();
      const volRaw = tick.volume || { time: candle.time, value: 0 };
      const volPoint = {
        time: candle.time,
        value: Number(volRaw.value || 0),
        color: candle.close >= candle.open ? cols.upVol : cols.downVol,
      };

      candleSeries.update(candle);
      volumeSeries.update(volPoint);

      const ind = tick.indicators || {};
      if (ind.sma20) sma20Series.update(ind.sma20);
      if (ind.sma60) sma60Series.update(ind.sma60);
      if (ind.bb_upper) bbUpperSeries.update(ind.bb_upper);
      if (ind.bb_mid) bbMidSeries.update(ind.bb_mid);
      if (ind.bb_lower) bbLowerSeries.update(ind.bb_lower);

      const payload = state.lastPayload;
      if (payload && payload.meta) {
        syncSeriesPoint(payload.candles, candle);
        syncSeriesPoint(payload.volume, volPoint);
        if (payload.indicators) {
          if (ind.sma20) syncSeriesPoint(payload.indicators.sma20, ind.sma20);
          if (ind.sma60) syncSeriesPoint(payload.indicators.sma60, ind.sma60);
          if (ind.bb_upper) syncSeriesPoint(payload.indicators.bb_upper, ind.bb_upper);
          if (ind.bb_mid) syncSeriesPoint(payload.indicators.bb_mid, ind.bb_mid);
          if (ind.bb_lower) syncSeriesPoint(payload.indicators.bb_lower, ind.bb_lower);
        }

        const meta = payload.meta;
        const p = Number(meta.price_precision || state.pricePrecision || inferPrecision(candle.close));
        meta.last_price = candle.close;
        meta.bar_count = payload.candles.length;
        if (tick.change != null) meta.change = tick.change;
        if (tick.change_pct != null) meta.change_pct = tick.change_pct;
        if (tick.updated_at) meta.updated_at = tick.updated_at;

        const chgVal = Number(meta.change || 0);
        const chgPct = meta.change_pct != null ? Number(meta.change_pct) : 0;
        const upDown = chgVal >= 0 ? "up" : "down";
        const sign = chgVal >= 0 ? "+" : "";
        const priceEl = document.getElementById("hdr-price");
        const chgEl = document.getElementById("hdr-change");
        priceEl.textContent = `${fmtNum(candle.close, p)} ${meta.currency || ""}`.trim();
        priceEl.className = `price-big ${upDown}`;
        chgEl.textContent = `${sign}${fmtNum(chgVal, p)} (${sign}${chgPct}%)`;
        chgEl.className = upDown;

        const hiLoStr = (meta.high_24h != null && meta.low_24h != null)
          ? ` | 24h高低: ${fmtNum(meta.high_24h, p)} / ${fmtNum(meta.low_24h, p)}`
          : "";
        document.getElementById("meta-summary").textContent =
          `K线: ${meta.bar_count} 根 | 信号: ${payload.markers.length} 次${hiLoStr} | 数据源: ${meta.source} | 更新于: ${meta.updated_at}`;

        if (!state.lastCrosshairBar) {
          updateLegend(candle, volPoint);
        }
        setLiveStatus("", `WS 实时推送中 · ${tick.updated_at || meta.updated_at}`);
      }
    }

    function scheduleTickFlush(tick) {
      state.pendingTick = tick;
      if (!state.rafScheduled) {
        state.rafScheduled = true;
        requestAnimationFrame(flushPendingTick);
      }
    }

    function connectStream() {
      if (state.isStatic || state.refreshMode !== "live" || !state.wsEnabled) return;
      closeStream();
      const token = state.streamToken;
      const wlSyms = state.watchlist.map((it) => it.symbol).filter(Boolean).join(",");
      const qs = new URLSearchParams({
        symbol: state.symbol,
        provider: state.provider,
        interval: state.interval,
        range: state.range,
        watchlist: wlSyms,
      });
      setLiveStatus("loading", "正在接入 Gate.io WS...");
      const es = new EventSource(`/api/stream?${qs.toString()}`);
      state.eventSource = es;

      es.onmessage = (evt) => {
        if (token !== state.streamToken || state.refreshMode !== "live") return;
        let msg;
        try {
          msg = JSON.parse(evt.data);
        } catch (_) {
          return;
        }
        if (!msg || !msg.type) return;
        if (msg.type === "status") {
          if (msg.status === "connected") {
            stopFallbackPolling();
            const ts = state.lastPayload && state.lastPayload.meta ? state.lastPayload.meta.updated_at : "";
            setLiveStatus("", ts ? `WS 实时推送中 · ${ts}` : "WS 实时推送中");
          } else if (msg.status === "connecting") {
            setLiveStatus("loading", "正在接入 Gate.io WS...");
          } else if (msg.status === "reconnecting" || msg.status === "error") {
            setLiveStatus("loading", "WS 重连中 · 1s 轮询兜底");
            startFallbackPolling();
          }
          return;
        }
        if (msg.type === "quote" && msg.quote) {
          patchWatchlistQuote(msg.quote);
          return;
        }
        if (msg.type === "tick") {
          stopFallbackPolling();
          scheduleTickFlush(msg);
        }
      };

      es.onerror = () => {
        if (token !== state.streamToken || state.refreshMode !== "live") return;
        setLiveStatus("loading", "实时流重连中 · 1s 轮询兜底");
        startFallbackPolling();
      };
    }

    function makeCacheKey(sym, iv, rng, strat) {
      return `${String(sym || "").trim().toUpperCase()}|${iv}|${rng}|${strat}`;
    }

    function storePayloadCache(reqSym, iv, rng, strat, payload) {
      state.payloadCache.set(makeCacheKey(reqSym, iv, rng, strat), payload);
      if (payload && payload.meta && payload.meta.symbol) {
        state.payloadCache.set(makeCacheKey(payload.meta.symbol, iv, rng, strat), payload);
        state.payloadCache.set(makeCacheKey(`gate:${payload.meta.symbol}`, iv, rng, strat), payload);
      }
      if (state.payloadCache.size > 60) {
        const firstKey = state.payloadCache.keys().next().value;
        if (firstKey) state.payloadCache.delete(firstKey);
      }
    }

    async function prefetchWatchlistCharts() {
      if (state.isStatic || !state.watchlist.length) return;
      const iv = state.interval;
      const rng = state.range;
      const strat = state.strategy;
      for (const item of state.watchlist) {
        const sym = item.symbol;
        if (!sym) continue;
        const k = makeCacheKey(sym, iv, rng, strat);
        if (state.payloadCache.has(k)) continue;
        try {
          const qs = new URLSearchParams({
            symbol: sym,
            provider: "gate",
            interval: iv,
            range: rng,
            strategy: strat,
          });
          const resp = await fetch(`/api/kline?${qs.toString()}`);
          if (!resp.ok) continue;
          const data = await resp.json();
          if (data && !data.error) storePayloadCache(sym, iv, rng, strat, data);
        } catch (_) {}
      }
    }

    async function fetchAndRender(isTimerRefresh) {
      if (state.isStatic) return;
      if (isTimerRefresh && state.abortCtrl) return;
      if (!isTimerRefresh) {
        closeStream();
        if (state.abortCtrl) state.abortCtrl.abort();
      }
      const ctrl = new AbortController();
      state.abortCtrl = ctrl;
      const reqId = ++state.activeRequestId;
      const reqSymbol = state.symbol;
      const reqInterval = state.interval;
      const reqRange = state.range;
      const reqStrategy = state.strategy;
      const loadBtn = document.getElementById("btn-load-symbol");

      const cached = !isTimerRefresh
        ? state.payloadCache.get(makeCacheKey(reqSymbol, reqInterval, reqRange, reqStrategy))
        : null;

      if (cached) {
        showError("");
        applyPayload(cached, false);
        setLiveStatus("loading", `同步最新 K 线中...`);
      } else if (!isTimerRefresh) {
        showError("");
        setLiveStatus("loading", `正在加载 ${reqSymbol}...`);
        if (loadBtn) {
          loadBtn.disabled = true;
          loadBtn.textContent = "加载中...";
        }
      }

      try {
        const qs = new URLSearchParams({
          symbol: reqSymbol,
          provider: state.provider,
          interval: reqInterval,
          range: reqRange,
          strategy: reqStrategy,
        });
        if (isTimerRefresh && (state.refreshMode === "1" || state.fallbackTimerId)) {
          qs.set("nocache", "1");
        }
        const resp = await fetch(`/api/kline?${qs.toString()}`, { signal: ctrl.signal });
        const data = await resp.json();
        if (reqId !== state.activeRequestId) return;
        if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);
        storePayloadCache(reqSymbol, reqInterval, reqRange, reqStrategy, data);
        applyPayload(data, isTimerRefresh || Boolean(cached));
        if (!isTimerRefresh && state.refreshMode === "live" && state.wsEnabled) {
          connectStream();
        }
      } catch (err) {
        if (err && err.name === "AbortError") return;
        if (reqId !== state.activeRequestId) return;
        const isConnErr = err && (err.name === "TypeError" || /failed to fetch|networkerror/i.test(String(err.message)));
        const msg = isConnErr
          ? "本地服务已断开（如用命令行启动请勿关闭终端；推荐双击 launch_client.bat）"
          : `拉取 ${reqSymbol} 失败: ${err.message}`;
        setLiveStatus("error", isConnErr ? "本地服务已断开" : `拉取失败: ${err.message}`);
        showError(msg);
      } finally {
        if (reqId === state.activeRequestId) {
          state.abortCtrl = null;
          if (loadBtn && !state.isStatic) {
            loadBtn.disabled = false;
            loadBtn.textContent = "加载";
          }
        }
      }
    }

    function resetTimer() {
      if (state.timerId) { clearInterval(state.timerId); state.timerId = null; }
      stopFallbackPolling();
      if (state.isStatic) return;
      if (state.refreshMode === "live" && state.wsEnabled) {
        if (state.lastPayload) connectStream();
        return;
      }
      closeStream();
      const sec = Number(state.refreshMode);
      if (sec > 0) {
        state.timerId = setInterval(() => {
          fetchAndRender(true);
          fetchWatchlistQuotes(sec === 1);
        }, sec * 1000);
      }
    }

    document.getElementById("wl-refresh-btn").onclick = () => fetchWatchlistQuotes(true);
    document.getElementById("wl-add-btn").onclick = () => {
      addSymbolToWatchlist(document.getElementById("wl-add-input").value);
    };
    document.getElementById("wl-add-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") document.getElementById("wl-add-btn").click();
    });

    document.getElementById("btn-load-symbol").onclick = () => {
      const val = document.getElementById("custom-symbol").value.trim();
      if (!val) return;
      state.symbol = val;
      state.provider = "gate";
      renderToolbar();
      renderWatchlist();
      fetchAndRender(false);
    };
    document.getElementById("custom-symbol").addEventListener("keydown", (e) => {
      if (e.key === "Enter") document.getElementById("btn-load-symbol").click();
    });
    document.getElementById("range-select").onchange = (e) => { state.range = e.target.value; fetchAndRender(false); };
    document.getElementById("strategy-select").onchange = (e) => { state.strategy = e.target.value; fetchAndRender(false); };
    document.getElementById("refresh-select").onchange = (e) => {
      state.refreshMode = e.target.value;
      if (state.refreshMode !== "live") {
        state.refreshSec = Number(state.refreshMode);
      }
      resetTimer();
      if (state.lastPayload && state.refreshMode !== "live") {
        const sec = Number(state.refreshMode);
        if (sec > 0) setLiveStatus("", `实时轮询中 · 每 ${sec}s · ${state.lastPayload.meta.updated_at}`);
        else setLiveStatus("paused", `已暂停自动刷新 · ${state.lastPayload.meta.updated_at}`);
      }
    };
    document.getElementById("btn-refresh").onclick = () => {
      fetchAndRender(true);
      fetchWatchlistQuotes(true);
    };
    document.getElementById("btn-fit").onclick = () => chart.timeScale().fitContent();
    document.getElementById("btn-color-scheme").onclick = () => {
      state.colorScheme = state.colorScheme === "green_up" ? "red_up" : "green_up";
      applyColorScheme(true);
    };
    ["chk-sma20", "chk-sma60", "chk-bb", "chk-vol"].forEach((id) => {
      document.getElementById(id).onchange = applyVisibility;
    });

    applyColorScheme(false);
    renderToolbar();
    renderWatchlist();
    if (INITIAL_PAYLOAD) applyPayload(INITIAL_PAYLOAD, false);
    else {
      fetchAndRender(false).then(() => prefetchWatchlistCharts());
      fetchWatchlistQuotes();
    }
    resetTimer();
  </script>
</body>
</html>
"""


def render_html(
    app_config: dict[str, Any],
    initial_payload: dict[str, Any] | None = None,
    inline_lwc: bool = False,
) -> str:
    if not LWC_JS_PATH.exists():
        raise FileNotFoundError(f"缺少本地 Lightweight Charts 文件: {LWC_JS_PATH}")

    if inline_lwc:
        lwc_js = LWC_JS_PATH.read_text(encoding="utf-8")
        script_tag = f"<script>\n{lwc_js}\n</script>"
    else:
        script_tag = '<script src="/assets/lightweight-charts.standalone.production.js"></script>'

    title = app_config.get("title") or "全市场交互式 K 线看板"
    cfg_json = json.dumps(app_config, ensure_ascii=False).replace("</", "<\\/")
    payload_json = (
        json.dumps(initial_payload, ensure_ascii=False).replace("</", "<\\/")
        if initial_payload is not None
        else "null"
    )
    return (
        HTML_TEMPLATE.replace("__PAGE_TITLE__", title)
        .replace("__LWC_SCRIPT_TAG__", script_tag)
        .replace("__APP_CONFIG_JSON__", cfg_json)
        .replace("__INITIAL_PAYLOAD_JSON__", payload_json)
    )


# ── 本地 HTTP 实时看板服务 ────────────────────────────────────────────────────

def make_handler(
    defaults: dict[str, Any],
    app_config: dict[str, Any],
    shutdown_callback: Callable[[], None] | None = None,
):
    default_provider = defaults.get("default_provider", "gate")

    class KlineHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, obj: Any) -> None:
            self._send_bytes(
                status,
                "application/json; charset=utf-8",
                json.dumps(obj, ensure_ascii=False).encode("utf-8"),
            )

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/":
                live_cfg = dict(app_config)
                live_cfg["symbols"] = load_watchlist(defaults)
                live_cfg["ws_enabled"] = ws_stream.HAS_WEBSOCKET
                html = render_html(live_cfg, initial_payload=None, inline_lwc=False)
                self._send_bytes(200, "text/html; charset=utf-8", html.encode("utf-8"))
                return

            if path == "/favicon.ico":
                if not ICON_PATH.exists():
                    self._send_bytes(404, "text/plain; charset=utf-8", b"Icon not found")
                    return
                self._send_bytes(200, "image/x-icon", ICON_PATH.read_bytes())
                return

            if path == "/assets/lightweight-charts.standalone.production.js":
                if not LWC_JS_PATH.exists():
                    self._send_bytes(404, "text/plain; charset=utf-8", b"Lightweight Charts bundle not found")
                    return
                self._send_bytes(200, "application/javascript; charset=utf-8", LWC_JS_PATH.read_bytes())
                return

            if path == "/api/health":
                self._send_json(200, {"ok": True, "mode": app_config.get("mode", "live"), "ws_enabled": ws_stream.HAS_WEBSOCKET})
                return

            if path == "/api/watchlist":
                self._send_json(200, {"symbols": load_watchlist(defaults)})
                return

            if path == "/api/quotes":
                qs = urllib.parse.parse_qs(parsed.query)
                raw_syms = (qs.get("symbols", [""])[0] or "").strip()
                nocache = (qs.get("nocache", ["0"])[0] or "0").lower() in ("1", "true", "yes")
                if raw_syms:
                    items: list[dict[str, str] | str] = [s.strip() for s in raw_syms.split(",") if s.strip()]
                else:
                    items = load_watchlist(defaults)
                quotes = providers.fetch_quotes_batch(items, default_provider=default_provider, use_cache=not nocache)
                self._send_json(
                    200,
                    {"quotes": quotes, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                )
                return

            if path == "/api/kline":
                qs = urllib.parse.parse_qs(parsed.query)
                symbol = (qs.get("symbol", [app_config["symbol"]])[0] or app_config["symbol"]).strip()
                provider = (qs.get("provider", [app_config.get("provider", "auto")])[0] or "auto").strip()
                interval = (qs.get("interval", [app_config["interval"]])[0] or app_config["interval"]).strip()
                range_str = (qs.get("range", [app_config["range"]])[0] or app_config["range"]).strip()
                strategy = (qs.get("strategy", [app_config["strategy"]])[0] or app_config["strategy"]).strip()
                nocache = (qs.get("nocache", ["0"])[0] or "0").lower() in ("1", "true", "yes")

                try:
                    raw_data = providers.fetch_ohlcv(
                        symbol_spec=symbol,
                        interval=interval,
                        range_str=range_str,
                        provider=provider,
                        default_provider=default_provider,
                        use_cache=not nocache,
                    )
                    payload = build_kline_payload(raw_data, strategy=strategy, defaults=defaults)
                    self._send_json(200, payload)
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                except Exception as exc:
                    self._send_json(502, {"error": str(exc)})
                return

            if path == "/api/stream":
                if not ws_stream.HAS_WEBSOCKET:
                    self._send_json(503, {"error": "websocket-client not installed"})
                    return
                qs = urllib.parse.parse_qs(parsed.query)
                symbol = (qs.get("symbol", [app_config["symbol"]])[0] or app_config["symbol"]).strip()
                provider = (qs.get("provider", [app_config.get("provider", "auto")])[0] or "auto").strip()
                interval = (qs.get("interval", [app_config["interval"]])[0] or app_config["interval"]).strip()
                range_str = (qs.get("range", [app_config["range"]])[0] or app_config["range"]).strip()
                raw_wl = (qs.get("watchlist", [""])[0] or "").strip()

                try:
                    raw_data = providers.fetch_ohlcv(
                        symbol_spec=symbol,
                        interval=interval,
                        range_str=range_str,
                        provider=provider,
                        default_provider=default_provider,
                        use_cache=True,
                    )
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                except Exception as exc:
                    self._send_json(502, {"error": str(exc)})
                    return

                pair = str(raw_data["symbol"]).upper()
                wl_items = [s.strip() for s in raw_wl.split(",") if s.strip()] if raw_wl else load_watchlist(defaults)
                wl_pairs: list[str] = []
                for it in wl_items:
                    spec = str(it.get("symbol", "") if isinstance(it, dict) else it).strip()
                    if not spec:
                        continue
                    try:
                        p_prov, p_sym = providers.parse_symbol(spec, default_provider=default_provider)
                        if p_prov == "gate" and p_sym not in wl_pairs:
                            wl_pairs.append(p_sym)
                    except Exception:
                        pass
                if pair not in wl_pairs:
                    wl_pairs.append(pair)

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                chan, sid, q = ws_stream.HUB.subscribe(
                    pair=pair,
                    interval=interval,
                    raw_data=raw_data,
                    watchlist_pairs=wl_pairs,
                    precision_fn=_infer_price_precision,
                    tail_ind_fn=lambda closes, tv: compute_tail_indicators(closes, tv, defaults=defaults),
                )
                try:
                    while True:
                        try:
                            event = q.get(timeout=15)
                            line = f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
                        except queue.Empty:
                            line = b": keepalive\n\n"
                        self.wfile.write(line)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    pass
                finally:
                    ws_stream.HUB.unsubscribe(pair, interval, chan, sid)
                return

            self._send_bytes(404, "text/plain; charset=utf-8", b"Not Found")

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/api/watchlist":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    body = self.rfile.read(length) if length > 0 else b"{}"
                    data = json.loads(body.decode("utf-8"))
                    saved = save_watchlist(data.get("symbols") if isinstance(data, dict) else data)
                    self._send_json(200, {"symbols": saved})
                except Exception as exc:
                    self._send_json(400, {"error": str(exc)})
                return

            if path == "/api/shutdown":
                if shutdown_callback is None:
                    self._send_json(404, {"error": "shutdown endpoint disabled"})
                    return
                self._send_json(200, {"ok": True})
                threading.Timer(0.1, shutdown_callback).start()
                return

            self._send_bytes(404, "text/plain; charset=utf-8", b"Not Found")

    return KlineHandler


def cmd_serve(args: argparse.Namespace, defaults: dict[str, Any]) -> None:
    app_config = {
        "mode": "live",
        "title": defaults.get("title", "全市场交互式 K 线看板"),
        "symbol": args.symbol.strip(),
        "provider": args.provider,
        "interval": args.interval,
        "range": args.range,
        "strategy": args.strategy,
        "refresh": args.refresh,
        "ws_enabled": ws_stream.HAS_WEBSOCKET,
        "color_scheme": args.color_scheme,
        "symbols": defaults.get("symbols", []),
    }
    handler_cls = make_handler(defaults, app_config)
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    url = f"http://{args.host}:{args.port}/"
    mode_desc = "WS实时推送" if app_config["ws_enabled"] else f"自动刷新={app_config['refresh']}s"
    print(f"→ 交互式 K 线看板已启动: {url}")
    print(
        f"  默认标的={app_config['symbol']} | 周期={app_config['interval']} | "
        f"{mode_desc} | 策略={app_config['strategy']} | 配色={app_config['color_scheme']}"
    )
    print("  按 Ctrl+C 停止服务。")

    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n→ 服务已停止。")
    finally:
        server.server_close()


def cmd_export(args: argparse.Namespace, defaults: dict[str, Any]) -> None:
    default_provider = defaults.get("default_provider", "gate")
    if args.csv:
        raw_data = providers.load_csv_ohlcv(
            args.csv,
            symbol=args.symbol if args.symbol != defaults.get("default_symbol") else None,
        )
    else:
        raw_data = providers.fetch_ohlcv(
            symbol_spec=args.symbol,
            interval=args.interval,
            range_str=args.range,
            provider=args.provider,
            default_provider=default_provider,
            use_cache=False,
        )

    payload = build_kline_payload(raw_data, strategy=args.strategy, defaults=defaults)
    app_config = {
        "mode": "static",
        "title": defaults.get("title", "全市场交互式 K 线看板"),
        "symbol": payload["meta"]["symbol"],
        "provider": payload["meta"]["provider"],
        "interval": payload["meta"]["interval"],
        "range": payload["meta"]["range"],
        "strategy": args.strategy,
        "refresh": 0,
        "color_scheme": args.color_scheme,
        "symbols": defaults.get("symbols", []),
    }
    html = render_html(app_config, initial_payload=payload, inline_lwc=True)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(
        f"✓ 已导出离线交互 K 线 HTML: {out_path} "
        f"({out_path.stat().st_size:,} bytes, {payload['meta']['bar_count']} 根 K 线, "
        f"{len(payload['markers'])} 个策略信号, 数据源={payload['meta']['provider']})"
    )

    if args.open:
        webbrowser.open(out_path.resolve().as_uri())


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def main() -> None:
    defaults = load_defaults()
    parser = argparse.ArgumentParser(
        description="全市场多源交互式 K 线看板 & 静态 HTML 导出器 (TradingView Lightweight Charts)"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    provider_choices = ["auto", *sorted(providers.VALID_PROVIDERS)]
    color_choices = ["green_up", "red_up"]

    p_serve = sub.add_parser("serve", help="启动本地实时轮询 K 线看板")
    p_serve.add_argument("--symbol", default=defaults.get("default_symbol", "gate:BTC_USDT"), help="默认标的代码 (如 BTC / TAUSDT / gate:TA_USDT)")
    p_serve.add_argument("--provider", default="gate", choices=provider_choices, help="数据源 (默认 gate)")
    p_serve.add_argument("--interval", default=defaults.get("default_interval", "15m"), choices=sorted(providers.VALID_INTERVALS))
    p_serve.add_argument("--range", default=defaults.get("default_range", "auto"), choices=sorted(providers.VALID_RANGES))
    p_serve.add_argument("--strategy", default=defaults.get("default_strategy", "sma_crossover"), choices=sorted(VALID_STRATEGIES))
    p_serve.add_argument("--refresh", type=int, default=int(defaults.get("default_refresh_seconds", 5)), help="自动刷新间隔(秒)，0为暂停")
    p_serve.add_argument("--color-scheme", default=defaults.get("color_scheme", "green_up"), choices=color_choices)
    p_serve.add_argument("--host", default=defaults.get("default_host", "127.0.0.1"))
    p_serve.add_argument("--port", type=int, default=int(defaults.get("default_port", 8766)))
    p_serve.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    p_serve.set_defaults(func=cmd_serve)

    p_exp = sub.add_parser("export", help="导出自包含交互式静态 HTML 文件")
    p_exp.add_argument("--symbol", default=defaults.get("default_symbol", "gate:BTC_USDT"), help="标的代码 (如 BTC / TAUSDT / gate:TA_USDT)")
    p_exp.add_argument("--provider", default="gate", choices=provider_choices, help="数据源 (默认 gate)")
    p_exp.add_argument("--csv", help="可选：从本地 OHLCV CSV 读取行情（替代在线拉取）")
    p_exp.add_argument("--interval", default="1d", choices=sorted(providers.VALID_INTERVALS))
    p_exp.add_argument("--range", default="1y", choices=sorted(providers.VALID_RANGES))
    p_exp.add_argument("--strategy", default=defaults.get("default_strategy", "sma_crossover"), choices=sorted(VALID_STRATEGIES))
    p_exp.add_argument("--color-scheme", default=defaults.get("color_scheme", "green_up"), choices=color_choices)
    p_exp.add_argument("-o", "--output", required=True, help="输出 HTML 文件路径")
    p_exp.add_argument("--open", action="store_true", help="导出后自动在浏览器打开")
    p_exp.set_defaults(func=cmd_export)

    args = parser.parse_args()
    args.func(args, defaults)


if __name__ == "__main__":
    main()
