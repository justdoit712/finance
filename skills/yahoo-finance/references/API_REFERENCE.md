# Yahoo Finance API 完整参考手册

> Yahoo Finance 非官方接口详尽参考文档。  
> 更新至 2026 年 6 月 —— 基于对 `yfinance` 的逆向工程与实际测试验证。

---

## 目录

1. [身份验证：Cookie + Crumb](#1-身份验证cookie--crumb)
2. [v8/finance/chart — 历史 OHLCV 行情](#2-v8financechart--历史-ohlcv-行情)
3. [v7/finance/quote — 实时行情报价](#3-v7financequote--实时行情报价)
4. [v10/finance/quoteSummary — 基本面数据](#4-v10financequotesummary--基本面数据)
5. [v7/finance/options — 期权链](#5-v7financeoptions--期权链)
6. [v1/finance/search — 搜索与新闻](#6-v1financesearch--搜索与新闻)
7. [v6/finance/recommendationsbysymbol — 相似标的推荐](#7-v6financerecommendationsbysymbol--相似标的推荐)
8. [v1/finance/trending — 热门趋势标的](#8-v1financetrending--热门趋势标的)
9. [v1/finance/lookup — 标的代码查询](#9-v1financelookup--标的代码查询)
10. [v1/finance/screener — 选股器](#10-v1financescreener--选股器)
11. [WebSocket 流式推送](#11-websocket-流式推送)
12. [速率限制与应对策略](#12-速率限制与应对策略)
13. [错误代码与故障排查](#13-错误代码与故障排查)
14. [国际标的代码（Tickers）](#14-国际标的代码tickers)
15. [跨接口通用字段规范](#15-跨接口通用字段规范)

---

## 1. 身份验证：Cookie + Crumb

Yahoo 采用 **Cookie + Crumb** 系统来保护特定接口免受爬虫与机器人滥用。  
该机制既非 OAuth，也无需任何 API Key —— 它本质上是一个 Yahoo 自制的 CSRF Token。

### 完整交互流程

```
  客户端 (Client)                   Yahoo
    |                                |
    |  GET https://fc.yahoo.com      |
    |-------------------------------->|
    |  Set-Cookie: A3=XXXXXXXXX...   |
    |<--------------------------------|
    |                                |
    |  GET /v1/test/getcrumb         |
    |  (携带 Cookie A3)              |
    |-------------------------------->|
    |  crumb: "abcdef123456"         |
    |<--------------------------------|
    |                                |
    |  GET /v7/finance/quote         |
    |  ?crumb=abcdef123456           |
    |-------------------------------->|
    |  JSON 响应数据                 |
    |<--------------------------------|
```

### Python 实现示例

```python
import requests

BASE = "https://query1.finance.yahoo.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def yahoo_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://fc.yahoo.com", timeout=10)          # 步骤 1：获取 A3 Cookie
    crumb = s.get(f"{BASE}/v1/test/getcrumb", timeout=10).text.strip()  # 步骤 2：获取 crumb
    s.params = {"crumb": crumb}                         # 步骤 3：为所有后续请求附加 crumb 参数
    return s
```

### 按验证要求分类的接口

| 接口 (Endpoint) | 是否需要 Crumb |
|-----------------|:--------------:|
| `v8/finance/chart` | ❌ 否 |
| `v7/finance/quote` | ✅ 是 |
| `v10/finance/quoteSummary` | ✅ 是 |
| `v7/finance/options` | ✅ 是 |
| `v1/finance/search` | ❌ 否 |
| `v6/finance/recommendationsbysymbol` | ✅ 是 |
| `v1/finance/trending` | ❌ 否 |
| `v1/finance/lookup` | ❌ 否 |
| `v1/finance/screener` | ✅ 是（部分需要） |

### Crumb 的有效期限

- Crumb 的有效期一般在数分钟到数小时不等。
- Yahoo 官方没有文档化的 TTL。如果收到响应 `{"finance":{"error":{"code":"Bad Request"}}}`，说明需要重新生成 Crumb。
- 稳健策略：为每个需要 Crumb 的请求单独初始化会话，或者在本地缓存并在调用失败时自动刷新重试。

---

## 2. v8/finance/chart — 历史 OHLCV 行情

### 接口地址

```
GET https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
```

### 请求参数

| 参数 | 取值范围 | 是否必填 | 描述说明 |
|------|----------|:--------:|----------|
| `range` | `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `ytd`, `max` | 否* | 时间跨度范围 |
| `interval` | `1m`, `2m`, `5m`, `15m`, `30m`, `60m`, `1h`, `1d`, `1wk`, `1mo` | 是 | 行情采样周期/颗粒度 |
| `period1` | Unix 时间戳 | 否* | 起始时间（与 `range` 二选一） |
| `period2` | Unix 时间戳 | 否* | 结束时间（默认值：当前时间） |
| `events` | `div`, `splits`, `div,splits` | 否 | 是否包含分红与拆股事件数据 |
| `includePrePost` | `true`, `false` | 否 | 是否包含盘前与盘后交易数据（仅日内周期有效） |

\* 注：使用 `range` 或 `period1`/`period2` 两者之一，不可同时传递。

### 有效的 range 与 interval 搭配组合

Yahoo 对不同时间范围可使用的采样周期有明确限制：

| Range（范围） | 有效的 Intervals（采样周期） |
|---------------|-----------------------------|
| `1d` | `1m`, `2m`, `5m` |
| `5d` | `1m`, `2m`, `5m`, `15m`, `30m` |
| `1mo` | `1m`, `5m`, `15m`, `30m`, `60m`, `1h`, `1d` |
| `3mo` | `1d`, `1wk` |
| `6mo` | `1d`, `1wk` |
| `1y` | `1d`, `1wk` |
| `2y` | `1d`, `1wk`, `1mo` |
| `5y` | `1d`, `1wk`, `1mo` |
| `max` | `1d`, `1wk`, `1mo` |

**注意：** 日内高频数据（如 `1m`, `5m`）通常仅保留最近 7 至 60 天的数据。

### JSON 响应结构

```json
{
  "chart": {
    "result": [
      {
        "meta": {
          "currency": "USD",
          "symbol": "AAPL",
          "exchangeName": "NMS",
          "instrumentType": "EQUITY",
          "firstTradeDate": 345479400,
          "regularMarketTime": 1717439040,
          "regularMarketPrice": 196.89,
          "regularMarketOpen": 195.19,
          "regularMarketDayHigh": 197.92,
          "regularMarketDayLow": 194.81,
          "regularMarketVolume": 45200000,
          "regularMarketPreviousClose": 194.50,
          "gmtoffset": -14400,
          "timezone": "EDT",
          "exchangeTimezoneName": "America/New_York",
          "chartPreviousClose": 194.50,
          "previousClose": 194.50,
          "scale": 3,
          "priceHint": 2,
          "currentTradingPeriod": {
            "pre": {
              "timezone": "EDT",
              "start": 1717401600,
              "end": 1717421400,
              "gmtoffset": -14400
            },
            "regular": {
              "timezone": "EDT",
              "start": 1717421400,
              "end": 1717444800,
              "gmtoffset": -14400
            },
            "post": {
              "timezone": "EDT",
              "start": 1717444800,
              "end": 1717459200,
              "gmtoffset": -14400
            }
          },
          "dataGranularity": "1d",
          "range": "1mo",
          "validRanges": ["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"]
        },
        "timestamp": [1715904000, 1715990400, 1716076800, ...],
        "indicators": {
          "quote": [
            {
              "open": [189.43, 187.70, 189.02, ...],
              "high": [190.68, 188.70, 190.00, ...],
              "low": [187.88, 186.80, 188.33, ...],
              "close": [189.66, 188.27, 189.83, ...],
              "volume": [34600800, 30563400, 29645200, ...]
            }
          ],
          "adjclose": [
            {
              "adjclose": [189.56, 188.17, 189.73, ...]
            }
          ]
        },
        "events": {
          "dividends": {
            "1718323200": {
              "amount": 0.25,
              "date": 1718323200
            }
          },
          "splits": {
            "1598572800": {
              "date": 1598572800,
              "numerator": 4,
              "denominator": 1,
              "splitRatio": "4:1"
            }
          }
        }
      }
    ],
    "error": null
  }
}
```

### 数据解析示例

```python
r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/AAPL",
                 params={"range": "1y", "interval": "1d", "events": "div,splits"},
                 headers=HEADERS)
data = r.json()
result = data["chart"]["result"][0]

# 时间戳列表
timestamps = result["timestamp"]

# OHLCV 并行数组
opens = result["indicators"]["quote"][0]["open"]
highs = result["indicators"]["quote"][0]["high"]
lows = result["indicators"]["quote"][0]["low"]
closes = result["indicators"]["quote"][0]["close"]
volumes = result["indicators"]["quote"][0]["volume"]

# 复权收盘价
adj_closes = result["indicators"]["adjclose"][0]["adjclose"]

# 元数据
meta = result["meta"]
print(meta["symbol"], meta["currency"], meta["regularMarketPrice"])

# 公司行动事件
events = result.get("events", {})
dividends = events.get("dividends", {})
splits = events.get("splits", {})
```

### 并行数组结构转换

返回的数据以按时间戳对齐的并行数组形式组织。若需将其转换为行记录（例如 DataFrame 格式）：

```python
rows = []
for i in range(len(timestamps)):
    rows.append({
        "date": datetime.fromtimestamp(timestamps[i], tz=timezone.utc),
        "open": opens[i],
        "high": highs[i],
        "low": lows[i],
        "close": closes[i],
        "volume": volumes[i],
        "adjclose": adj_closes[i],
    })
```

### 分红与拆股事件

分红与拆股采用字典格式组织（以字符串形式的 Unix 时间戳作为键名）：

```python
for ts_str, div in dividends.items():
    print(f"分红: ${div['amount']}，除息日 {datetime.fromtimestamp(int(ts_str))}")

for ts_str, split in splits.items():
    print(f"拆股: {split['numerator']}:{split['denominator']} "
          f"，生效日 {datetime.fromtimestamp(int(ts_str))}")
```

### v8/chart 关键注意事项

- **Yahoo Finance 中最稳定的接口**。无需身份验证即可正常调用。
- **必须提供 User-Agent 请求头。** 如果缺少浏览器 User-Agent，Yahoo 将返回错误响应或空数据。
- **无需使用 `yfinance`** —— 本技能直接通过 HTTP 请求与其通信。
- 非交易时段（周末、法定假日）的行情点位将显示为 `null`。
- `adjclose`（复权收盘价）对量化策略回测至关重要，因其已自动剔除拆股与现金分红的影响。

---

## 3. v7/finance/quote — 实时行情报价

### 接口地址

```
GET https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol1},{symbol2},...
```

**需要 Crumb 验证**（详见[身份验证](#1-身份验证cookie--crumb)一节）。

### 请求参数

| 参数 | 描述说明 |
|------|----------|
| `symbols` | 逗号分隔的标的代码（例如：`AAPL,MSFT,GOOGL`） |
| `crumb` | 身份验证令牌（使用 `yahoo_session()` 时自动附带） |

### JSON 响应结构

```json
{
  "quoteResponse": {
    "result": [
      {
        "language": "en-US",
        "region": "US",
        "quoteType": "EQUITY",
        "typeDisp": "Equity",
        "quoteSourceName": "Nasdaq Real Time Price",
        "triggerable": true,
        "customPriceAlertConfidence": "HIGH",
        "currency": "USD",
        "exchange": "NMS",
        "shortName": "Apple Inc.",
        "longName": "Apple Inc.",
        "messageBoardId": "finmb_24937",
        "exchangeTimezoneName": "America/New_York",
        "exchangeTimezoneShortName": "EDT",
        "gmtOffSetMilliseconds": -14400000,
        "market": "us_market",
        "marketState": "REGULAR",
        "esgPopulated": true,
        "firstTradeDateMilliseconds": 345479400000,
        "priceHint": 2,
        "regularMarketChange": {
          "raw": 2.39,
          "fmt": "2.39"
        },
        "regularMarketChangePercent": {
          "raw": 1.2284,
          "fmt": "1.23%"
        },
        "regularMarketPrice": {
          "raw": 196.89,
          "fmt": "196.89"
        },
        "regularMarketDayHigh": {
          "raw": 197.92,
          "fmt": "197.92"
        },
        "regularMarketDayLow": {
          "raw": 194.81,
          "fmt": "194.81"
        },
        "regularMarketVolume": {
          "raw": 45200000,
          "fmt": "45.2M"
        },
        "regularMarketPreviousClose": {
          "raw": 194.50,
          "fmt": "194.50"
        },
        "regularMarketOpen": {
          "raw": 195.19,
          "fmt": "195.19"
        },
        "averageDailyVolume3Month": {
          "raw": 50300000,
          "fmt": "50.3M"
        },
        "averageDailyVolume10Day": {
          "raw": 42100000,
          "fmt": "42.1M"
        },
        "fiftyTwoWeekLowChange": {
          "raw": 55.68,
          "fmt": "55.68"
        },
        "fiftyTwoWeekLowChangePercent": {
          "raw": 0.3943,
          "fmt": "39.43%"
        },
        "fiftyTwoWeekRange": {
          "raw": "141.21 - 199.62",
          "fmt": "141.21 - 199.62"
        },
        "fiftyTwoWeekHighChange": {
          "raw": -2.73,
          "fmt": "-2.73"
        },
        "fiftyTwoWeekHighChangePercent": {
          "raw": -0.0137,
          "fmt": "-1.37%"
        },
        "fiftyTwoWeekLow": {
          "raw": 141.21,
          "fmt": "141.21"
        },
        "fiftyTwoWeekHigh": {
          "raw": 199.62,
          "fmt": "199.62"
        },
        "dividendDate": 1718323200,
        "earningsTimestamp": 1717459200,
        "earningsTimestampStart": 1717459200,
        "earningsTimestampEnd": 1717459200,
        "earningsCallTimestampStart": 1717466400,
        "earningsCallTimestampEnd": 1717466400,
        "isEarningsDateEstimate": false,
        "trailingAnnualDividendRate": {
          "raw": 1.0,
          "fmt": "1.00"
        },
        "trailingPE": {
          "raw": 29.86,
          "fmt": "29.86"
        },
        "trailingAnnualDividendYield": {
          "raw": 0.0051,
          "fmt": "0.51%"
        },
        "marketCap": {
          "raw": 3020000000000,
          "fmt": "3.02T"
        },
        "tradeable": false
      }
    ],
    "error": null
  }
}
```

### 行情核心字段说明

| 字段路径 | 类型 | 描述说明 |
|----------|------|----------|
| `regularMarketPrice.raw` | float | 当前价格 |
| `regularMarketChangePercent.raw` | float | 涨跌幅百分比（例如：1.23 表示 +1.23%） |
| `regularMarketVolume.raw` | int | 当日成交量 |
| `regularMarketOpen.raw` | float | 今日开盘价 |
| `regularMarketDayHigh.raw` | float | 今日最高价 |
| `regularMarketDayLow.raw` | float | 今日最低价 |
| `regularMarketPreviousClose.raw` | float | 昨日收盘价 |
| `fiftyTwoWeekHigh.raw` | float | 52 周最高价 |
| `fiftyTwoWeekLow.raw` | float | 52 周最低价 |
| `marketCap.raw` | int | 总市值 |
| `trailingPE.raw` | float | 滚动市盈率 (TTM P/E) |
| `trailingAnnualDividendYield.raw` | float | 滚动年化股息率 |
| `trailingAnnualDividendRate.raw` | float | 滚动年化每股股息金额 |
| `dividendDate` | int | 下次派息日期 (Unix 时间戳) |
| `earningsTimestamp` | int | 下次财报发布时间 (Unix 时间戳) |
| `shortName` | string | 标的简称 |
| `longName` | string | 标的全称 |
| `exchange` | string | 交易所代码（NMS, NYQ, NASDAQ 等） |
| `marketState` | string | 市场状态：`PRE` (盘前), `REGULAR` (正常交易), `POST` (盘后), `CLOSED` (闭市) |
| `currency` | string | 结算货币（USD, ARS, CNY 等） |
| `averageDailyVolume3Month.raw` | int | 3 个月日均成交量 |

### 注意事项

- 包含 `raw` 与 `fmt` 的字段在所有接口中保持完全一致：`raw` 是原始数值，适用于数值运算与量化策略；`fmt` 是格式化后的字符串，适用于界面展示。
- `marketState` 非常适合用于判断当前目标市场是否处于开市交易时段。
- `esgPopulated` 用于指示该标的是否存在 ESG 评分数据。

---

## 4. v10/finance/quoteSummary — 基本面数据

### 接口地址

```
GET https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules={mod1},{mod2}
```

**需要 Crumb 验证。**

### 全部可用模块（共 33 个）

| # | 模块名 | 描述说明 | 典型响应体积 |
|---|--------|----------|:------------:|
| 1 | `assetProfile` | 标的完整概况：所属行业板块、细分行业、全职雇员数、业务描述、总部地址 | 大 |
| 2 | `summaryProfile` | 标的概况摘要（简明版） | 小 |
| 3 | `financialData` | 核心财务指标：EBITDA、营收、利润率、净资产收益率 (ROE)、资产回报率 (ROA)、负债权益比 (Debt/Equity) | 中 |
| 4 | `defaultKeyStatistics` | 关键估值与交易统计指标：Beta 系数、总市值、流通股本、做空比例等 | 中 |
| 5 | `incomeStatementHistory` | 利润表历史（按年度，包含多年） | 大 |
| 6 | `incomeStatementHistoryQuarterly` | 季度利润表历史 | 大 |
| 7 | `balanceSheetHistory` | 资产负债表历史（按年度，包含多年） | 大 |
| 8 | `balanceSheetHistoryQuarterly` | 季度资产负债表历史 | 大 |
| 9 | `cashflowStatementHistory` | 现金流量表历史（按年度，包含多年） | 大 |
| 10 | `cashflowStatementHistoryQuarterly` | 季度现金流量表历史 | 大 |
| 11 | `earnings` | 季度历史收益与年度盈利趋势 | 中 |
| 12 | `earningsHistory` | 各季度每股收益 (EPS) 实际值 vs 市场预期值 | 中 |
| 13 | `earningsTrend` | 未来盈利预期与分析师 EPS 预测趋势 | 中 |
| 14 | `recommendationTrend` | 分析师评级走势：各周期内强力买入、买入、持有、卖出评级分布 | 中 |
| 15 | `upgradeDowngradeHistory` | 券商评级上调/下调历史记录 | 中 |
| 16 | `insiderTransactions` | 内部人士交易记录（高管/董事买入与卖出明细） | 中 |
| 17 | `insiderHolders` | 内部持股人名单及持股数量 | 小 |
| 18 | `institutionOwnership` | 机构投资者持股明细、变动及持股占比 | 中 |
| 19 | `fundOwnership` | 共同基金持股明细 | 中 |
| 20 | `majorDirectHolders` | 主要直接持股人 | 小 |
| 21 | `majorHoldersBreakdown` | 股权结构分布（机构、内部人士、公众流通股等比例） | 小 |
| 22 | `secFilings` | 最新 SEC 监管申报文件（10-K, 10-Q, 8-K 等） | 中 |
| 23 | `calendarEvents` | 财经日历事件：下次财报发布日、分红派息日、除息日 | 小 |
| 24 | `price` | 详细价格信息、盘前/盘后价格、52 周价格区间 | 中 |
| 25 | `quoteType` | 标的资产类型：EQUITY, ETF, MUTUALFUND, INDEX 等 | 小 |
| 26 | `summaryDetail` | 核心交易摘要：买价、卖价、成交量、平均成交量、股息率、Beta | 中 |
| 27 | `symbol` | 标的代码 | 极小 |
| 28 | `topHoldings` | 前大重仓持仓（仅限 ETF） | 大（仅限 ETF） |
| 29 | `fundProfile` | 基金资料与分类属性（仅限 ETF / 共同基金） | 大（仅限基金） |
| 30 | `indexTrend` | 指数趋势变化数据 | 小 |
| 31 | `sectorTrend` | 板块趋势变化数据 | 小 |
| 32 | `industryTrend` | 细分行业趋势变化数据 | 小 |
| 33 | `netSharePurchaseActivity` | 股票回购与股份净申购活动 | 中 |

### 推荐的核心模块组合

若需对任意股票标的进行快速且全面的基本面画像分析，建议请求以下核心模块组合：

```
assetProfile,financialData,defaultKeyStatistics,
incomeStatementHistory,balanceSheetHistory,cashflowStatementHistory,
earnings,earningsTrend,recommendationTrend,
calendarEvents,price,summaryDetail
```

### 响应示例（assetProfile）

```json
{
  "quoteSummary": {
    "result": [
      {
        "assetProfile": {
          "address1": "One Apple Park Way",
          "city": "Cupertino",
          "state": "CA",
          "zip": "95014",
          "country": "United States",
          "phone": "14089961010",
          "website": "https://www.apple.com",
          "industry": "Consumer Electronics",
          "industryKey": "consumer-electronics",
          "industryDisp": "Consumer Electronics",
          "sector": "Technology",
          "sectorKey": "technology",
          "sectorDisp": "Technology",
          "longBusinessSummary": "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide...",
          "fullTimeEmployees": 161000,
          "companyOfficers": [
            {
              "name": "Mr. Timothy D. Cook",
              "age": 63,
              "title": "CEO & Director",
              "yearBorn": 1961,
              "fiscalYear": 2023,
              "totalPay": {"raw": 63200000, "fmt": "63.2M"}
            }
          ],
          "auditRisk": 7,
          "boardRisk": 3,
          "compensationRisk": 6,
          "shareHolderRightsRisk": 2,
          "overallRisk": 5,
          "governanceEpochDate": 1719792000,
          "compensationAsOfEpochDate": 1704067200,
          "maxAge": 1
        }
      }
    ],
    "error": null
  }
}
```

### 财务指标示例（financialData）

```json
{
  "financialData": {
    "currentPrice": {"raw": 196.89, "fmt": "196.89"},
    "targetHighPrice": {"raw": 250.00, "fmt": "250.00"},
    "targetLowPrice": {"raw": 150.00, "fmt": "150.00"},
    "targetMeanPrice": {"raw": 205.43, "fmt": "205.43"},
    "targetMedianPrice": {"raw": 205.00, "fmt": "205.00"},
    "recommendationMean": {"raw": 1.8, "fmt": "1.80"},
    "recommendationKey": "buy",
    "numberOfAnalystOpinions": {"raw": 42, "fmt": "42"},
    "totalRevenue": {"raw": 391400000000, "fmt": "391.4B"},
    "revenuePerShare": {"raw": 24.95, "fmt": "24.95"},
    "revenueGrowth": {"raw": 0.071, "fmt": "7.1%"},
    "grossProfits": {"raw": 170800000000, "fmt": "170.8B"},
    "grossMargin": {"raw": 0.452, "fmt": "45.2%"},
    "ebitda": {"raw": 130000000000, "fmt": "130B"},
    "ebitdaMargins": {"raw": 0.332, "fmt": "33.2%"},
    "operatingMargin": {"raw": 0.293, "fmt": "29.3%"},
    "profitMargins": {"raw": 0.251, "fmt": "25.1%"},
    "netIncomeToCommon": {"raw": 96990000000, "fmt": "96.99B"},
    "earningsGrowth": {"raw": 0.089, "fmt": "8.9%"},
    "returnOnAssets": {"raw": 0.214, "fmt": "21.4%"},
    "returnOnEquity": {"raw": 1.342, "fmt": "134.2%"},
    "debtToEquity": {"raw": 1.49, "fmt": "149.0%"},
    "quickRatio": {"raw": 0.81, "fmt": "0.81"},
    "currentRatio": {"raw": 0.97, "fmt": "0.97"},
    "totalCash": {"raw": 61100000000, "fmt": "61.1B"},
    "totalDebt": {"raw": 105500000000, "fmt": "105.5B"},
    "totalCashPerShare": {"raw": 3.90, "fmt": "3.90"},
    "earningsQuarterlyGrowth": {"raw": -0.041, "fmt": "-4.1%"},
    "revenuePerEmployee": {"raw": 2430000, "fmt": "2.43M"},
    "freeCashflow": {"raw": 96920000000, "fmt": "96.92B"}
  }
}
```

### 核心模块常用字段解析

**defaultKeyStatistics（关键估值统计）：**

| 字段 | 描述说明 |
|------|----------|
| `beta` | Beta 系数（相对于市场基准的波动率） |
| `floatShares` | 自由流通股本数 |
| `sharesOutstanding` | 总发行流通股本数 |
| `sharesShort` | 融券做空股数 |
| `shortRatio` | 做空比率（补仓所需天数） |
| `heldPercentInstitutions` | 机构投资者持股比例 |
| `heldPercentInsiders` | 内部人士持股比例 |
| `bookValue` | 每股净资产 (Book Value Per Share) |
| `priceToBook` | 市净率 (P/B Ratio) |
| `earningsQuarterlyGrowth` | 季度净利润同比增速 |
| `netIncomeToCommon` | 归属于普通股股东的净利润 |
| `trailingEps` | 滚动每股收益 (TTM EPS) |
| `forwardEps` | 预期每股收益 (Forward EPS) |
| `pegRatio` | PEG 比率（市盈率相对盈利增长比率） |
| `lastDividendValue` | 最近一次派息每股分红额 |
| `lastDividendDate` | 最近一次派息日期 (Unix 时间戳) |
| `nextFiscalYearEnd` | 下一财年截止日 (Unix 时间戳) |
| `mostRecentQuarter` | 最新财报报告期 (Unix 时间戳) |

**incomeStatementHistory（利润表历史）：**

```json
{
  "incomeStatementHistory": {
    "incomeStatementHistory": [
      {
        "endDate": {"raw": 1704067200, "fmt": "2023-12-31"},
        "totalRevenue": {"raw": 383300000000, "fmt": "383.3B"},
        "costOfRevenue": {"raw": 214100000000, "fmt": "214.1B"},
        "grossProfit": {"raw": 169200000000, "fmt": "169.2B"},
        "operatingIncome": {"raw": 114300000000, "fmt": "114.3B"},
        "netIncome": {"raw": 97000000000, "fmt": "97B"},
        "ebit": {"raw": 114300000000, "fmt": "114.3B"},
        "totalOperatingExpenses": {"raw": 269000000000, "fmt": "269B"}
      }
    ],
    "maxAge": 86400
  }
}
```

---

## 5. v7/finance/options — 期权链

### 接口地址

```
GET https://query1.finance.yahoo.com/v7/finance/options/{symbol}
GET https://query1.finance.yahoo.com/v7/finance/options/{symbol}?date={unix_timestamp}
```

**需要 Crumb 验证。**

### JSON 响应结构

```json
{
  "optionChain": {
    "result": [
      {
        "underlyingSymbol": "AAPL",
        "expirationDates": [1719878400, 1720569600, 1721260800, ...],
        "strikes": [170.0, 175.0, 180.0, 185.0, 190.0, 195.0, 200.0, ...],
        "hasMiniOptions": false,
        "quote": {
          "shortName": "Apple Inc.",
          "regularMarketPrice": {"raw": 196.89},
          "regularMarketChange": {"raw": 2.39},
          "regularMarketVolume": {"raw": 45200000},
          "fiftyTwoWeekHigh": {"raw": 199.62},
          "fiftyTwoWeekLow": {"raw": 141.21},
          "marketCap": {"raw": 3020000000000}
        },
        "options": [
          {
            "expirationDate": 1719878400,
            "hasMiniOptions": false,
            "calls": [
              {
                "contractSymbol": "AAPL240621C00195000",
                "strike": {"raw": 195.0, "fmt": "195.00"},
                "currency": "USD",
                "lastPrice": {"raw": 4.55, "fmt": "4.55"},
                "change": {"raw": 0.45, "fmt": "0.45"},
                "percentChange": {"raw": 10.97, "fmt": "10.97%"},
                "volume": {"raw": 15234, "fmt": "15.2k"},
                "openInterest": {"raw": 84500, "fmt": "84.5k"},
                "bid": {"raw": 4.50, "fmt": "4.50"},
                "ask": {"raw": 4.60, "fmt": "4.60"},
                "contractSize": "REGULAR",
                "expiration": 1719878400,
                "lastTradeDate": 1717444800,
                "impliedVolatility": {"raw": 0.281, "fmt": "28.1%"},
                "inTheMoney": true
              }
            ],
            "puts": [
              {
                "contractSymbol": "AAPL240621P00195000",
                "strike": {"raw": 195.0, "fmt": "195.00"},
                "currency": "USD",
                "lastPrice": {"raw": 2.85, "fmt": "2.85"},
                "change": {"raw": -0.32, "fmt": "-0.32"},
                "percentChange": {"raw": -10.09, "fmt": "-10.09%"},
                "volume": {"raw": 8900, "fmt": "8.9k"},
                "openInterest": {"raw": 62300, "fmt": "62.3k"},
                "bid": {"raw": 2.80, "fmt": "2.80"},
                "ask": {"raw": 2.90, "fmt": "2.90"},
                "contractSize": "REGULAR",
                "expiration": 1719878400,
                "lastTradeDate": 1717444800,
                "impliedVolatility": {"raw": 0.305, "fmt": "30.5%"},
                "inTheMoney": false
              }
            ]
          }
        ]
      }
    ],
    "error": null
  }
}
```

### 期权合约字段说明

| 字段 | 描述说明 |
|------|----------|
| `contractSymbol` | OCC 标准期权合约代码 |
| `strike` | 行权价 (Strike Price) |
| `lastPrice` | 最新成交价 |
| `bid` | 当前最高买价 |
| `ask` | 当前最低卖价 |
| `volume` | 当日成交量 |
| `openInterest` | 未平仓合约数 (Open Interest) |
| `impliedVolatility` | 隐含波动率 (IV) |
| `inTheMoney` | 是否为实值期权（布尔值，true 表示实值期权） |
| `expiration` | 到期日 Unix 时间戳 |
| `change` | 价格涨跌额 |
| `percentChange` | 涨跌幅百分比 |
| `contractSize` | 合约乘数（REGULAR 通常对应 100 股标的股票） |

### 如何获取所有到期日的期权链

```python
# 1. 获取所有到期日列表
r = session.get("https://query1.finance.yahoo.com/v7/finance/options/AAPL")
data = r.json()
expirations = data["optionChain"]["result"][0]["expirationDates"]

# 2. 依次遍历每个到期日
for exp in expirations[:5]:  # 获取前 5 个到期日
    r = session.get(f"https://query1.finance.yahoo.com/v7/finance/options/AAPL?date={exp}")
    data = r.json()
    options = data["optionChain"]["result"][0]["options"][0]
    calls = options["calls"]
    puts = options["puts"]
    print(f"到期日 {datetime.fromtimestamp(exp)}: {len(calls)} 看涨期权(calls), {len(puts)} 看跌期权(puts)")
    time.sleep(0.5)
```

> **注意：** 美股以外的标的一般不提供期权数据。例如布宜诺斯艾利斯证券交易所的 GGAL (BCBA)，该接口可能返回空结果。

---

## 6. v1/finance/search — 搜索与新闻

### 接口地址

```
GET https://query1.finance.yahoo.com/v1/finance/search?q={query}
```

**无需身份验证。**

### 请求参数

| 参数 | 默认值 | 描述说明 |
|------|--------|----------|
| `q` | — | 搜索关键词（必填） |
| `quotesCount` | 10 | 返回的标的报价数量 |
| `newsCount` | 10 | 返回的新闻条数 |
| `enableCb` | false | 是否包含商业银行相关结果 |

### JSON 响应结构

```json
{
  "explains": [],
  "count": 5,
  "quotes": [
    {
      "symbol": "AAPL",
      "isYahooFinance": true,
      "exchange": "NMS",
      "exchangeName": "NasdaqGS",
      "typeDisp": "Equity",
      "quoteType": "EQUITY",
      "shortname": "Apple Inc.",
      "longname": "Apple Inc.",
      "sector": "Technology",
      "industry": "Consumer Electronics",
      "isEligibleForCrossBorder": false
    }
  ],
  "news": [
    {
      "uuid": "some-uuid",
      "title": "Apple Hits New All-Time High Ahead of WWDC",
      "publisher": "Bloomberg",
      "link": "https://finance.yahoo.com/news/...",
      "type": "STORY",
      "providerPublishTime": 1717444800,
      "relatedTickers": ["AAPL"],
      "summary": "Apple Inc. shares reached a new all-time high...",
      "thumbnail": {
        "resolutions": [
          {"url": "https://s.yimg.com/...", "width": 200, "height": 200, "tag": "original"}
        ]
      }
    }
  ],
  "timeZoneShortName": "EDT"
}
```

### 注意事项

- 适用于在标的代码不确定时的**自动补全**与**标的快速查询**。
- 新闻数据包含带有配图 URL 与尺寸信息的 `thumbnail` 对象。
- `typeDisp` 字段有助于准确识别资产类型：`Equity`（股票）、`ETF`、`Mutual Fund`（共同基金）、`Index`（指数）等。
- 若所搜标的不存在，`quotes` 数组将为空，但仍可能返回相关的 `news`。

---

## 7. v6/finance/recommendationsbysymbol — 相似标的推荐

### 接口地址

```
GET https://query1.finance.yahoo.com/v6/finance/recommendationsbysymbol/{symbol}
```

**需要 Crumb 验证。**

### JSON 响应结构

```json
{
  "finance": {
    "result": [
      {
        "symbol": "AAPL",
        "recommendedSymbols": [
          {"symbol": "MSFT", "score": 0.95},
          {"symbol": "GOOGL", "score": 0.88},
          {"symbol": "AMZN", "score": 0.82},
          {"symbol": "NVDA", "score": 0.79}
        ]
      }
    ],
    "error": null
  }
}
```

该接口返回与目标标的**具有相似业务属性的推荐标的代码**及相关性得分（注意：此为基于标的属性的算法推荐，而非分析师买卖评级；分析师评级请参考 `quoteSummary.recommendationTrend`）。

---

## 8. v1/finance/trending — 热门趋势标的

### 接口地址

```
GET https://query1.finance.yahoo.com/v1/finance/trending/{country}
```

**无需身份验证。**

### 请求参数

| 参数 | 可选国家/地区代码 |
|------|-------------------|
| `country` | `US`, `AU`, `CA`, `DE`, `HK`, `IN`, `MX`, `MY`, `NZ`, `SG`, `UK`, `VN` |

### JSON 响应结构

```json
{
  "finance": {
    "result": [
      {
        "count": 10,
        "quotes": [
          {"symbol": "AAPL"},
          {"symbol": "NVDA"},
          {"symbol": "TSLA"},
          {"symbol": "MSFT"},
          {"symbol": "AMZN"}
        ],
        "jobTimestamp": 1717444800,
        "startInterval": 1717358400
      }
    ],
    "error": null
  }
}
```

### 注意事项

- 热门趋势列表每隔约 15 分钟更新一次。
- `US`（美国市场）的数据最为全面稳定；其他国家/地区可能数据较少。

---

## 9. v1/finance/lookup — 标的代码查询

### 接口地址

```
GET https://query1.finance.yahoo.com/v1/finance/lookup?query={query}&type=equity
```

**无需身份验证。**

### 请求参数

| 参数 | 描述说明 |
|------|----------|
| `query` | 检索关键词 |
| `type` | 资产类别：`equity`（股票）, `option`（期权）, `future`（期货）, `currency`（货币） |
| `lang` | 语言代码（默认值：`en-US`） |
| `region` | 地区代码（默认值：`US`） |

### JSON 响应结构

```json
{
  "finance": {
    "result": [
      {"symbol": "AAPL", "name": "Apple Inc.", "type": "EQUITY", "exch": "NMS"}
    ],
    "error": null
  }
}
```

---

## 10. v1/finance/screener — 选股器

### 接口地址

```
GET https://query1.finance.yahoo.com/v1/finance/screener?scrIds={scrId}&count={count}
```

**有时需要 Crumb 验证。**

### 常用预设选股器策略

| scrId | 策略描述 |
|-------|----------|
| `most_actives` | 最活跃股票（按成交量/成交额） |
| `day_gainers` | 今日涨幅榜 |
| `day_losers` | 今日跌幅榜 |
| `undervalued_growth_stocks` | 低估值成长股 |
| `aggressive_small_caps` | 进取型小盘股 |
| `portfolio_anchors` | 核心持仓基石股 |

### 调用示例

```python
s = yahoo_session()
r = s.get("https://query1.finance.yahoo.com/v1/finance/screener",
          params={"scrIds": "most_actives", "count": 10})
data = r.json()
for quote in data["finance"]["result"][0]["quotes"]:
    print(quote["symbol"], quote.get("regularMarketPrice"))
```

---

## 11. WebSocket 流式推送

Yahoo Finance 提供了用于获取实时行情的 WebSocket 接口端点：

```
wss://streamer.finance.yahoo.com/?version=2
```

### 基础用法示例

```python
import websocket

def on_message(ws, message):
    data = json.loads(message)
    print(data)

ws = websocket.WebSocketApp("wss://streamer.finance.yahoo.com/?version=2",
                            on_message=on_message)
ws.run_forever()
```

数据消息使用 **Protobuf 格式** 编码，而非纯 JSON 格式。客户端需要处理 Crumb 签名与鉴权握手。其实现复杂度远高于 REST 接口，在常规数据采集与量化研究场景中**不推荐使用**。采用每隔 20-30 秒轮询一次的 REST 接口方案更为稳健高效。

---

## 12. 速率限制与应对策略

### 实际观测的限流阈值

| 请求频率 | 后果与系统表现 |
|----------|----------------|
| ~2 请求/秒 | 绝对安全阈值 |
| 持续 3-5 请求/秒 | 极高概率触发 429 Too Many Requests 错误 |
| 突发 >10 请求/秒 | 临时封禁 IP（通常持续 30-60 分钟） |
| 预估约 2000 请求/小时 | 软性每日请求上限 |

### 推荐的重试策略

```python
import time
import random

def safe_request(func, *args, retries=3, **kwargs):
    """采用指数退避算法的请求封装函数。"""
    for attempt in range(retries):
        try:
            resp = func(*args, **kwargs)
            if resp.status_code == 429:
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"触发限流，等待 {wait:.1f} 秒后重试...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(wait)
```

### User-Agent 轮换机制

```python
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/17.1",
]

headers = {"User-Agent": random.choice(USER_AGENTS)}
```

### 响应数据本地缓存

历史行情数据是不变的。对于批量拉取任务，建议在本地建立缓存以避免重复请求：

```python
import os
import hashlib
import json

CACHE_DIR = ".yf_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def cached_get(url, params, ttl_seconds=3600):
    key = hashlib.md5(f"{url}{json.dumps(params, sort_keys=True)}".encode()).hexdigest()
    cache_file = os.path.join(CACHE_DIR, f"{key}.json")
    
    if os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < ttl_seconds:
            with open(cache_file) as f:
                return json.load(f)
    
    resp = requests.get(url, params=params, headers=HEADERS)
    data = resp.json()
    with open(cache_file, "w") as f:
        json.dump(data, f)
    return data
```

---

## 13. 错误代码与故障排查

| 错误信息 | 原因分析 | 解决方案 |
|----------|----------|----------|
| `401 Unauthorized` | 缺少 Crumb 或 A3 Cookie | 使用 `yahoo_session()` 初始化会话 |
| `429 Too Many Requests` | 超过接口访问速率限制 | 等待 30-60 秒后重试，降低请求频率 |
| `{"finance":{"error":{"code":"Bad Request"}}}` | Crumb 无效或已过期 | 重新获取并生成新的 Crumb |
| `chart.result` 为空或为 `null` | 标的代码无效，或指定的时间范围/采样周期无数据 | 检查代码是否正确；尝试调整 `range` 或 `interval` |
| `Quote data missing` | 该标的未公开报价数据 | 确认该标的代码在 Yahoo 上是否存在 |
| 连接被拒绝 (Connection Refused) | 主域名 `query1.finance.yahoo.com` 无响应 | 降级备用域名 `query2.finance.yahoo.com` |
| 返回空 JSON `{}` | 遭遇限流或 IP 临时受限 | 暂停请求，使用指数退避算法重试 |
| `chart.error.code: "Not Found"` | 未找到该标的 | 检查代码后缀（如阿根廷标的须加 `.BA`） |
| 检测到 `Python-requests/2.xx` | 使用了 requests 库默认的 User-Agent | 设置为常见浏览器的 User-Agent |
| SSL Error | 网络异常或证书握手失败 | 重试请求，检查网络代理及网络连通性 |

### 快速调试代码

```python
# 验证标的代码是否存在
r = requests.get(
    "https://query1.finance.yahoo.com/v1/finance/lookup",
    params={"query": "GGAL", "type": "equity"},
    headers=HEADERS
)
print(r.json())

# 验证 Crumb 是否能正常获取
s = requests.Session()
s.headers.update(HEADERS)
s.get("https://fc.yahoo.com")
crumb = s.get("https://query1.finance.yahoo.com/v1/test/getcrumb").text
print(f"Crumb: {crumb}")
```

---

## 14. 国际标的代码（Tickers）

Yahoo Finance 通过**交易所后缀**支持全球各大证券市场的行情代码：

| 国家/市场 | 后缀 | 示例 |
|-----------|------|------|
| 阿根廷 (BCBA) | `.BA` | `GGAL.BA`, `YPFD.BA`, `PAMP.BA` |
| 巴西 (Bovespa) | `.SA` | `PETR4.SA`, `VALE3.SA` |
| 墨西哥 (BMV) | `.MX` | `WALMEX.MX`, `CEMEX.CPO.MX` |
| 加拿大 (TSX) | `.TO` | `SHOP.TO`, `TD.TO` |
| 英国 (LSE) | `.L` | `HSBA.L`, `BP.L` |
| 德国 (Xetra) | `.DE` | `SAP.DE`, `DAI.DE` |
| 中国香港 (HKEX) | `.HK` | `0700.HK`, `9988.HK` |
| 日本 (TSE) | `.T` | `7203.T`, `9984.T` |
| 澳大利亚 (ASX) | `.AX` | `CBA.AX`, `BHP.AX` |
| 中国 (上交所) | `.SS` | `600519.SS` |
| 中国 (深交所) | `.SZ` | `000858.SZ` |
| 印度 (NSE) | `.NS` | `RELIANCE.NS`, `TCS.NS` |
| 印度 (BSE) | `.BO` | `RELIANCE.BO` |
| ETF 基金 | 无后缀 | `SPY`, `QQQ`, `ARKK` |
| 加密货币 | `-XXX` | `BTC-USD`, `ETH-USD`, `DOGE-USD` |
| 外汇汇率 | `=X` | `EURUSD=X`, `USDBRL=X` |
| 市场指数 | 前缀 `^` | `^GSPC` (标普500), `^IXIC` (纳斯达克), `^BVSP` (巴西伊波韦斯帕指数) |

### 国际标的代码查询示例

```python
# 查询布宜诺斯艾利斯证券交易所的 GGAL 行情
r = requests.get(
    "https://query1.finance.yahoo.com/v8/finance/chart/GGAL.BA",
    params={"range": "1y", "interval": "1d"},
    headers=HEADERS
)
print(r.json())
```

> **重要提示：** 并非所有接口都支持国际标的。例如 `v7/options` 通常仅支持美股期权；而 `v10/quoteSummary` 则支持绝大多数国际市场。

---

## 15. 跨接口通用字段规范

### `raw` 与 `fmt` 格式规范

Yahoo Finance 中几乎所有数值型字段均采用这种键值对结构：

```json
{
  "regularMarketPrice": {
    "raw": 196.89,       # 用于计算的原始数值 (float/int)
    "fmt": "196.89"      # 用于前端展示的格式化字符串
  }
}
```

在量化计算与指标运算中**始终使用 `.raw`**，在图表展示与打印输出时使用 `.fmt`。

### 市场交易状态（Market states）

| 状态值 | 含义解释 |
|--------|----------|
| `PRE` | 盘前交易（美东时间开盘前） |
| `REGULAR` | 正常交易时段（开盘中） |
| `POST` | 盘后交易（美东时间收盘后） |
| `CLOSED` | 休市/闭市状态 |

### 常见资产报价类型（Quote types）

| quoteType | 资产类别说明 |
|-----------|--------------|
| `EQUITY` | 普通股股票 |
| `ETF` | 交易型开放式指数基金 (ETF) |
| `MUTUALFUND` | 共同基金 / 公募基金 |
| `INDEX` | 市场指数 |
| `CURRENCY` | 法定货币汇率对 |
| `CRYPTOCURRENCY` | 加密货币 |
| `OPTION` | 期权合约 |
| `FUTURE` | 期货合约 |
| `BOND` | 债券 |

---

## 附录：快速 URL 参考汇总

```
# 无需身份验证
GET https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
GET https://query1.finance.yahoo.com/v1/finance/search
GET https://query1.finance.yahoo.com/v1/finance/trending/{country}
GET https://query1.finance.yahoo.com/v1/finance/lookup
GET https://fc.yahoo.com
GET https://query1.finance.yahoo.com/v1/test/getcrumb

# 需要 Crumb 验证（使用 yahoo_session()）
GET https://query1.finance.yahoo.com/v7/finance/quote
GET https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}
GET https://query1.finance.yahoo.com/v7/finance/options/{symbol}
GET https://query1.finance.yahoo.com/v6/finance/recommendationsbysymbol/{symbol}
GET https://query1.finance.yahoo.com/v1/finance/screener
```

---

*本文档基于对 Yahoo Finance 非官方接口的逆向工程整理而成。  
不保证接口的长期可用性或数据一致性，相关端点可能会在未经提前通知的情况下变更。*
