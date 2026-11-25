"""
kline_chart.py — 黄金白银交互式 K 线看板 & 离线静态 HTML 导出器。

基于本地打包的 TradingView Lightweight Charts v4.2.3，通过 providers.py 支持
COMEX 金银期货 (GC=F/SI=F)、伦敦金银现货 (XAUUSD=X/XAGUSD=X)、海外 ETF
(GLD/SLV/GDX)、国内黄金白银基金 (518880/159934/161226)、24h 链上锚定金
(PAXGUSDT/XAUT-USDT) 与本地 OHLCV CSV。

用法:
    # 启动本地实时交互看板（默认 GC=F 1h，每 15 秒自动刷新）
    python skills/kline-chart/scripts/kline_chart.py serve

    # 指定标的、周期与配色（如国内黄金 ETF 红涨绿跌）
    python skills/kline-chart/scripts/kline_chart.py serve --symbol eastmoney:518880 --interval 1d --color-scheme red_up
    python skills/kline-chart/scripts/kline_chart.py serve --symbol binance:PAXGUSDT --interval 15m --refresh 5

    # 导出单文件交互式静态 HTML（内嵌 Lightweight Charts 与数据，可离线分享）
    python skills/kline-chart/scripts/kline_chart.py export --symbol yahoo:GC=F --interval 1d --range 1y -o D:/empty/gc_kline.html
    python skills/kline-chart/scripts/kline_chart.py export --csv data/GC=F_historical.csv -o D:/empty/gc_local.html
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import urllib.parse
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from . import providers
except (ImportError, ValueError):
    import providers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, Exception):
    pass

SKILL_DIR = SCRIPT_DIR.parent
ASSETS_DIR = SKILL_DIR / "assets"
LWC_JS_PATH = ASSETS_DIR / "lightweight-charts.standalone.production.js"
DEFAULTS_PATH = ASSETS_DIR / "defaults.json"

VALID_STRATEGIES = {
    "none",
    "sma_crossover",
    "bbands_contrarian",
    "rsi_meanrev",
    "macd_crossover",
}


def load_defaults() -> dict[str, Any]:
    if DEFAULTS_PATH.exists():
        with open(DEFAULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "title": "国际金银现货与期货 K 线看板",
        "default_symbol": "XAUUSD",
        "default_provider": "yahoo",
        "default_interval": "1h",
        "default_range": "auto",
        "default_strategy": "sma_crossover",
        "default_refresh_seconds": 15,
        "color_scheme": "green_up",
        "default_host": "127.0.0.1",
        "default_port": 8765,
        "symbols": [
            {"symbol": "XAUUSD", "label": "伦敦金现货"},
            {"symbol": "XAGUSD", "label": "伦敦银现货"},
            {"symbol": "yahoo:GC=F", "label": "COMEX 黄金"},
            {"symbol": "yahoo:SI=F", "label": "COMEX 白银"},
            {"symbol": "yahoo:MGC=F", "label": "微型金期货"},
            {"symbol": "yahoo:SIL=F", "label": "微型银期货"},
            {"symbol": "yahoo:GLD", "label": "黄金ETF"},
            {"symbol": "yahoo:SLV", "label": "白银ETF"},
            {"symbol": "yahoo:GDX", "label": "金矿ETF"},
            {"symbol": "binance:PAXGUSDT", "label": "24h锚定金"},
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

    return {
        "meta": {
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
            "last_price": round(last_price, 4),
            "prev_close": round(prev_close, 4),
            "change": round(change, 4),
            "change_pct": round(change_pct, 2),
            "bar_count": len(bars),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": raw_data.get("source", raw_data.get("provider", "yahoo")),
        },
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


# ── 前端交互页面 HTML 模板 ────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>__PAGE_TITLE__</title>
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
    .brand { font-weight: 700; color: var(--accent); letter-spacing: 0.3px; margin-right: 4px; white-space: nowrap; }
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
    input[type="text"] { width: 145px; }
    label.chk {
      display: inline-flex; align-items: center; gap: 4px; cursor: pointer;
      padding: 2px 6px; border-radius: 4px; user-select: none;
    }
    label.chk:hover { background: #2a2e39; }
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
      <span class="brand" id="brand-title">__PAGE_TITLE__</span>
      <div class="group" id="symbol-buttons"></div>
      <div class="group">
        <select id="provider-select" title="数据源适配器">
          <option value="auto">源: 自动推断</option>
          <option value="yahoo">Yahoo (COMEX期货/ETF)</option>
          <option value="eastmoney">国际现货/期货实时 (XAU/COMEX)</option>
          <option value="binance">Binance 24h锚定金</option>
          <option value="okx">OKX 24h锚定金</option>
        </select>
        <input type="text" id="custom-symbol" placeholder="代码如 XAUUSD / GC=F / GCG27.CMX" />
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
        <select id="refresh-select" title="自动刷新间隔">
          <option value="0">刷新: 暂停</option>
          <option value="5">刷新: 5s</option>
          <option value="15">刷新: 15s</option>
          <option value="30">刷新: 30s</option>
          <option value="60">刷新: 60s</option>
        </select>
        <button id="btn-refresh">立即刷新</button>
        <button id="btn-color-scheme" title="切换绿涨红跌 / 红涨绿跌">绿涨红跌</button>
        <button id="btn-fit" title="重置缩放适应全屏">适应屏幕</button>
      </div>
    </div>

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

    <div class="hint-footer">
      <span>国际金银核心标的: 现货 XAUUSD / XAGUSD | COMEX期货 GC=F / SI=F / MGC=F / 月合约(.CMX) | ETF GLD / SLV / GDX</span>
      <span id="meta-summary">--</span>
    </div>
  </div>

  __LWC_SCRIPT_TAG__
  <script>
    const APP_CONFIG = __APP_CONFIG_JSON__;
    const INITIAL_PAYLOAD = __INITIAL_PAYLOAD_JSON__;

    const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d", "1wk"];
    const state = {
      symbol: APP_CONFIG.symbol,
      provider: APP_CONFIG.provider || "auto",
      interval: APP_CONFIG.interval,
      range: APP_CONFIG.range,
      strategy: APP_CONFIG.strategy,
      refreshSec: Number(APP_CONFIG.refresh || 0),
      colorScheme: APP_CONFIG.color_scheme || "green_up",
      isStatic: APP_CONFIG.mode === "static",
      lastKey: "",
      lastPayload: null,
      lastCrosshairBar: null,
      lastCrosshairVol: null,
      timerId: null,
      loading: false,
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
    }

    function renderToolbar() {
      const symBox = document.getElementById("symbol-buttons");
      symBox.innerHTML = "";
      (APP_CONFIG.symbols || []).forEach((item) => {
        const btn = document.createElement("button");
        btn.textContent = item.label;
        btn.title = item.symbol;
        if (item.symbol.toUpperCase() === state.symbol.toUpperCase()) btn.classList.add("active");
        if (state.isStatic) btn.disabled = true;
        btn.onclick = () => {
          state.symbol = item.symbol;
          state.provider = "auto";
          document.getElementById("custom-symbol").value = "";
          renderToolbar();
          fetchAndRender(false);
        };
        symBox.appendChild(btn);
      });

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

      document.getElementById("provider-select").value = state.provider;
      document.getElementById("provider-select").disabled = state.isStatic;
      document.getElementById("range-select").value = state.range;
      document.getElementById("range-select").disabled = state.isStatic;
      document.getElementById("strategy-select").value = state.strategy;
      document.getElementById("strategy-select").disabled = state.isStatic;
      document.getElementById("refresh-select").value = String(state.refreshSec);
      document.getElementById("refresh-select").disabled = state.isStatic;
      document.getElementById("custom-symbol").disabled = state.isStatic;
      document.getElementById("btn-load-symbol").disabled = state.isStatic;
      document.getElementById("btn-refresh").disabled = state.isStatic;
    }

    function updateLegend(bar, volBar) {
      if (!bar) return;
      const cls = bar.close >= bar.open ? "up" : "down";
      const volTxt = volBar && volBar.value ? Number(volBar.value).toLocaleString() : "-";
      document.getElementById("ohlcv-legend").innerHTML =
        `<span><b>O</b><span class="${cls}">${bar.open}</span></span>` +
        `<span><b>H</b><span class="${cls}">${bar.high}</span></span>` +
        `<span><b>L</b><span class="${cls}">${bar.low}</span></span>` +
        `<span><b>C</b><span class="${cls}">${bar.close}</span></span>` +
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

      const priceEl = document.getElementById("hdr-price");
      const chgEl = document.getElementById("hdr-change");
      const upDown = meta.change >= 0 ? "up" : "down";
      const sign = meta.change >= 0 ? "+" : "";
      priceEl.textContent = `${meta.last_price} ${meta.currency || ""}`.trim();
      priceEl.className = `price-big ${upDown}`;
      chgEl.textContent = `${sign}${meta.change} (${sign}${meta.change_pct}%)`;
      chgEl.className = upDown;

      document.getElementById("meta-summary").textContent =
        `K线: ${meta.bar_count} 根 | 信号: ${payload.markers.length} 次 | 数据源: ${meta.source} | 更新于: ${meta.updated_at}`;

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
      updateLegend(newCandles[newCandles.length - 1], volColored[volColored.length - 1]);
      applyVisibility();

      if (state.isStatic) setLiveStatus("static", `静态快照 (${meta.updated_at})`);
      else if (state.refreshSec > 0) setLiveStatus("", `实时轮询中 · 每 ${state.refreshSec}s · ${meta.updated_at}`);
      else setLiveStatus("paused", `已暂停自动刷新 · ${meta.updated_at}`);
    }

    async function fetchAndRender(isTimerRefresh) {
      if (state.isStatic || state.loading) return;
      state.loading = true;
      try {
        const qs = new URLSearchParams({
          symbol: state.symbol,
          provider: state.provider,
          interval: state.interval,
          range: state.range,
          strategy: state.strategy,
        });
        const resp = await fetch(`/api/kline?${qs.toString()}`);
        const data = await resp.json();
        if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);
        applyPayload(data, isTimerRefresh);
      } catch (err) {
        setLiveStatus("error", `拉取失败: ${err.message}`);
        showError(`拉取 ${state.symbol} 失败: ${err.message}`);
      } finally {
        state.loading = false;
      }
    }

    function resetTimer() {
      if (state.timerId) { clearInterval(state.timerId); state.timerId = null; }
      if (!state.isStatic && state.refreshSec > 0) {
        state.timerId = setInterval(() => fetchAndRender(true), state.refreshSec * 1000);
      }
    }

    document.getElementById("btn-load-symbol").onclick = () => {
      const val = document.getElementById("custom-symbol").value.trim();
      if (!val) return;
      state.symbol = val;
      state.provider = document.getElementById("provider-select").value;
      renderToolbar();
      fetchAndRender(false);
    };
    document.getElementById("custom-symbol").addEventListener("keydown", (e) => {
      if (e.key === "Enter") document.getElementById("btn-load-symbol").click();
    });
    document.getElementById("provider-select").onchange = (e) => {
      state.provider = e.target.value;
      fetchAndRender(false);
    };
    document.getElementById("range-select").onchange = (e) => { state.range = e.target.value; fetchAndRender(false); };
    document.getElementById("strategy-select").onchange = (e) => { state.strategy = e.target.value; fetchAndRender(false); };
    document.getElementById("refresh-select").onchange = (e) => {
      state.refreshSec = Number(e.target.value);
      resetTimer();
      if (state.lastPayload) {
        if (state.refreshSec > 0) setLiveStatus("", `实时轮询中 · 每 ${state.refreshSec}s · ${state.lastPayload.meta.updated_at}`);
        else setLiveStatus("paused", `已暂停自动刷新 · ${state.lastPayload.meta.updated_at}`);
      }
    };
    document.getElementById("btn-refresh").onclick = () => fetchAndRender(true);
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
    if (INITIAL_PAYLOAD) applyPayload(INITIAL_PAYLOAD, false);
    else fetchAndRender(false);
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

    title = app_config.get("title") or "黄金白银交互 K 线看板"
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

def make_handler(defaults: dict[str, Any], app_config: dict[str, Any]):
    default_provider = defaults.get("default_provider", "yahoo")

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

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/":
                html = render_html(app_config, initial_payload=None, inline_lwc=False)
                self._send_bytes(200, "text/html; charset=utf-8", html.encode("utf-8"))
                return

            if path == "/assets/lightweight-charts.standalone.production.js":
                if not LWC_JS_PATH.exists():
                    self._send_bytes(404, "text/plain; charset=utf-8", b"Lightweight Charts bundle not found")
                    return
                self._send_bytes(200, "application/javascript; charset=utf-8", LWC_JS_PATH.read_bytes())
                return

            if path == "/api/kline":
                qs = urllib.parse.parse_qs(parsed.query)
                symbol = (qs.get("symbol", [app_config["symbol"]])[0] or app_config["symbol"]).strip()
                provider = (qs.get("provider", [app_config.get("provider", "auto")])[0] or "auto").strip()
                interval = (qs.get("interval", [app_config["interval"]])[0] or app_config["interval"]).strip()
                range_str = (qs.get("range", [app_config["range"]])[0] or app_config["range"]).strip()
                strategy = (qs.get("strategy", [app_config["strategy"]])[0] or app_config["strategy"]).strip()

                try:
                    raw_data = providers.fetch_ohlcv(
                        symbol_spec=symbol,
                        interval=interval,
                        range_str=range_str,
                        provider=provider,
                        default_provider=default_provider,
                    )
                    payload = build_kline_payload(raw_data, strategy=strategy, defaults=defaults)
                    self._send_bytes(
                        200,
                        "application/json; charset=utf-8",
                        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    )
                except ValueError as exc:
                    self._send_bytes(
                        400,
                        "application/json; charset=utf-8",
                        json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"),
                    )
                except Exception as exc:
                    self._send_bytes(
                        502,
                        "application/json; charset=utf-8",
                        json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"),
                    )
                return

            self._send_bytes(404, "text/plain; charset=utf-8", b"Not Found")

    return KlineHandler


def cmd_serve(args: argparse.Namespace, defaults: dict[str, Any]) -> None:
    app_config = {
        "mode": "live",
        "title": defaults.get("title", "黄金白银交互 K 线看板"),
        "symbol": args.symbol.strip(),
        "provider": args.provider,
        "interval": args.interval,
        "range": args.range,
        "strategy": args.strategy,
        "refresh": args.refresh,
        "color_scheme": args.color_scheme,
        "symbols": defaults.get("symbols", []),
    }
    handler_cls = make_handler(defaults, app_config)
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    url = f"http://{args.host}:{args.port}/"
    print(f"→ 黄金白银交互式 K 线看板已启动: {url}")
    print(
        f"  默认标的={app_config['symbol']} | 周期={app_config['interval']} | "
        f"自动刷新={app_config['refresh']}s | 策略={app_config['strategy']} | 配色={app_config['color_scheme']}"
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
    default_provider = defaults.get("default_provider", "yahoo")
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
        "title": defaults.get("title", "黄金白银交互 K 线看板"),
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
        description="黄金白银交互式 K 线看板 & 静态 HTML 导出器 (TradingView Lightweight Charts)"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    provider_choices = ["auto", *sorted(providers.VALID_PROVIDERS)]
    color_choices = ["green_up", "red_up"]

    p_serve = sub.add_parser("serve", help="启动本地实时轮询 K 线看板")
    p_serve.add_argument("--symbol", default=defaults.get("default_symbol", "XAUUSD"), help="默认国际金银代码 (支持 provider:SYMBOL)")
    p_serve.add_argument("--provider", default="auto", choices=provider_choices, help="强制数据源或 auto 自动推断")
    p_serve.add_argument("--interval", default=defaults.get("default_interval", "1h"), choices=sorted(providers.VALID_INTERVALS))
    p_serve.add_argument("--range", default=defaults.get("default_range", "auto"), choices=sorted(providers.VALID_RANGES))
    p_serve.add_argument("--strategy", default=defaults.get("default_strategy", "sma_crossover"), choices=sorted(VALID_STRATEGIES))
    p_serve.add_argument("--refresh", type=int, default=int(defaults.get("default_refresh_seconds", 15)), help="自动刷新间隔(秒)，0为暂停")
    p_serve.add_argument("--color-scheme", default=defaults.get("color_scheme", "green_up"), choices=color_choices)
    p_serve.add_argument("--host", default=defaults.get("default_host", "127.0.0.1"))
    p_serve.add_argument("--port", type=int, default=int(defaults.get("default_port", 8765)))
    p_serve.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    p_serve.set_defaults(func=cmd_serve)

    p_exp = sub.add_parser("export", help="导出自包含交互式静态 HTML 文件")
    p_exp.add_argument("--symbol", default=defaults.get("default_symbol", "XAUUSD"), help="国际金银代码 (支持 provider:SYMBOL)")
    p_exp.add_argument("--provider", default="auto", choices=provider_choices, help="强制数据源或 auto 自动推断")
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
