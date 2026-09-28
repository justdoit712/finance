---
name: fred-macro
description: "美联储经济数据库（FRED）免费 API：840K+ 宏观经济时间序列（GDP、CPI、利率、就业、M2、VIX、国债收益率等）。"
license: MIT
metadata:
  category: 金融, API, 宏观经济, 美联储, 美国
  language: zh
  source: https://fred.stlouisfed.org/docs/api/fred/
---

# FRED Macro — 美联储经济数据（FRED）API

圣路易斯联储（FRED）提供的**官方免费** API，拥有 **840,000+ 条宏观经济时间序列**：国内生产总值（GDP）、通胀指标（CPI/PCE）、基准与市场利率、就业劳动力、M2 货币供应量、VIX 恐慌指数、各期限国债收益率、抵押贷款利率等。

**Base URL:** `https://api.stlouisfed.org/fred`  
**官方文档:** [fred.stlouisfed.org/docs/api/fred/](https://fred.stlouisfed.org/docs/api/fred/)

---

## 身份认证 (Authentication)

### 获取 API Key（免费）

1. 访问：https://fred.stlouisfed.org/docs/api/api_key.html
2. 注册免费账户（邮箱 + 密码）
3. 申请 API key（即时生成）
4. **无需绑定信用卡**

### 使用 API Key

```python
import os
API_KEY = os.getenv("FRED_API_KEY")  # 推荐方式
# 或直接用于本地测试：
# API_KEY = "YOUR_API_KEY_HERE"
```

**⚠️ 严禁将 API key 硬编码提交到公开代码仓库或版本控制中。**

---

## 速率限制 (Rate Limits)

| 限制指标 | 限额 |
|---------|------|
| **每分钟请求数** | 120 req/min |
| **每天请求数** | 无限制（无显式每日限额） |
| **单次请求最大观测值数** | 100,000 |
| **单次请求最大序列数** | 取决于端点（通常为 1） |
| **费用** | **完全免费** |

### 建议与实践

- 本地缓存数据响应（宏观经济数据更新频率较低，无需高频重复拉取）
- 使用 `observation_start` 和 `observation_end` 缩小请求的时间跨度
- 若收到 HTTP 429（Too Many Requests），实现带有指数退避（exponential backoff）的重试机制
- 大批量下载多条时间序列时，各请求之间建议至少间隔 0.5 秒

---

## 核心端点 (Core Endpoints)

### 时序与观测值 (Series & Observations)

| 端点 | 描述 | 认证 |
|------|------|------|
| `GET /fred/series/observations` | 获取单条时间序列的历史观测值 | API Key |
| `GET /fred/series/search` | 按文本关键字搜索时间序列 | API Key |
| `GET /fred/series` | 获取时间序列的元数据信息 | API Key |
| `GET /fred/series/categories` | 获取时间序列所属的分类 | API Key |
| `GET /fred/series/release` | 获取时间序列关联的数据发布报告（Release） | API Key |

### 分类与发布报告 (Categories & Releases)

| 端点 | 描述 |
|------|------|
| `GET /fred/category` | 获取分类信息 |
| `GET /fred/category/children` | 获取子分类列表 |
| `GET /fred/category/related` | 获取相关分类列表 |
| `GET /fred/category/series` | 获取指定分类下的所有时间序列 |
| `GET /fred/release` | 获取数据发布报告（Release）信息 |
| `GET /fred/release/dates` | 获取发布报告的历史与未来发布日期 |
| `GET /fred/release/series` | 获取指定发布报告包含的所有时间序列 |

### 标签 (Tags)

| 端点 | 描述 |
|------|------|
| `GET /fred/tags` | 搜索与浏览标签 |
| `GET /fred/related_tags` | 获取关联标签 |
| `GET /fred/tags/series` | 获取带有特定标签的时间序列 |
| `GET /fred/series/tags` | 获取单条时间序列所拥有的标签 |

### 数据来源 (Sources)

| 端点 | 描述 |
|------|------|
| `GET /fred/sources` | 获取所有数据来源机构列表 |
| `GET /fred/source` | 获取指定数据源机构的详细信息 |

### 更新与日历 (Updates & Calendar)

| 端点 | 描述 |
|------|------|
| `GET /fred/series/updates` | 获取最近更新的时间序列 |
| `GET /fred/seasonal/adjustments` | 获取季节性调整选项列表 |

---

## 响应格式 (Response Format)

接口默认返回 XML 格式。可通过在请求中追加 `&file_type=json` 指定返回 JSON 格式：

```json
{
  "realtime_start": "2026-06-01",
  "realtime_end": "2026-06-01",
  "observation_start": "1954-07-01",
  "observation_end": "2026-06-01",
  "units": "lin",
  "count": 864,
  "observations": [
    {
      "realtime_start": "2026-06-01",
      "realtime_end": "2026-06-01",
      "date": "1954-07-01",
      "value": "."
    },
    {
      "realtime_start": "2026-06-01",
      "realtime_end": "2026-06-01",
      "date": "1954-10-01",
      "value": "126.8"
    }
  ]
}
```

> **注意：** 返回值中的 `"."` 表示该观测日期无可用数据（缺失值 / N/A）。

---

## 序列分类 (Series Categories)

FRED 的时间序列按**分类 ID**（整数）分层组织：

| ID | 分类名称 | 代表性时序代码 |
|----|----------|----------------|
| 0 | 所有分类（根分类） | — |
| 32991 | **Population, Employment, & Labor Markets**（人口、就业与劳动力市场） | UNRATE, PAYEMS, NFP |
| 32992 | **National Income & Product Accounts**（国民收入与生产账户） | GDP, GDPC1, GNP |
| 32993 | **Consumer Price Indexes (CPI)**（消费者物价指数） | CPIAUCSL, CPILFESL |
| 32994 | **Producer Price Indexes (PPI)**（生产者物价指数） | PPIACO, PPIFIS |
| 32995 | **Interest Rates**（利率） | FEDFUNDS, DGS10, DGS2 |
| 32996 | **Money, Banking, & Finance**（货币、银行与金融） | M2SL, M1SL, TOTBKCR |
| 32997 | **International Trade**（国际贸易） | BOPGSTB |
| 33000 | **U.S. Regional Data**（美国区域经济数据） | 各州统计指标 |
| 33001 | **Academic Data**（学术研究数据） | 学术数据集 |

完整参考详见 [references/SERIES_REFERENCE.md](./references/SERIES_REFERENCE.md)。

---

## 快速上手 (Quick Start)

### 1. 下载单条时间序列（Python）

```python
import requests

API_KEY = "YOUR_API_KEY"
url = "https://api.stlouisfed.org/fred/series/observations"
params = {
    "series_id": "GDP",
    "api_key": API_KEY,
    "file_type": "json",
    "observation_start": "2020-01-01",
    "observation_end": "2025-12-31"
}
r = requests.get(url, params=params)
data = r.json()
for obs in data["observations"]:
    if obs["value"] != ".":
        print(obs["date"], obs["value"])
```

### 2. 按关键字搜索时间序列

```python
params = {
    "api_key": API_KEY,
    "file_type": "json",
    "search_text": "inflation",
    "search_type": "full_text",  # 或 "series_id"
    "limit": 10
}
r = requests.get("https://api.stlouisfed.org/fred/series/search", params=params)
```

### 3. 配合 pandas 处理

```python
import pandas as pd
import requests

def fetch_fred(series_id, api_key, start="2020-01-01"):
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {"series_id": series_id, "api_key": api_key,
              "file_type": "json", "observation_start": start}
    r = requests.get(url, params=params)
    df = pd.DataFrame(r.json()["observations"])
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.set_index("date")["value"]

gdp = fetch_fred("GDP", API_KEY)
cpi = fetch_fred("CPIAUCSL", API_KEY)
fedfunds = fetch_fred("FEDFUNDS", API_KEY)
```

---

## 可用脚本 (Available Scripts)

| 脚本 | 描述 |
|------|------|
| **[fetch_series.py](./scripts/fetch_series.py)** | 下载一条或多条 FRED 时序并导出为 CSV / JSON / Parquet |
| **[search_series.py](./scripts/search_series.py)** | 按文本、分类或标签搜索 FRED 时序 |
| **[download_multiple.py](./scripts/download_multiple.py)** | 按预设分类批量下载多条时序 |

---

## 核心基准时序 (Headlines)

| 时序代码 | 描述 | 频率 |
|----------|------|------|
| `GDP` | 名义 GDP（十亿美元） | 季度 |
| `GDPC1` | 实际 GDP（十亿链式 2017 美元） | 季度 |
| `CPIAUCSL` | 总体 CPI（CPI All Items，季调） | 月度 |
| `CPILFESL` | 核心 CPI（剔除食品和能源，季调） | 月度 |
| `PCEPILFE` | 核心 PCE 物价指数（美联储核心通胀锚） | 月度 |
| `FEDFUNDS` | 联邦基金目标利率 | 日度 |
| `DFF` | 联邦基金有效利率（Effective Federal Funds Rate） | 日度 |
| `DGS10` | 10 年期美国国债名义收益率 | 日度 |
| `DGS2` | 2 年期美国国债名义收益率 | 日度 |
| `T10Y2Y` | 10年与2年期美债利差（收益率曲线倒挂指标） | 日度 |
| `UNRATE` | 官方失业率（U-3） | 月度 |
| `PAYEMS` | 非农就业人数（Nonfarm Payrolls） | 月度 |
| `M2SL` | M2 货币供应量 | 月度 |
| `M1SL` | M1 货币供应量 | 月度 |
| `VIXCLS` | CBOE 波动率指数（VIX，S&P 500 隐含波动率） | 日度 |
| `BAA10Y` | 穆迪 BAA 级企业债与 10 年期国债信用利差 | 日度 |
| `TOTALSA` | 零售总销售额 | 月度 |
| `INDPRO` | 工业生产指数 | 月度 |
| `HOUST` | 新屋开工量 | 月度 |
| `MORTGAGE30US` | 30 年期固定房贷利率（房利美/房地美统计） | 周度 |

完整时序清单请参阅：**[references/SERIES_REFERENCE.md](./references/SERIES_REFERENCE.md)**（收录 100+ 条常用重要时序）。

---

## 最佳实践 (Best Practices)

1. **缓存数据**：宏观数据变动频率较低，建议拉取后保存到本地 Parquet 或 CSV 文件。
2. **指定 `file_type=json`**：相较默认的 XML，JSON 解析速度更快且更契合现代数据栈。
3. **按日期区间过滤**：设置 `observation_start`，避免下载全量无用的过早历史数据。
4. **妥善处理缺失值 `"."`**：将 `"."` 转为 `NaN` 或 `None`，防止类型转换异常。
5. **遵守速率限制**：上限 120 req/min，多线程或批量请求时单线程应保留至少 0.5 秒间隔。
6. **保护 API Key**：通过环境变量 `FRED_API_KEY` 读取，勿明文写入代码。
7. **数据源免责声明**：在商业应用中必须包含版权声明：“This product uses the FRED API but is not endorsed or certified by the Federal Reserve Bank of St. Louis”。
