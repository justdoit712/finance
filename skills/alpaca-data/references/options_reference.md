# 期权参考文档 (Options Reference) — Alpaca Data

## 期权合约代号命名规范

Alpaca 的期权合约代码遵循标准 OCC（Options Clearing Corporation）格式：

```
{标的代号}{到期日}{类型}{行权价}{100}
```

### 示例解析

```
AAPL240119C00100000
├── AAPL    = 标的资产代号 (Underlying symbol，占6字符)
├── 240119  = 到期日：2024年1月19日 (格式 YYMMDD)
├── C       = 期权类型：C (看涨 Call) 或 P (看跌 Put)
├── 00100   = 行权价乘以 1000 (代表 $100.00)
└── 000     = 填充零
```

---

## 过滤参数说明

### 到期日区间 (expiration_date)

```python
request = OptionContractsRequest(
    underlying_symbols=["AAPL"],
    expiration_date_gte="2024-01-01",  # 起始到期日（含）
    expiration_date_lte="2024-12-31",  # 截止到期日（含）
)
```

### 行权价区间 (strike_price)

```python
request = OptionContractsRequest(
    underlying_symbols=["AAPL"],
    strike_price_gte=100,   # 最低行权价 100
    strike_price_lte=200,   # 最高行权价 200
)
```

### 期权类型 (type)

```python
request = OptionContractsRequest(
    underlying_symbols=["AAPL"],
    type="call"  # "call" (看涨) 或 "put" (看跌)
)
```

### 期权行权风格 (style)

```python
request = OptionContractsRequest(
    underlying_symbols=["AAPL"],
    style="american"  # "american" (美式) 或 "european" (欧式)
)
```

---

## 所需账户交易等级 (Trading Levels)

| 等级 | 允许执行的期权交易权限 |
|:---:|:---|
| **Level 0** | 禁止期权交易 |
| **Level 1** | 备兑看涨期权（Covered Calls）、现金担保看跌期权（Cash-Secured Puts） |
| **Level 2** | 买入/卖出看涨期权与看跌期权（单腿多头） |
| **Level 3** | 垂直价差、水平价差与多腿期权组合策略（Spreads） |

---

## 获取完整期权链 (Option Chain)

```python
from datetime import datetime, timedelta
from alpaca.data.requests import OptionContractsRequest

# 设置到期日范围（如未来 1 年内）
min_exp = datetime.now()
max_exp = datetime.now() + timedelta(days=365)

request = OptionContractsRequest(
    underlying_symbols=["AAPL"],
    expiration_date_gte=min_exp.strftime("%Y-%m-%d"),
    expiration_date_lte=max_exp.strftime("%Y-%m-%d"),
    strike_price_gte=50,
    strike_price_lte=300,
    limit=1000  # 每次请求最大 1000
)

contracts = client.get_option_contracts(request)
```

---

## 解析期权合约代号辅助函数

```python
def parse_option_symbol(symbol: str) -> dict:
    """将 OCC 格式代码 AAPL240119C00100000 解析为字典结构"""
    underlying = symbol[:6].strip()
    date_str = symbol[6:12]
    exp_type = symbol[12]
    strike_raw = int(symbol[13:21])
    strike_price = strike_raw / 1000.0

    return {
        "underlying": underlying,
        "expiration": f"20{date_str[0:2]}-{date_str[2:4]}-{date_str[4:6]}",
        "type": "call" if exp_type.upper() == "C" else "put",
        "strike": strike_price
    }
```
