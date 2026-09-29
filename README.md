# 02-crypto 分支 — 加密货币与数字资产量化系统 (Crypto Quant System)

[![Branch: 02-crypto](https://img.shields.io/badge/branch-02--crypto-orange.svg)](https://github.com/justdoit712/finance/tree/02-crypto)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

专用于加密货币与数字资产（Crypto / Web3）的量化投研与实盘/模拟交易。

---

## 一、 标的资产池与数据映射 (Crypto Universe)

| 类别 | 标的名称 | 代表代码 (TradingView / Yahoo / Alpaca) | 核心用途与投研价值 |
|:---|:---|:---|:---|
| **原生主流资产** | 比特币 / 以太坊 / 索拉纳 | `BTC-USD`, `ETH-USD`, `SOL-USD` | 全球数字资产基准、Beta 核心资产、价值存储与公链生态 |
| **高弹性山寨公链** | Avalanche / Chainlink 等主流代币 | `AVAX-USD`, `LINK-USD` | 高波动 Alpha 标的、跨品种轮动与动量突破 |
| **实盘/模拟交易对** | Alpaca Crypto 交易对 | `BTC/USD`, `ETH/USD`, `SOL/USD` | 免佣金实盘下单、市价/限价/止盈止损与仓位管理 |
| **交易所全品种扫描** | Binance / Bybit / OKX 全合约 | `BINANCE:BTCUSDT`, `BINANCE:ETHUSDT` | 全网秒级行情、资金费率、预计算指标与选币扫描 |
| **现货信托 ETF** | 现货比特币 ETF / 现货以太坊 ETF | `IBIT`, `FBTC`, `ETHA` | 传统机构资金大额净流入/净流出风向标 |
| **加密概念权益股** | Coinbase / 微策略 / 矿企 | `COIN`, `MSTR`, `MARA`, `RIOT` | 加密资产经营杠杆与美股合规敞口映射 |
| **全球宏观流动性** | 美联储资产负债表规模 / M2 | FRED: `WALCL`, `WM2NS` | **加密资产终极定价驱动力**（全球流动性水龙头） |
| **政策与利率环境** | 联邦基准利率 / 美元指数 | FRED: `FEDFUNDS`, `DTWEXBGS` | 降息周期、风险资产溢价与美元信用定价 |

---

## 二、 保留的 8 大核心技能矩阵 (Retained Core Skills)

全部技能遵循 [SKILL.md](https://skills.sh) 规范，代码轻量，无重型框架绑定。

```
skills/
├── [加密实盘交易与专属数据]
│   ├── alpaca-trading/     # 加密货币实盘与模拟（Paper Trading）交易接口
│   ├── alpaca-data/        # 加密资产实时 K 线 (Bars)、成交 (Trades) 与盘口快照
│   └── tradingview/        # 全网交易所 (Binance/OKX等) 选币扫描与预计算技术指标
├── [量化投研与计算引擎]
│   ├── backtesting/        # 7×24h 策略全流程回测（30+ 风险指标、走步交叉验证）
│   ├── portfolio/          # 多币种资产配置优化与 HRP 层次化风险平价
│   └── option-pricing/     # 加密期权定价、隐含波动率（IV）曲面与偏度 (Skew) 分析
└── [宏观流动性与长周期历史]
    ├── fred-macro/         # 美联储全球流动性时序 (资产负债表 WALCL, 货币量 M2)
    └── yahoo-finance/      # 主流币历史时序、加密 ETF (IBIT) 及概念股 (COIN/MSTR)
```

### 1. 加密货币实盘交易与行情源 (Brokers & Data)
- **[alpaca-trading](./skills/alpaca-trading/)**：通过官方 `alpaca-py` SDK，支持 BTC、ETH 等多种加密资产的自动化下单交易。提供模拟交易环境（Paper Trading）与实盘账户无缝切换。
- **[alpaca-data](./skills/alpaca-data/)**：专注加密货币行情流，通过 `download_crypto_bars.py` 获取加密货币分钟线、小时线与日线历史 K 线。
- **[tradingview](./skills/tradingview/)**：全市场加密币种扫描器。直连主流交易所数据，内置 300+ 预计算字段（RSI、MACD、Stoch、布林带、成交量突破、波动率），支持多空全天候扫描。

### 2. 底层量化策略与计算引擎 (Tools)
- **[backtesting](./skills/backtesting/)**：学术级 5 阶段回测框架，专为高波动资产优化。内置 30+ 种风险收益比率（夏普、索提诺、卡玛、最大回撤、CVaR 等）、10 大类技术指标、走步向前（Walk-forward）交叉验证与 t-Copula 极端前瞻模拟。
- **[portfolio](./skills/portfolio/)**：用于求解多币种投资组合的最优配置权重。提供层次化风险平价（HRP）与嵌套聚类优化（NCO），有效解决加密资产之间的高相关性与协方差病态问题。
- **[option-pricing](./skills/option-pricing/)**：用于 BTC/ETH 加密期权（对标 Deribit / OKX 期权）定价与对冲分析。支持 Black-Scholes、二叉树、蒙特卡洛及 Heston 随机波动率模型，计算 Greeks 与 IV 偏度。

### 3. 宏观流动性与跨市场数据 (Macro & Cross-Asset)
- **[fred-macro](./skills/fred-macro/)**：获取美联储全球流动性数据（资产负债表 `WALCL`、货币供应量 `WM2NS`、基准利率 `FEDFUNDS`），构建加密宏观周期顶底指标。
- **[yahoo-finance](./skills/yahoo-finance/)**：免 Key、零成本拉取 `BTC-USD`、`ETH-USD`、现货 ETF（`IBIT`）及加密概念股（`COIN`、`MSTR`）。

---

## 三、 核心量化策略体系规划

针对加密货币 7×24 小时、高波动、多品种的特点，规划以下策略体系：

### 1. 多币种动量与趋势跟踪 (Multi-Crypto Momentum Trend)
- **逻辑**：加密货币具有极强的顺势动量与肥尾效应，牛市行情持续度极高。
- **策略**：自适应均线通道 + ATR 动态止损，结合成交量放大过滤虚假突破。

### 2. 跨品种与山寨轮动策略 (Altcoin Rotation & Pairs Trading)
- **逻辑**：BTC 突破主升浪后，市场资金通常向 ETH 及高 Beta 优质山寨币（Layer1 / DeFi / AI 赛道）外溢轮动。
- **策略**：计算 ETH/BTC 汇率对与各公链相对强弱指标（RSI / Z-Score），实现周期性再平衡轮动。

### 3. 多币种投资组合风险平价 (HRP Crypto Portfolio)
- **逻辑**：传统均值-方差优化在加密极端暴跌中易失效。
- **策略**：利用 `portfolio` 模块的层次化风险平价（HRP），在控制整体组合回撤的前提下最大化风险调整后收益。

### 4. 宏观流动性周期大模型 (Macro Liquidity Overlay)
- **逻辑**：BTC 价格与美联储流动性（M2 / 资产负债表扩张）具有 1~3 个月的滞后联动效应。
- **策略**：基于 FRED 宏观流动性拐点信号，作为底层现货/杠杆仓位的主观动态调节权重。

---

## 四、 快速上手 (Quick Start)

### 1. 查看与检查 Alpaca 加密交易账户
```bash
# 检查 Alpaca 账户资金与购买力（Paper 模拟环境）
python skills/alpaca-trading/scripts/check_account.py
```

### 2. 拉取主流加密货币历史 K 线
```bash
# 获取比特币历史 K 线
python skills/alpaca-data/scripts/download_crypto_bars.py --symbols BTC/USD --timeframe 1Day
```

### 3. 使用 Yahoo Finance 获取 BTC 与相关概念股
```bash
# 获取比特币现货、IBIT ETF 与微策略最新价格
python skills/yahoo-finance/scripts/fetch_quote.py --tickers BTC-USD,ETH-USD,IBIT,MSTR,COIN
```

### 4. 运行多资产组合 HRP 风险平价优化
```bash
# 运行层次化风险平价 (HRP)
python skills/portfolio/scripts/cli.py hrp
```


