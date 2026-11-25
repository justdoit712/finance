---
name: kline-chart
description: "黄金与白银交互式 K 线看板及离线静态 HTML 导出技能（基于 TradingView Lightweight Charts v4.2.3）。支持 COMEX 金银期货、伦敦金银现货、海外贵金属 ETF、国内场内金银 ETF（东方财富前复权）、24h 链上锚定黄金代币（Binance / OKX）及本地历史 K 线 CSV，提供无闪烁定时刷新、均线/布林带/策略买卖点叠加与绿涨红跌/红涨绿跌一键切换。"
license: MIT
---

# K-Line Chart — 黄金白银交互式 K 线看板

基于本地打包的 **TradingView Lightweight Charts v4.2.3** 构建的贵金属专属 K 线可视化工具，零重型前端或 Python 依赖。

---

## 目录结构

```text
skills/kline-chart/
├── SKILL.md                                             ← 本说明文档
├── assets/
│   ├── defaults.json                                    ← 贵金属默认标的池、周期、刷新频率与配色
│   └── lightweight-charts.standalone.production.js      ← 本地打包的 Lightweight Charts v4.2.3
└── scripts/
    ├── providers.py                                     ← 贵金属多源行情适配器（5 个数据源）
    └── kline_chart.py                                   ← 实时看板服务 + 静态 HTML 导出 CLI
```

---

## 支持的贵金属数据源 (`provider:SYMBOL`)

| 数据源 (`provider`) | 覆盖贵金属品种 | 代码示例 | 鉴权 | 核心特性 |
|---|---|---|---|---|
| `yahoo` | COMEX 期货、伦敦现货、海外 ETF 及金矿股 | `yahoo:GC=F`、`yahoo:SI=F`、`yahoo:XAUUSD=X`、`yahoo:GLD`、`yahoo:SLV`、`yahoo:GDX` | 免 Key | 国际金银基准核心数据源 |
| `eastmoney` | 国内场内黄金/白银 ETF 与 LOF 基金 | `eastmoney:518880`、`eastmoney:159934.SZ`、`eastmoney:161226` | 免 Key | 盘中实时、支持前复权 (`qfq`) 与中文名称 |
| `binance` | 24h 链上锚定黄金代币 (`PAXGUSDT`) | `binance:PAXGUSDT` | 免 Key | 7×24 小时无休连续金价参考 |
| `okx` | 24h 链上锚定黄金代币 (`XAUT-USDT`) | `okx:XAUT-USDT` | 免 Key | 7×24 小时无休连续金价参考 |
| `csv` | 本地历史 K 线 / OHLCV 序列文件 | `--csv data/GC=F_historical.csv` | 离线 | 兼容标准 OHLCV 列名 |

**自动推断规则（省略前缀时）**：
- `*.SH` / `*.SZ` / `*.BJ` 或 6 位国内基金代码（如 `518880`、`159934`） → 自动路由到 `eastmoney`
- `PAXGUSDT` 等无连字符 `USDT`/`USDC` 锚定代币 → 自动路由到 `binance`
- `XAUT-USDT` 等带连字符代币 → 自动路由到 `okx`
- 其余代码（`GC=F`、`SI=F`、`XAUUSD=X`、`GLD`、`SLV`、`GDX`） → 默认走 `yahoo`

---

## 快速上手 (Quick Start)

### 1. 启动黄金白银实时交互看板

```bash
# 默认启动：COMEX 黄金 (GC=F) 1 小时线，每 15 秒自动刷新，叠加双均线交叉信号
python skills/kline-chart/scripts/kline_chart.py serve

# 看伦敦金现货 15 分钟线，叠加布林带反转信号
python skills/kline-chart/scripts/kline_chart.py serve --symbol yahoo:XAUUSD=X --interval 15m --strategy bbands_contrarian

# 看国内黄金 ETF（518880），启用红涨绿跌配色
python skills/kline-chart/scripts/kline_chart.py serve --symbol eastmoney:518880 --interval 1d --color-scheme red_up

# 周末/盘后看 24 小时链上锚定黄金 (PAXGUSDT)，每 5 秒刷新
python skills/kline-chart/scripts/kline_chart.py serve --symbol binance:PAXGUSDT --interval 15m --refresh 5
```

### 2. 导出单文件离线静态 HTML

```bash
# 导出 COMEX 黄金近 1 年日线交互 K 线
python skills/kline-chart/scripts/kline_chart.py export --symbol yahoo:GC=F --interval 1d --range 1y -o D:/empty/gc_kline.html

# 从本地历史 K 线 CSV 直接导出交互图表（完全离线）
python skills/kline-chart/scripts/kline_chart.py export --csv data/GC=F_historical.csv -o D:/empty/gc_local.html
```

---

## 核心交互功能

- **多周期**：`1m`、`5m`、`15m`、`1h`、`4h`（Binance/OKX 支持）、`1d`、`1wk`。
- **主图叠加**：`SMA20`、`SMA60`、布林带 `(20, 2.0)`、成交量柱状图（可一键显隐）。
- **策略买卖点标记（严格多头交替）**：`none`、`sma_crossover`、`bbands_contrarian`、`rsi_meanrev`、`macd_crossover`。
- **国内外配色切换**：工具栏一键切换**绿涨红跌**（国际金银习惯）与**红涨绿跌**（国内 ETF 习惯）。
- **无闪烁增量刷新**：自动轮询时保留当前缩放与平移视口，仅对最后一根 K 线调用 `series.update()`。

---

## 依赖说明

仅依赖 Python 3.10+ 标准库与 `requests`（缺少 `requests` 时自动回退 `urllib.request`），**无需 `scipy`、`matplotlib` 或 `plotly`**。
