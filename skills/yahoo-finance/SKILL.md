---
name: yahoo-finance
description: "Yahoo Finance 非官方 API：获取股票价格、历史行情、基本面、期权及新闻的纯 JSON 数据，无需任何第三方包装库。"
license: MIT
---

# Yahoo Finance — 直连 API（无需 yfinance）

Yahoo Finance 非官方 API。无需使用 `yfinance` 或任何第三方包装库，直接通过 **HTTP 请求** 获取**股票、ETF、加密货币、外汇、债券、指数、期权、基本面及新闻**数据。

**Base URL（基础地址）：** `https://query1.finance.yahoo.com`  
**备用地址：** `https://query2.finance.yahoo.com`

---

## ⚠️ 重要说明

- Yahoo 自 2017 年起**不再提供官方公开 API**。此类接口均为非官方端点，可能会在未经通知的情况下发生变动。
- 部分接口需要通过 **Cookie + Crumb** 进行身份验证（详见下文）。
- `v8/finance/chart` 接口无需身份验证（仅需浏览器 User-Agent）。
- 请务必在代码中实现**速率限制（Rate Limiting）**与**错误处理**。

---

## 完整参考文档

如需查看所有接口、字段、JSON 结构、错误码、国际代码、速率限制策略及详细示例的全面参考，请参阅：

📖 **[references/API_REFERENCE.md](./references/API_REFERENCE.md)**

该文档包含：
- `quoteSummary` 的全部 **33 个模块**及其详细字段说明
- 每个接口的**完整** JSON 响应结构
- **国际代码（Tickers）**（阿根廷 `.BA`、巴西 `.SA` 等）
- **WebSocket 流式推送**
- **选股器（Screener）**、**代码查询（Lookup）**、**热门趋势（Trending）**
- 基于指数退避（Exponential Backoff）和 User-Agent 轮换的**速率限制策略**

---

## 身份验证：Cookie + Crumb

多个接口需要通过会话 Cookie 获取 **Crumb**（CSRF 令牌）。

```python
import requests

BASE = "https://query1.finance.yahoo.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def yahoo_session():
    """返回携带 A3 Cookie 和 Crumb 的 requests.Session。"""
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://fc.yahoo.com", timeout=10)
    crumb = s.get(f"{BASE}/v1/test/getcrumb", timeout=10).text.strip()
    s.params = {"crumb": crumb}
    return s

# 使用示例：
# s = yahoo_session()
# r = s.get("https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAPL,MSFT")
```

### 按验证方式分类的接口

| 无需验证（仅需 User-Agent） | 需要 Crumb 验证 |
|----------------------------|-----------------|
| `v8/finance/chart`（历史行情） | `v7/finance/quote`（实时行情） |
| `v1/finance/search`（搜索与新闻） | `v10/finance/quoteSummary`（基本面） |
| `v1/finance/trending`（热门趋势） | `v7/finance/options`（期权链） |
| `v1/finance/lookup`（代码查询） | `v6/finance/recommendationsbysymbol`（相似推荐） |

---

## 接口速查

### 1. 历史 OHLCV 行情 — `v8/finance/chart`

GET https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d

| 参数 | 示例值 |
|------|--------|
| `range` | `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `5y`, `10y`, `ytd`, `max` |
| `interval` | `1m`, `5m`, `15m`, `1h`, `1d`, `1wk`, `1mo` |
| `events` | `div,splits`（包含分红与拆股数据） |

```python
import requests
headers = {"User-Agent": "Mozilla/5.0 (...) Chrome/120.0.0.0 Safari/537.36"}
r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/AAPL",
                 params={"range": "1y", "interval": "1d", "events": "div,splits"},
                 headers=headers)
data = r.json()["chart"]["result"][0]
# data["timestamp"] -> Unix 时间戳列表
# data["indicators"]["quote"][0] -> open, high, low, close, volume
# data["indicators"]["adjclose"][0] -> 复权收盘价
# data["events"] -> 分红与拆股事件
```

### 2. 实时行情 — `v7/finance/quote`

```python
s = yahoo_session()
r = s.get("https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAPL,MSFT,GOOGL")
quotes = r.json()["quoteResponse"]["result"]
for q in quotes:
    print(q["symbol"], q["regularMarketPrice"], q["regularMarketChangePercent"])
```

常用字段：`regularMarketPrice`（当前价格）、`regularMarketChangePercent`（涨跌幅%）、`marketCap`（市值）、`trailingPE`（滚动市盈率）、`fiftyTwoWeekHigh/Low`（52周最高/最低）、`dividendYield`（股息率）、`volume`（成交量）、`marketState`（市场状态：PRE/REGULAR/POST/CLOSED）。

### 3. 基本面数据 — `v10/finance/quoteSummary`

```python
s = yahoo_session()
r = s.get("https://query1.finance.yahoo.com/v10/finance/quoteSummary/AAPL",
          params={"modules": "assetProfile,financialData,defaultKeyStatistics,incomeStatementHistory,balanceSheetHistory,cashflowStatementHistory,earnings,recommendationTrend"})
fundamentals = r.json()["quoteSummary"]["result"][0]
profile = fundamentals["assetProfile"]           # 板块、细分行业、雇员数、业务描述
financials = fundamentals["financialData"]        # EBITDA、营收、利润率、ROE、ROA
stats = fundamentals["defaultKeyStatistics"]      # Beta系数、股本、PE、PEG、做空数据
```

共有 **33 个可用模块**。完整列表详见 [API_REFERENCE.md 第 4 节](./references/API_REFERENCE.md#4-v10financequotesummary--基本面数据)。

### 4. 期权链 — `v7/finance/options`

```python
s = yahoo_session()
r = s.get("https://query1.finance.yahoo.com/v7/finance/options/AAPL")
data = r.json()["optionChain"]["result"][0]
expirations = data["expirationDates"]
strikes = data["strikes"]
options = data["options"][0]  # 看涨期权（calls） + 看跌期权（puts）
```

### 5. 搜索与新闻 — `v1/finance/search`

```python
r = requests.get("https://query1.finance.yahoo.com/v1/finance/search",
                 params={"q": "Apple", "quotesCount": 3, "newsCount": 5},
                 headers=HEADERS)
data = r.json()
# data["quotes"] -> 搜索到的标的代码及简要信息
# data["news"] -> 相关新闻资讯
```

---

## 脚本工具

| 脚本 | 描述说明 |
|------|----------|
| **[batch_fetch.py](./scripts/batch_fetch.py)** | 采用令牌桶（Token Bucket）+ ThreadPoolExecutor 的多标的批量抓取工具。行情批量打包（单次请求获取所有标的）。在严格遵守速率限制的同时并行获取图表数据。 |
| **[fetch_all.py](./scripts/fetch_all.py)** | 全功能综合采集脚本：一次性获取历史数据 + 实时行情 + 基本面 + 期权 + 搜索 + 相似推荐。支持任意标的的通用 CLI 参数配置。 |
| **[fetch_quote.py](./scripts/fetch_quote.py)** | 快速获取单个标的的实时行情与核心基本面数据。 |
| **[download_historical.py](./scripts/download_historical.py)** | 下载 OHLCV 历史行情并导出为 CSV 文件。 |

### batch_fetch.py — 带速率限制的多标的批量抓取

```bash
# 安全测试（3 个标的，仅获取历史图表，速率 2 请求/秒）
py scripts/batch_fetch.py --tickers AAPL,MSFT,NVDA --chart --rate 2.0

# 完整批量获取（单次请求获取所有行情 + 并发获取图表数据）
py scripts/batch_fetch.py --tickers AAPL,MSFT,NVDA,GOOGL,META,AMZN,TSLA --all --rate 2.0 --workers 4

# 仅获取实时行情（始终单次请求完成，绝对不会触发限流）
py scripts/batch_fetch.py --tickers AAPL,MSFT,NVDA,GOOGL --quote

# 自定义速率限制与工作线程数
py scripts/batch_fetch.py --tickers AAPL,MSFT,NVDA --all --rate 1.5 --workers 3 --range 5y
```

**核心参数说明：**
- `--rate`：令牌桶每秒生成的令牌数（默认值：2.0，推荐的安全上限）
- `--burst`：突发流量允许积累的最大令牌数（默认值：5）
- `--workers`：并发工作线程数（默认值：4）

**处理架构：**
1. **阶段 1 — 行情批量获取（Quote batch）**：所有标的合并在 1 次请求中完成（`v7/finance/quote?symbols=AAPL,MSFT,...`）
2. **阶段 2 — 令牌桶限流（Token bucket）**：`ThreadPoolExecutor` 搭配跨线程共享的线程安全 `TokenBucket`。每个工作线程在发起请求前必须获取一个令牌。在 2 req/s 且 burst=5 时，允许突发发起最多 5 次瞬时请求而不被阻塞；随后令牌桶将请求吞吐量平滑稳定在安全阈值以内。

### fetch_all.py — 主采集脚本

```bash
python scripts/fetch_all.py --ticker AAPL --all                     # 获取所有可用数据
python scripts/fetch_all.py --ticker GGAL --all --range 5y --interval 1d  # 获取 GGAL 5年日K线及全量数据
python scripts/fetch_all.py --ticker MSFT --chart --range max        # 获取微软完整历史行情
python scripts/fetch_all.py --ticker NVDA --quote --fundamentals     # 获取英伟达实时行情 + 基本面
python scripts/fetch_all.py --ticker TSLA --all --all-modules        # 获取特斯拉全部模块（~33 个）
python scripts/fetch_all.py --ticker AAPL --options                  # 仅获取苹果期权链
python scripts/fetch_all.py -t AAPL -o mi_data.json -q               # 静默模式，保存输出至 JSON 文件
```

**主要参数说明：**
- `--all`：获取所有类别数据（图表行情、实时报价、基本面、期权、搜索、相似推荐）
- `--chart`：OHLCV 历史行情
- `--quote`：实时价格与行情
- `--fundamentals`：基本面数据（quoteSummary）
- `--options`：期权链
- `--search`：搜索与新闻资讯
- `--range` / `--interval`：历史数据的时间范围与周期颗粒度
- `--modules` / `--all-modules`：指定 quoteSummary 模块 / 全部模块
- `--output`：输出的 JSON 文件路径

### 实测案例（以 GGAL 为例已验证）

```
>> Chart (1y, 1d)... OK 250 bars
>> Quote...             OK Price: $50.33 (-1.62%)
>> Fundamentals...      OK 12 módulos (core)
>> Options...           OK 5 expiration dates, 17 calls, 19 puts
>> Search+News...       OK 5 news items
Guardado en: ggal_temp.json  (123 KB)
```

---

## 国际标的代码（Tickers）

Yahoo Finance 对非美股市场使用后缀标识不同的交易所：

| 市场 | 后缀 | 示例 |
|------|------|------|
| 阿根廷 (BCBA) | `.BA` | `GGAL.BA`, `YPFD.BA` |
| 巴西 (Bovespa) | `.SA` | `PETR4.SA`, `VALE3.SA` |
| 墨西哥 (BMV) | `.MX` | `WALMEX.MX` |
| 加密货币 | `-USD` | `BTC-USD`, `ETH-USD` |
| 外汇 | `=X` | `EURUSD=X` |
| 指数 | 前缀 `^` | `^GSPC` (标普500) |

完整列表请参阅 [API_REFERENCE.md 第 14 节](./references/API_REFERENCE.md#14-国际标的代码tickers)。

---

## 速率限制（Rate Limits）

| 请求频率 | 状态与表现 |
|---------|------------|
| ~2 req/s | 安全阈值 |
| 3-5 req/s | 极高概率触发 429 Too Many Requests |
| >10 req/s | 临时封禁 IP（IP block） |

**强烈建议在各次请求之间保持 `time.sleep(0.5)` 的间隔，并实现指数退避重试（Exponential Backoff）。**

对于多标的批量获取，请使用 [`batch_fetch.py`](./scripts/batch_fetch.py)。该脚本实现了 2 req/s、突发容忍量为 5 的令牌桶机制。与 yfinance（无速率限制器且直接并发启动 N 个线程）相比，batch_fetch 能够严格保证聚合吞吐量不超过安全上限。

---

## 常见错误与排查

| 错误信息 | 原因分析 | 解决方案 |
|---------|----------|----------|
| `401 Unauthorized` | 缺少 Crumb 或会话 Cookie | 使用 `yahoo_session()` 初始化会话 |
| `429 Too Many Requests` | 超过接口访问速率限制 | 等待 30-60 秒后重试，降低请求频率 |
| `Bad Request` | Crumb 已失效或过期 | 重新获取并生成新的 Crumb |
| `result` 为空 | 标的代码无效或无数据 | 先使用 search 接口验证标的代码是否存在 |
| `Python-requests` 拦截 | 使用了 requests 默认 User-Agent | 设置常见浏览器的 User-Agent 请求头 |

---

## Skill 目录结构

```
skills/yahoo-finance/
├── SKILL.md                          # 本文件（快速入门指引）
├── references/
│   └── API_REFERENCE.md              # 所有接口的完整参考文档
└── scripts/
    ├── batch_fetch.py                # 带速率限制的多标的批量抓取脚本（推荐）
    ├── fetch_all.py                  # 全功能综合采集脚本
    ├── fetch_quote.py                # 快速行情与基本面抓取脚本
    └── download_historical.py        # 历史行情导出为 CSV 脚本
```
