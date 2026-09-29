# Scanner 过滤器 (Filters) — 完整语法指南

> 本文介绍了 Scanner 请求载荷中 `filter` 数组的完整语法规则。支持在 TradingView 涵盖的 ~100k+ 全球品种资产池上，构建类似 SQL 般灵活高效的查询过滤条件。

---

## 目录

1. [过滤器的结构剖析 (Anatomy of Filter)](#1-过滤器的结构剖析-anatomy-of-filter)
2. [支持的操作符 (Supported Operations)](#2-支持的操作符-supported-operations)
3. [多条件组合 — 隐式 AND 关系](#3-多条件组合--隐式-and-关系)
4. [结果排序 (Sort)](#4-结果排序-sort)
5. [通过 range 进行分页查询](#5-通过-range-进行分页查询)
6. [常见实战用例](#6-常见实战用例)
7. [高级进阶用例](#7-高级进阶用例)
8. [常见错误排查](#8-常见错误排查)

---

## 1. 过滤器的结构剖析 (Anatomy of Filter)

每个过滤条件都是一个包含 3 个 Key 的字典对象：

```json
{
  "left": "<column_name>",
  "operation": "<operation>",
  "right": <value>
}
```

| 键名 (Key) | 数据类型 | 说明 |
|-----|------|-------------|
| `left` | str | 字段列名称（必须在 Scanner 支持的字段目录中） |
| `operation` | str | 操作符名称（详见下方操作符对照表） |
| `right` | mixed | 对比的值或值列表（具体类型取决于操作符） |

示例：

```json
{"left": "sector", "operation": "equal", "right": "Finance"}
```

---

## 2. 支持的操作符 (Supported Operations)

### 等值 / 不等值 (Equality / Inequality)

| 操作符 | `right` 类型 | 含义说明 |
|-----------|--------------|-------------|
| `equal` | str/number | `left == right` (等于) |
| `nequal` | str/number | `left != right` (不等于) |

### 数值大小比较 (Numeric Comparison)

| 操作符 | `right` 类型 | 含义说明 |
|-----------|--------------|-------------|
| `greater` | number | `left > right` (大于) |
| `egreater` | number | `left >= right` (大于等于) |
| `less` | number | `left < right` (小于) |
| `eless` | number | `left <= right` (小于等于) |

### 数值区间 (Range)

| 操作符 | `right` 类型 | 含义说明 |
|-----------|--------------|-------------|
| `in_range` | `[min, max]` | `min <= left <= max` (在闭区间内) |
| `not_in_range` | `[min, max]` | `left < min OR left > max` (在区间外) |

### 集合成员判定 (Set Membership)

| 操作符 | `right` 类型 | 含义说明 |
|-----------|--------------|-------------|
| `in_range_strings` | `["a","b","c"]` | `left in [...]` (字符串集合包含) |
| `not_in_range_strings` | `["a","b","c"]` | `left not in [...]` (字符串集合不包含) |

### 字符串模糊匹配 (Strings)

| 操作符 | `right` 类型 | 含义说明 |
|-----------|--------------|-------------|
| `match` | str | `left LIKE '%right%'` (包含子串匹配) |
| `nmatch` | str | `left NOT LIKE '%right%'` (不包含子串) |

### 布尔值 / 空值判定 (Boolean / Null)

| 操作符 | `right` 类型 | 含义说明 |
|-----------|--------------|-------------|
| `empty` | (无需 right) | `left IS NULL` (字段为空) |
| `nempty` | (无需 right) | `left IS NOT NULL` (字段非空) |
| `equal` 配合 `right: true/false` | bool | 用于布尔标志位判定 |

### 时序跨越交叉 (Cross / Price Action)

| 操作符 | `right` 类型 | 含义说明 |
|-----------|--------------|-------------|
| `crosses` | 列名或数值 | `left 穿越 right` (行情穿越) |
| `crosses_above` | 列名或数值 | `left 从下方上穿 right` (金叉) |
| `crosses_below` | 列名或数值 | `left 从上方下穿 right` (死叉) |
| `above%` | 列名或数值 | `left > right * (1 + pct)` |
| `below%` | 列名或数值 | `left < right * (1 - pct)` |

---

## 3. 多条件组合 — 隐式 AND 关系

在 `filter` 数组中传入多个条件对象时，会自动以隐式 **AND** 进行与运算组合：

```json
{
  "filter": [
    {"left": "sector", "operation": "equal", "right": "Technology"},
    {"left": "market_cap_basic", "operation": "greater", "right": 1000000000000},
    {"left": "country", "operation": "equal", "right": "United States"}
  ]
}
```

等价的 SQL 语句：

```sql
WHERE sector = 'Technology'
  AND market_cap_basic > 1e12
  AND country = 'United States'
```

### 如何实现 OR 逻辑

对于同一字段的 `OR` 条件，请使用**复数集合操作符**：

```json
{"left": "sector", "operation": "in_range_strings", "right": ["Finance", "Technology"]}
```

等价于：

```sql
WHERE sector IN ('Finance', 'Technology')
```

> 服务端不支持不同字段间的任意 `OR` 语法。仅支持在同一字段内部通过 `IN` 实现多选。

---

## 4. 结果排序 (Sort)

```json
{
  "sort": {
    "sortBy": "<column>",
    "sortOrder": "asc" | "desc"
  }
}
```

实战示例：

```json
{"sortBy": "market_cap_basic", "sortOrder": "desc"}     // 市值由大到小排序
{"sortBy": "Perf.YTD", "sortOrder": "desc"}              // 年初至今表现最优优先
{"sortBy": "dividend_yield_recent", "sortOrder": "desc"} // 股息率最高优先
```

> 单次请求**仅支持按单一字段列排序**，不支持多列组合复合排序。

---

## 5. 通过 range 进行分页查询

Scanner **不使用**传统的 `page` 页码参数，而是使用切片区间 `range: [start, end]`：

```json
"range": [0, 30]    // 获取前 30 条记录
"range": [30, 60]   // 获取第 31 至 60 条记录 (跳过前 30 条)
"range": [0, 5000]  // 一次性获取前 5000 条 (单次请求的实用上限)
```

**实测经验上限：** 单次请求约 ~5000 条数据不会触发限流或超时。如需获取更多数据，请通过分段递增偏移量分批拉取。

---

## 6. 常见实战用例

### 美股市值前 10 大普通股

```json
{
  "filter": [
    {"left": "type", "operation": "equal", "right": "stock"},
    {"left": "country", "operation": "equal", "right": "United States"}
  ],
  "columns": ["name", "description", "market_cap_basic", "close", "change"],
  "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
  "range": [0, 10]
}
```

### 在 NASDAQ / NYSE 挂牌上市的阿根廷企业 (ADR)

```json
{
  "filter": [
    {"left": "country", "operation": "equal", "right": "Argentina"},
    {"left": "exchange", "operation": "in_range_strings", "right": ["NASDAQ", "NYSE"]}
  ],
  "columns": ["name", "description", "exchange", "close", "market_cap_basic"],
  "range": [0, 30]
}
```

### 本周披露财报的股票

```json
{
  "filter": [
    {
      "left": "earnings_release_next_date",
      "operation": "in_range",
      "right": [1780000000, 1780604800]
    },
    {"left": "type", "operation": "equal", "right": "stock"}
  ],
  "columns": ["name", "description", "earnings_release_next_date", "market_cap_basic"],
  "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
  "range": [0, 50]
}
```

### 超卖 (RSI < 30) 且高股息的大盘股

```json
{
  "filter": [
    {"left": "RSI", "operation": "less", "right": 30},
    {"left": "dividend_yield_recent", "operation": "greater", "right": 0.05},
    {"left": "market_cap_basic", "operation": "greater", "right": 1000000000}
  ],
  "columns": ["name", "close", "RSI", "dividend_yield_recent"],
  "sort": {"sortBy": "dividend_yield_recent", "sortOrder": "desc"},
  "range": [0, 20]
}
```

### 技术评级为 STRONG_BUY (强力买入) 的股票

```json
{
  "filter": [
    {"left": "Recommend.All", "operation": "greater", "right": 0.5},
    {"left": "type", "operation": "equal", "right": "stock"}
  ],
  "columns": ["name", "close", "Recommend.All", "Recommend.MA", "Recommend.Other"],
  "sort": {"sortBy": "Recommend.All", "sortOrder": "desc"},
  "range": [0, 50]
}
```

### 指定行业且净资产收益率 (ROE) 优异的股票

```json
{
  "filter": [
    {"left": "industry", "operation": "equal", "right": "Regional Banks"},
    {"left": "return_on_equity", "operation": "greater", "right": 15}
  ],
  "columns": ["name", "country", "return_on_equity", "price_book", "dividend_yield_recent"],
  "sort": {"sortBy": "return_on_equity", "sortOrder": "desc"},
  "range": [0, 20]
}
```

### 按市值排名的前 20 大加密货币

```json
{
  "filter": [],
  "columns": ["name", "description", "close", "change", "market_cap_basic"],
  "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
  "range": [0, 20]
}
```

注意需配合请求端点 `market: "crypto"`（而非 `global`）。

### 阿根廷国债与债券

```json
{
  "filter": [
    {"left": "country", "operation": "equal", "right": "Argentina"}
  ],
  "columns": ["name", "description", "close"],
  "range": [0, 30]
}
```

注意需配合请求端点 `market: "bonds"`。

---

## 7. 高级进阶用例

### 金叉探测器 (50 日均线自下而上穿过 200 日均线)

```json
{
  "filter": [
    {
      "left": "SMA50",
      "operation": "crosses_above",
      "right": "SMA200"
    }
  ],
  "columns": ["name", "close", "SMA50", "SMA200"]
}
```

### 死叉探测器 (50 日均线自上而下跌破 200 日均线)

```json
{
  "filter": [
    {
      "left": "SMA50",
      "operation": "crosses_below",
      "right": "SMA200"
    }
  ]
}
```

### 接近 52 周新高的股票 (距离高点在 5% 以内)

```json
{
  "filter": [
    {"left": "close", "operation": "above%", "right": "price_52_week_high"},
    {"left": "close", "operation": "egreater", "right": 1}
  ]
}
```

> 将操作符 `above%` 的 `right` 指定为列名时，表示对比 `close > price_52_week_high * 0.95`。

### 覆盖分析师众多且普遍看多的共识标的

```json
{
  "filter": [
    {"left": "number_of_analyst_opinions", "operation": "greater", "right": 15},
    {"left": "recommendation_buy", "operation": "greater", "right": "recommendation_sell"},
    {"left": "price_target_average", "operation": "above%", "right": "close"}
  ]
}
```

---

## 8. 常见错误排查

### 返回 `data: []` 且 `totalCount: 0`

- **原因：** 过滤条件过于严苛无匹配品种，或者右侧 `right` 引用的列名不存在。
- **排查解决：** 逐一移除过滤条件排查，定位引起无匹配的具体条件。

### HTTP 400 `"Invalid request"`

- **原因：** 过滤器 JSON 语法有误（例如漏掉了必需的 `"left"` 键）。
- **排查解决：** 在发送前通过 `python -c 'import json; json.loads(...)'` 校验 JSON 结构合法性。

### 指定的列 `xxx` 没有返回数据

- **原因：** 字段列名不存在或大小写不匹配。
- **排查解决：** 在 `SCANNER_COLUMNS.md` 中核对准确列名。接口字段名严格区分大小写 —— 例如 `Recommend.All` ≠ `recommend.all` ≠ `recommend_all`。

### 使用 `right: <列名>` 过滤无效

- **原因：** 部分操作符仅支持静态常量，不支持将动态列名作为右侧参数。支持动态列名对比的操作符包括：`crosses`, `crosses_above`, `crosses_below`, `above%`, `below%`。其它操作符（如 `equal`, `greater` 等）通常只支持字面量。

### 结果排序与预期不符

- **原因：** `sortOrder` 出现拼写错误（例如误写成了 `descending`）。
- **排查解决：** 排序方向只能精确使用 `asc` 或 `desc`。

---

## 附录：如何实现类似 UNION / 子查询的效果

Scanner 服务端**不支持** UNION 联合查询或子查询。若需合并多个不同维度的筛选结果，请发起多次请求并在客户端完成合并：

```python
acciones_us = scanner_scan(filter_=[{"left": "country", "operation": "equal", "right": "United States"}], ...)
acciones_ar = scanner_scan(filter_=[{"left": "country", "operation": "equal", "right": "Argentina"}], ...)
combined = acciones_us["data"] + acciones_ar["data"]
```
