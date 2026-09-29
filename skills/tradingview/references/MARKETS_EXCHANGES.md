# 市场 (Markets)、交易所 (Exchanges) 与国家 (Countries) 参考指南

> 本文列出了在 Scanner API 与 Symbol Search 中可用作 `market` 参数、`exchange` 过滤字段和 `country` 过滤字段的有效市场、交易所及国家代码清单。

---

## 目录

1. [有效市场代码 (Markets)](#1-有效市场代码-markets)
2. [各市场对应的交易所 (Exchanges)](#2-各市场对应的交易所-exchanges)
3. [有效国家名称 (Countries)](#3-有效国家名称-countries)
4. [各市场标的代码 (Tickers) 格式规范](#4-各市场标的代码-tickers-格式规范)
5. [常见决策：该选用哪个 market](#5-常见决策该选用哪个-market)
6. [已识别交易所完整清单](#6-已识别交易所完整清单)

---

## 1. 有效市场代码 (Markets)

`POST /{market}/scan` 请求中的 `{market}` 参数控制了查询检索的资产池范围。以下为截至 2026-06 验证的有效市场列表：

| 市场代码 (Market) | 描述 | 大致覆盖品种数量 |
|--------|-------------|-----------------|
| `global` | 全球综合市场资产池 | 100k+ |
| `america` | 美股：NYSE + NASDAQ + AMEX + OTC | 15k+ |
| `argentina` | 阿根廷：BCBA / BYMA | 300+ |
| `brazil` | 巴西：B3 / Bovespa | 500+ |
| `spain` | 西班牙：BME | 200+ |
| `italy` | 意大利：Borsa Italiana | 400+ |
| `germany` | 德国：Xetra + Frankfurt | 1000+ |
| `uk` | 英国：LSE | 2000+ |
| `france` | 法国：Euronext Paris | 800+ |
| `russia` | 俄罗斯：MOEX | 200+ |
| `crypto` | 加密货币 | 50k+ |
| `forex` | 外汇货币对 | 1000+ |
| `bonds` | 全球债券 (TVC) | 300+ |

### 已确认的无效市场（返回 HTTP 404）

`asia`、`world` —— 这两个不存在作为独立的 market 分段。

---

## 2. 各市场对应的交易所 (Exchanges)

### america

| 交易所代码 | 交易所名称 | 常见品种类型 |
|---------------|--------|---------------|
| `NASDAQ` | 纳斯达克证券交易所 (Nasdaq Stock Market) | 股票、ETF、存托凭证 (CEDEAR、ADR) |
| `NYSE` | 纽约证券交易所 (New York Stock Exchange) | 股票、存托凭证 (DR) |
| `AMEX` | 美洲证券交易所 (American Stock Exchange) | 主要是 ETF |
| `OTC` | 场外交易市场 (Over-the-counter) | 小型股票、粉单市场 (Pink sheets) |

### argentina (BYMA / BCBA)

| 交易所代码 | 交易所名称 |
|---------------|--------|
| `BCBA` | 布宜诺斯艾利斯证券交易所 (Bolsa de Comercio de Buenos Aires，亦称 BYMA) |
| `BYMA` | 阿根廷证券市场 (Bolsas y Mercados Argentinos) |

两种代码均有效；`BCBA` 是历史上使用最广泛的代码。

### brazil

| 交易所代码 | 交易所名称 |
|---------------|--------|
| `BMFBOVESPA` | 巴西证券交易所 (B3 — Brasil Bolsa Balcao) |

### spain

| 交易所代码 | 交易所名称 |
|---------------|--------|
| `BME` | 西班牙证券市场公司 (Bolsas y Mercados Españoles) |

### italy

| 交易所代码 | 交易所名称 |
|---------------|--------|
| `MIL` | 意大利证券交易所 (Borsa Italiana，米兰) |
| `EUROTLX` | 欧洲多边交易设施 (EuroTLX) |

### germany

| 交易所代码 | 交易所名称 |
|---------------|--------|
| `XETR` | 德国电子交易平台 (Xetra) |
| `FWB` | 法兰克福证券交易所 (Frankfurter Wertpapierborse) |
| `MUN`, `BER`, `DUS`, `HAM`, `STU` | 德国各地方证券交易所 |

### uk

| 交易所代码 | 交易所名称 |
|---------------|--------|
| `LSE` | 伦敦证券交易所 (London Stock Exchange) |
| `LSIN` | 伦敦证券交易所国际板 (LSE International) |
| `AQUIS` | 阿奎斯证券交易所 (Aquis Stock Exchange) |

### france

| 交易所代码 | 交易所名称 |
|---------------|--------|
| `EURONEXT` | 泛欧交易所 (巴黎、阿姆斯特丹、布鲁塞尔等) |

### crypto

| 交易所代码 | 交易所名称 |
|---------------|--------|
| `BINANCE` | 币安 (Binance) |
| `COINBASE` | Coinbase |
| `BITSTAMP` | Bitstamp |
| `KRAKEN` | Kraken |
| `BYBIT` | Bybit |
| `OKX` | OKX |
| `BITFINEX` | Bitfinex |
| `HUOBI` | 火币 (Huobi) |
| `BITTREX` | Bittrex |
| `POLONIEX` | Poloniex |

### forex

| 交易所代码 | 交易所名称 |
|---------------|--------|
| `FX` | 聚合外汇行情经纪商 (FX) |
| `OANDA` | 安达 (OANDA) |
| `FX_IDC` | International Datacasting |
| `SAXO` | 盛宝银行 (Saxo Bank) |

### bonds

| 交易所代码 | 交易所名称 |
|---------------|--------|
| `TVC` | TradingView 官方计算源 (收益率曲线综合数据) |

---

## 3. 有效国家名称 (Countries)

在 Scanner 中按国家过滤的语法示例：

```json
{"left": "country", "operation": "equal", "right": "Argentina"}
```

常用国家英文名称列表（非穷尽列表 —— 支持使用任何符合英文标准命名的国家，配合 `equal` 筛选）：

**美洲 (Americas):**
`United States`, `Argentina`, `Brazil`, `Canada`, `Chile`, `Colombia`,
`Mexico`, `Peru`, `Uruguay`, `Venezuela`.

**欧洲 (Europe):**
`United Kingdom`, `Germany`, `France`, `Italy`, `Spain`, `Portugal`,
`Netherlands`, `Belgium`, `Switzerland`, `Austria`, `Sweden`, `Norway`,
`Denmark`, `Finland`, `Ireland`, `Poland`, `Czech Republic`, `Greece`,
`Russia`, `Turkey`, `Ukraine`.

**亚洲 (Asia):**
`Japan`, `China`, `Hong Kong`, `Taiwan`, `South Korea`, `India`,
`Singapore`, `Malaysia`, `Thailand`, `Indonesia`, `Philippines`, `Vietnam`,
`Israel`, `Saudi Arabia`, `United Arab Emirates`, `Qatar`.

**大洋洲 (Oceania):**
`Australia`, `New Zealand`.

**非洲 (Africa):**
`South Africa`, `Egypt`, `Nigeria`, `Kenya`, `Morocco`.

> **重要提示：** API 严格**区分大小写 (case-sensitive)**，且必须使用规范的英文名称。如传入小写 `argentina` 会返回 0 条结果，而传入 `Argentina` 方可正确匹配。

### 实战示例：

```bash
# 阿根廷所有企业（包含在美国挂牌的 ADR）
py fetch_tradingview.py country Argentina

# 仅在阿根廷本土交易所上市的企业
py fetch_tradingview.py screen --filter '[["country","equal","Argentina"],["exchange","equal","BCBA"]]'

# 在纽交所挂牌上市的巴西企业 (ADR)
py fetch_tradingview.py screen --filter '[["country","equal","Brazil"],["exchange","equal","NYSE"]]'
```

---

## 4. 各市场标的代码 (Tickers) 格式规范

| 市场/品种 | 格式规范 | 示例 |
|---------|---------|----------|
| 美股普通股 | `{EXCHANGE}:{TICKER}` | `NASDAQ:AAPL`, `NYSE:JPM`, `AMEX:SPY` |
| 美股 ADR | `{EXCHANGE}:{TICKER}` | `NASDAQ:GGAL`, `NYSE:BBAR` (部分可能带有 D 后缀) |
| 阿根廷本地股票 | `BCBA:{TICKER}` | `BCBA:GGAL`, `BCBA:YPF`, `BCBA:PAMP` |
| 阿根廷 CEDEAR | `BCBA:{TICKER}` (采用本地代码格式) | `BCBA:AAPL`, `BCBA:KO` |
| 巴西股票 | `BMFBOVESPA:{TICKER}{NUM}` | `BMFBOVESPA:PETR4`, `BMFBOVESPA:VALE3` |
| 西班牙股票 | `BME:{TICKER}` | `BME:SAN`, `BME:TEF`, `BME:IBE` |
| 德国股票 | `XETR:{TICKER}` | `XETR:SAP`, `XETR:VOW3`, `XETR:BMW` |
| 英国股票 | `LSE:{TICKER}` | `LSE:HSBA`, `LSE:VOD` |
| 加密货币 | `{EXCHANGE}:{PAIR}` | `BINANCE:BTCUSDT`, `COINBASE:ETHUSD` |
| 外汇货币对 | `FX:{PAIR}` | `FX:EURUSD`, `OANDA:GBPUSD` |
| 债券收益率 | `TVC:{CODIGO}` | `TVC:US10Y`, `TVC:DE10Y`, `TVC:AR10Y` |
| 股指 | `{EXCHANGE}:{INDEX}` | `INDEX:NDX`, `INDEX:DJI`, `INDEX:SPX`, `INDEX:ARG30` |

### 拼接 HTML 页面 URL

需将冒号 `:` 替换为连字符 `-`：

`NASDAQ:GGAL` → `https://es.tradingview.com/symbols/NASDAQ-GGAL/`

---

## 5. 常见决策：该选用哪个 market

### 场景 1：查询纳斯达克上市的 GGAL

→ 使用 `market=america` 或 `market=global`，代码指定为 `NASDAQ:GGAL`。

```bash
py fetch_tradingview.py quote NASDAQ:GGAL --market global
```

### 场景 2：查询在阿根廷 BYMA 本土交易的 GGAL

→ 使用 `market=argentina`，代码指定为 `BCBA:GGAL`。

```bash
py fetch_tradingview.py quote BCBA:GGAL --market argentina
```

### 场景 3：检索在全球各市场上市的所有阿根廷企业

→ 使用 `market=global` + 按 country 过滤。

```bash
py fetch_tradingview.py country Argentina --market global --limit 30
```

### 场景 4：按市值筛选排名前列的加密货币

→ 使用 `market=crypto`，按 `market_cap_basic` 降序排序。

```bash
py fetch_tradingview.py market crypto --limit 20
```

### 场景 5：在全球所有交易所中查找 AAPL 的上市版本

→ 使用 `symbol_search`（将返回全球范围内的所有发行变体）。

```bash
py fetch_tradingview.py search "AAPL" --type stocks
# 返回 NASDAQ:AAPL 以及在 BMV、XETR、LSE 等挂牌的各版本
```

---

## 6. 已识别交易所完整清单

下表整理自对 Scanner 接口中不同国家响应数据的 `exchange` 字段采样。非穷尽列表（TradingView 支持全球 100+ 家交易所）。

### 北美洲 (North America)
- 美国：NYSE, NASDAQ, AMEX, OTC, ARCA, BATS, IEX
- 加拿大：TSX, TSXV, CSE, NEO
- 墨西哥：BMV

### 拉丁美洲 (Latin America)
- 阿根廷：BCBA / BYMA
- 巴西：BMFBOVESPA
- 智利：BCS
- 哥伦比亚：BVCA
- 秘鲁：BVL

### 欧洲 (Europe)
- 英国：LSE, LSIN, AQUIS
- 法国/荷兰/比利时：EURONEXT
- 德国：XETR, FWB
- 西班牙：BME
- 意大利：MIL, EUROTLX
- 瑞士：SIX
- 奥地利：WIENER, VIE
- 波兰：WSE
- 瑞典：OMXSTO
- 芬兰：OMXHEX
- 丹麦：OMXCOP

### 亚太地区 (Asia-Pacific)
- 日本：TSE (东京，别名 JPX)
- 中国香港：HKEX
- 中国内地：SSE, SZSE (上交所、深交所)
- 中国台湾：TWSE
- 韩国：KRX
- 印度：NSE, BSE
- 澳大利亚：ASX
- 新西兰：NZX
- 新加坡：SGX
- 泰国：SET
- 印度尼西亚：IDX
- 马来西亚：KLSE
- 越南：HOSE

### 非洲 / 中东 (Africa / Middle East)
- 南非：JSE
- 埃及：EGX
- 以色列：TASE
- 迪拜：DFM

### 主流加密货币交易所 (Crypto)
BINANCE, COINBASE, KRAKEN, BITSTAMP, OKX, BYBIT, GEMINI, BITTREX, HUOBI,
BITMEX, BITFINEX, POLONIEX, KUCOIN

### 外汇 / 经纪商行情源 (Forex)
FX, OANDA, FX_IDC, SAXO, FXCM, NASDAQ:FOREX

### 指数 / 综合衍生源
- INDEX (TradingView 官方指数)
- TVC (TradingView Calculated 计算衍生源)
- DJ (道琼斯 Dow Jones)
- CBOE (芝加哥期权交易所指数)

---

## 附录：探测与发现新交易所

若需探测未在列表中的交易所代码：

```python
# 列出某国家包含的所有独立交易所代码
from fetch_tradingview import screen
data = screen(
    filter_=[{"left": "country", "operation": "equal", "right": "Japan"}],
    columns=["name", "exchange"],
    limit=5000,
)
exchanges = sorted(set(item["exchange"] for item in data["data"]))
```
