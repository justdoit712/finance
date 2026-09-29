# Symbol Search v3 (标的检索) — 详细参考指南

> 接口端点：`GET https://symbol-search.tradingview.com/symbol_search/v3/?text={query}`
>
> TradingView 全球标的搜索引擎。返回匹配项的 **ISIN、CUSIP、CIK、计价货币、挂牌交易所、Logo ID、详细描述** 等核心字段。免认证鉴权。

---

## 目录

1. [接口端点与请求参数](#1-接口端点与请求参数)
2. [响应数据 Schema](#2-响应数据-schema)
3. [字段详细说明](#3-字段详细说明)
4. [search_type — 可选资产类别](#4-search_type--可选资产类别)
5. [附加过滤参数](#5-附加过滤参数)
6. [接口端点变体](#6-接口端点变体)
7. [常见实战用例](#7-常见实战用例)
8. [局限性与已知限制](#8-局限性与已知限制)

---

## 1. 接口端点与请求参数

### URL 地址

```
GET https://symbol-search.tradingview.com/symbol_search/v3/
```

### Query 查询参数

| 参数 | 类型 | 说明 | 默认值 |
|-------|------|-------------|---------|
| `text` | str | 检索关键词（标的代码、ISIN、CUSIP、企业名称） | (必填) |
| `search_type` | str | 标的资产类别（详见第 4 节） | 无过滤 (全类别) |
| `exchange` | str | 按交易所过滤 (NASDAQ, NYSE, BCBA, BME 等) | 无过滤 |
| `lang` | str | 响应语言代码 (en, es) | en |
| `domain` | str | 运行环境标识 (`production`) | production |
| `hl` | int | 设为 1 则在 `description` 中高亮匹配词 (`<em>`) | 1 |

### 请求头 (Headers)

与 Scanner 接口保持一致：

```python
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Origin": "https://es.tradingview.com",
    "Referer": "https://es.tradingview.com/",
}
```

---

## 2. 响应数据 Schema

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

| 顶层字段 | 类型 | 说明 |
|-----------------|------|-------------|
| `symbols_remaining` | int | 未在本次返回的剩余匹配项数（为 0 表示已全部返回） |
| `symbols` | list | 匹配结果对象数组 |

---

## 3. 字段详细说明

### 基础标识字段

| 字段 | 说明 |
|-------|-------------|
| `symbol` | 简短代码 (例如: `GGAL`)，不包含交易所前缀。若需在 Scanner 中使用，请拼装为 `exchange:symbol`。 |
| `description` | 标的完整名称。当 `hl=1` 时匹配的部分会被 `<em>` 标签包裹。 |
| `type` | 资产类别: `stock`, `dr` (ADR/CEDEAR), `etf`, `fund`, `crypto`, `forex`, `bond`, `index`, `future`, `option` |
| `exchange` | 挂牌交易所代码 |
| `currency_code` | ISO 4217 计价货币代码 (USD, EUR, ARS, BRL 等) |

### 全球通用唯一标识符 (核心价值字段!)

| 字段 | 说明 |
|-------|-------------|
| `isin` | **ISIN 国际证券识别码** (International Securities Identification Number)，12 位全球通用标准代码。例如: `US3999091008` |
| `cusip` | **CUSIP 代码** (美加标准 9 位代码)。例如: `399909100` |
| `cik_code` | **CIK 代码** (美国 SEC 报备机构代码，10 位数字)。例如: `0001114700`，可直接关联对接 SEC EDGAR 数据库。 |
| `found_by_isin` | 若通过 ISIN 匹配成功则为 `true` (非名称匹配) |
| `found_by_cusip` | 若通过 CUSIP 匹配成功则为 `true` |

> 这 3 个代码是进行跨数据源套利与数据对齐的核心桥梁：
> - **ISIN**：全球统一标准，唯一确定某只发行证券。
> - **CUSIP**：北美通用证券标识，属于 ISIN 的核心构成部分。
> - **CIK**：用于无缝对接 SEC EDGAR（获取 10-K、10-Q、8-K 披露财报）。

### 图标与 Logo

| 字段 | 说明 |
|-------|-----|
| `logoid` | 品牌 Logo ID。完整图片链接为: `https://s3-symbol-logo.tradingview.com/{logoid}--big.svg` |
| `logo` | 字典结构，包含 `style` (`single` 单图标或 `dual` 双图标) 与 `logoid` |
| `currency-logoid` | 货币图标 ID (例如: `country/US`) |
| `source_logoid` | 交易所图标 ID (例如: `source/NASDAQ`) |

### 数据来源

| 字段 | 说明 |
|-------|-------------|
| `provider_id` | 行情数据提供商 (`ice`, `nasdaq`, `cboe` 等) |
| `source2` | 交易所信息字典 `{id, name}` |

---

## 4. search_type — 可选资产类别

| 类型取值 | 涵盖范围 | 查询示例 |
|------|-------------|---------|
| `stocks` | 普通股 + ADR + CEDEAR + 封闭式基金 | `text=GGAL` |
| `funds` | 共同基金 (Mutual funds) + ETF 基金 | `text=SPY` |
| `futures` | 期货合约 | `text=ES1!` |
| `forex` | 外汇货币对 | `text=EURUSD` |
| `crypto` | 加密货币 | `text=BTC` |
| `indices` | 股票指数 | `text=SPX` |
| `bonds` | 债券 | `text=US10Y` |
| `economic` | 宏观经济指标 | `text=CPI` |
| `options` | 期权合约 | `text=AAPL` |

> 不指定 `search_type` 时将检索**全量资产类别**。适合用于探测某个 Ticker 在多个市场/资产池中是否存在重名。

### 无效的 search_type 取值

- `search_type=etf`（ETF 包含在 `funds` 分类下）
- `search_type=cedear`（CEDEAR 归属于 `stocks`，通过 `type=dr` 标识）

---

## 5. 附加过滤参数

### 按挂牌交易所过滤

```
GET /symbol_search/v3/?text=Apple&exchange=NASDAQ
```

→ 仅返回在 NASDAQ 上市的匹配项。

### 按语言本地化

```
GET /symbol_search/v3/?text=GGAL&lang=es
```

→ 当存在对应语言翻译时，返回本地化的描述信息。

### 关键词高亮 (Highlight)

```
GET /symbol_search/v3/?text=Apple&hl=1
```

→ `description` 字段中的匹配部分会被 `<em>Apple</em>` 标签包裹。

若传入 `hl=0` 则返回纯文本，不包含 HTML 标签。

---

## 6. 接口端点变体

| 接口路径 | 状态 | 响应格式 |
|------|--------|------------------|
| `/symbol_search/v3/` | ✅ 200 | 字典对象 `{symbols_remaining, symbols[]}` (推荐) |
| `/symbol_search/` | ✅ 200 | 直接返回列表 `[...]` (旧版格式) |
| `/local_search/v3/` | ✅ 200 | 与 `/symbol_search/v3/` 完全相同 |
| `/symbol_search/v2/` | ❓ | 未测试 |

**最佳实践建议：** 始终使用 **`/v3/`** —— 返回规范的结构化字典，包含 `symbols_remaining` 计数。

---

## 7. 常见实战用例

### 1. 通过简短 Ticker 解析标的

```python
results = symbol_search("GGAL", search_type="stocks")
# 返回不同交易所挂牌的最多 50 个 GGAL 匹配项
```

### 2. 通过企业名称检索

```python
results = symbol_search("Apple", search_type="stocks")
# 首个匹配项即为 NASDAQ:AAPL
```

### 3. 通过 ISIN 代码反查

```python
results = symbol_search("US3999091008")
# 匹配结果对象的 found_by_isin 将为 true
```

### 4. 通过 CUSIP 代码反查

```python
results = symbol_search("399909100")
# found_by_cusip 将为 true
```

### 5. 限定特定交易所检索

```python
results = symbol_search("AAPL", exchange="NASDAQ")
# 仅返回 NASDAQ:AAPL (排除 XETR:APC, BMV:AAPL 等)
```

### 6. 列出某标的在全球挂牌的所有交易所

```python
results = symbol_search("AAPL", search_type="stocks")
exchanges = [s["exchange"] for s in results["symbols"]]
# ['NASDAQ', 'XETR', 'BMV', 'LSE', 'MEX', ...]
```

### 7. 检索加密货币标的

```python
results = symbol_search("BTC", search_type="crypto")
# 返回各交易所的 BTCUSD, BTCEUR, BTCUSDT 等交易对
```

### 8. 通过 CIK 与 SEC EDGAR 数据库对接

```python
ggal = symbol_search("GGAL", search_type="stocks")["symbols"][0]
cik = ggal["cik_code"]
# 随后可调用 SEC EDGAR API：
# https://data.sec.gov/submissions/CIK{cik}.json
```

### 9. 搜索 → 报价流水线协同

```python
# 1. 搜索标的
matches = symbol_search("Galicia", search_type="stocks")
nasdaq_match = next((s for s in matches["symbols"] if s["exchange"] == "NASDAQ"), None)
# 2. 查询报价
ticker = f"{nasdaq_match['exchange']}:{nasdaq_match['symbol']}"
quote_data = quote(ticker)
```

### 10. 验证标的代码是否存在

```python
results = symbol_search("XYZQ", search_type="stocks")
exists = len(results["symbols"]) > 0
```

---

## 8. 局限性与已知限制

1. **单次请求最多返回 ~50 个匹配结果**（受 `symbols_remaining` 控制），该端点不支持分页。如需缩小范围，请配合 `exchange` 等过滤参数进行精确检索。
2. **`search_type` 必须与真实资产分类严格匹配**：
   - 检索 `text=BTCUSD` 配合 `search_type=forex` → 返回 0 条结果（属于 crypto 分类）。
   - 检索 `text=EURUSD` 配合 `search_type=crypto` → 返回 0 条结果（属于 forex 分类）。
3. **不支持直接按国家 (Country) 过滤**：若需按国家筛选，请使用 Scanner API 配合 `filter: country = X`。
4. **二级资产类型无独立过滤项**（如区分 CEDEAR 与 ADR）：两者 `type` 均为 `dr`。需通过挂牌交易所区分（`BCBA:*` 对比 `NASDAQ:*`）。
5. **非拉丁字符标的代码**（如日文、中文、希伯来文等）在部分非 UTF-8 控制台中可能出现字符编码异常。保存到文件时请务必使用 `ensure_ascii=False`。
6. **未提供“列出指定交易所所有标的”的专用端点**：如需获取某交易所的全部品种清单，应使用 Scanner API：

```python
all_nasdaq = scanner_scan(
    columns=["name", "description"],
    filter_=[{"left": "exchange", "operation": "equal", "right": "NASDAQ"}],
    market="america",
    range_=(0, 5000),
)
```

---

## 附录：与其他金融 Skill 的协同集成

| 关联 Skill | 如何通过 SymbolSearch 实现跨库协同 |
|-------|--------------------------------|
| **sec-data** | 获取 `cik_code` → 请求 SEC EDGAR 获取 10-K / 10-Q 申报文件 |
| **finviz** | 获取美股 `symbol` → 按 Ticker 查询 Finviz 图表与筛选器 |
| **macrotrends** | 获取企业准确名称 + Ticker → 拼装 Macrotrends 财务历史 URL |
| **yahoo-finance** | 获取 Ticker + 挂牌 Exchange → 对接 Yahoo Finance 详情 |
| **byma** | 获取阿根廷 Ticker (`exchange=BCBA`) → 对接 BYMA 行情看板 |
| **investing** | 获取英文 `description` → 匹配 Investing.com 标的 Slug |
