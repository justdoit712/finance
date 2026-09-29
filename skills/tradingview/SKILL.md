---
name: tradingview
description: "通过无鉴权的 TradingView 内部公开 API 获取市场数据：Scanner（~300 列，涵盖行情报价、技术指标、财务数据、财报、评级、目标价）、Symbol Search v3（ISIN/CUSIP/CIK）、新闻头条（News Headlines）、子页面 HTML 抓取（技术指标/财务/预测/期权/观点等）。全球覆盖：100k+ 股票、50k+ 加密货币、指数、外汇、债券。支持 24 种 CLI 模式。"
license: MIT
---

# TradingView — 基于公开 API 的市场数据接口

通过逆向工程发现的 [TradingView](https://www.tradingview.com) **内部公开 API** 提取市场数据的 **高级（premium）** Skill —— **无需 API Key，无需认证鉴权**。

TradingView 是全球使用最广泛的市场数据 + 技术分析 + 社交交易平台（拥有超过 5000 万活跃用户）。本 Skill 提供：

- **Scanner API**：包含 ~300 个字段列：行情报价、预计算技术指标、基本面、财报、分析师目标价、聚合买入/卖出（BUY/SELL）评级。
- **Symbol Search v3**：提供 **ISIN、CUSIP、CIK** 标识符（可与 SEC EDGAR 对接关联）。
- **News Headlines**：新闻头条（每个代码支持多达 ~200 条新闻，包含 Dow Jones / Reuters 等来源）。
- **HTML 网页抓取**：抓取 16+ 个子页面（`technicals`、`financials-*`、`forecast`、`options-chain`、`ideas` 等），提取页面内的 `prs.init-data+json` 数据块。
- **海量选股筛选器（Screener）**：支持多维度过滤 + 排序 + 分页查询（覆盖 ~100k+ 交易品种）。

---

## ⚠️ 免责声明与注意事项

- TradingView **未发布这些 API 的官方文档**。接口可能在不经通知的情况下发生变动。
- 在社区跟踪的 **~6 年** 时间里，变动一直非常渐进 —— Scanner 的核心架构自 2017 年以来一直保持稳定。
- 请遵守使用条款。如需大规模商业化使用，请购买官方付费的 **REST API**。
- 数据存在 **延迟（delayed）**（通常延迟约 15 分钟）。实时数据采用专有的 WebSocket 传输（本 Skill 未做实现）。

---

## 🚀 快速上手 (Quick start)

```bash
# 快速行情
py scripts/fetch_tradingview.py quote NASDAQ:GGAL

# 全合一综合查询 (合并 6 个请求)
py scripts/fetch_tradingview.py all NASDAQ:GGAL

# 海量选股筛选 (Screener)
py scripts/fetch_tradingview.py country Argentina --limit 30
py scripts/fetch_tradingview.py sector Finance --market america --limit 20

# 标的新闻 (单标的最多 ~200 条)
py scripts/fetch_tradingview.py news NASDAQ:AAPL

# 标的搜索 (含 ISIN/CUSIP/CIK)
py scripts/fetch_tradingview.py search "Galicia"
```

---

## Skill 目录结构

```
skills/tradingview/
├── SKILL.md                              # 本文件 (快速参考指南)
├── references/                           # 8 份详细参考文档
│   ├── REFERENCE.md                      # API 整体概述与架构
│   ├── SCANNER_COLUMNS.md                # 130+ 字段列分类目录与说明表
│   ├── SCANNER_FILTERS.md                # 过滤操作符 + 复杂查询详解
│   ├── MARKETS_EXCHANGES.md              # 支持的市场 + 各国交易所代码
│   ├── NEWS_API.md                       # News API 深度解析
│   ├── SYMBOL_SEARCH.md                  # Symbol Search v3 深度解析
│   ├── HTML_SCRAPING.md                  # prs.init-data+json 提取指南
│   └── COOKBOOK.md                       # 30 个即开即用的实战配方
├── assets/                               # 4 个 JSON 资产文件
│   ├── scanner_columns.json              # 字段列目录及描述
│   ├── column_groups.json                # 按场景预置的字段组合包 (Bundles)
│   ├── markets.json                      # 有效市场与覆盖范围
│   └── recommend_ratings.json            # Recommend.* 到 STRONG_BUY 等评级的映射
└── scripts/
    └── fetch_tradingview.py              # 核心脚本，支持 24 种 CLI 模式
```

---

## 可用端点 (4 个独立 HTTP 端点，24 种 CLI 模式)

### Scanner API (1 个端点，14 种 CLI 模式)

`POST https://scanner.tradingview.com/{market}/scan`

| 模式 | 字段列组合包 (Bundle) | 说明 |
|------|-------------------|-------------|
| `quote SYM` | `quote_basic` (14 列) | 基础行情报价 |
| `quote-extended SYM` | `quote_extended` (30 列) | 基础行情 + 技术指标 + 估值数据 |
| `technicals SYM` | `technicals` (36 列) | RSI、MACD、EMA、SMA、综合技术评级 |
| `pivots SYM` | `pivots` (17 列) | 月线枢轴点 Pivot Points (5 种计算方法) |
| `financials SYM` | `financials` (35 列) | 资产负债表 + 利润表 + 现金流量表 + 关键财务比率 |
| `earnings SYM` | `earnings` (12 列) | 历史财报表现 + 盈利预测 |
| `targets SYM` | `targets` (10 列) | 分析师目标价 + 推荐评级 |
| `performance SYM` | `performance` (18 列) | 收益率 (周/1月/3月/6月/年/年初至今/5年/全部) + 波动率 + Beta |
| `dividends SYM` | `dividends` (8 列) | 股息率 + 每股派息 + 派息比率 + 股息增长率 |
| `ownership SYM` | `ownership` (10 列) | 流通盘 + 机构持股 + 内部人持股 + 做空持仓 |
| `screen` | 自定义 (custom) | 通用选股筛选器，支持过滤条件 + 排序 + 分页 |
| `country COUNTRY` | `quote_basic` | 按国家筛选股票列表 |
| `sector SECTOR` | `quote_basic` | 按行业板块筛选股票列表 |
| `market MARKET` | `quote_basic` | 列出指定市场的全部品种 |

### Symbol Search v3 (1 个端点，1 种模式)

`GET https://symbol-search.tradingview.com/symbol_search/v3/`

| 模式 | 说明 |
|------|-------------|
| `search QUERY` | 全局标的搜索，返回 ISIN、CUSIP、CIK、logoid、交易所等信息 |

### News API (1 个端点，3 种模式)

`GET https://news-headlines.tradingview.com/v2/headlines`

| 模式 | 说明 |
|------|-------------|
| `news SYM` | 获取指定标的的新闻头条 (最多 200 条) |
| `news-global` | 全球宏观市场新闻头条 (最多 200 条) |
| `story STORY_PATH` | 获取单篇新闻正文详情 (HTML 抓取) |

### HTML 网页抓取 (1 个端点，1 种模式)

`GET https://es.tradingview.com/symbols/{EX}-{SYM}/{path}/`

| 模式 | 说明 |
|------|-------------|
| `subpage SYM PATH` | 请求网页 HTML 并提取其中的 `prs.init-data+json` 数据块 |

### 本地资产目录模式 (3 种模式)

| 模式 | 说明 |
|------|-------------|
| `columns [GROUP]` | 列出支持的字段列 (全部或指定分组) |
| `groups` | 列出所有预置的字段组合包 (Bundles) |
| `markets` | 列出所有受支持的市场代码 |

### 组合模式 (1 种模式)

| 模式 | 说明 |
|------|-------------|
| `all SYM` | 聚合 6 次请求 (quote_extended + technicals + financials + earnings + targets + news) |

---

## 快速上手 — 分类使用示例

### 行情与技术面

```bash
py scripts/fetch_tradingview.py quote NASDAQ:GGAL                  # 14 列
py scripts/fetch_tradingview.py quote-extended NASDAQ:AAPL         # 30 列
py scripts/fetch_tradingview.py technicals NASDAQ:GGAL             # 36 列
py scripts/fetch_tradingview.py pivots NASDAQ:AAPL                 # 17 列
py scripts/fetch_tradingview.py performance NYSE:JPM               # 收益率 (周/1月/3月/6月/年/YTD/5年/全部)
```

### 财务与基本面

```bash
py scripts/fetch_tradingview.py financials NASDAQ:AAPL             # 资产负债表 + 利润表 + 现金流量表 + 财务比率
py scripts/fetch_tradingview.py earnings NASDAQ:GGAL               # 历史财报 + 预期
py scripts/fetch_tradingview.py targets NASDAQ:NVDA                # 分析师目标价 + 推荐评级
py scripts/fetch_tradingview.py dividends NYSE:KO                  # 股息率 + 每股股息 + 派息比率
py scripts/fetch_tradingview.py ownership NASDAQ:NVDA              # 流通盘 + 机构持股 + 内部人持股 + 做空数据
```

### 选股筛选 (Screening)

```bash
# 任意过滤条件 — 传入遵循 Scanner 语法的 JSON 数组
py scripts/fetch_tradingview.py screen \
  --filter '[["sector","equal","Finance"],["market_cap_basic","greater",100000000000]]' \
  --sort market_cap_basic:desc --limit 10

# 预设快捷方式
py scripts/fetch_tradingview.py country Argentina --limit 30
py scripts/fetch_tradingview.py sector Finance --market america --limit 20
py scripts/fetch_tradingview.py market crypto --limit 20
```

### 标的搜索 (Symbol Search)

```bash
py scripts/fetch_tradingview.py search "GGAL"                                       # 自动识别类型
py scripts/fetch_tradingview.py search "Apple" --type stocks --exchange NASDAQ
py scripts/fetch_tradingview.py search "BTC" --type crypto
py scripts/fetch_tradingview.py search "US3999091008"                                # 按 ISIN 查询
```

### 新闻 (News)

```bash
py scripts/fetch_tradingview.py news NASDAQ:AAPL                   # 最多 200 条
py scripts/fetch_tradingview.py news-global                        # 全球宏观要闻
py scripts/fetch_tradingview.py story "/news/DJN_DN20260604009289:0/"  # 新闻正文内容
```

### HTML 网页抓取

```bash
py scripts/fetch_tradingview.py subpage NASDAQ:GGAL technicals     # 技术指标子页面 HTML
py scripts/fetch_tradingview.py subpage NASDAQ:GGAL financials-income-statement
py scripts/fetch_tradingview.py subpage NASDAQ:GGAL options-chain
py scripts/fetch_tradingview.py subpage NASDAQ:GGAL forecast
```

### 本地目录与配置

```bash
py scripts/fetch_tradingview.py columns                            # 列出所有字段列
py scripts/fetch_tradingview.py columns technicals                 # 列出指定分组字段
py scripts/fetch_tradingview.py groups                             # 查看所有预置组合包
py scripts/fetch_tradingview.py markets                            # 查看受支持市场
```

### 综合模式

```bash
py scripts/fetch_tradingview.py all NASDAQ:GGAL                    # 一次性执行 6 项查询
py scripts/fetch_tradingview.py all NASDAQ:GGAL -o ggal_full.json  # 保存结果至文件
```

### 自定义列查询

```bash
py scripts/fetch_tradingview.py quote NASDAQ:GGAL \
  --columns "name,close,RSI,MACD.macd,Recommend.All,price_target_average"
```

### 输出重定向 / 静默模式

```bash
py scripts/fetch_tradingview.py quote NASDAQ:GGAL -o ggal_quote.json   # 写入文件
py scripts/fetch_tradingview.py quote NASDAQ:GGAL -q                    # 静默模式 (无 INFO 日志)
```

---

## 标的代码格式规范

| 使用场景 | 格式规范 | 示例 |
|-------|---------|----------|
| Scanner / News / Search (JSON API) | `{EXCHANGE}:{TICKER}` | `NASDAQ:GGAL`, `BCBA:YPF`, `BINANCE:BTCUSDT` |
| HTML 子页面抓取 | `{EXCHANGE}-{TICKER}` | `NASDAQ-GGAL` (URL 路径中使用) |

自动转换机制：在拼接 HTML 网页 URL 时，脚本会自动将 `:` 替换为 `-`。

---

## 支持的市场 (Markets)

| 市场代码 | 覆盖范围 | 典型代码示例 |
|--------|-----------|--------------|
| `global` | 全球所有市场 (100k+) | 任意 `EX:TKR` |
| `america` | 美股：NYSE、NASDAQ、AMEX、OTC (15k+) | `NASDAQ:AAPL` |
| `argentina` | 阿根廷：BCBA / BYMA (300+) | `BCBA:GGAL` |
| `brazil` | 巴西：B3 / Bovespa (500+) | `BMFBOVESPA:PETR4` |
| `spain` | 西班牙：BME (200+) | `BME:SAN` |
| `italy` | 意大利：Borsa Italiana (400+) | `MIL:ENI` |
| `germany` | 德国：Xetra / FWB (1k+) | `XETR:SAP` |
| `uk` | 英国：LSE (2k+) | `LSE:HSBA` |
| `france` | 法国：Euronext Paris (800+) | `EURONEXT:MC` |
| `russia` | 俄罗斯：MOEX (200+) | `MOEX:SBER` |
| `crypto` | 加密货币 (50k+) | `BINANCE:BTCUSDT` |
| `forex` | 外汇货币对 (1k+) | `FX:EURUSD` |
| `bonds` | 全球国债/债券 (TVC) | `TVC:US10Y` |

> 完整市场清单与细节请查阅 [references/MARKETS_EXCHANGES.md](./references/MARKETS_EXCHANGES.md)。

---

## 资产标的类型 (`type` 字段)

| 类型标识 | 说明 |
|------|-------------|
| `stock` | 普通股 (Common Stock) |
| `dr` | 存托凭证 (美股 ADR、阿根廷 CEDEAR、巴西 BDR) |
| `etf` | 交易所交易基金 (Exchange-Traded Fund) |
| `fund` | 共同基金 (Mutual Fund) |
| `structured` | 结构化产品 (Structured Product) |
| `bond` | 债券 (Bond) |
| `crypto` | 加密货币 (Cryptocurrency) |
| `forex` | 外汇货币对 (Forex Pair) |
| `index` | 股票指数 (Index) |
| `future` | 期货合约 (Future) |
| `option` | 期权合约 (Option) |

---

## 买入/卖出评级 (Recommend.*)

TradingView 基于各类技术指标计算出 3 种综合评估评分：

| 字段名称 | 计算来源与依据 |
|-------|----------------------|
| `Recommend.All` | **全部**技术指标（移动均线类 + 震荡指标类） |
| `Recommend.MA` | **仅移动均线类**（SMA/EMA 10..200、VWMA、Ichimoku、HullMA） |
| `Recommend.Other` | **仅震荡指标类**（RSI、Stoch、MACD、ADX、CCI、BBP、UO、W%R、AO） |

数值取值范围为 `[-1.0, +1.0]`，对应的区间分档如下：

| 区间范围 | 分档标识 (Bucket) | 界面标签 (UI Label) |
|-------|--------|----------|
| -1.00 到 -0.50 | `STRONG_SELL` | 强力卖出 |
| -0.50 到 -0.10 | `SELL` | 卖出 |
| -0.10 到 +0.10 | `NEUTRAL` | 中立 |
| +0.10 到 +0.50 | `BUY` | 买入 |
| +0.50 到 +1.00 | `STRONG_BUY` | 强力买入 |

> 脚本内置了 `recommend_label(value)` 函数用于执行直接转换。
> 结构化数据定义见 [assets/recommend_ratings.json](./assets/recommend_ratings.json)。

---

## 主要命令行参数 (CLI Flags)

| 参数 | 说明 |
|------|-------------|
| `--market X` | Scanner 目标市场代码 (默认: `global`) |
| `--columns "a,b,c"` | 自定义字段列 (覆盖当前模式默认的 Bundle) |
| `--filter '[...]'` | 用于 `screen` 模式的 JSON 过滤条件 (详见 [SCANNER_FILTERS.md](./references/SCANNER_FILTERS.md)) |
| `--sort field:order` | 排序规则 (例如: `market_cap_basic:desc`) |
| `--limit N` | 返回结果数量上限 (默认: 30) |
| `--offset N` | 分页偏移量 (默认: 0) |
| `--type X` | 用于 `search` 的标的类别 (`stocks`, `crypto`, `forex` 等) |
| `--exchange X` | 用于 `search` 的交易所过滤条件 |
| `--lang X` | 新闻与搜索的语言代码 (默认: `en`) |
| `-o archivo` | 将结果输出保存到指定文件 (JSON 或 Markdown) |
| `-q` / `--quiet` | 静默模式 (不打印 INFO 日志) |

---

## 横向对比：与其他金融 Skill 的差异

| 功能特性 | TradingView | Yahoo Finance | Finnhub | Investing.com | Morningstar |
|---------|:-----------:|:-------------:|:-------:|:-------------:|:-----------:|
| 公开免 Key API | ✅ | ✅ | Freemium (需Key) | ✅ | ✅ |
| 实时行情报价 | ⚠️ 延迟 | ⚠️ 延迟 | ✅ | ⚠️ 延迟 | ❌ |
| **预计算技术指标 (~30+)** | ✅ **独家** | ❌ | ❌ | ❌ | ❌ |
| **聚合买入/卖出评级** | ✅ **独家** | ❌ | ⚠️ | ⚠️ | ❌ |
| **支撑阻力枢轴点 (5 种算法)** | ✅ **独家** | ❌ | ❌ | ❌ | ❌ |
| 财务报表数据 | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| 分析师目标价 | ✅ | ⚠️ | ✅ | ✅ | ❌ |
| **搜索含 ISIN/CUSIP/CIK** | ✅ **独家** | ❌ | ⚠️ | ❌ | ❌ |
| 多国海量选股器 (Screener) | ✅ (~100k+) | ⚠️ | ⚠️ | ⚠️ | ✅ |
| 新闻头条 | ✅ (200 条) | ✅ | ✅ | ✅ | ❌ |
| 加密货币覆盖度 | ✅ (50k+) | ⚠️ | ⚠️ | ✅ | ❌ |

**TradingView 的独家核心优势：**
1. **服务端预计算的技术指标**（RSI、MACD、EMA、综合技术评级）—— 客户端完全无需自行编写公式计算。
2. **5 种算法计算的月线枢轴点**（Classic、Fibonacci、Camarilla、Woodie、DeMark）。
3. **支持 ISIN/CUSIP/CIK 的标的搜索** —— 可直接与 SEC EDGAR 系统无缝关联匹配。
4. **超大规模筛选器** —— 单次请求即可通过类似 SQL 的丰富过滤条件检索 100k+ 品种。

**何时不建议使用 TradingView：**
- 非美股微型股新闻 → 推荐使用 Yahoo Finance。
- 逐笔实时行情 (Tick-by-tick) → 需要 WebSocket 接入（本 Skill 未实现）。
- 长期历史 OHLCV K 线数据 → 未开放公开 REST 接口；建议使用 Alpha Vantage 或 Yahoo Finance。
- 跨多年完整财务报表对比（如 5 年连续损益表） → 美股建议使用 SEC EDGAR，全球范围推荐 simplywallst。

---

## 技术实现考量

### 免认证鉴权 (No Auth)

所有端点均无需 API Key、Token、Cookie 或 Session ID。支持在无头脚本、CI/CD 流水线、Docker 容器等环境下直接运行。

### 推荐请求头 (Headers)

脚本中已预置配置好的请求头：

```python
HEADERS = {
    "User-Agent": "Mozilla/5.0 ...",
    "Accept": "*/*",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Origin": "https://es.tradingview.com",
    "Referer": "https://es.tradingview.com/",
}
```

### 请求速率限制 (Rate Limiting)

官方未公开说明。根据实际调用观察：
- **Scanner**：可承受 ~5 请求/秒。
- **News**：可承受 ~3 请求/秒。
- **Symbol Search**：可承受 ~5 请求/秒。
- **HTML 子页面**：~1 请求/秒（受 Cloudflare WAF 防护限制）。

最佳实践建议：请求间隔加入 `time.sleep(0.3)`。在 `all` 组合模式中已自动启用此延时控制。

### 字符编码 (Encoding)

完全兼容有效 UTF-8。在部分 Windows 控制台（默认 cp1252 / gbk）下特殊字符可能会显示为 `?`。脚本在启动时已自动将 `sys.stdout` 重置配置为 UTF-8 编码。

### 错误状态码处理

| 状态码 | 常见原因 |
|--------|--------------|
| 200 | 成功。对于 Scanner 请求，建议检查 `totalCount > 0`。 |
| 400 | 请求载荷无效（包含未识别字段列、过滤语法错误、Body 为空等） |
| 403 | 访问路径不存在或缺少必要请求头 |
| 404 | 请求的 HTML 子页面不存在（例如无效的 `/news/` 路径） |
| 405 | 请求方法错误（例如 `/v3/headlines` 不支持 GET，仅 v2 支持） |

### 已知限制

1. **REST 接口未开放历史 OHLCV K 线**：Scanner 中仅提供 `Perf.*` 收益率统计。如需长期历史 K 线请结合其他 Skill 使用。
2. **新闻覆盖范围不均衡**：美股大型蓝筹股最多可达 200 条，但小盘股可能仅有 1-5 条。
3. **新闻的 `lang=es` 语言数据稀少**：西班牙语新闻较少，建议默认使用 `lang=en`。
4. **未实现实时 WebSocket 连接**（`wss://data.tradingview.com`）。
5. **阿根廷本地市场标识区别**：阿根廷本地市场使用 `BCBA:GGAL`，美股 ADR 使用 `NASDAQ:GGAL` —— 二者不可混用。

### 商业合规说明

- 非官方公开 API，接口可能随时调整。
- **请勿恶意滥用**：保持合理的请求速率。
- 如需高并发或商业级生产用途，建议采购 TradingView 官方付费 REST API 服务。

---

## 完整文档导航

| 文档 | 核心内容 |
|-----------|-----------|
| [references/REFERENCE.md](./references/REFERENCE.md) | 4 个 HTTP 核心端点总览与底层架构 |
| [references/SCANNER_COLUMNS.md](./references/SCANNER_COLUMNS.md) | 130+ 字段列分类目录与详尽对照表 |
| [references/SCANNER_FILTERS.md](./references/SCANNER_FILTERS.md) | 过滤操作符 + 复杂查询语句与实战示例 |
| [references/MARKETS_EXCHANGES.md](./references/MARKETS_EXCHANGES.md) | 支持的市场 + 各国交易所代码与代码格式规范 |
| [references/NEWS_API.md](./references/NEWS_API.md) | News API 深度解析：新闻提供商、Schema 字段、正文解析 |
| [references/SYMBOL_SEARCH.md](./references/SYMBOL_SEARCH.md) | Symbol Search v3 深度解析：ISIN/CUSIP/CIK 映射 |
| [references/HTML_SCRAPING.md](./references/HTML_SCRAPING.md) | 提取 prs.init-data+json 与网页抓取典型场景 |
| [references/COOKBOOK.md](./references/COOKBOOK.md) | **30 个即开即用的实战配方大全** |
| [assets/scanner_columns.json](./assets/scanner_columns.json) | 字段列目录及中文/英文描述 |
| [assets/column_groups.json](./assets/column_groups.json) | 按业务场景预置的字段组合包 |
| [assets/markets.json](./assets/markets.json) | 受支持的市场代码与覆盖范围 |
| [assets/recommend_ratings.json](./assets/recommend_ratings.json) | Recommend.* 指标到评级区间的映射规则 |

---

## 典型应用场景示例

> **更多详细案例见 [references/COOKBOOK.md](./references/COOKBOOK.md) 中的 30 个完整配方。**

```bash
# 美股市值前 10 大普通股
py scripts/fetch_tradingview.py screen \
  --filter '[["country","equal","United States"],["type","equal","stock"]]' \
  --sort market_cap_basic:desc --limit 10

# 超跌高股息选股 (RSI < 30 且股息率 > 5%)
py scripts/fetch_tradingview.py screen \
  --filter '[["RSI","less",30],["dividend_yield_recent","greater",5]]' \
  --sort dividend_yield_recent:desc --limit 20

# 检索在任意市场上市的阿根廷企业
py scripts/fetch_tradingview.py country Argentina --limit 30

# 流水线协同：搜索 → 报价 → 新闻
py scripts/fetch_tradingview.py search "Apple" -q | jq -r '.symbols[0].symbol'
py scripts/fetch_tradingview.py quote NASDAQ:AAPL
py scripts/fetch_tradingview.py news NASDAQ:AAPL

# 通过 CIK 对接关联 SEC EDGAR
py scripts/fetch_tradingview.py search "GGAL" -q | jq -r '.symbols[0].cik_code'
# -> 0001114700  (可将该 CIK 用于 sec-data skill)
```
