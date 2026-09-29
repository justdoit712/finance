# FRED API 参考手册 (API Reference)

圣路易斯联储宏观经济数据库（Federal Reserve Economic Data, FRED）API 详细接口文档。

**Base URL:** `https://api.stlouisfed.org/fred`  
**返回格式:** XML（默认）或 JSON（追加 `&file_type=json`）  
**身份认证:** 支持 URL 查询参数 `&api_key=YOUR_KEY` 或 HTTP 请求头 `X-API-KEY`

---

## 接口端点详解 (Detailed Endpoints)

### 1. 时序观测值 — `GET /fred/series/observations`

**描述:** 获取单条时间序列的历史观测数据。

**请求参数:**

| 参数名 | 是否必填 | 默认值 | 描述 |
|--------|---------|--------|------|
| `series_id` | ✅ | — | 时间序列代码（例如：`GDP`, `UNRATE`） |
| `api_key` | ✅ | — | 32 位 API Key |
| `file_type` | ❌ | `xml` | 指定 `json` 以获取 JSON 格式响应 |
| `observation_start` | ❌ | 起始最早时间 | 起始日期，格式 `YYYY-MM-DD` |
| `observation_end` | ❌ | 当前最新时间 | 结束日期，格式 `YYYY-MM-DD` |
| `units` | ❌ | `lin` | 数据变换单位：`lin`=原值(线性)，`chg`=绝对变动量，`ch1`=同比绝对变动量，`pch`=百分比变动，`pc1`=同比百分比变动，`pca`=复合年化百分比变动，`log`=自然对数 |
| `frequency` | ❌ | 原始频率 | 重采样频率：`d`(日), `w`(周), `bw`(双周), `m`(月), `q`(季), `sa`(半年), `a`(年) |
| `aggregation_method` | ❌ | `avg` | 降频聚合方式：`avg`(均值), `sum`(求和), `eop`(期末值/End of Period) |
| `output_type` | ❌ | 1 | 输出数据结构：1=仅观测值列表，2=包含序列对象 |
| `sort_order` | ❌ | `asc` | 排序方向：`asc`(升序), `desc`(降序) |
| `limit` | ❌ | 100000 | 单次最大返回条数（上限 100,000） |
| `offset` | ❌ | 0 | 分页偏移量 |

**完整调用示例:**

```python
import requests

url = "https://api.stlouisfed.org/fred/series/observations"
params = {
    "series_id": "FEDFUNDS",
    "api_key": "YOUR_API_KEY",
    "file_type": "json",
    "observation_start": "2023-01-01",
    "observation_end": "2024-01-01",
    "units": "lin",
    "frequency": "m",
    "aggregation_method": "avg",
    "sort_order": "asc"
}
r = requests.get(url, params=params)
data = r.json()
print(f"观测值总数: {data['count']}")
for obs in data["observations"]:
    if obs["value"] != ".":
        print(f"{obs['date']} → {obs['value']}")
```

**JSON 响应示例:**

```json
{
  "realtime_start": "2026-06-03",
  "realtime_end": "2026-06-03",
  "observation_start": "2023-01-01",
  "observation_end": "2024-01-01",
  "units": "lin",
  "output_type": 1,
  "file_type": "json",
  "order": "asc",
  "count": 12,
  "observations": [
    {"realtime_start": "2026-06-03", "realtime_end": "2026-06-03", "date": "2023-01-01", "value": "4.33"},
    {"realtime_start": "2026-06-03", "realtime_end": "2026-06-03", "date": "2023-02-01", "value": "4.50"},
    {"realtime_start": "2026-06-03", "realtime_end": "2026-06-03", "date": "2023-03-01", "value": "4.73"}
  ]
}
```

---

### 2. 搜索时序 — `GET /fred/series/search`

**描述:** 按文本关键字或时序代码搜索时间序列。

**请求参数:**

| 参数名 | 是否必填 | 默认值 | 描述 |
|--------|---------|--------|------|
| `api_key` | ✅ | — | API Key |
| `search_text` | ✅ | — | 搜索关键词 |
| `search_type` | ❌ | `full_text` | 搜索模式：`full_text`（全文检索）或 `series_id`（代码前缀匹配） |
| `realtime_start` | ❌ | 当天 | 实时数据起始日 |
| `realtime_end` | ❌ | 当天 | 实时数据结束日 |
| `limit` | ❌ | 100 | 返回结果数（最大 1000） |
| `offset` | ❌ | 0 | 分页偏移量 |
| `order_by` | ❌ | `search_rank` | 排序字段：`search_rank`(相关度), `series_id`(代码), `title`(标题), `popularity`(热度) |
| `sort_order` | ❌ | `desc` | 排序方向：`asc` 或 `desc` |
| `filter_variable` | ❌ | — | 过滤属性维度：`frequency`, `units`, `seasonal_adjustment` |
| `filter_value` | ❌ | — | 对应属性的过滤取值 |

**调用示例:**

```python
params = {
    "api_key": API_KEY,
    "file_type": "json",
    "search_text": "GDP",
    "search_type": "full_text",
    "limit": 10,
    "order_by": "popularity",
    "sort_order": "desc"
}
r = requests.get("https://api.stlouisfed.org/fred/series/search", params=params)
```

---

### 3. 时序元数据 — `GET /fred/series`

**描述:** 获取特定时间序列的详细元数据信息（名称、单位、更新时间、频度、季节调整等）。

| 参数名 | 是否必填 | 描述 |
|--------|---------|------|
| `series_id` | ✅ | 时间序列代码 |

**响应示例:**

```json
{
  "seriess": [{
    "id": "UNRATE",
    "realtime_start": "2026-06-03",
    "realtime_end": "2026-06-03",
    "title": "Unemployment Rate",
    "observation_start": "1948-01-01",
    "observation_end": "2026-05-01",
    "frequency": "Monthly",
    "frequency_short": "M",
    "units": "Percent",
    "units_short": "%",
    "seasonal_adjustment": "Seasonally Adjusted",
    "seasonal_adjustment_short": "SA",
    "last_updated": "2026-05-06 09:11:22-05",
    "popularity": 99,
    "notes": "..."
  }]
}
```

---

### 4. 时序所属分类 — `GET /fred/series/categories`

**描述:** 查询特定时序所属的所有类别 ID 与名称。

| 参数名 | 是否必填 |
|--------|---------|
| `series_id` | ✅ |

```python
params = {"api_key": API_KEY, "file_type": "json", "series_id": "UNRATE"}
r = requests.get("https://api.stlouisfed.org/fred/series/categories", params=params)
# 响应结构: {"categories": [{"id": 32991, "name": "..."}]}
```

---

### 5. 分类详情 — `GET /fred/category`

**描述:** 获取指定分类的名称和父级分类 ID。

| 参数名 | 是否必填 | 默认值 |
|--------|---------|--------|
| `category_id` | ✅ | — |

---

### 6. 子分类列表 — `GET /fred/category/children`

**描述:** 获取指定分类的直接子分类列表。

| 参数名 | 是否必填 | 默认值 |
|--------|---------|--------|
| `category_id` | ✅ | — |

---

### 7. 分类下时序 — `GET /fred/category/series`

**描述:** 分页获取属于某个分类的所有时间序列。

| 参数名 | 是否必填 | 默认值 |
|--------|---------|--------|
| `category_id` | ✅ | — |
| `limit` | ❌ | 100 |
| `offset` | ❌ | 0 |

**示例 — 查询利率分类（ID: 32995）下的所有时序:**

```python
params = {"api_key": API_KEY, "file_type": "json", "category_id": 32995, "limit": 100}
r = requests.get("https://api.stlouisfed.org/fred/category/series", params=params)
```

---

### 8. 标签浏览 — `GET /fred/tags` 与 `GET /fred/related_tags`

**描述:** 查询和检索 FRED 的时序标签（Tags）。

```python
# 检索高热度的货币与利率相关标签
params = {"api_key": API_KEY, "file_type": "json",
          "tag_names": "money;interest rate", "order_by": "popularity"}
r = requests.get("https://api.stlouisfed.org/fred/tags", params=params)
```

---

### 9. 标签包含时序 — `GET /fred/tags/series`

**描述:** 获取同时满足一组标签的所有时间序列。

```python
# 获取同时带有 "monthly" 与 "inflation" 标签的时序
params = {"api_key": API_KEY, "file_type": "json",
          "tag_names": "monthly;inflation", "limit": 50}
r = requests.get("https://api.stlouisfed.org/fred/tags/series", params=params)
```

---

### 10. 数据来源机构 — `GET /fred/sources` 与 `GET /fred/source`

**描述:** 查询底层数据发布机构（如 BLS 劳工统计局、BEA 经济分析局、美联储等）。

```python
# 获取所有数据来源机构
r = requests.get("https://api.stlouisfed.org/fred/sources",
                 params={"api_key": API_KEY, "file_type": "json"})

# 查询特定机构（source_id=1 为美国劳工统计局 BLS）
r = requests.get("https://api.stlouisfed.org/fred/source",
                 params={"api_key": API_KEY, "file_type": "json", "source_id": 1})
```

| source_id | 机构名称 |
|-----------|---------|
| 1 | 美国劳工统计局（U.S. Bureau of Labor Statistics, BLS） |
| 2 | 美国经济分析局（U.S. Bureau of Economic Analysis, BEA） |
| 3 | 美联储理事会（Federal Reserve Board） |
| 6 | 美国普查局（U.S. Census Bureau） |
| 19 | 美国财政部（U.S. Department of the Treasury） |
| 31 | 房地美（Freddie Mac） |

---

### 11. 数据发布报告 — `GET /fred/release`

**描述:** 查询宏观数据定期发布报告（Release，如就业形势报告、CPI 报告等）。

```python
# 查询美国就业形势报告（Employment Situation，release_id=50 为 FOMC，release_id=9 为就业形势）
params = {"api_key": API_KEY, "file_type": "json", "release_id": 50}
r = requests.get("https://api.stlouisfed.org/fred/release", params=params)
```

| release_id | 发布报告名称 |
|------------|-------------|
| 9 | 美国就业形势报告（Employment Situation, BLS） |
| 10 | 消费者物价指数报告（Consumer Price Index, BLS） |
| 18 | 国内生产总值报告（GDP, BEA） |
| 50 | 联邦公开市场委员会报告（Federal Reserve FOMC） |
| 53 | H.8 商业银行资产与负债（Assets and Liabilities） |
| 55 | H.4.1 影响储备余额因素（Factors Affecting Reserve Balances） |
| 93 | 工业生产与产能利用率（Industrial Production, G.17） |

---

## 常用参数说明 (Common Parameters)

### 单位转换 (Units)

| 取值 | 说明 |
|------|------|
| `lin` | 原始水平值（默认） |
| `chg` | 相比上期绝对变动量（Change） |
| `ch1` | 相比去年同期绝对变动量（Year-over-Year Change） |
| `pch` | 环比百分比变动（Percent Change） |
| `pc1` | 同比百分比变动（Year-over-Year Percent Change） |
| `pca` | 复合年化增长率（Compounded Annual Rate of Change） |
| `log` | 自然对数（Natural Log） |

### 频率转换 (Frequency)

| 取值 | 说明 |
|------|------|
| `d` | 日度（Daily） |
| `w` | 周度（Weekly） |
| `bw` | 双周度（Biweekly） |
| `m` | 月度（Monthly） |
| `q` | 季度（Quarterly） |
| `sa` | 半年度（Semiannual） |
| `a` | 年度（Annual） |

### 降频聚合方法 (Aggregation Method)

| 取值 | 说明 |
|------|------|
| `avg` | 期内均值（Average，默认） |
| `sum` | 期内累加求和（Sum） |
| `eop` | 期末值（End of Period） |

---

## HTTP 状态码与异常处理

| 状态码 | 含义 | 诊断与处理方法 |
|--------|------|----------------|
| 200 | 请求成功 | 正常处理返回数据 |
| 400 | Bad Request | 检查请求参数名与参数格式 |
| 401 | Unauthorized | API Key 无效或未提供 |
| 403 | Forbidden | API Key 未获得相应接口授权 |
| 404 | Not Found | 请求的 `series_id` 或资源不存在 |
| 429 | Too Many Requests | 触发速率限制（超 120 req/min），需增加延迟或退避重试 |
| 500 | Server Error | FRED 服务端内部错误，建议稍后重试 |

### 400 错误响应示例:

```json
{
  "error_code": 400,
  "error_message": "Bad Request. Parameter 'series_id' is required."
}
```

---

## 速率限制与安全重试策略 (Rate Limiting)

```python
import time
import requests

def fetch_fred_safe(series_id, api_key, retries=3):
    """带指数退避重试的安全请求封装。"""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": "2020-01-01"
    }

    for attempt in range(retries):
        r = requests.get(url, params=params)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 429:
            wait = 2 ** attempt * 2  # 退避等待 2, 4, 8 秒
            print(f"触发速率限制，等待 {wait} 秒后重试...")
            time.sleep(wait)
        else:
            r.raise_for_status()
    raise Exception(f"请求失败，已重试 {retries} 次。")
```

---

## 高级实战用例 (Advanced Examples)

### 并发拉取多条时序（受控限速）

```python
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_one(series_id, api_key):
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {"series_id": series_id, "api_key": api_key,
              "file_type": "json", "observation_start": "2010-01-01",
              "limit": 1000}
    r = requests.get(url, params=params)
    time.sleep(1.0)  # 主动限速，避免打满 120 req/min
    return series_id, r.json()

def fetch_many(series_ids, api_key):
    results = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(fetch_one, sid, api_key): sid for sid in series_ids}
        for f in as_completed(futures):
            sid, data = f.result()
            results[sid] = data
    return results
```

### 转换为 pandas Series

```python
import pandas as pd

def fred_to_df(series_id, api_key, start="2010-01-01"):
    """下载 FRED 时间序列并转换为 pandas Series。"""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {"series_id": series_id, "api_key": api_key,
              "file_type": "json", "observation_start": start}
    r = requests.get(url, params=params)
    df = pd.DataFrame(r.json()["observations"])
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])
    return df.set_index("date")["value"]

# 使用示例
gdp = fred_to_df("GDPC1", API_KEY)
gdp.plot(title="US Real GDP")
```

### 多序列宏观监控看板

```python
import matplotlib.pyplot as plt

series = {
    "FEDFUNDS": "Federal Funds Rate",
    "DGS10": "Treasury 10y",
    "UNRATE": "Unemployment",
    "CPIAUCSL": "CPI Index"
}

dfs = {}
for sid, name in series.items():
    dfs[sid] = fred_to_df(sid, API_KEY)
    print(f"{name}: {len(dfs[sid])} obs")

# 绘图展示
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
for ax, (sid, name) in zip(axes.flat, series.items()):
    dfs[sid].plot(ax=ax, title=name)
plt.tight_layout()
plt.show()
```
