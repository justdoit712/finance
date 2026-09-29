---
name: alpaca-trading
description: "Alpaca 交易 API：订单、持仓、账户管理。支持美股、加密货币与期权的模拟（Paper）及实盘交易。"
license: MIT
---

# Alpaca Trading — 实盘与模拟交易 API

提供股票、加密货币与期权的自动化交易接口。支持免费模拟交易（Paper Trading）与实盘（Live Trading）无缝切换。

**Base URLs:**
- 模拟环境 (Paper): `https://paper-api.alpaca.markets`
- 实盘环境 (Live): `https://api.alpaca.markets`
- 官方 SDK: `pip install alpaca-py`

**官方文档:** [docs.alpaca.markets](https://docs.alpaca.markets/us/docs/trading-api)

---

## 身份认证与客户端初始化

### 获取 API Keys

1. 前往 [app.alpaca.markets](https://app.alpaca.markets) 注册账户；
2. 免费开通 Paper Trading 模拟账户；
3. 进入 "API Keys" 页面生成并复制 API Key 和 Secret Key。

### 代码配置

```python
import os
from alpaca.trading.client import TradingClient

# 模拟交易环境配置 (Paper Trading)
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")

# paper=True 自动连接模拟环境，paper=False 连接实盘环境
client = TradingClient(API_KEY, SECRET_KEY, paper=True)
```

**⚠️ 绝对不要在代码中硬编码秘钥，必须使用环境变量管理。**

---

## 请求频率限制 (Rate Limits)

| 业务接口 | 频率上限 |
|:---|:---:|
| 订单接口 (Orders) | 200 次请求/分钟 |
| 账户与持仓 (Account/Positions) | 200 次请求/分钟 |
| 资金异动记录 (Activities) | 200 次请求/分钟 |

### 交易系统设计建议

- **使用 WebSocket 流接收订单状态**：比轮询 (Polling) 效率更高且不消耗 HTTP 限额；
- **本地缓存持仓信息**：避免在策略循环中高频重复调用持仓接口；
- **实现指数退避重试**：防范偶发 429 报错。

---

## 账户管理 (Account)

### 获取账户概况与购买力

```python
account = client.get_account()
print(f"购买力 (Buying Power): ${account.buying_power}")
print(f"现金余额 (Cash): ${account.cash}")
print(f"组合总资产 (Portfolio Value): ${account.portfolio_value}")
print(f"账户状态 (Status): {account.status}")
```

### 更新账户偏好设置

```python
from alpaca.trading.requests import AccountConfigurationsRequest

config_request = AccountConfigurationsRequest(
    trade_confirmation_email=True,
    suspend_trade=False
)
client.update_account_configuration(config_request)
```

---

## 订单管理 (Orders)

### 常用订单类型

| 类型 | 说明 |
|:---|:---|
| `market` | 市价单：以当前最优可成交价立即执行 |
| `limit` | 限价单：买入不高于限价，卖出不低于限价 |
| `stop` | 止损市价单：当价格达到触发价时以市价单委托 |
| `stop_limit` | 止损限价单：达到触发价后以指定限价挂单 |
| `trailing_stop` | 追踪止损单：随行情高低点动态跟踪止损价 |

### 有效期类型 (Time in Force)

| 标识 | 说明 |
|:---|:---|
| `day` | 当日有效（收盘未成交自动撤单） |
| `gtc` | 撤销前持续有效 (Good Till Cancelled) |
| `ioc` | 立即成交并取消剩余 (Immediate Or Cancel) |
| `fok` | 全部成交否则全部取消 (Fill Or Kill) |

### 提交市价单

```python
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

order_request = MarketOrderRequest(
    symbol="BTC/USD",             # 支持股票或加密交易对
    qty=0.05,                    # 加密货币支持碎股/分数买入
    side=OrderSide.BUY,
    time_in_force=TimeInForce.GTC
)

order = client.submit_order(order_request)
print(f"订单提交成功，ID: {order.id}，状态: {order.status}")
```

### 提交限价单

```python
from alpaca.trading.requests import LimitOrderRequest

order_request = LimitOrderRequest(
    symbol="BTC/USD",
    qty=0.1,
    side=OrderSide.BUY,
    limit_price=60000.00,        # 最高愿意支付的价格
    time_in_force=TimeInForce.GTC
)

order = client.submit_order(order_request)
```

### 撤销订单

```python
# 按 ID 撤销单笔订单
client.cancel_order(order_id)

# 一键撤销当前所有挂单
client.cancel_orders()
```

---

## 持仓管理 (Positions)

### 获取全部活跃持仓

```python
positions = client.get_all_positions()

for pos in positions:
    print(f"标的: {pos.symbol}, 持仓量: {pos.qty}")
    print(f"  均价: ${pos.avg_entry_price}, 市值: ${pos.market_value}")
    print(f"  未实现盈亏: ${pos.unrealized_pl} ({float(pos.unrealized_plpc)*100:.2f}%)")
```

### 平仓操作

```python
# 全部平掉指定标的
client.close_position("BTC/USD")

# 部分平仓（例如平掉 0.02 个 BTC）
client.close_position("BTC/USD", qty=0.02)

# 一键清仓所有资产（紧急避险）
client.close_all_positions()
```

---

## 加密货币实盘交易专章 (Crypto Trading)

### 查询可交易代币清单

```python
from alpaca.trading.enums import AssetClass

crypto_assets = client.get_all_assets(asset_class=AssetClass.CRYPTO)
tradables = [a.symbol for a in crypto_assets if a.tradable]
print(f"当前支持交易的加密货币总数: {len(tradables)}")
print(f"前 10 个可交易币种: {tradables[:10]}")
```

### 加密货币下单范式（支持 7×24 小时）

```python
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

order_request = MarketOrderRequest(
    symbol="ETH/USD",
    qty=1.5,
    side=OrderSide.BUY,
    time_in_force=TimeInForce.GTC
)
client.submit_order(order_request)
```

---

## WebSocket 实时交易流推送

```python
from alpaca.trading.stream import TradingStream

stream = TradingStream(API_KEY, SECRET_KEY, paper=True)

async def handle_trade_update(data):
    # 当订单被部分撮合、完全成交或撤销时实时推送
    print(f"收到成交动态: {data.event} - 标的: {data.order['symbol']} - 数量: {data.order['filled_qty']}")

stream.subscribe_trade_updates(handle_trade_update)
stream.run()
```

---

## 模拟交易 (Paper) 与实盘 (Live) 对比

| 维度 | 模拟交易 (Paper) | 实盘交易 (Live) |
|:---|:---:|:---:|
| **接口地址** | `paper-api.alpaca.markets` | `api.alpaca.markets` |
| **真实资金风险** | ❌ 无任何资金风险 | ⚠️ 真实资金结算 |
| **成交模式** | 根据真实盘口模拟撮合 | 真实交易所撮合成交 |
| **行情数据** | ✅ 真实实时市场数据 | ✅ 真实实时市场数据 |
| **推荐流程** | **必须先在模拟盘充分回测验证** | 策略稳定后再切入实盘 |
