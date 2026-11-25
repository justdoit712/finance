---
name: kline-chart
description: "国际黄金与白银现货、COMEX 期货交互式 K 线看板及离线静态 HTML 导出技能（基于 TradingView Lightweight Charts v4.2.3）。默认聚焦伦敦金银现货（XAUUSD / XAGUSD）、COMEX 期货（主力连续 GC=F/SI=F/GC00Y/SI00Y、微型期货 MGC=F/SIL=F、具体月份合约 *.CMX）、海外 ETF（GLD / SLV / GDX）及 24h 美元锚定黄金代币（PAXGUSDT / XAUT-USDT），提供无闪烁定时刷新、均线/布林带/策略买卖点叠加，统一采用国际绿涨红跌配色。"
license: MIT
---

# K-Line Chart — 国际金银现货与期货 K 线看板

基于本地打包的 **TradingView Lightweight Charts v4.2.3** 构建的国际黄金与白银 K 线可视化工具，零重型前端或 Python 依赖。

---

## 目录结构

```text
skills/kline-chart/
├── SKILL.md                                             ← 本说明文档
├── assets/
│   ├── defaults.json                                    ← 国际金银默认标的池、周期、刷新频率与配色
│   └── lightweight-charts.standalone.production.js      ← 本地打包的 Lightweight Charts v4.2.3
└── scripts/
    ├── providers.py                                     ← 国际金银多源行情适配器
    └── kline_chart.py                                   ← 实时看板服务 + 静态 HTML 导出 CLI
```

---

## 支持的国际金银标的与数据路由 (`provider:SYMBOL`)

> 注：国际现货 `XAUUSD` / `XAGUSD` 采用**动静分离架构**——历史 K 线底图长缓存 10 分钟（支持可选 `TWELVEDATA_API_KEY` 优先、东财/新浪自动兜底），盘中每 10 秒轮询通过 `/api/tick` 直连 **Swissquote 瑞讯银行 BBO 实时报价**推进最后一根 K 线与顶部 `GSR` 卡片，兼顾真实时性与抗限流能力。

| 资产类别 | 标的代码 | 数据源 (`provider`) | 说明 |
|---|---|---|---|
| **伦敦现货 (Spot)** | `XAUUSD`、`XAGUSD` | `spot` (Swissquote 实时 + 历史长缓存) | 伦敦金 / 伦敦银国际现货连续价格（USD） |
| **金银比 (GSR)** | `GSR` (`XAU/XAG`) | `ratio` (自动合成) | 实时金银比 K 线走势，顶部状态栏同步显示 1 年分位数与 Z-Score |
| **COMEX 主连 / 微型期货** | `GC=F`、`SI=F`、`MGC=F`、`SIL=F` | `yahoo` | COMEX 黄金/白银主连与微型期货 |
| **COMEX 实时连续期货** | `GC00Y`、`SI00Y` | `eastmoney` (自动路由) | COMEX 黄金/白银连续实时分时与日线 |
| **COMEX 指定月份合约** | `GCZ26.CMX`、`GCG27.CMX`、`SIH27.CMX` | `yahoo` | 远月/近月期限结构合约（支持升贴水对比） |
| **海外高流动性 ETF** | `GLD`、`IAU`、`SLV`、`GDX`、`SIL` | `yahoo` | 国际贵金属现货 ETF 与金银矿业股 ETF |
| **24h 链上锚定黄金** | `binance:PAXGUSDT`、`okx:XAUT-USDT` | `binance` / `okx` | 周末及盘后 7×24 小时美元金价连续参考 |
| **本地历史 K 线** | `--csv path/to/ohlcv.csv` | `csv` | 离线回测数据与历史序列复盘 |

> 补充：如偶需对照国内期货夜盘，也可直接输入 `SHFE:AU`（沪金主连）或 `SHFE:AG`（沪银主连）。

---

## 快速上手 (Quick Start)

### 1. 启动国际金银实时交互看板

```bash
# 默认启动：伦敦金现货 (XAUUSD) 1 小时线，每 15 秒自动刷新，叠加双均线交叉信号
python skills/kline-chart/scripts/kline_chart.py serve

# 看 COMEX 黄金主连期货 (GC=F) 或微型黄金期货 (MGC=F)
python skills/kline-chart/scripts/kline_chart.py serve --symbol yahoo:GC=F --interval 1h --strategy bbands_contrarian
python skills/kline-chart/scripts/kline_chart.py serve --symbol yahoo:MGC=F --interval 15m

# 看 COMEX 远月合约（如 2027 年 2 月黄金合约 GCG27.CMX）
python skills/kline-chart/scripts/kline_chart.py serve --symbol yahoo:GCG27.CMX --interval 1h

# 看伦敦银现货 (XAGUSD) 或 COMEX 白银连续 (SI00Y)
python skills/kline-chart/scripts/kline_chart.py serve --symbol XAGUSD --interval 15m --refresh 10

# 直接看金银比 (GSR) 日线与布林带均值回归信号
python skills/kline-chart/scripts/kline_chart.py serve --symbol GSR --interval 1d --strategy bbands_contrarian

# 周末/盘后看 24 小时链上锚定黄金 (PAXGUSDT)，每 5 秒刷新
python skills/kline-chart/scripts/kline_chart.py serve --symbol binance:PAXGUSDT --interval 15m --refresh 5
```

### 2. 导出单文件离线静态 HTML

```bash
# 导出伦敦金现货近 1 年日线交互 K 线
python skills/kline-chart/scripts/kline_chart.py export --symbol XAUUSD --interval 1d --range 1y -o D:/empty/xauusd_kline.html

# 导出 COMEX 黄金期货 1 小时线
python skills/kline-chart/scripts/kline_chart.py export --symbol yahoo:GC=F --interval 1h --range 1mo -o D:/empty/gc_kline.html
```

---

## 核心交互功能

- **多周期**：`1m`、`5m`、`15m`、`1h`、`4h`（Binance/OKX 支持）、`1d`、`1wk`。
- **主图叠加**：`SMA20`、`SMA60`、布林带 `(20, 2.0)`、成交量柱状图（可一键显隐）。
- **策略买卖点标记（严格多头交替）**：`none`、`sma_crossover`、`bbands_contrarian`、`rsi_meanrev`、`macd_crossover`。
- **国际配色与无闪烁刷新**：统一采用国际绿涨红跌标准，自动轮询保留缩放平移视口。

---

## 依赖说明

仅依赖 Python 3.10+ 标准库与 `requests`（缺少 `requests` 时自动回退 `urllib.request`），**无需 `scipy`、`matplotlib` 或 `plotly`**。
