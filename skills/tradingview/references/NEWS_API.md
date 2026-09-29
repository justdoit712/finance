# News API — 详细参考指南

> 接口端点：`GET https://news-headlines.tradingview.com/v2/headlines`
>
> 单次请求最多可返回 200 条最新新闻。免鉴权。**仅 `/v2/` 可用** —— `/v3/` 返回 405，`/v1/` 返回 404。

---

## 目录

1. [接口端点与请求参数](#1-接口端点与请求参数)
2. [响应数据 Schema](#2-响应数据-schema)
3. [字段详细说明](#3-字段详细说明)
4. [新闻正文详情 (Story Detail)](#4-新闻正文详情-story-detail)
5. [实测覆盖范围](#5-实测覆盖范围)
6. [新闻提供商 / 数据来源](#6-新闻提供商--数据来源)
7. [常见工作流与实战代码](#7-常见工作流与实战代码)
8. [局限性与已知限制](#8-局限性与已知限制)

---

## 1. 接口端点与请求参数

### URL 地址

```
GET https://news-headlines.tradingview.com/v2/headlines
```

### Query 查询参数

| 参数 | 类型 | 描述 | 默认值 |
|-------|------|-------------|---------|
| `client` | str | 发起请求的客户端标识 (建议使用 `web`) | (必填) |
| `lang` | str | 语言代码 (`en`, `es`) —— 英语 `en` 的数据覆盖量**显著更大** | (必填) |
| `symbol` | str | (可选) 标的代码如 `NASDAQ:AAPL`。不传该参数则返回全球宏观市场头条。 | — |

### 已确认不可用的变体路径

| 路径 | 状态码 | 说明 |
|------|--------|------|
| `/v3/headlines` | 405 | Method Not Allowed (方法不被允许) |
| `/headlines` | 404 | 页面不存在 |
| `/v3/stream` | 404 | 页面不存在 |
| `/v2/headlines/marketdata` | 404 | 页面不存在 |
| `/v2/categories` | 404 | 页面不存在 |
| `/v2/sections` | 404 | 页面不存在 |
| `/v2/news` | 404 | 页面不存在 |

### 不生效的载荷变体

在 Query 参数中传入 `category`、`section`、`from` 等参数会被服务端直接忽略或过滤为 0 条。该端点**不支持分页查询** —— 始终返回最新的新闻列表（最多 200 条）。

---

## 2. 响应数据 Schema

```json
{
  "items": [
    {
      "id": "DJN_DN20260604009289:0",
      "title": "Apple's Plan for AI Dominance Rests on Fixing Its Much-Maligned Chatbot — WSJ",
      "provider": "dow-jones",
      "sourceLogoId": "dow-jones",
      "published": 1780619400,
      "source": "Dow Jones Newswires",
      "urgency": 2,
      "permission": "provider",
      "link": "https://...",
      "relatedSymbols": [
        {"symbol": "NASDAQ:AAPL", "logoid": "apple"}
      ],
      "storyPath": "/news/DJN_DN20260604009289:0/"
    }
  ]
}
```

> 响应中**不包含** `totalCount` 字段，仅包含 `items[]` 数组。

---

## 3. 字段详细说明

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `id` | str | 新闻唯一标识符。格式为 `{PROVIDER}_{INTERNALID}:0`。 |
| `title` | str | 新闻标题。 |
| `provider` | str | 新闻提供商/通讯社 (`dow-jones`, `reuters`, `marketbeat` 等)。 |
| `sourceLogoId` | str | 来源机构 Logo ID（通常与 provider 相同）。 |
| `published` | int | Unix 时间戳（UTC 秒数）。 |
| `source` | str | 机构来源名称 (`Dow Jones Newswires`, `Reuters` 等)。 |
| `urgency` | int | 紧急程度：1 (最高) - 5 (最低)。常见取值为 2-3。 |
| `permission` | str | 权限类型：`provider` (公开可用)，`pro` (需 TradingView 付费订阅)。 |
| `link` | str | 原文外部文章链接 (可选，可能缺失)。 |
| `relatedSymbols` | list | 关联的标的列表，包含 `symbol` 和 `logoid`。 |
| `storyPath` | str | 用于获取正文内容的页面路径 (详见第 4 节)。 |

### 将 `published` 时间戳转换为日期时间

```python
from datetime import datetime, timezone
dt = datetime.fromtimestamp(item["published"], tz=timezone.utc)
print(dt.isoformat())  # 2026-06-04T13:50:00+00:00
```

---

## 4. 新闻正文详情 (Story Detail)

直接请求新闻详情的 API 端点：

```
GET /v2/story?id={story_id}
```

会返回 **HTTP 400** ("Bad Request")。新闻正文内容**未通过 JSON 开放**。

### 替代方案：抓取对应页面的 HTML

```
GET https://es.tradingview.com{storyPath}
```

该请求返回 **HTTP 200**，响应为一个约 190 KB 的 HTML 页面，其中包含渲染好的新闻正文。

脚本中的 `news_story(story_path)` 实现了尽力而为（best-effort）的正文解析：

```python
{
  "url": "https://es.tradingview.com/news/...",
  "title": "Apple's Plan for AI Dominance...",
  "body": "Apple Inc. is racing to fix its Siri assistant...",
  "html_size": 191997
}
```

### 正文提取模式

```python
import re
title_m = re.search(r'<title>([^<]+)</title>', html)
body_m = re.search(r'<article[^>]*>(.+?)</article>', html, re.DOTALL)
```

`<article>` 标签包裹着新闻的核心正文。可通过如下方式清洗 HTML 标签：

```python
body_text = re.sub(r'<[^>]+>', ' ', body_m.group(1))
body_text = re.sub(r'\s+', ' ', body_text).strip()
```

---

## 5. 实测覆盖范围

截至 2026-06，使用 `lang=en` 观察到的覆盖度如下：

| 标的代码 | 返回条数 |
|--------|-------|
| `NASDAQ:AAPL` | 200 |
| `NASDAQ:MSFT` | 200 |
| `NASDAQ:NVDA` | 200 |
| `NYSE:JPM` | 200 |
| `NASDAQ:GGAL` | 1 |
| (不带 symbol 参数) | 200 (全球宏观要闻) |

### 按语言划分

| 语言代码 | 覆盖表现 |
|------|----------|
| `en` | 美股大型蓝筹股均可返回 200 条新闻 |
| `es` | 0-10 条（极其稀少，几乎全为 MarketBeat 来源） |
| `de`, `fr`, `pt` 等 | 未深度测试，但预计覆盖量同样较低 |

**最佳实践建议：** **始终使用 `lang=en`**。如需面向中文或其他语言展示，建议在客户端进行文本翻译。

---

## 6. 新闻提供商 / 数据来源

目前观察到的主要新闻提供商列表：

| 提供商标识 (Provider ID) | 机构名称 | 机构类别 |
|-------------|--------|------|
| `dow-jones` | 道琼斯通讯社 (Dow Jones Newswires) | 专业财经媒体 (优质高级源) |
| `reuters` | 路透社 (Reuters) | 专业权威通讯社 |
| `mt-newswires` | MT Newswires | 专业财经通讯社 |
| `tradingview-research` | TradingView Research | 平台官方原创研究 |
| `marketbeat` | MarketBeat | 散户资讯 / 博客 |
| `benzinga` | Benzinga | 散户资讯 / 财经博客 |
| `binance_news` | Binance News | 加密货币资讯 |
| `cnbc` | CNBC | 专业主流媒体 |
| `bloomberg` | 彭博社 (Bloomberg) | 专业媒体 (需付费墙) |
| `seekingalpha` | Seeking Alpha | 散户分析师专栏 |
| `cointelegraph` | Cointelegraph | 加密货币垂直媒体 |
| `forexlive` | ForexLive | 外汇资讯 |
| `economist` | 经济学人 (The Economist) | 深度财经评论 |

### `permission` 字段含义

| 字段值 | 含义说明 |
|-------|-------------|
| `provider` | 公开新闻，可直接访问外部源链接 |
| `pro` | 需 TradingView Pro 付费会员订阅方可阅读（内部跳转链接） |

---

## 7. 常见工作流与实战代码

### 1. 获取单只标的前 10 条新闻头条

```python
data = news_by_symbol("NASDAQ:AAPL", lang="en")
top_10 = data["items"][:10]
for item in top_10:
    print(f"[{item['source']}] {item['title']}")
```

### 2. 按提供商过滤新闻

```python
data = news_by_symbol("NASDAQ:AAPL", lang="en")
dj_only = [it for it in data["items"] if it["provider"] == "dow-jones"]
```

### 3. 获取新闻完整正文详情

```python
items = news_by_symbol("NASDAQ:AAPL")["items"]
first = items[0]
detail = news_story(first["storyPath"])
print(detail["title"])
print(detail["body"][:500])
```

### 4. 聚合多只标的的新闻

```python
symbols = ["NASDAQ:AAPL", "NASDAQ:MSFT", "NYSE:JPM"]
all_items = []
for s in symbols:
    items = news_by_symbol(s)["items"]
    all_items.extend(items)
# 按 ID 去重
seen = set()
unique = []
for it in all_items:
    if it["id"] not in seen:
        seen.add(it["id"])
        unique.append(it)
# 按发布时间倒序排序
unique.sort(key=lambda x: x["published"], reverse=True)
```

### 5. 获取全球宏观新闻头条 (无标的过滤)

```python
data = news_global(lang="en")
# 返回全球范围内最新的 200 条要闻
```

### 6. 按紧急程度筛选

```python
data = news_by_symbol("NASDAQ:AAPL")
urgent = [it for it in data["items"] if it["urgency"] <= 2]
```

### 7. 按发布日期筛选

```python
from datetime import datetime, timezone, timedelta
data = news_by_symbol("NASDAQ:AAPL")
cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=7)).timestamp()
last_week = [it for it in data["items"] if it["published"] >= cutoff]
```

### 8. 获取单条新闻关联的标的列表

```python
items = news_global()["items"]
for it in items[:20]:
    syms = [s["symbol"] for s in it.get("relatedSymbols", [])]
    print(f"{it['title'][:50]} -> {syms[:3]}")
```

---

## 8. 局限性与已知限制

1. **不支持分页**：单次最多 200 条，无 offset/cursor 参数。若需要长期历史数据，需结合其他新闻源。
2. **服务端无多维过滤**：无法在服务端按提供商、日期区间或类别进行检索。需在客户端拉取后自行过滤。
3. **非英语语言覆盖极低**：`lang=es` 或其他语言资源极少，建议默认使用 `lang=en`。
4. **JSON 接口未开放正文**：若需正文内容，必须解析对应 `storyPath` 的 HTML 页面。
5. **不支持全文关键词检索**：不能在请求中指定搜索关键词。需在拉取到的 200 条列表中进行本地模糊/正则搜索。
6. **`permission: pro` 内容限制**：部分内容为 TradingView 内部专属，若无 Pro 会员则只能看到标题而无法访问正文。
7. **请求速率限制**：未公开说明，实测可承受 ~3 请求/秒。
8. **小盘股新闻偏少**：非核心标的通常仅有 1-5 条，多来自 `marketbeat` 或 `benzinga`。若需全面覆盖小型股票，建议搭配 Yahoo Finance 等 Skill 补充。

---

## 附录：与其他金融新闻接口横向对比

| 数据源 | 小型股票覆盖度 | API 是否提供正文 | 分页支持 | 鉴权要求 |
|--------|------------------------|--------------|------------|------|
| **TradingView** | ⚠️ 偏低 (1-5 条) | ❌ (需抓取 HTML) | ❌ | ❌ 无需鉴权 |
| Yahoo Finance | ✅ 丰富 | ✅ 原生 JSON | ✅ | ❌ 无需鉴权 |
| Finnhub | ✅ 丰富 | ✅ 原生 JSON | ✅ | ⚠️ 需 API Key |
| Alpha Vantage | ⚠️ 中等 | ✅ 原生 JSON | ✅ | ⚠️ 需 API Key |
| Marketwatch | ✅ 丰富 | ✅ 网页解析 | ❌ | ❌ 无需鉴权 |

**何时适合选用 TradingView News：**
- 美股大型蓝筹股 (AAPL/MSFT/NVDA 等)：新闻更新及时且覆盖全面。
- 获取来自 Dow Jones、Reuters 等专业通讯社的高级权威资讯（其他平台通常有付费墙）。
- 加密货币资讯，直接聚合 Binance News。

**何时不建议使用 TradingView News：**
- 非美股市场的小型微盘股：建议优先使用 Yahoo Finance 或 Finnhub。
- 检索长周期的历史新闻归档：公开端点均未提供。
- 自动化批量获取结构化的新闻正文全文：仅官方 Pro 会员或原版权方提供直接接口。
