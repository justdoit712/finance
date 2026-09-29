---
name: alpaca-data
description: "Alpaca 行情数据 API：股票、加密货币、期权。提供 5000+ 标的历史与实时市场数据。"
license: MIT
---

# Alpaca Data — 行情数据 API

提供股票、加密货币及期权历史与实时市场数据的专业行情 API。

**Base URL:** `https://data.alpaca.markets`  
**官方 SDK:** `pip install alpaca-py`  
**官方文档:** [docs.alpaca.markets](https://docs.alpaca.markets/us/docs/about-market-data-api)

---

## 身份认证

### 获取 API Keys

1. 前往 [app.alpaca.markets](https://app.alpaca.markets)
2. 注册并登录账户（模拟交易 Paper Trading 完全免费）
3. 进入 "API Keys" → 点击 "Generate New Keys"
4. 妥善保存 **API Key** 与 **Secret Key**

### 代码配置

```python
import os
from alpaca.data.historical import StockHistoricalDataClient

# API Keys（获取股票与期权数据时必需）
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# 加密货币数据客户端无需 API Key 即可获取公开行情
from alpaca.data.historical import CryptoHistoricalDataClient
crypto_client = CryptoHistoricalDataClient()
```

**⚠️ 绝对不要将 API Keys 硬编码在公开分享的代码中。**

---

## 速率限制 (Rate Limits)

| 套餐方案 | 请求限制 (Requests/Min) | 数据深度与覆盖 |
|:---|:---:|:---|
| **Free (IEX)** | 200 | ~5 年历史数据，来自 IEX 单一交易所 |
| **Paid (SIP)** | 更高 | 全美综合交易所 (Consolidated)，~7 年历史 |

### 最佳实践建议

- **本地缓存数据**：历史已完成 K 线永不变化，应优先缓存在本地磁盘；
- **批量请求 (Batch)**：单次调用请求多个标的代号；
- **设置 `limit=10000`**：每次请求拉取最大允许记录数；
- **通过 `next_page_token` 分页**：处理大规模历史数据遍历。

---

## 行情数据源 (Data Feeds)

| 数据源 | 说明 | 费用 |
|:---|:---|:---:|
| `iex` | Investors Exchange（约占全美成交量 2.5%） | 免费 |
| `sip` | 全美综合报价流（包含所有美股交易所） | 付费 |
| `boats` | Blue Ocean ATS（支持夜盘盘后交易时段） | 付费 |
| `otc` | 场外交易市场 (Over-the-counter) | 付费 |

> **免费套餐用户默认仅可访问 `iex` 数据源。**

---

## 股票历史数据 (Historical Stock Data)

### K 线数据 (Bars / OHLCV)

```python
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime

request = StockBarsRequest(
    symbol_or_symbols=["AAPL", "GOOGL"],
    timeframe=TimeFrame.Day,
    start=datetime(2023, 1, 1),
    end=datetime(2024, 12, 31),
    feed="iex"  # 免费套餐指定 iex
)

bars = client.get_stock_bars(request)
df = bars.df  # 转换为 Pandas DataFrame
```

**支持的时间粒度 (TimeFrames)：**
- `TimeFrame.Minute` / `TimeFrame(5, TimeFrame.Minute)`（1分钟 / 5分钟）
- `TimeFrame.Hour`（小时线）
- `TimeFrame.Day`（日线）
- `TimeFrame.Week`（周线）
- `TimeFrame.Month`（月线）

### 盘口报价 (Quotes - Bid/Ask)

```python
from alpaca.data.requests import StockQuotesRequest

request = StockQuotesRequest(
    symbol_or_symbols=["AAPL"],
    start=datetime(2024, 1, 1),
    end=datetime(2024, 1, 31),
    feed="iex"
)

quotes = client.get_stock_quotes(request)
```

### 逐笔成交 (Trades)

```python
from alpaca.data.requests import StockTradesRequest

request = StockTradesRequest(
    symbol_or_symbols=["AAPL"],
    start=datetime(2024, 1, 1),
    feed="iex"
)

trades = client.get_stock_trades(request)
```

### 最新行情快照 (Latest Data)

```python
# 获取最新 K 线
bars = client.get_stock_latest_bar(["AAPL", "GOOGL"])

# 获取最新盘口买卖价
quotes = client.get_stock_latest_quote(["AAPL"])

# 获取最新逐笔成交
trades = client.get_stock_latest_trade(["AAPL"])
```

### 综合市场快照 (Snapshots)

```python
from alpaca.data.requests import SnapshotRequest

request = SnapshotRequest(
    symbol_or_symbols=["AAPL", "GOOGL"]
)
snapshots = client.get_snapshot(request)
```

---

## 加密货币历史数据 (Historical Crypto Data)

> **💡 加密货币行情客户端无需配置 API Key 即可直接调用。**

```python
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime

client = CryptoHistoricalDataClient()

request = CryptoBarsRequest(
    symbol_or_symbols=["BTC/USD", "ETH/USD"],
    timeframe=TimeFrame.Day,
    start=datetime(2023, 1, 1),
    end=datetime(2024, 12, 31)
)

bars = client.get_crypto_bars(request)
df = bars.df
```

### 加密货币实时盘口报价

```python
from alpaca.data.requests import CryptoLatestQuoteRequest

request = CryptoLatestQuoteRequest(symbol_or_symbols=["BTC/USD"])
quotes = client.get_crypto_latest_quote(request)
```

---

## 期权历史数据 (Historical Options Data)

### 期权链合约检索 (Option Chains)

```python
from alpaca.data.requests import OptionContractsRequest

request = OptionContractsRequest(
    underlying_symbols=["AAPL"],
    expiration_date_gte="2024-01-01",  # 起始到期日
    expiration_date_lte="2024-12-31",  # 截止到期日
    strike_price_gte=100,              # 最低行权价
    strike_price_lte=200               # 最高行权价
)

contracts = client.get_option_contracts(request)
```

### 期权 K 线 / 成交 / 盘口

```python
from alpaca.data.requests import OptionBarsRequest

# 先通过合约检索获取 contract_id
contract_id = "6e58f870-fe73-4583-81e4-b9a37892c36f"

request = OptionBarsRequest(
    symbol_or_contract_ids=[contract_id],
    start=datetime(2024, 1, 1),
    end=datetime(2024, 1, 31)
)

bars = client.get_option_bars(request)
```

详细期权格式与参数规范请参阅：[./references/options_reference.md](./references/options_reference.md)。

---

## 新闻资讯 (News API)

```python
from alpaca.data.requests import StockNewsRequest

request = StockNewsRequest(
    symbol_or_symbols=["AAPL", "GOOGL"],
    start=datetime(2024, 1, 1),
    end=datetime(2024, 1, 31)
)

news = client.get_stock_news(request)
```

---

## 活跃异动扫描器 (Screener)

```python
from alpaca.data.requests import MostActivesRequest

request = MostActivesRequest(
    by="volume",      # volume (成交量), share (成交股数), number (成交笔数)
    top=10,
    date="2024-01-15"
)

movers = client.get_most_actives(request)
```

---

## WebSocket 实时流 (WebSocket Streaming)

```python
from alpaca.data.stream import StockDataStream

ws = StockDataStream(API_KEY, SECRET_KEY)

async def handle_bar(bar):
    print(bar)

ws.subscribe_bars(handle_bar, "AAPL", "GOOGL")
ws.run()
```

---

## 常用下载脚本

可直接使用 [./scripts/](./scripts/) 目录下的现成 CLI 脚本：

```bash
# 下载美股 K 线历史
python ./scripts/download_stock_bars.py --symbols AAPL,GOOGL --days 365 --output data/

# 下载加密货币历史 K 线
python ./scripts/download_crypto_bars.py --symbols BTC,ETH --days 90 --output data/

# 下载期权合约列表
python ./scripts/download_options.py --symbol AAPL --output data/
```

---

## 常见错误与排查速查

| 错误代码 / 提示 | 常见原因 | 解决方案 |
|:---|:---|:---|
| `403 Forbidden` | API Keys 无效或缺乏对应品种权限 | 检查环境变量与后台 API Key 权限配置 |
| `429 Too Many Requests` | 超过请求频率上限 | 降低并发频率、增加休眠间隔、使用本地缓存 |
| `Empty response` | 标的代号在该时间区间内无成交数据 | 检查交易对代号拼写（如加密货币需用 `BTC/USD`） |
| `"options_enabled"` | 标的未开放期权交易 | 确认标的是否支持期权衍生品 |
