# 01 分支 — 黄金与白银专属量化投研系统 (Precious Metals Quant System)

[![Branch: 01](https://img.shields.io/badge/branch-01-gold.svg)](https://github.com/justdoit712/finance/tree/01)
[![Base: main](https://img.shields.io/badge/root_base-main-blue.svg)](https://github.com/justdoit712/finance/tree/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

本项目 `01` 分支专精于**黄金与白银（Gold & Silver / 贵金属）**的量化投研体系。在主干 `main`（保留全量 26 个通用技能）的基础上，精炼保留了 6 个与大宗商品、宏观因子及量化投研密切相关的顶级计算与数据引擎，移除了无关的个股与微观财报模块，打造高纯度、工程化的贵金属量化投研系统。

---

## 一、 标的资产池与数据映射 (Precious Metals Universe)

| 类别 | 标的名称 | 代码 (Yahoo / TradingView / FRED) | 投研价值与核心用途 |
|:---|:---|:---|:---|
| **现货/外汇** | 伦敦金现货 / 伦敦银现货 | `XAUUSD=X`, `XAGUSD=X` | 国际贵金属基准现货连续价格 |
| **主流期货** | COMEX 黄金主力 / 白银主力 | `GC=F`, `SI=F` | 期货期限结构、基差、升贴水与成交量 |
| **高流动性 ETF** | 黄金 ETF / 白银 ETF | `GLD`, `IAU`, `SLV` | 现货托管份额、机构资金流向与期权对冲 |
| **金银矿业股** | 金矿 ETF / 银矿 ETF / 龙头矿企 | `GDX`, `GDXJ`, `SIL`, `NEM` | 贵金属权益资产，提供 1.5~3 倍经营杠杆 Beta |
| **核心定价因子** | 10Y 美债实际收益率 (TIPS) | FRED: `DFII10` | **黄金最大核心定价因子**（负相关显著） |
| **货币信用因子** | 贸易加权美元指数 / DXY | FRED: `DTWEXBGS`, `DX-Y.NYB` | 信用货币信用对冲与计价反向驱动 |
| **通胀与流动性** | 10Y 盈亏平衡通胀预期 / M2 | FRED: `T10YIE`, `WM2NS` | 货币购买力贬值与抗通胀溢价 |
| **官方基准价** | 伦敦金早盘/晚盘定盘价历史 | FRED: `GOLDAMGBD228NLBM` | 长周期基准定盘价序列 |

---

## 二、 保留的 6 大核心量化技能 (Retained Core Skills)

全部技能遵循 [SKILL.md](https://skills.sh) 规范，代码高度轻量化，无重型第三方金融包依赖。

```
skills/
├── [量化投研与计算引擎]
│   ├── backtesting/        # 学术级全流程量化回测与压力测试引擎
│   ├── portfolio/          # 投资组合构建与层次化风险平价 (HRP/HERC/NCO)
│   └── option-pricing/     # 纯 NumPy 极速期权定价与波动率偏度 (41.9万次/秒)
└── [行情与宏观数据源]
    ├── yahoo-finance/      # 黄金白银全品种行情拉取 (现货、期货、ETF、矿业股)
    ├── fred-macro/         # 美联储宏观经济时序 (实际利率、美元指数、通胀)
    └── tradingview/        # 大宗商品全品种技术指标预计算扫描
```

### 1. 量化计算与回测引擎 (Tools)
- **[backtesting](./skills/backtesting/)**：完整实现 5 阶段回测方法论（数据→研究→度量→调参→验证）。内置 30+ 种风险收益比率（夏普、索提诺、卡玛、凯利、最大回撤、Ulcer、Rachev、CVaR 等）、10 大类技术指标、Johnson SU + t-Copula 前瞻模拟、Walk-forward 走步验证与情景压力测试。
- **[portfolio](./skills/portfolio/)**：用于计算黄金白银在全天候配置（如桥水全天候）或多元资产组合中的最优仓位比重。支持马科维茨有效前沿、Black-Litterman 贝叶斯后验、层次化风险平价（HRP / HERC）及带约束的嵌套聚类优化（NCO）。
- **[option-pricing](./skills/option-pricing/)**：用于 GLD / SLV 期权、黄金期货期权的定价与波动率偏度（Skew）分析。支持 Black-Scholes、CRR 二叉树、三叉树、蒙特卡洛（对偶变量）、美式 Longstaff-Schwartz、Heston 随机波动率模型与 Bates 跳跃扩散模型。

### 2. 核心数据源 (Data)
- **[yahoo-finance](./skills/yahoo-finance/)**：免 API Key、免认证，稳定抓取黄金白银现货（`XAUUSD=X`, `XAGUSD=X`）、COMEX 期货（`GC=F`, `SI=F`）、ETF（`GLD`, `SLV`）和矿业股（`GDX`）的日线与日内 OHLCV。
- **[fred-macro](./skills/fred-macro/)**：美联储官方宏观数据库，覆盖 84 万+ 时序，提供黄金定价关键因子（10Y TIPS 实际利率、美元指数、通胀预期、M2）。
- **[tradingview](./skills/tradingview/)**：涵盖大宗商品全品种的 SQL-like 扫描与预计算技术指标（RSI、MACD、布林带、枢轴点）。

---

## 三、 核心投研方法论与策略规划

在 `01` 分支中，主要针对贵金属的两大特性（商品属性 + 货币金融属性）构建以下量化策略体系：

### 1. 金银比均值回归与配对交易 (Gold-Silver Ratio, GSR)
- **逻辑**：金银比反映了黄金（货币避险）与白银（工业弹性）的相对强弱。历史中枢在 50~90 之间波动。
- **策略**：当 GSR 触及历史高位分位数（白银被极度低估）时做多白银/做空黄金；触及历史低位分位数时反向操作。结合协整检验、滚动 Z-Score 与动态布林带出入场。

### 2. 宏观实际利率驱动动量策略 (Macro-Real-Yield Trend)
- **逻辑**：美债 10 年期实际利率（10Y TIPS: `DFII10`）是黄金中长期走势的最强驱动（负相关性极高）。
- **策略**：构建实际利率拐点信号与黄金动量突破过滤机制，在实际利率下行周期顺势做多，震荡周期自适应防守。

### 3. 矿业股 vs 现货相对价值交易 (GDX / GLD Ratio)
- **逻辑**：金矿企业利润受金价边际放大，GDX 对黄金具备 1.5~3 倍经营杠杆。
- **策略**：捕捉矿企利润周期与现货金价之间的传导时滞与溢价折价收敛机会。

### 4. 贵金属全天候防御对冲配置 (Risk Parity Allocation)
- 利用 `portfolio` 模块，通过层次化风险平价（HRP）评估黄金和白银在组合中平抑系统性风险的最优权重。

---

## 四、 快速上手 (Quick Start)

### 1. 抓取黄金白银主力行情
```bash
# 获取 COMEX 黄金主力期货、白银主力期货、黄金现货最新行情
python skills/yahoo-finance/scripts/fetch_quote.py GC=F SI=F XAUUSD=X XAGUSD=X GLD SLV
```

### 2. 抓取美债 10Y TIPS 实际利率宏观时序
```bash
# 获取 10年期美债实际收益率 (DFII10) 与美元指数 (DTWEXBGS)
python skills/fred-macro/scripts/fetch_series.py DFII10 --limit 100
python skills/fred-macro/scripts/fetch_series.py DTWEXBGS --limit 100
```

### 3. 运行策略回测验证
```bash
# 运行策略回测验证套件
python skills/backtesting/scripts/backtesting.py validate
```

### 4. 运行期权定价与基准测试
```bash
# 期权定价与数学验证
python skills/option-pricing/scripts/option_pricing.py validate
```

---

## 五、 分支管理说明

- **`main` 分支**：项目主干，完整保留全部 26 个量化技能（含美股、期权、全球 39 国股票市场、基本面财报等全量代码）。
- **`01` 分支**：当前分支，专精于黄金白银贵金属量化投研。
