---
name: kline-chart
description: "加密货币桌面行情客户端与交互式 K 线看板技能（基于 TradingView Lightweight Charts v4.2.3）。支持独立桌面窗口启动、左侧自选标的实时报价列表、Binance / Gate.io / OKX / Alpaca / Yahoo 多源自动路由与无闪烁实时刷新，以及离线单文件静态 HTML 导出。"
license: MIT
---

# K-Line Chart — 加密货币桌面行情客户端与 K 线引擎

基于本地打包的 **TradingView Lightweight Charts v4.2.3** 构建的独立桌面行情客户端与 K 线可视化引擎，零重型前端或 Python 依赖。

---

## 目录结构

```text
skills/kline-chart/
├── SKILL.md                                             ← 本说明文档
├── assets/
│   ├── defaults.json                                    ← 默认自选标的池、周期、刷新间隔与配色
│   └── lightweight-charts.standalone.production.js      ← 本地打包的 Lightweight Charts v4.2.3
└── scripts/
    ├── providers.py                                     ← 统一多市场数据适配器与批量报价引擎
    ├── kline_chart.py                                   ← 终端 UI、HTTP API 服务与离线 HTML 导出 CLI
    └── desktop_app.py                                   ← 独立桌面窗口启动器 (pywebview / Edge App)
```

---

## 支持的数据源与代码路由 (`provider:SYMBOL`)

支持显式指定 `数据源:代码`（如 `gate:TA_USDT`、`binance:BTCUSDT`），也支持直接输入代码自动推断：

| 数据源 (`provider`) | 覆盖市场与资产 | 代码示例 | 鉴权 | 核心特性 |
|---|---|---|---|---|
| `binance` | 加密货币主流现货 | `binance:BTCUSDT`、`binance:ETHUSDT` | 免 Key | 7×24 毫秒级实时（默认走 `data-api.binance.vision`） |
| `gate` | 加密货币全品种现货（含长尾新币） | `gate:TA_USDT`、`gate:SOL_USDT` | 免 Key | 覆盖长尾山寨币种，并作为 `binance` 未收录币种的自动回退源 |
| `okx` | 加密货币现货 | `okx:BTC-USDT`、`okx:ETH-USDT` | 免 Key | 7×24 毫秒级实时 |
| `yahoo` | 现货 ETF、加密概念股与期货 | `yahoo:IBIT`、`yahoo:COIN`、`yahoo:MSTR` | 免 Key | 覆盖美股合规加密敞口标的 |
| `eastmoney` | 沪深北 A 股与港股 | `eastmoney:600519`、`00700.HK` | 免 Key | 盘中实时、支持前复权 (`qfq`) |
| `alpaca` | 美股与 Alpaca 加密交易对 | `alpaca:BTC/USD`、`alpaca:NVDA` | 需环境变量 Key | 读取 `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` |
| `csv` | 本地历史行情或回测导出文件 | `--csv path/to/ohlcv.csv` | 离线 | 自动兼容常见 OHLCV 列名 |

**自动推断与容错回退规则（省略前缀时）**：
- `*USDT` / `*USDC`（无连字符，如 `BTCUSDT`、`TAUSDT`） → 优先路由到 `binance`；若 Binance 未收录（如 `TAUSDT`），自动回退至 `gate` 并标注 `gate(auto)`
- `*-USDT` / `*-USDC` → 自动路由到 `okx`
- `*_USDT` / `*_USDC` → 可直接指定 `gate:TA_USDT`
- 含 `/` 代码（如 `BTC/USD`） → 自动路由到 `alpaca`
- `*.SH` / `*.SZ` / `*.BJ` 或 6 位代码 → 自动路由到 `eastmoney`
- 其余代码 → 走 `defaults.json` 中的 `default_provider`

---

## 快速上手 (Quick Start)

### 1. 启动独立桌面行情客户端（推荐）

双击仓库根目录的 `launch_client.bat`，或在终端执行：

```bash
# 启动独立桌面窗口（自动适配 pywebview 或无地址栏 Edge/Chrome App 窗口）
python skills/kline-chart/scripts/desktop_app.py

# 启动时直接定位到指定标的与周期
python skills/kline-chart/scripts/desktop_app.py --symbol gate:TA_USDT --interval 15m
```

桌面客户端内置特性：
- **左侧自选标的面板**：并发拉取并展示所有自选标的的最新价格与 24h 涨跌幅，点击秒切 K 线；支持通过输入框添加任意标的（如 `TAUSDT`、`SOLUSDT`）及移除标的，自选配置自动持久化至用户目录 `~/.crypto_quant_watchlist.json`。
- **自适应价格精度**：自动按标的价格量级切换 `2`~`6` 位小数精度，低价币种（如 `0.11938`）坐标与读数清晰准确。
- **生命周期托管**：关闭桌面窗口时自动停止后台本地服务并清理临时运行目录。

### 2. 浏览器看板模式 (`serve`) 与静态 HTML 导出 (`export`)

```bash
# 仅启动本地 HTTP 看板服务（默认端口 8765）
python skills/kline-chart/scripts/kline_chart.py serve

# 导出单文件离线交互 K 线 HTML（内嵌 Lightweight Charts 与数据）
python skills/kline-chart/scripts/kline_chart.py export --symbol gate:TA_USDT --interval 1h --range 1mo -o D:/empty/ta_kline.html

# 从本地 OHLCV CSV 文件直接导出交互 K 线（完全离线）
python skills/kline-chart/scripts/kline_chart.py export --csv data/ohlcv.csv -o D:/empty/local.html
```

---

## 核心交互功能

- **多周期**：`1m`、`5m`、`15m`、`1h`、`4h`、`1d`、`1wk`。
- **主图叠加**：`SMA20`、`SMA60`、布林带 `(20, 2.0)`、成交量柱状图（可一键显隐）。
- **策略买卖点标记（严格多头交替）**：`none`、`sma_crossover`、`bbands_contrarian`、`rsi_meanrev`、`macd_crossover`。
- **绿涨红跌 / 红涨绿跌一键切换**：工具栏实时切换配色并同步自选列表涨跌幅颜色。
- **无闪烁增量刷新**：同一标的自动轮询时保留当前缩放与平移视口，仅对最后一根 K 线调用 `series.update()`。

---

## 依赖说明

仅依赖 Python 3.10+ 标准库与 `requests`（缺少 `requests` 时自动回退 `urllib.request`），桌面窗口自动适配本机 Edge/Chrome App 模式或可选 `pywebview`，**无需 `scipy`、`matplotlib` 或 `plotly`**。
