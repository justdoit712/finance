# TradingView — API 完整参考指南

> **TradingView** 是全球使用最广泛的市场数据、技术分析和社交交易平台（拥有超过 5000 万活跃用户）。尽管官方未提供免费的公开 API，但其 Web 端应用暴露了若干**无需认证、无需 API Key** 即可直接访问的内部 API。
>
> 本文档涵盖了通过对标的页面 HTML 进行逆向工程所识别的 **6 个核心 Host**，并在 2026-06 进行了**实测验证**。

---

## 目录

1. [端点总览](#1-端点总览)
2. [API 服务主机 (Hosts)](#2-api-服务主机-hosts)
3. [通用约定与规范](#3-通用约定与规范)
4. [Scanner API — 核心主力端点](#4-scanner-api--核心主力端点)
5. [Symbol Search v3 (标的检索)](#5-symbol-search-v3-标的检索)
6. [News Headlines (新闻头条)](#6-news-headlines-新闻头条)
7. [子页面 HTML 抓取](#7-子页面-html-抓取)
8. [Recommend.All / .MA / .Other (买卖评级)](#8-recommendall--ma--other-买卖评级)
9. [错误处理](#9-错误处理)
10. [已知限制](#10-已知限制)
11. [技术注意事项](#11-技术注意事项)
12. [其它已识别的主机 (暂未实现)](#12-其它已识别的主机-暂未实现)

---

## 1. 端点总览

| 序号 | CLI 模式 | URL | 请求方法 | 备注说明 |
|---|----------|-----|--------|-------|
| 1 | `quote SYM` 及相关变体 | `/{market}/scan` | POST | 针对单标的的 Scanner 查询（10 种按字段列分组的变体） |
| 2 | `screen`, `country`, `sector`, `market` | `/{market}/scan` | POST | 带有过滤条件的海量选股筛选器 |
| 3 | `search QUERY` | `/symbol_search/v3/` | GET | 全球标的搜索，返回 ISIN/CUSIP/CIK |
| 4 | `news SYM` / `news-global` | `/v2/headlines` | GET | 获取指定标的或全球宏观新闻头条 |
| 5 | `story STORY_PATH` | `{web}/{storyPath}` | GET | 抓取新闻正文 HTML 内容 |
| 6 | `subpage SYM PATH` | `{web}/symbols/{ex}-{sym}/{path}/` | GET | 请求网页 HTML 并提取 `prs.init-data+json` 数据块 |
| 7 | `columns`, `groups`, `markets` | (本地) | — | 本地资产目录查询，不产生 HTTP 网络请求 |
| 8 | `all SYM` | 组合 6 次调用 | POST+GET | 全合一综合行情数据 |

**总计：基于 4 个独立的 HTTP 端点，提供 ~24 种 CLI 模式**（其中 Scanner 作为一个通用端点，承载了绝大多数行情报价和筛选模式）。

---

## 2. API 服务主机 (Hosts)

通过在任意标的详情页面的 HTML 中提取 `window.*` 全局变量赋值所识别：

| JS 变量名 | 服务 Host | 用途说明 |
|-------------|------|------|
| `window.SCREENER_HOST` | `https://scanner.tradingview.com` | **Scanner** — 核心主力查询端点 |
| `window.SS_HOST` | `symbol-search.tradingview.com` | Symbol Search 标的搜索 |
| `window.NEWS_SERVICE_URL` | `https://news-headlines.tradingview.com` | 新闻头条服务 |
| `window.WEBSOCKET_HOST` | `data.tradingview.com` | 实时行情 WebSocket (未实现) |
| `window.WEBSOCKET_PRO_HOST` | `prodata.tradingview.com` | 高级付费行情 WS (未实现) |
| `window.WEBSOCKET_HOST_FOR_DEEP_BACKTESTING` | `history-data.tradingview.com` | 深度历史 K 线 WS |
| `window.PUSHSTREAM_URL` | `wss://pushstream.tradingview.com` | 消息推送 WS |
| `window.ECONOMIC_CALENDAR_URL` | `economic-calendar.tradingview.com` | 财经日历 |
| `window.EARNINGS_CALENDAR_URL` | `scanner.tradingview.com` | 财报日历 (Scanner 别名) |
| `window.CHARTEVENTS_URL` | `chartevents-reuters.tradingview.com` | 图表上的路透事件标注 |
| `window.OPTIONS_CHARTING_URL` | `options-charting.tradingview.com` | 期权图表 |
| `window.PORTFOLIO_URL` | `portfolio.tradingview.com/portfolio/v1` | 投资组合管理 |
| `window.PINE_FACADE` | `pine-facade.tradingview.com/pine-facade` | Pine Script 脚本执行门面 |
| (图标静态资源) | `s3-symbol-logo.tradingview.com` | PNG/SVG 格式的品牌 Logo 图标 |

---

## 3. 通用约定与规范

### 免认证鉴权 (No Auth)

所有端点均无需 API Key、Token、Cookie 或 Session ID。支持在无头脚本、CI/CD 持续集成、Docker 容器等环境下直接调用。

### 推荐请求头 (Headers)

```python
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Origin": "https://es.tradingview.com",
    "Referer": "https://es.tradingview.com/",
}
```

针对 Scanner 的 POST 请求端点，还需追加：

```python
"Content-Type": "application/json"
```

（在使用 `requests` 库且传入 `json=payload` 时会自动添加该头部）。

### 标的代码格式

| 格式 | 应用场景 |
|---------|-------|
| `{EXCHANGE}:{TICKER}` | Scanner、News 及所有 JSON 接口 |
| `{EXCHANGE}-{TICKER}` | HTML 网页路径 (es.tradingview.com/symbols/) |

转换规则：直接将冒号 `:` 与连字符 `-` 互换即可。例如：`NASDAQ:GGAL` ↔ `NASDAQ-GGAL`。

### 字符编码 (Encoding)

所有端点均返回标准的 UTF-8 编码。在部分 Windows 控制台（默认 cp1252 或 gbk）中可能会将非 ASCII 字符显示为 `?`。通用的解决方案如下：

```python
import sys
sys.stdout.reconfigure(encoding="utf-8")
```

或者在写入文件时使用 `json.dumps(..., ensure_ascii=False)`。

---

## 4. Scanner API — 核心主力端点

**请求 URL：** `POST https://scanner.tradingview.com/{market}/scan`

这是功能最为强大的 API。支持单次请求中按需查询 **300+ 个字段列** 的任意组合，并原生支持过滤、排序以及分页能力。

### 有效市场代码 (Markets)

| 市场代码 | 典型覆盖品种 |
|--------|------------------|
| `global` | 全球所有市场 (>100k 标的) |
| `america` | 美股：NYSE, NASDAQ, AMEX, OTC (~15k) |
| `argentina` | 阿根廷：BCBA/BYMA (~300) |
| `brazil` | 巴西：B3/Bovespa (~500) |
| `spain` | 西班牙：BME (~200) |
| `italy` | 意大利：Borsa Italiana (~400) |
| `germany` | 德国：Xetra/Frankfurt (~1k) |
| `uk` | 英国：LSE (~2k) |
| `france` | 法国：Euronext Paris (~800) |
| `russia` | 俄罗斯：MOEX (~200) |
| `crypto` | 加密货币 (>50k) |
| `forex` | 外汇货币对 |
| `bonds` | 全球债券 |

详见 `assets/markets.json` 与 `references/MARKETS_EXCHANGES.md`。

### 请求载荷结构 (Request Body)

```json
{
  "symbols": {"tickers": ["NASDAQ:GGAL"]},   // 可选：指定标的代码列表
  "filter": [                                  // 可选：过滤条件数组
    {"left": "sector", "operation": "equal", "right": "Finance"},
    {"left": "market_cap_basic", "operation": "greater", "right": 100000000000}
  ],
  "columns": ["name", "close", "RSI"],        // 必填：目标列名列表
  "range": [0, 30],                            // [起始偏移量, 结束偏移量]
  "sort": {                                    // 可选：排序规则
    "sortBy": "market_cap_basic",
    "sortOrder": "desc"
  },
  "options": {"lang": "en"}                    // 可选：语言偏好
}
```

> ⚠️ **若未指定 `columns`**，API 将返回 `data: [{"s": "...", "d": []}]`（数据为空）。必须显式传入所需查询的列。
>
> ⚠️ **若既未指定 `symbols` 也未指定 `filter`**，API 将过滤掉所有数据。若需查询整个市场的全部标的，请传入 `"filter": []`。

### 响应载荷结构 (Response Body)

```json
{
  "totalCount": 1,
  "data": [
    {
      "s": "NASDAQ:GGAL",
      "d": [48.62, 0.6, 729353, "Finance", ...]
    }
  ]
}
```

**采用列式存储结构：** `data[i].d[j]` 的值严格对应于请求中 `columns[j]` 的列（顺序一致）。

将其反规范化映射为字典结构（`fetch_tradingview.py` 的内部处理逻辑）：

```python
record = {"symbol": row["s"]}
for col, val in zip(columns_requested, row["d"]):
    record[col] = val
```

### 字段列定义

完整字段列表请查阅 `references/SCANNER_COLUMNS.md` 以及结构化资产文件 `assets/scanner_columns.json`。

### 过滤条件语法

支持的各类过滤操作符（equal, greater, in_range, match 等）请查阅 `references/SCANNER_FILTERS.md`。

---

## 5. Symbol Search v3 (标的检索)

**请求 URL：** `GET https://symbol-search.tradingview.com/symbol_search/v3/?text={query}`

全局搜索引擎。返回匹配项的 ISIN、CUSIP、CIK、计价货币、挂牌交易所、Logo ID 以及描述信息。覆盖 TradingView 的全量标的数据库。

### Query 查询参数

| 参数 | 说明 | 默认值 |
|-------|-------------|---------|
| `text` | 检索文本（支持代码、ISIN、CUSIP、企业名称） | (必填) |
| `search_type` | `stocks` \| `funds` \| `futures` \| `forex` \| `crypto` \| `indices` \| `bonds` \| `options` | 不限类型 |
| `exchange` | 按交易所过滤 (`NASDAQ`, `NYSE`, `BCBA`, `BME` 等) | 不限交易所 |
| `lang` | 响应语言代码 (en, es) | en |
| `domain` | 运行环境标识 (`production`) | production |
| `hl` | 设为 1 则在 `description` 中高亮匹配词 (`<em>`) | 1 |

### 响应示例

```json
{
  "symbols_remaining": 0,
  "symbols": [
    {
      "symbol": "GGAL",
      "description": "Grupo Financiero <em>Galicia</em> S.A.",
      "type": "dr",
      "exchange": "NASDAQ",
      "found_by_isin": false,
      "found_by_cusip": false,
      "cusip": "399909100",
      "isin": "US3999091008",
      "cik_code": "0001114700",
      "currency_code": "USD",
      "currency-logoid": "country/US",
      "logoid": "gpo-fin-galicia",
      "logo": {"style": "single", "logoid": "gpo-fin-galicia"},
      "provider_id": "ice",
      "source_logoid": "source/NASDAQ",
      "source2": {"id": "NASDAQ", "name": "Nasdaq Stock Market"}
    }
  ]
}
```

更多细节请查阅 `references/SYMBOL_SEARCH.md`。

---

## 6. News Headlines (新闻头条)

**请求 URL：** `GET https://news-headlines.tradingview.com/v2/headlines`

单次请求最多可返回 200 条最新新闻。

### Query 查询参数

| 参数 | 说明 |
|-------|-------------|
| `client` | 客户端类型，固定为 `web` |
| `lang` | 语言代码，推荐 `en`（`es` 等其它语言新闻收录量较少） |
| `symbol` | (可选) 标的代码如 `NASDAQ:AAPL`。若省略则返回全球宏观市场新闻 |

### 响应示例

```json
{
  "items": [
    {
      "id": "DJN_DN20260604009289:0",
      "title": "Apple's Plan for AI Dominance...",
      "provider": "dow-jones",
      "sourceLogoId": "dow-jones",
      "published": 1780619400,
      "source": "Dow Jones Newswires",
      "urgency": 2,
      "permission": "provider",
      "relatedSymbols": [
        {"symbol": "NASDAQ:AAPL", "logoid": "apple"}
      ],
      "storyPath": "/news/DJN_DN20260604009289:0/"
    }
  ]
}
```

### 新闻正文提取

直接调用新闻正文 API（`/v2/story?id=...`）会返回 **400 错误**。解决方案：直接抓取网页 HTML：`https://es.tradingview.com{storyPath}`（HTTP 状态码 200，大小约 190 KB）。

更多细节请查阅 `references/NEWS_API.md`。

---

## 7. 子页面 HTML 抓取

**请求 URL：** `GET https://es.tradingview.com/symbols/{EX}-{SYM}/{subpath}/`

每个标的详情页面包含若干个 HTML 子页面（返回 200 OK，页面体积约 200-1000 KB），内置了丰富的服务端渲染 (SSR) 数据。

### 有效子页面清单 (已确认 16 个有效路径)

| 子路径 (Subpath) | 体积大小 | 页面包含内容 |
|---------|--------|-----------|
| `` (根路径) | 400 KB | 标的综合概览 |
| `technicals` | 211 KB | 综合评级 + 技术指标明细 |
| `financials-overview` | 217 KB | 财务核心概览 |
| `financials-income-statement` | 610 KB | 利润表 (多期对比) |
| `financials-balance-sheet` | 386 KB | 资产负债表 (多期对比) |
| `financials-cash-flow` | 333 KB | 现金流量表 (多期对比) |
| `financials-statistics-and-ratios` | 1 MB | 完整统计指标与财务比率 |
| `financials-dividends` | 203 KB | 历史分红记录 |
| `financials-revenue` | 205 KB | 业务分部收入明细 |
| `financials-earnings` | 215 KB | 历史财报 + 业绩预测 |
| `forecast` | 200 KB | 分析师目标价预测 |
| `ideas` | 438 KB | 社区交易策略与观点 |
| `options-chain` | 398 KB | 标的期权链 |
| `seasonals` | 194 KB | 月度季节性走势规律 |
| `bonds` | 218 KB | 同发行主体发行的相关债券 |
| `etfs` | 256 KB | 持有该标的的 ETF 基金 |
| `minds` | 278 KB | 社区实时简短动态讨论 |

### 不存在的子路径 (返回 HTTP 404)

`/news/`、`/analysis/`、`/profile/`、`/markets/`、`/insider-trading/`、`/financials-statistics/`、`/financials-statements-and-ratios/`。

### 如何从 HTML 中提取数据

页面 HTML 内部包含若干 **`<script type="application/prs.init-data+json">` 数据块**，存储了完整的 SSR 数据。数据提取正则与代码模式请参阅 `references/HTML_SCRAPING.md`。

---

## 8. Recommend.All / .MA / .Other (买卖评级)

Scanner 中的 `Recommend.All`、`Recommend.MA`、`Recommend.Other` 字段为 **TradingView 官方聚合技术评级**，取值范围介于 `-1.0` 到 `+1.0` 之间。

| 数值范围 | 分档标识 (Bucket) | 界面标签 (UI Label) |
|-------|--------|-------------|
| -1.00 到 -0.50 | STRONG_SELL | 强力卖出 |
| -0.50 到 -0.10 | SELL | 卖出 |
| -0.10 到 +0.10 | NEUTRAL | 中立 |
| +0.10 到 +0.50 | BUY | 买入 |
| +0.50 到 +1.00 | STRONG_BUY | 强力买入 |

| 字段名称 | 计算来源与依据 |
|-------|----------------------|
| `Recommend.All` | **全部**技术指标的加权综合平均值 |
| `Recommend.MA` | **仅移动均线类**（SMA/EMA 10..200、VWMA、Ichimoku、HullMA） |
| `Recommend.Other` | **仅震荡指标类**（RSI、Stoch、MACD、ADX、CCI、BBP、UO、W%R、AO） |

映射关系持久化存储于 `assets/recommend_ratings.json`。脚本内置了 `recommend_label(value)` 函数供直接调用转换。

---

## 9. 错误处理

| HTTP 状态码 | 常见原因 |
|--------|--------|
| 200 | 请求成功。对于 Scanner，建议额外校验 `totalCount > 0` 且 `data[0].d` 不为空。 |
| 400 | 请求载荷无效（包含未定义列名、过滤语法错误、Body 为 `null`） |
| 403 | 访问路径不存在或缺少请求头（部分接口强制要求带上 `Origin` / `Referer`） |
| 404 | HTML 子页面不存在（例如请求了 `/news/`） |
| 405 | 请求方法不匹配（例如 `/v3/headlines` 不支持 GET，仅 v2 支持） |

### Scanner 常见错误特征

- `data: [{"s": "X", "d": []}]` → 请求体中漏传了 `columns`。
- `data: []` 且 `totalCount: 0` → 目标标的在当前 `market` 中不存在（尝试更换为 `global` 或正确的市场代码）。
- HTTP 200 但某列返回空值 → 目标标的类别不支持该属性（例如 ETF 基金没有每股收益 EPS）。

### Symbol Search 常见错误特征

- HTTP 200 但 `symbols: []` → 未匹配到任何标的。建议缩短搜索关键词再次尝试。

---

## 10. 已知限制

1. **未开放公开 REST 历史 OHLCV 接口**：实时历史 K 线位于 WebSocket 接口 `wss://data.tradingview.com` 之后（专有协议格式，本 Skill 未实现）。Scanner 仅提供当前 `close` 价格与预计算的 `Perf.W/1M/3M/...` 收益率。
2. **新闻覆盖范围不均衡**：美股核心大盘股（AAPL/MSFT/NVDA/JPM）单次请求可达 ~200 条，但小盘股或非美市场标的可能仅有 1-10 条。非英语（如 `lang=es`）几乎无数据。
3. **缺少官方正式文档**：均为内部接口，可能随时变更。不过 Scanner 的列式数据结构自 2017 年以来保持高度稳定。
4. **Scanner 的分页机制非传统 `page` 参数**：Scanner 采用 `range: [offset, end]` 范围切片模式。若需单次获取较多数据，可设置形如 `range: [0, 5000]`。
5. **部分字段列对特定资产类型会返回 `null`**：
   - ETF / 基金：`earnings_per_share_*`, `revenue_*` 等财报指标
   - 加密货币：绝大多数传统基本面财务指标
   - 债券：`EPS`, `P/E`, `dividend_*` 等
6. **`/argentina/scan` 查询 `NASDAQ:GGAL`** 会返回 0 条结果 —— 标的代码的前缀交易所必须与目标市场归属一致（阿根廷本地市场使用 `BCBA:GGAL`，美股市场使用 `NASDAQ:GGAL`）。
7. **`symbol_search_type=forex`** 查询 `text=BTCUSD` 会返回 0 条结果 —— 搜索类型过滤必须与资产类别匹配（BTCUSD 属于 `crypto` 而非 `forex`）。
8. **HTML 响应中包含字符实体转义**：页面虽然为 UTF-8 编码，但在 HTML 属性中部分字段会包含 `&amp;`、`&quot;` 等转义字符。解析内嵌 JSON 之前需先通过 `html.unescape()` 清洗。
9. **实时 WebSocket 未做封装**：本 Skill 未封装 WebSocket 连接。如需无延迟的真实逐笔 Tick 行情，可参考 `tvDatafeed` 或 `tradingview-ta` 等开源库（通过模拟 WebSocket 握手协议实现）。

---

## 11. 技术注意事项

### 请求速率限制 (Rate Limiting)

官方未对外公开具体规则，根据实际测试表现：
- **Scanner**：可稳定承受 ~5 请求/秒，不触发限流。
- **News**：可承受 ~3 请求/秒。
- **Symbol Search**：可承受 ~5 请求/秒。
- **HTML 子页面**：受 Cloudflare WAF 保护，规则较严苛（建议维持在 ~1 请求/秒，以防触发 429）。

常规调用建议在各次请求间添加 `time.sleep(0.3)`。

### 市场数据延迟

- **行情报价 (`close`, `change`, `volume`)**：存在各交易所通用的 ~15 分钟标准行情延迟。
- **技术指标**：基于该延迟数据进行服务端预计算（延迟 ~15-20 分钟）。
- **财报发布 / 业绩预期**：在财报披露结算后更新 (T+0)。
- **新闻资讯**：实时推流。
- **历史表现 (`Perf.*`)**：每日收盘结算后更新。

### 跨域资源共享 (CORS)

各接口端点默认仅接受来自 TradingView 官方域名的跨域请求。若在外部浏览器前端直接调用，需通过后端服务进行反向代理。

### 法律合规与使用声明

- TradingView 未针对这些内部 API 发布官方公开文档。
- 接口可能在不经通知的情况下发生变动（在社区跟踪的 ~6 年时间里，变动一直极少且非常平滑）。
- 请遵守 TradingView 平台使用规范。如需高频商业化使用，请联系其商务合作团队购买 **TradingView 官方付费 REST API**。
- **严禁滥用**：保持合理请求频率，禁止暴力爬取，严禁未经授权转售或伪造数据产权。

---

## 12. 其它已识别的主机 (暂未实现)

在页面 HTML 的 `window.*` 全局变量中检测到以下服务节点，但接入需要更深度的协议逆向：

| 服务 Host | 推测用途 |
|------|------------------|
| `wss://data.tradingview.com` | 实时逐笔行情 WebSocket 推流（采用专有握手协议） |
| `wss://prodata.tradingview.com` | 付费专业版实时行情 WS（需携带 Pro 订阅 Token） |
| `wss://history-data.tradingview.com` | 深度历史 K 线数据 WS（支持 1分/5分/15分/1小时等级别） |
| `wss://pushstream.tradingview.com` | 实时消息与通知推送 |
| `economic-calendar.tradingview.com` | 财经日历（实测：缺少特定参数时返回 403） |
| `chartevents-reuters.tradingview.com` | 在图表上叠加的路透社重大事件数据 |
| `options-charting.tradingview.com` | 希腊字母 Greeks 与高级期权链分析（推测需要登录凭证） |
| `options-storage.tradingview.com` | 期权个性化配置存储服务 |
| `portfolio.tradingview.com/portfolio/v1` | 个人投资组合服务（需要用户登录鉴权） |
| `pine-facade.tradingview.com/pine-facade` | Pine Script 策略脚本在线编译执行（需登录） |

其中 WebSocket 是最具挖掘价值的方向 —— 支持无延迟的逐笔 Tick 级推送，但需要特定的握手与心跳机制。目前已有部分开源库实现了逆向解析（可参考 `tvDatafeed`、`tradingview-ta`）。

---

## 参考与资源链接

- **TradingView 官方网站：** https://www.tradingview.com
- **TradingView 官方付费 REST API：** https://www.tradingview.com/rest-api/
- **社区维护的字段列清单：** 逆向工程产出
- **相关的开源库项目：**
  - `tvDatafeed` (Python 版本的 WebSocket 客户端)
  - `tradingview-ta` (Python 版本的 Scanner 封装库)
  - `tvjs` (JavaScript 版本的 Scanner 客户端)
