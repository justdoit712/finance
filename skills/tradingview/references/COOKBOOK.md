# 实战配方指南 (Cookbook) — 常见实用场景

> 收集了一系列可直接复制运行的代码示例配方。每个示例均可使用 CLI 脚本 `fetch_tradingview.py` 或直接调用 Python API 函数。

---

## 目录

### 行情与技术面
1. [股票快速行情报价](#1-股票快速行情报价)
2. [含技术指标的扩展行情](#2-含技术指标的扩展行情)
3. [仅获取技术指标](#3-仅获取技术指标)
4. [仅获取枢轴点 (Pivots)](#4-仅获取枢轴点-pivots)
5. [仅获取历史收益率与表现 (Performance)](#5-仅获取历史收益率与表现-performance)
6. [TradingView 聚合买入/卖出评级](#6-tradingview-聚合买入卖出评级)

### 财务与基本面
7. [利润表 / 资产负债表 / 现金流量表](#7-利润表--资产负债表--现金流量表)
8. [对比 3 家公司的财务比率](#8-对比-3-家公司的财务比率)
9. [财报日历与业绩预期](#9-财报日历与业绩预期)
10. [分析师目标价](#10-分析师目标价)
11. [股息数据](#11-股息数据)
12. [做空持仓与股权结构](#12-做空持仓与股权结构)

### 选股筛选 (Screening)
13. [美股市值排名前列的股票](#13-美股市值排名前列的股票)
14. [超卖标的筛选 (RSI < 30)](#14-超卖标的筛选-rsi--30)
15. [今日金叉标的筛选](#15-今日金叉标的筛选)
16. [高股息率标的筛选](#16-高股息率标的筛选)
17. [本周发布财报的标的](#17-本周发布财报的标的)
18. [在任意市场上市的阿根廷企业](#18-在任意市场上市的阿根廷企业)
19. [市值前列的加密货币](#19-市值前列的加密货币)
20. [获取指定行业的完整股票清单](#20-获取指定行业的完整股票清单)

### 标的搜索 (Symbol Search)
21. [通过公司名称解析代码 (Ticker)](#21-通过公司名称解析代码-ticker)
22. [通过 CIK 关联 SEC EDGAR](#22-通过-cik-关联-sec-edgar)
23. [列出某标的在各全球市场的全部上市版本](#23-列出某标的在各全球市场的全部上市版本)

### 新闻 (News)
24. [获取单只股票的新闻头条](#24-获取单只股票的新闻头条)
25. [获取全球宏观市场新闻头条](#25-获取全球宏观市场新闻头条)
26. [聚合多只股票的新闻](#26-聚合多只股票的新闻)
27. [按新闻提供商过滤新闻](#27-按新闻提供商过滤新闻)
28. [获取新闻完整正文详情](#28-获取新闻完整正文详情)

### 组合流水线 (Pipelines)
29. [搜索 → 报价 → 新闻流水线](#29-搜索--报价--新闻流水线)
30. [全合一综合行情 (All-in-One)](#30-全合一综合行情-all-in-one)

---

## 1. 股票快速行情报价

```bash
py fetch_tradingview.py quote NASDAQ:GGAL -q
```

```python
from fetch_tradingview import quote
q = quote("NASDAQ:GGAL")
g = q["data"][0]
print(f"{g['name']} {g['close']} ({g['change']:+.2f}%)")
```

---

## 2. 含技术指标的扩展行情

```bash
py fetch_tradingview.py quote-extended NASDAQ:AAPL -q
```

返回 ~30 个字段列：价格 + 市值 + 市盈率 (P/E) + 每股收益 (EPS) + 股息率 + 综合评级 + RSI + MACD + ADX + EMA + 52 周最高/最低价 + Beta + 所属行业。

---

## 3. 仅获取技术指标

```bash
py fetch_tradingview.py technicals NASDAQ:GGAL -q
```

```python
from fetch_tradingview import technicals
t = technicals("NASDAQ:GGAL")["data"][0]
print(f"RSI: {t['RSI']:.2f}")
print(f"MACD: {t['MACD.macd']:.4f} vs Signal: {t['MACD.signal']:.4f}")
print(f"EMA50: {t['EMA50']:.2f}, EMA200: {t['EMA200']:.2f}")
print(f"Rating: {t['Recommend.All']:+.3f}  (1=STRONG_BUY, -1=STRONG_SELL)")
```

---

## 4. 仅获取枢轴点 (Pivots)

```bash
py fetch_tradingview.py pivots NASDAQ:AAPL -q
```

```python
from fetch_tradingview import pivots
p = pivots("NASDAQ:AAPL")["data"][0]
close = p["close"]
print(f"R3: {p['Pivot.M.Classic.R3']:.2f}")
print(f"R2: {p['Pivot.M.Classic.R2']:.2f}")
print(f"R1: {p['Pivot.M.Classic.R1']:.2f}")
print(f"P:  {p['Pivot.M.Classic.Middle']:.2f}  <- pivot")
print(f"=== CLOSE: {close:.2f} ===")
print(f"S1: {p['Pivot.M.Classic.S1']:.2f}")
print(f"S2: {p['Pivot.M.Classic.S2']:.2f}")
print(f"S3: {p['Pivot.M.Classic.S3']:.2f}")
```

---

## 5. 仅获取历史收益率与表现 (Performance)

```bash
py fetch_tradingview.py performance NYSE:JPM -q
```

```python
from fetch_tradingview import performance
p = performance("NYSE:JPM")["data"][0]
for period in ["W", "1M", "3M", "6M", "Y", "YTD", "5Y", "All"]:
    val = p.get(f"Perf.{period}")
    if val is not None:
        print(f"  {period:5s}: {val:+.2f}%")
```

---

## 6. TradingView 聚合买入/卖出评级

```bash
py fetch_tradingview.py technicals NASDAQ:NVDA -q
```

```python
from fetch_tradingview import technicals, recommend_label

t = technicals("NASDAQ:NVDA")["data"][0]
print(f"Overall:   {recommend_label(t['Recommend.All']):12s}  ({t['Recommend.All']:+.3f})")
print(f"MAs:       {recommend_label(t['Recommend.MA']):12s}  ({t['Recommend.MA']:+.3f})")
print(f"Oscilators:{recommend_label(t['Recommend.Other']):12s}  ({t['Recommend.Other']:+.3f})")
```

---

## 7. 利润表 / 资产负债表 / 现金流量表

```bash
py fetch_tradingview.py financials NASDAQ:AAPL -q
```

返回 ~35 个字段列，涵盖资产负债表 + 利润表 + 现金流量表 + 关键财务比率 + 成长性指标。

```python
from fetch_tradingview import financials
f = financials("NASDAQ:AAPL")["data"][0]
print(f"Revenue:     ${f['total_revenue']/1e9:.1f}B")
print(f"Net income:  ${f['net_income']/1e9:.1f}B")
print(f"EBITDA:      ${f['ebitda']/1e9:.1f}B")
print(f"FCF:         ${f['free_cash_flow']/1e9:.1f}B")
print(f"Net margin:  {f['net_margin']:.1f}%")
print(f"ROE:         {f['return_on_equity']:.1f}%")
print(f"D/E:         {f['debt_to_equity']:.2f}")
```

---

## 8. 对比 3 家公司的财务比率

```python
from fetch_tradingview import scanner_scan

cols = [
    "name", "description", "market_cap_basic",
    "price_earnings_ttm", "price_book", "return_on_equity",
    "operating_margin", "net_margin", "debt_to_equity",
    "dividend_yield_recent",
]
data = scanner_scan(
    symbols=["NASDAQ:GGAL", "NYSE:BMA", "NYSE:BBAR"],
    columns=cols,
)

import json
print(f"{'Ticker':12} {'P/E':>7} {'P/B':>7} {'ROE%':>7} {'NetMrg%':>8} {'D/E':>6} {'DivY%':>6}")
for it in data["data"]:
    print(f"{it['symbol']:12} {it['price_earnings_ttm']:7.2f} {it['price_book']:7.2f} "
          f"{it['return_on_equity']:7.1f} {it['net_margin']:8.1f} "
          f"{it['debt_to_equity']:6.2f} {it['dividend_yield_recent']:6.2f}")
```

---

## 9. 财报日历与业绩预期

```bash
py fetch_tradingview.py earnings NASDAQ:GGAL -q
```

```python
from datetime import datetime, timezone
from fetch_tradingview import earnings

e = earnings("NASDAQ:GGAL")["data"][0]
next_ts = e["earnings_release_next_date"]
if next_ts:
    next_dt = datetime.fromtimestamp(next_ts, tz=timezone.utc)
    print(f"Next earnings: {next_dt.strftime('%Y-%m-%d')}")
    print(f"Forecast EPS:  {e['earnings_per_share_forecast_next_fq']}")
    print(f"Forecast Rev:  ${e['revenue_forecast_next_fq']/1e6:.1f}M")
```

---

## 10. 分析师目标价

```bash
py fetch_tradingview.py targets NASDAQ:NVDA -q
```

```python
from fetch_tradingview import targets, quote

t = targets("NASDAQ:NVDA")["data"][0]
current = t["close"]
avg = t["price_target_average"]
upside = (avg / current - 1) * 100 if (current and avg) else None

print(f"Current:  ${current:.2f}")
print(f"Avg PT:   ${avg:.2f}")
print(f"High PT:  ${t['price_target_high']:.2f}")
print(f"Low PT:   ${t['price_target_low']:.2f}")
print(f"Upside:   {upside:+.1f}%")
print(f"Analysts: {t['number_of_analyst_opinions']}")
print(f"Buy: {t['recommendation_buy']} | Hold: {t['recommendation_hold']} | Sell: {t['recommendation_sell']}")
```

---

## 11. 股息数据

```bash
py fetch_tradingview.py dividends NYSE:KO -q
```

```python
from fetch_tradingview import dividends
d = dividends("NYSE:KO")["data"][0]
print(f"Dividend yield (recent):    {d['dividend_yield_recent']:.2f}%")
print(f"Dividend yield (TTM):       {d['dividends_yield']:.2f}%")
print(f"DPS anual:                  ${d['dps_common_stock_prim_issue_fy']:.2f}")
print(f"Payout ratio:               {d['payout_ratio_fy']:.1f}%")
print(f"Años consecutivos pagando:  {d['continuous_dividend_payout']}")
print(f"Años consecutivos creciendo: {d['continuous_dividend_growth']}")
```

---

## 12. 做空持仓与股权结构

```bash
py fetch_tradingview.py ownership NASDAQ:NVDA -q
```

```python
from fetch_tradingview import ownership
o = ownership("NASDAQ:NVDA")["data"][0]
print(f"Market cap:        ${o['market_cap_basic']/1e9:.1f}B")
print(f"Float shares:      {o['float_shares_outstanding']/1e9:.2f}B")
print(f"Inst. ownership:   {o['shares_owned_institutions']:.1f}%")
print(f"Insider ownership: {o['shares_owned_insiders']:.1f}%")
print(f"Short interest:    {o['short_interest_percent']:.2f}%")
print(f"Days to cover:     {o['days_to_cover_short_interest']:.1f}")
```

---

## 13. 美股市值排名前列的股票

```bash
py fetch_tradingview.py screen --filter '[["country","equal","United States"],["type","equal","stock"]]' --sort market_cap_basic:desc --limit 10 -q
```

```python
from fetch_tradingview import screen
top = screen(
    filter_=[
        {"left": "country", "operation": "equal", "right": "United States"},
        {"left": "type", "operation": "equal", "right": "stock"},
    ],
    sort={"sortBy": "market_cap_basic", "sortOrder": "desc"},
    limit=10,
)
for item in top["data"]:
    print(f"{item['symbol']:18} ${item['market_cap_basic']/1e9:>8.1f}B  {item['name']:8} {item['description'][:50]}")
```

---

## 14. 超卖标的筛选 (RSI < 30)

```bash
py fetch_tradingview.py screen \
  --filter '[["type","equal","stock"],["country","equal","United States"],["RSI","less",30],["market_cap_basic","greater",10000000000]]' \
  --columns "name,description,close,RSI,Recommend.All" \
  --sort RSI:asc \
  --limit 20 -q
```

---

## 15. 今日金叉标的筛选

```bash
py fetch_tradingview.py screen \
  --filter '[["SMA50","crosses_above","SMA200"],["country","equal","United States"]]' \
  --columns "name,close,SMA50,SMA200,Recommend.All" \
  --limit 30 -q
```

---

## 16. 高股息率标的筛选

```bash
py fetch_tradingview.py screen \
  --filter '[["dividend_yield_recent","greater",5],["type","equal","stock"],["market_cap_basic","greater",1000000000]]' \
  --columns "name,description,close,dividend_yield_recent,payout_ratio_fy,sector" \
  --sort dividend_yield_recent:desc \
  --limit 30 -q
```

---

## 17. 本周发布财报的标的

```python
from datetime import datetime, timezone, timedelta
from fetch_tradingview import screen

now = int(datetime.now(tz=timezone.utc).timestamp())
week_later = now + 7 * 86400

data = screen(
    filter_=[
        {"left": "earnings_release_next_date", "operation": "in_range", "right": [now, week_later]},
        {"left": "type", "operation": "equal", "right": "stock"},
        {"left": "market_cap_basic", "operation": "greater", "right": 10_000_000_000},
    ],
    columns=[
        "name", "description", "earnings_release_next_date",
        "earnings_per_share_forecast_next_fq", "market_cap_basic",
    ],
    sort={"sortBy": "earnings_release_next_date", "sortOrder": "asc"},
    limit=50,
)
for it in data["data"]:
    dt = datetime.fromtimestamp(it["earnings_release_next_date"], tz=timezone.utc)
    print(f"{dt.strftime('%a %m-%d')}  {it['symbol']:15}  est EPS ${it['earnings_per_share_forecast_next_fq']:.2f}")
```

---

## 18. 在任意市场上市的阿根廷企业

```bash
py fetch_tradingview.py country Argentina --limit 30 -q
```

返回在 NASDAQ、NYSE、BCBA、BMV (CEDEAR)、BMFBOVESPA (BDR) 等全球各市场上市的阿根廷企业。

---

## 19. 市值前列的加密货币

```bash
py fetch_tradingview.py market crypto --limit 20 -q
```

---

## 20. 获取指定行业的完整股票清单

```bash
py fetch_tradingview.py sector Finance --market america --limit 50 -q
```

```python
from fetch_tradingview import by_sector
data = by_sector("Finance", market="america", limit=100)
for it in data["data"][:20]:
    print(f"{it['symbol']:15} {it['market_cap_basic']/1e9:>8.1f}B  {it['name']}")
```

---

## 21. 通过公司名称解析代码 (Ticker)

```bash
py fetch_tradingview.py search "Apple" --type stocks -q
```

```python
from fetch_tradingview import symbol_search
results = symbol_search("Apple", search_type="stocks")
for s in results["symbols"][:5]:
    print(f"{s['exchange']:10}:{s['symbol']:8}  {s['description'][:60]}")
```

---

## 22. 通过 CIK 关联 SEC EDGAR

```python
import requests
from fetch_tradingview import symbol_search

# 1. 查找 CIK
results = symbol_search("GGAL", search_type="stocks")
nasdaq = next((s for s in results["symbols"] if s["exchange"] == "NASDAQ"), None)
cik = nasdaq["cik_code"]
print(f"CIK: {cik}")

# 2. 从 SEC EDGAR 获取报备文件 (调用其它对应 Skill)
url = f"https://data.sec.gov/submissions/CIK{cik}.json"
data = requests.get(url, headers={"User-Agent": "research test@example.com"}).json()
print(f"公司: {data['name']}")
print(f"最新报备: {data['filings']['recent']['form'][:5]}")
```

---

## 23. 列出某标的在各全球市场的全部上市版本

```python
from fetch_tradingview import symbol_search
results = symbol_search("AAPL", search_type="stocks")
for s in results["symbols"]:
    print(f"{s['exchange']:12} {s['symbol']:8} {s['currency_code']:5} {s['description'][:60]}")
# 输出: NASDAQ:AAPL (USD), XETR:APC (EUR), BMV:AAPL (MXN), LSE:0R2V (GBP) 等
```

---

## 24. 获取单只股票的新闻头条

```bash
py fetch_tradingview.py news NASDAQ:AAPL -q
```

```python
from datetime import datetime, timezone
from fetch_tradingview import news_by_symbol

items = news_by_symbol("NASDAQ:AAPL")["items"]
for it in items[:10]:
    dt = datetime.fromtimestamp(it["published"], tz=timezone.utc)
    print(f"[{dt.strftime('%m-%d %H:%M')}] [{it['source'][:15]:15}] {it['title']}")
```

---

## 25. 获取全球宏观市场新闻头条

```bash
py fetch_tradingview.py news-global -q
```

---

## 26. 聚合多只股票的新闻

```python
from fetch_tradingview import news_by_symbol

symbols = ["NASDAQ:AAPL", "NASDAQ:MSFT", "NASDAQ:GOOGL", "NASDAQ:AMZN", "NASDAQ:META"]
all_items = []
for s in symbols:
    items = news_by_symbol(s)["items"]
    all_items.extend(items)

# 去重
seen = set()
unique = [it for it in all_items if not (it["id"] in seen or seen.add(it["id"]))]

# 排序
unique.sort(key=lambda x: x["published"], reverse=True)
print(f"Total unique news: {len(unique)}")
```

---

## 27. 按新闻提供商过滤新闻

```python
from fetch_tradingview import news_by_symbol
items = news_by_symbol("NASDAQ:AAPL")["items"]
dj_only = [it for it in items if it["provider"] == "dow-jones"]
reuters_only = [it for it in items if it["provider"] == "reuters"]
print(f"DJ items: {len(dj_only)}")
print(f"Reuters items: {len(reuters_only)}")
```

---

## 28. 获取新闻完整正文详情

```bash
py fetch_tradingview.py story "/news/DJN_DN20260604009289:0/" -q
```

```python
from fetch_tradingview import news_by_symbol, news_story

items = news_by_symbol("NASDAQ:AAPL")["items"]
first = items[0]
detail = news_story(first["storyPath"])
print(f"Title: {detail['title']}")
print(f"Body:  {detail['body'][:500]}...")
```

---

## 29. 搜索 → 报价 → 新闻流水线

```python
from fetch_tradingview import symbol_search, quote, news_by_symbol

# 1. 搜索标的
match = symbol_search("Apple", search_type="stocks")["symbols"][0]
ticker = f"{match['exchange']}:{match['symbol']}"
print(f"Resolved to: {ticker}")

# 2. 获取报价
q = quote(ticker)["data"][0]
print(f"Price: ${q['close']:.2f} ({q['change']:+.2f}%)")

# 3. 获取新闻
n = news_by_symbol(ticker)["items"][:3]
for it in n:
    print(f"  - {it['title']}")
```

---

## 30. 全合一综合行情 (All-in-One)

```bash
py fetch_tradingview.py all NASDAQ:GGAL -o ggal_full.json
```

将 **6 次请求** 整合为单个字典数据：
- `quote_extended` (~30 列，含价格 + 评级 + 技术指标 + 估值)
- `technicals` (~36 列)
- `financials` (~35 列)
- `earnings` (~12 列)
- `targets` (~10 列)
- `news` (最多 200 条)
- `_rating_label`: `Recommend.All` 的直观文本标签

```python
from fetch_tradingview import fetch_all
data = fetch_all("NASDAQ:GGAL")
print(data["_rating_label"])           # 例如: "BUY"
print(data["quote_extended"]["data"][0]["close"])
print(data["targets"]["data"][0]["price_target_average"])
print(len(data["news"]["items"]))
```
