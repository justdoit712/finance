---
name: kline-chart
description: "全市场交互式 K 线看板与离线静态 HTML 导出技能（基于 TradingView Lightweight Charts v4.2.3）。原生适配美股/港股/A股（Yahoo Finance / 东方财富）、贵金属大宗商品、加密货币（Binance / OKX / Alpaca）及本地 CSV 数据，支持无闪烁定时实时刷新、均线/布林带/策略买卖点叠加与绿涨红跌/红涨绿跌一键切换。"
license: MIT
---

# K-Line Chart — 全市场交互式 K 线看板底座

基于本地打包的 **TradingView Lightweight Charts v4.2.3** 构建的通用 K 线可视化引擎，零重型前端或 Python 依赖。不同业务分支只需定制 `assets/defaults.json` 即可复用同一套核心代码。

---

## 目录结构

```text
skills/kline-chart/
├── SKILL.md                                             ← 本说明文档
├── assets/
│   ├── defaults.json                                    ← 分支专属配置（标题/默认标的/数据源/配色）
│   └── lightweight-charts.standalone.production.js      ← 本地打包的 Lightweight Charts v4.2.3
└── scripts/
    ├── providers.py                                     ← 统一多市场数据适配器（6 个数据源）
    └── kline_chart.py                                   ← 实时看板服务 + 静态 HTML 导出 CLI
```

---

## 支持的数据源与代码路由 (`provider:SYMBOL`)

支持显式指定 `数据源:代码`（如 `eastmoney:600519`、`binance:BTCUSDT`），也支持直接输入代码自动推断：

| 数据源 (`provider`) | 覆盖市场与资产 | 代码示例 | 鉴权 | 核心特性 |
|---|---|---|---|---|
| `yahoo` | 美股、ETF、港股、COMEX 期货、外汇现货 | `yahoo:AAPL`、`yahoo:GC=F`、`yahoo:0700.HK` | 免 Key | 全球资产覆盖面最广 |
| `eastmoney` | 沪深北 A 股（含场内 ETF）、港股 | `eastmoney:600519`、`300750.SZ`、`00700.HK` | 免 Key | 盘中实时、支持前复权 (`qfq`) 与中文名称 |
| `binance` | 加密货币现货、黄金代币 (`PAXGUSDT`) | `binance:BTCUSDT`、`binance:PAXGUSDT` | 免 Key | 7×24 毫秒级实时（默认走 `data-api.binance.vision`） |
| `okx` | 加密货币现货、黄金代币 (`XAUT-USDT`) | `okx:BTC-USDT`、`okx:XAUT-USDT` | 免 Key | 7×24 毫秒级实时 |
| `alpaca` | 美股与 Alpaca 加密交易对 | `alpaca:BTC/USD`、`alpaca:NVDA` | 需环境变量 Key | 读取 `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` |
| `csv` | 本地历史行情或回测导出文件 | `--csv path/to/ohlcv.csv` | 离线 | 自动兼容常见 OHLCV 列名 |

**自动推断规则（省略前缀时）**：
- `*.SH` / `*.SZ` / `*.BJ` 或 6 位 A 股/ETF 代码 → 自动路由到 `eastmoney`
- `*USDT` / `*USDC`（无连字符） → 自动路由到 `binance`
- `*-USDT` / `*-USDC` → 自动路由到 `okx`
- 含 `/` 代码（如 `BTC/USD`） → 自动路由到 `alpaca`
- 其余代码 → 走 `defaults.json` 中的 `default_provider`（默认 `yahoo`）

---

## 快速上手 (Quick Start)

### 1. 启动本地实时交互看板

```bash
# 按当前分支 defaults.json 默认配置启动
python skills/kline-chart/scripts/kline_chart.py serve

# 看 A 股茅台日线（东方财富前复权，自动启用红涨绿跌）
python skills/kline-chart/scripts/kline_chart.py serve --symbol eastmoney:600519 --interval 1d --color-scheme red_up

# 看比特币 15 分钟线（Binance 7×24 实时，每 5 秒自动刷新）
python skills/kline-chart/scripts/kline_chart.py serve --symbol binance:BTCUSDT --interval 15m --refresh 5

# 看 COMEX 黄金 1 小时线并叠加布林带反转信号
python skills/kline-chart/scripts/kline_chart.py serve --symbol yahoo:GC=F --interval 1h --strategy bbands_contrarian
```

### 2. 导出单文件离线静态 HTML

```bash
# 导出苹果近 1 年日线交互 K 线
python skills/kline-chart/scripts/kline_chart.py export --symbol yahoo:AAPL --interval 1d --range 1y -o D:/empty/aapl.html

# 从本地 OHLCV CSV 文件直接导出交互 K 线（完全离线）
python skills/kline-chart/scripts/kline_chart.py export --csv data/ohlcv.csv -o D:/empty/local.html
```

---

## 核心交互功能

- **多周期**：`1m`、`5m`、`15m`、`1h`、`4h`（Binance/OKX/Alpaca 支持）、`1d`、`1wk`。
- **主图叠加**：`SMA20`、`SMA60`、布林带 `(20, 2.0)`、成交量柱状图（可一键显隐）。
- **策略买卖点标记（严格多头交替）**：`none`、`sma_crossover`、`bbands_contrarian`、`rsi_meanrev`、`macd_crossover`。
- **A股/美股配色一键切换**：工具栏支持实时切换**绿涨红跌**与**红涨绿跌**。
- **无闪烁增量刷新**：同一标的自动轮询时保留当前缩放与平移视口，仅对最后一根 K 线调用 `series.update()`。

---

## 依赖说明

仅依赖 Python 3.10+ 标准库与 `requests`（缺少 `requests` 时自动回退 `urllib.request`），**无需 `scipy`、`matplotlib` 或 `plotly`**。
