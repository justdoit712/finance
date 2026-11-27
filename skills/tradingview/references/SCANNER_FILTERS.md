# TradingView Scanner 过滤语法与常用加密配方

接口地址：`POST https://scanner.tradingview.com/crypto/scan`

---

## 1. 过滤条件结构

每条规则支持标准 JSON 对象或三元简写 `[left, operation, right]`（多条规则之间默认逻辑与 `AND`）：

```json
{"left": "exchange", "operation": "equal", "right": "BINANCE"}
```

CLI `--filter` 参数可直接传入简写数组：

```json
[["RSI", "less", 30], ["Volatility.D", "greater", 5]]
```

---

## 2. 常用操作符

| 操作符 | `right` 类型 | 含义 |
|:---|:---|:---|
| `equal` / `nequal` | string / number | 等于 / 不等于 |
| `greater` / `egreater` | number | 大于 / 大于等于 |
| `less` / `eless` | number | 小于 / 小于等于 |
| `in_range` / `not_in_range` | `[min, max]` | 闭区间内 / 区间外 |
| `in_range_strings` / `not_in_range_strings` | `["a", "b"]` | 字符串集合包含 / 排除 |
| `match` / `nmatch` | regex string | 正则匹配 / 排除 |

---

## 3. 币安 U 本位永续实战筛选配方

### 币安 U 本位永续基础条件
```json
[
  {"left": "exchange", "operation": "equal", "right": "BINANCE"},
  {"left": "type", "operation": "equal", "right": "swap"},
  {"left": "name", "operation": "match", "right": "USDT\\.P$"}
]
```
*(提示：直接使用 `perps` 模式会自动注入以上三条过滤以及 `--min-vol` 24h 成交额门槛。)*

### 常用选币场景示例

```bash
# 1. 币安 U 本位永续 24h 成交额 Top 20
python skills/tradingview/scripts/fetch_tradingview.py perps --limit 20

# 2. 币安 U 本位永续涨幅榜（24h 成交额 >= 2000 万 USDT）
python skills/tradingview/scripts/fetch_tradingview.py perps --sort change:desc --min-vol 20000000 --limit 15

# 3. 筛出日线 RSI < 30 的超卖高成交额币安永续合约
python skills/tradingview/scripts/fetch_tradingview.py perps --filter '[["RSI","less",30]]' --sort RSI:asc --limit 15

# 4. 筛出强买评级且日内波动率 > 5% 的强势合约
python skills/tradingview/scripts/fetch_tradingview.py perps --filter '[["Recommend.All","egreater",0.5],["Volatility.D","greater",5]]' --sort change:desc --limit 15
```
