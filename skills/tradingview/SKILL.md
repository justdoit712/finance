---
name: tradingview
description: "TradingView 加密市场与永续合约选币扫描器（免 API Key）。支持按 24 小时成交额、涨跌幅、RSI、ADX、波动率与技术综合评级批量筛选币安 U 本位/TradFi 永续及全网加密品种，同时提供技术指标明细、月度枢轴点、代码搜索与快讯查询。"
license: MIT
---

# TradingView — 加密市场与永续合约选币扫描器

免鉴权调用 TradingView 公开 Scanner、Symbol Search 与 News 接口，专注加密货币及币安 U 本位永续合约批量选币与技术面扫描（默认延迟取决于 TradingView 公开快照）。

---

## 目录结构

```text
skills/tradingview/
├── SKILL.md
├── references/
│   └── SCANNER_FILTERS.md        # 过滤语法与常用永续选币配方
├── assets/
│   ├── column_groups.json        # 预设字段组合包（quote / technicals / pivots / performance）
│   ├── scanner_columns.json      # 加密与永续有效字段目录
│   └── recommend_ratings.json    # 技术评级数值分档映射
└── scripts/
    └── fetch_tradingview.py      # 统一选币与行情查询 CLI（13 种模式）
```

---

## 支持模式

| 类别 | 模式 | 说明 |
|:---|:---|:---|
| **选币扫描** | `perps` | 一键筛选 USDT 永续合约（默认 `BINANCE`、24h 成交额 ≥ 500 万 USDT） |
| | `screen` | 自定义 `--filter` / `--sort` / `--perps-only` 多条件筛选 |
| | `market` | 列出指定市场（默认 `crypto`）按成交额排序的品种 |
| **单标分析** | `quote` | 基础行情、24h 成交额与日内波动率 |
| | `technicals` | RSI、MACD、ADX、ATR、各周期均线与综合评级 |
| | `pivots` | 月度枢轴点（Classic / Fibonacci / Camarilla / Woodie / DeMark） |
| | `performance` | 周 / 月 / 季 / 年涨跌幅与多周期波动率 |
| | `all` | 聚合 `quote + technicals + pivots + performance + news` |
| **搜索与快讯** | `search` | 检索交易对代码与交易所 |
| | `news` / `news-global` | 查指定标的或全球市场新闻标题 |
| **本地目录** | `columns` / `groups` | 查看可用字段名与字段组合包 |

---

## 常用实战命令

```bash
# 1. 币安 U 本位永续 24h 成交额 Top 15
python skills/tradingview/scripts/fetch_tradingview.py perps --limit 15 -q

# 2. 币安 U 本位永续 24h 涨幅榜（成交额 >= 2000 万 USDT）
python skills/tradingview/scripts/fetch_tradingview.py perps --sort change:desc --min-vol 20000000 --limit 15 -q

# 3. 筛选 RSI < 30 的超卖币安永续合约
python skills/tradingview/scripts/fetch_tradingview.py perps --filter '[["RSI","less",30]]' --sort RSI:asc --limit 15 -q

# 4. 筛选强力买入评级且日波动率 > 5% 的合约
python skills/tradingview/scripts/fetch_tradingview.py perps --filter '[["Recommend.All","egreater",0.5],["Volatility.D","greater",5]]' --sort change:desc --limit 15 -q

# 5. 查询单个永续合约技术指标与评级（注意 TradingView 永续代码带 .P 后缀）
python skills/tradingview/scripts/fetch_tradingview.py technicals BINANCE:ETHUSDT.P -q

# 6. 在全网或币安搜索交易对（例如 TradFi 合约 NIO）
python skills/tradingview/scripts/fetch_tradingview.py search NIO --exchange BINANCE --type all -q
```
