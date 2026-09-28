# HTML 抓取 — 提取 prs.init-data+json

> TradingView 的标的详情页面（`es.tradingview.com/symbols/{EX}-{SYM}/{path}/`）采用**服务端渲染（Server-Side Rendered, SSR）**：服务端数据直接内置于 `<script type="application/prs.init-data+json">` 数据块中并在客户端注水（hydrate）。这些数据块**无需执行 JavaScript 即可直接抓取解析**，并且暴露出许多在标准 JSON API 中未包含的信息。

---

## 目录

1. [为什么需要抓取 HTML](#1-为什么需要抓取-html)
2. [已确认的子页面路径](#2-已确认的子页面路径)
3. [prs.init-data+json 的数据结构](#3-prsinit-datajson-的数据结构)
4. [典型页面中的数据块特征](#4-典型页面中的数据块特征)
5. [数据提取模式代码](#5-数据提取模式代码)
6. [HTML 中其它可抓取的数据](#6-html-中其它可抓取的数据)
7. [注意事项与限制 (Caveats)](#7-注意事项与限制-caveats)

---

## 1. 为什么需要抓取 HTML

Scanner API 已经提供了 ~300+ 个结构化字段列 —— 在大多数场景下你**不需要**抓取 HTML。但有部分信息**仅在 HTML 中存在**：

| 仅在 HTML 中存在的信息 | 所在位置 |
|-----------------------|-------|
| 标的当前可用的**标签页/子页面 (Tabs/subpages)** | `<a href="/symbols/{EX}-{SYM}/{tab}/">` |
| **面包屑导航 (Breadcrumbs)**（行业 > 板块 > 国家） | `data.breadcrumbs[]` |
| TradingView 推荐的**相似资产 (Similar assets)** | `data.similar_assets` |
| 该标的的**特选经纪商 (Featured broker)** | `data.symbol_featured_broker` |
| 包含完整元数据的**初始行情 (Initial quotes)** | `initialQuotes` 字典 |
| 自动生成的 **FAQ 常见问题数据** | `symbolFaqData` |
| 多种尺寸规格的**Logo 图标** | `medium_logo_urls`, `logo_id`, `base_currency_logo_id` |
| **价格精度 (Pricescale)** (最小跳动价位 tick size) | `pricescale` |
| **新闻正文内容** | `/news/{id}/` 页面中的 `<article>` 标签 |

---

## 2. 已确认的子页面路径

URL 路径规范：`https://es.tradingview.com/symbols/{EXCHANGE}-{TICKER}/{subpath}/`

需将标的代码中的 `:` 替换为 `-`。例如：`NASDAQ:GGAL` → `NASDAQ-GGAL`。

| 子路径 (Subpath) | 响应大小 | HTML 包含的内容 |
|---------|--------|-------------------|
| `` (根路径) | 400 KB | 行情 + 图表 + 概览 + 相似标的/经纪商侧边栏 |
| `technicals` | 211 KB | 评级对照表 + 带有 BUY/SELL 判定的技术指标 |
| `financials-overview` | 217 KB | 财务简报 (损益/资产负债概览) |
| `financials-income-statement` | **610 KB** | 多期完整利润表 (Income statement) |
| `financials-balance-sheet` | 386 KB | 多期资产负债表 (Balance sheet) |
| `financials-cash-flow` | 333 KB | 多期现金流量表 (Cash flow) |
| `financials-statistics-and-ratios` | **1 MB** | 完整统计指标与财务比率 |
| `financials-dividends` | 203 KB | 历史分红派息记录 |
| `financials-revenue` | 205 KB | 按业务分部的收入明细拆解 |
| `financials-earnings` | 215 KB | 历史财报记录 + 预测值 |
| `forecast` | 200 KB | 分析师目标价 + 预期预测 |
| `ideas` | 438 KB | 社区交易观点与策略 (作者、点赞数等) |
| `options-chain` | 398 KB | 带有行权价的完整期权链 |
| `seasonals` | 194 KB | 月度季节性走势统计 |
| `bonds` | 218 KB | 同一发债主体的相关债券 |
| `etfs` | 256 KB | 包含该标的的 ETF 基金列表 |
| `minds` | 278 KB | 社区简短讨论与评论 |

### 返回 404 的无效子路径

`/news/`、`/analysis/`、`/profile/`、`/markets/`、`/insider-trading/`、`/financials-statements-and-ratios/`、`/financials-statistics/`。

---

## 3. prs.init-data+json 的数据结构

每个页面通常包含 **~7 个** 如下格式的 `<script>` 数据块：

```html
<script type="application/prs.init-data+json">
{
  "<random_key>": {
    "context": {...},
    "data": {...},
    "meta": {...}
  }
}
</script>
```

这些 **随机键名 (random_keys)**（例如 `wEzKaD`、`UBqnNC`、`dIwTxt` 等）会随 TradingView 的前端部署重新生成。**请勿在代码中硬编码匹配具体的 key**，而应通过迭代遍历寻找对应的数据结构。

### 已观察到的数据块类型

| 序号 | 类型 | 大小 | 包含内容 |
|---|------|--------|-----------|
| 1 | `{mainMenuCategories: [...]}` | 45 KB | TradingView 顶部主导航菜单（通常无用） |
| 2 | 包含 `data.symbol` 的 `{<key>: {context, data, meta}}` | 7 KB | **标的基础数据** ⭐ |
| 3 | 体积较大的 `{<key>: {context, data, meta}}` | 43 KB | **子页面专属详细数据** ⭐ |
| 4 | `{<key>: {initialQuotes, description, symbolFaqData}}` | 1 KB | **初始报价与元数据** ⭐ |
| 5 | `{<key>: {languageName, blogBaseUrl, ...}}` | 130 B | UI 语言与页面配置 |
| 6 | `{gaId, gaVars, gadwId, ...}` | 185 B | 统计分析埋点 ID |
| 7 | `{days_to_deactivation, ...}` | 189 B | 用户会话与上下文信息 |

其中第 2、3、4 号数据块为**核心价值数据块** —— 包含了最值得抓取的关键信息。

---

## 4. 典型页面中的数据块特征

### 标的数据块 (data.symbol)

```json
{
  "wEzKaD": {
    "context": {
      "request_context": {...},
      "device": {...}
    },
    "data": {
      "symbol": {
        "pro_symbol": "NASDAQ:GGAL",
        "short_name": "GGAL",
        "instrument_name": "Grupo Financiero Galicia SA Sponsored ADR Class B",
        "exchange": "NASDAQ",
        "type": "dr",
        "country": "Argentina",
        "currency": "USD",
        "logoid": "gpo-fin-galicia",
        "pricescale": 100,
        ...
      },
      "breadcrumbs": [
        {"id": "markets", "name": "Mercados"},
        {"id": "stocks-usa", "name": "Acciones USA"},
        {"id": "sector-finance", "name": "Finance"},
        {"id": "industry-regional-banks", "name": "Regional Banks"},
        ...
      ],
      "similar_assets": {
        "items": [...]  // 推荐的相似标的代码
      },
      "tabs": [...],   // 可用标签页
      "symbol_featured_broker": null
    },
    "meta": {...}
  }
}
```

### initialQuotes 数据块

```json
{
  "UBqnNC": {
    "initialQuotes": {
      "pro_symbol": "NASDAQ:GGAL",
      "short_name": "GGAL",
      "exchange": "NASDAQ",
      "type": "dr",
      "typespecs": [],
      "tv_symbol_page_url_force_exchange": true,
      "ticker_title": "Grupo Financiero Galicia...",
      "instrument_name": "Grupo Financiero Galicia SA Sponsored ADR Class B",
      "medium_logo_urls": ["..."],
      "logo": {...},
      "logo_id": "gpo-fin-galicia",
      "base_currency_logo_id": "country/AR",
      "currency_logo_id": "country/US",
      "country": "Argentina",
      "data_frequency": "EOD",  // EOD (日终结算) / RT (实时)
      "pricescale": 100
    },
    "description": {...},
    "symbolFaqData": {...}  // 自动生成的 FAQ 数据
  }
}
```

### 专属子页面数据块

结构随子页面而异。例如对于 `/technicals/`：

```json
{
  "data": {
    "symbol": {...},
    "tabs": [...],
    // ...技术指标选项卡特有字段...
  }
}
```

---

## 5. 数据提取模式代码

### 通过正则表达式提取所有数据块

```python
import re, json

def extract_prs_blocks(html: str) -> list[dict]:
    """从 HTML 中提取所有 prs.init-data+json 脚本块。"""
    blocks = []
    for m in re.finditer(
        r'<script[^>]*type="application/prs\.init-data\+json"[^>]*>(.+?)</script>',
        html, re.DOTALL,
    ):
        try:
            blocks.append(json.loads(m.group(1).strip()))
        except json.JSONDecodeError:
            pass
    return blocks
```

### 查找包含标的数据的块

```python
def find_symbol_block(blocks: list[dict]) -> dict | None:
    """查找包含 data.symbol 的数据块。"""
    for blk in blocks:
        for key, value in blk.items():
            if isinstance(value, dict) and 'data' in value:
                data = value['data']
                if isinstance(data, dict) and 'symbol' in data:
                    return data['symbol']
    return None
```

### 查找 initialQuotes 块

```python
def find_initial_quotes(blocks: list[dict]) -> dict | None:
    """查找包含 initialQuotes 的数据块。"""
    for blk in blocks:
        for key, value in blk.items():
            if isinstance(value, dict) and 'initialQuotes' in value:
                return value['initialQuotes']
    return None
```

### 提取可用的标签页链接

```python
import re

def find_tabs(html: str, symbol_with_dash: str) -> list[str]:
    """查找当前页面链接的所有有效子页面路径。"""
    pattern = rf'href="(/symbols/{re.escape(symbol_with_dash)}/[a-z-]+/?)"'
    return sorted(set(re.findall(pattern, html)))
```

### 提取 Window.* 内部变量

用于获取内部 API 的 URL 地址：

```python
def find_window_vars(html: str) -> dict:
    """提取形如 window.X = "Y" 的全局变量赋值。"""
    out = {}
    for m in re.finditer(r'window\.([A-Z][A-Z_0-9]+)\s*=\s*"([^"]+)"', html):
        out[m.group(1)] = m.group(2)
    return out
```

---

## 6. HTML 中其它可抓取的数据

### OpenGraph Meta 标签

```python
def extract_og_meta(html: str) -> dict:
    """提取 og:* 和 twitter:* meta 标签内容。"""
    out = {}
    for m in re.finditer(
        r'<meta\s+property="(og:[^"]+|twitter:[^"]+)"\s+content="([^"]+)"',
        html
    ):
        out[m.group(1)] = m.group(2)
    return out
```

返回字段包含：
- `og:title`：SEO 标题
- `og:description`：SEO 描述信息
- `og:image`：标的图标 Logo 图片链接
- `og:url`：规范链接 Canonical URL（注意可能会重定向到其它交易所）
- `twitter:*`：Twitter Card 相关配置

### 嵌入在 Canvas 中的投资组合持仓占比 (针对 ETF)

```python
def find_pie_chart(html: str) -> list[dict] | None:
    """部分页面使用 <canvas data-pie-chart-items-value=...> 存放饼图数据。"""
    import html as html_mod
    m = re.search(r'data-pie-chart-items-value="([^"]+)"', html)
    if m:
        return json.loads(html_mod.unescape(m.group(1)))
    return None
```

### 新闻正文内容 (位于 /news/{id}/ 页面)

```python
def extract_news_body(html: str) -> str | None:
    """提取新闻正文文本。"""
    m = re.search(r'<article[^>]*>(.+?)</article>', html, re.DOTALL)
    if m:
        body = re.sub(r'<[^>]+>', ' ', m.group(1))
        body = re.sub(r'\s+', ' ', body).strip()
        return body
    return None
```

---

## 7. 注意事项与限制 (Caveats)

### 1. 字符实体转义 (Encoding)

返回的 HTML 为合法的 UTF-8，但内部可能包含 **HTML 实体**（如 `&amp;`、`&quot;`、`&lt;` 等）。如果在 HTML 标签属性中提取内嵌的 JSON，务必先调用 `html.unescape()`：

```python
import html
clean_json = html.unescape(extracted_attr)
data = json.loads(clean_json)
```

### 2. 随机键名 (Random keys)

`prs.init-data+json` 块内部的顶层 key 是动态随机生成的，每次构建部署都会改变。切勿硬编码 key 名称 —— 始终通过遍历对象并检查其内部结构（如是否存在 `data.symbol`、`initialQuotes` 等）。

### 3. 构建 Hash (Build hash)

静态资源 URL 中含有前端构建哈希（例如 `/static/bundles/2026.06.04-abc123.js`）。如果需要获取静态资源，建议通过正则从页面动态提取。

### 4. 规范 URL 可能发生重定向

`og:url` 可能会根据地理位置重定向到不同交易所的标的代码（TradingView 会根据用户 IP 自动推荐“主要”交易标的）。例如：请求 `NASDAQ:GGAL` 时，若服务器定位在阿根廷，`og:url` 可能指向 `BCBA:GGACB`。**请始终以调用时传入的原始 Ticker 为准**，不要直接信任 `og:url`。

### 5. 严格的速率限制 (Rate Limiting)

HTML 页面部署了更为严格的 Cloudflare WAF 防护策略，容忍度远低于内部 JSON API。请求频率超过 5 次/秒容易触发 429 限制。进行 HTML 抓取时建议将频率控制在 **1 次请求/秒**。

### 6. 响应体积较大

财务相关的子页面体积偏大（300 KB 到 1 MB 不等）。在对大量标的进行批量抓取时，需合理规划网络带宽与请求耗时。

### 7. 页面结构变动风险

TradingView 大约每隔 6 个月会对前端 HTML 进行样式和结构重构（CSS 类名、DOM 外层包裹等会变化）。虽然 `prs.init-data+json` 数据块自 2024 年以来保持高度稳定，但依然存在变动风险。如果业务强依赖网页抓取，建议配置自动化回归测试。

### 8. 数据与 Scanner 接口的重复性

HTML 中呈现的大多数数据在 Scanner API 中均已直接提供。在编写爬虫脚本前，请优先确认目标字段是否可以通过 Scanner 列直接获取 —— 采用 Scanner API 速度更快且稳定性高得多。

**适宜抓取 HTML 的典型场景：**
- 获取标的当前有效的子页面列表（验证 `/technicals/` 或 `/options-chain/` 是否存在）
- 提取新闻正文详情（JSON 接口未包含正文）
- 提取内嵌在 `<canvas>` 中的 ETF 持仓资产饼图数据
- 获取推荐的相似资产与特选经纪商
- 抓取自动生成的 FAQ 问答库
- 获取不同尺寸的高清品牌 Logo 图标

**不适宜抓取 HTML（应优先调用 API）的场景：**
- 行情价格、技术指标、财务三表、业绩财报、分析师目标价 → 优先使用 Scanner API
- 标的检索 → 优先使用 Symbol Search API
- 新闻头条列表 → 优先使用 News API

---

## 附录：完整的网页抓取示例脚本

```python
import re
import json
import html as html_mod
import requests

def scrape_symbol_page(symbol: str, subpath: str = "") -> dict:
    """完整抓取 TradingView 标的页面信息。"""
    sym_path = symbol.replace(":", "-")
    url = f"https://es.tradingview.com/symbols/{sym_path}/{subpath.strip('/')}/" if subpath else \
          f"https://es.tradingview.com/symbols/{sym_path}/"

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    h = r.text

    # 提取 prs.init-data+json 脚本块
    blocks = []
    for m in re.finditer(
        r'<script[^>]*type="application/prs\.init-data\+json"[^>]*>(.+?)</script>',
        h, re.DOTALL,
    ):
        try:
            blocks.append(json.loads(m.group(1).strip()))
        except json.JSONDecodeError:
            pass

    # 提取标的数据与初始行情
    symbol_data = None
    initial_quotes = None
    for blk in blocks:
        for key, value in blk.items():
            if isinstance(value, dict):
                if 'data' in value and isinstance(value['data'], dict):
                    if 'symbol' in value['data']:
                        symbol_data = value['data']['symbol']
                if 'initialQuotes' in value:
                    initial_quotes = value['initialQuotes']

    # 提取 OpenGraph Meta 信息
    og = {}
    for m in re.finditer(
        r'<meta\s+property="(og:[^"]+|twitter:[^"]+)"\s+content="([^"]+)"', h
    ):
        og[m.group(1)] = m.group(2)

    # 提取有效子页面链接
    tabs = sorted(set(re.findall(
        rf'href="(/symbols/{sym_path}/[a-z-]+/?)"', h
    )))

    # 提取 window 全局变量 (API 地址)
    window_vars = {}
    for m in re.finditer(r'window\.([A-Z][A-Z_0-9]+)\s*=\s*"([^"]+)"', h):
        window_vars[m.group(1)] = m.group(2)

    return {
        "url": url,
        "html_size": len(h),
        "symbol_data": symbol_data,
        "initial_quotes": initial_quotes,
        "og_meta": og,
        "tabs": tabs,
        "window_vars": window_vars,
        "all_blocks_count": len(blocks),
    }


# 运行示例
result = scrape_symbol_page("NASDAQ:GGAL", "technicals")
print(json.dumps(result, indent=2, ensure_ascii=False)[:3000])
```
