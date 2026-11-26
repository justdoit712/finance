---
name: kline-chart
description: "加密货币桌面行情客户端与交互式 K 线看板技能（基于 TradingView Lightweight Charts v4.2.3 + Gate.io 现货公开 API）。支持独立桌面窗口启动、左侧自选标的实时报价列表、免 Key 实时刷新与离线单文件静态 HTML 导出。"
license: MIT
---

# K-Line Chart — 加密货币桌面行情客户端与 K 线引擎

基于本地打包的 **TradingView Lightweight Charts v4.2.3** 与 **Gate.io 公开现货 API**（免 Key，覆盖 2,100+ 主流与山寨币种）构建的独立桌面行情客户端。

---

## 目录结构

```text
skills/kline-chart/
├── SKILL.md                                             ← 本说明文档
├── assets/
│   ├── defaults.json                                    ← 默认自选币种、周期、刷新间隔与配色
│   └── lightweight-charts.standalone.production.js      ← 本地打包的 Lightweight Charts v4.2.3
└── scripts/
    ├── providers.py                                     ← Gate.io 现货行情适配器与批量报价引擎
    ├── kline_chart.py                                   ← 终端 UI、HTTP API 服务与离线 HTML 导出 CLI
    └── desktop_app.py                                   ← 独立桌面窗口启动器 (pywebview / Edge App)
```

---

## 数据源与代码输入格式

在线行情统一使用 **Gate.io 现货公开接口**（无需任何 API Key，限频 200 次 / 10 秒），同时支持导出时读取本地 `--csv` 历史文件：

| 输入写法 | 自动标准化结果 | 说明 |
|---|---|---|
| `BTC` / `TA` / `SOL` | `BTC_USDT` / `TA_USDT` / `SOL_USDT` | 省略计价币时默认补全 `_USDT` |
| `BTCUSDT` / `TAUSDT` | `BTC_USDT` / `TA_USDT` | 自动拆分常见计价后缀（`USDT`/`USDC`/`BTC`/`ETH`） |
| `TA-USDT` / `TA/USDT` / `TA_USDT` | `TA_USDT` | 兼容常见分隔符与 `gate:TA_USDT` 前缀 |
| `--csv path/to/ohlcv.csv` | 本地 CSV | 仅 `export` 离线导出使用 |

---

## 快速上手 (Quick Start)

### 1. 启动独立桌面行情客户端（推荐）

双击仓库根目录的 `launch_client.bat`，或在终端执行：

```bash
# 启动独立桌面窗口（自动适配 pywebview 或无地址栏 Edge/Chrome App 窗口）
python skills/kline-chart/scripts/desktop_app.py

# 启动时直接定位到指定币种与周期
python skills/kline-chart/scripts/desktop_app.py --symbol TAUSDT --interval 15m
```

桌面客户端内置特性：
- **左侧自选标的面板**：并发拉取并展示所有自选币种的最新价格与 24h 涨跌幅，点击秒切 K 线；支持通过输入框添加任意币种（如 `TA`、`TAUSDT`、`SOLUSDT`）及移除币种，配置持久化至 `~/.crypto_quant_watchlist.json`。
- **自适应价格精度**：自动按币价量级切换 `2`~`6` 位小数精度，低价山寨币（如 `0.11938`）坐标与读数清晰准确。
- **生命周期托管**：关闭桌面窗口时自动停止后台本地服务并清理临时运行目录。

### 2. 浏览器看板模式 (`serve`) 与静态 HTML 导出 (`export`)

```bash
# 仅启动本地 HTTP 看板服务
python skills/kline-chart/scripts/kline_chart.py serve

# 导出单文件离线交互 K 线 HTML（内嵌 Lightweight Charts 与数据）
python skills/kline-chart/scripts/kline_chart.py export --symbol TAUSDT --interval 1h --range 1mo -o D:/empty/ta_kline.html

# 从本地 OHLCV CSV 文件直接导出交互 K 线（完全离线）
python skills/kline-chart/scripts/kline_chart.py export --csv data/ohlcv.csv -o D:/empty/local.html
```

---

## 核心交互功能

- **多周期**：`5m`、`15m`、`30m`、`1h`、`4h`、`1d`、`1wk`。
- **主图叠加**：`SMA20`、`SMA60`、布林带 `(20, 2.0)`、成交量柱状图（可一键显隐）。
- **策略买卖点标记（严格多头交替）**：`none`、`sma_crossover`、`bbands_contrarian`、`rsi_meanrev`、`macd_crossover`。
- **绿涨红跌 / 红涨绿跌一键切换**：工具栏实时切换配色并同步自选列表涨跌幅颜色。
- **无闪烁增量刷新**：默认通过 Python 后台接入 Gate.io WebSocket v4（`spot.candlesticks` + `spot.trades` + `spot.tickers`）并经 `/api/stream` (SSE) 向前端浏览器推送毫秒级跳价与指标更新；断线时自动指数退避重连并降级至 `1s` REST 轮询。

---

## 依赖说明

依赖 Python 3.10+ 标准库、`requests`（缺少 `requests` 时自动回退 `urllib.request`）以及 `websocket-client`（用于实时 WebSocket 行情推送；未安装时自动回退 HTTP 轮询），桌面窗口自动适配本机 Edge/Chrome App 模式或可选 `pywebview`，**无需 `scipy`、`matplotlib` 或 `plotly`**。
