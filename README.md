# 03-a-share 分支 — 中国 A 股量化投研系统 (A-Share Quant System)

[![Branch: 03-a-share](https://img.shields.io/badge/branch-03--a--share-red.svg)](https://github.com/justdoit712/finance/tree/03-a-share)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

专用于中国 A 股市场（沪深京交易所及场内 ETF）的量化投研、回测、组合优化与 K 线可视化。

---

## 一、 标的资产池与数据映射 (A-Share Universe)

| 类别 | 标的名称 | 代表代码 (东方财富 / 交易所) | 核心用途与投研价值 |
|:---|:---|:---|:---|
| **宽基核心指数** | 上证指数 / 沪深 300 / 中证 500 / 创业板指 | `000001.SH`, `000300.SH`, `000905.SH`, `399006.SZ` | 大盘基准、市场 Beta 择时、风格强弱对比 |
| **核心蓝筹与龙头** | 贵州茅台 / 宁德时代 / 招商银行 / 中国平安 | `600519.SH`, `300750.SZ`, `600036.SH`, `601318.SH` | 消费/新能源/金融核心权重股与基本面因子研究 |
| **高股息红利资产** | 长江电力 / 中国神华 / 四大行 | `600900.SH`, `601088.SH`, `601398.SH` | 防御性红利策略、低波高股息组合配置 |
| **场内宽基与行业 ETF** | 沪深300ETF / 科创50ETF / 红利ETF / 半导体ETF | `510300.SH`, `588000.SH`, `510880.SH`, `512480.SH` | T+0/T+1 轮动、无个股黑天鹅风险的赛道配置 |
| **期权与波动率标的** | 上证 50ETF / 沪深 300ETF 期权标的 | `510050.SH`, `510300.SH` | 场内 ETF 期权定价、隐含波动率与对冲研究 |
| **国内宏观与流动性** | CPI / PMI / M2 / 社融 / LPR / 10年期国债收益率 | *(规划中：`cn-macro`)* | 信用周期、货币环境与权益资产定价锚 |

---

## 二、 核心技能与功能模块 (Core Skills)

全部技能遵循 [SKILL.md](https://skills.sh) 规范，代码轻量，无重型框架绑定。

```text
skills/
├── [行情可视化与选股扫描]
│   ├── kline-chart/        # 交互式 K 线看板与离线 HTML 导出（原生支持东方财富 A 股前复权 & 红涨绿跌）
│   ├── tradingview/        # 全市场选股扫描与预计算技术指标（支持中国沪深市场）
│   └── morningstar/        # 全球股票池与基础因子筛选（含上交所 XSHG / 深交所 XSHE）
└── [量化回测、组合优化与衍生品]
    ├── backtesting/        # 5 阶段量化回测框架（待适配 A 股 T+1、涨跌停、印花税规则）
    ├── portfolio/          # 多资产/行业组合优化（Markowitz、Black-Litterman、HRP/HERC/NCO）
    └── option-pricing/     # 期权定价与 Greeks 计算（适用于 50ETF / 300ETF 期权研究）
```

### 1. 行情可视化与选股扫描
- **[kline-chart](./skills/kline-chart/)**：基于本地打包 TradingView Lightweight Charts v4.2.3 的通用 K 线引擎，内置东方财富数据源（支持沪深北 A 股及场内 ETF、`qfq` 前复权、中文名称），支持实时刷新、SMA/布林带叠加、策略买卖点标记与红涨绿跌切换。
- **[tradingview](./skills/tradingview/)**：支持中国市场（`china`）的 Scanner API 与预计算技术指标、估值、财务数据扫描。
- **[morningstar](./skills/morningstar/)**：内置上交所（`XSHG`）与深交所（`XSHE`）股票池，可用于跨市场基础数据对比与筛选。

### 2. 量化回测、组合与定价引擎
- **[backtesting](./skills/backtesting/)**：学术级 5 阶段回测框架（30+ 风险收益比率、10 类指标、事件驱动引擎、Johnson SU + Copula 前向模拟、Walk-Forward 交叉验证）。
- **[portfolio](./skills/portfolio/)**：投资组合优化工具，支持 Markowitz、Black-Litterman 与层次化风险平价（HRP / HERC / NCO），适合行业 ETF 轮动或核心资产仓位分配。
- **[option-pricing](./skills/option-pricing/)**：多模型期权定价与隐含波动率求解引擎，可用于分析 50ETF / 300ETF 场内期权。

---

## 三、 后续建设规划 (Roadmap)

1. **配置本地化与 A 股数据技能补齐**
   - 调整 `kline-chart/assets/defaults.json` 为 A 股默认配置（东方财富源 + 红涨绿跌）。
   - 新增 `akshare` / `eastmoney-data`（免费行情、财报、资金流向、龙虎榜、融资融券）、`cn-macro`（国内宏观）与 `cninfo`（巨潮资讯公告）。
2. **A 股交易规则回测适配**
   - 在 `backtesting` 中补充 **T+1**、**涨跌停板限制**（±10% / ±20% / ±30% / ±5%）、**交易成本**（佣金 + 卖出印花税 0.05% + 过户费）、**整手买入（100 股整数倍）** 与 **停牌/退市处理**。
   - 从 `02-crypto` 引入 `ticker-strategy` 并改造为 A 股单标的策略工厂。

---

## 四、 快速上手 (Quick Start)

### 1. 启动 A 股交互式 K 线看板（东方财富实时源）
```bash
# 查看贵州茅台日线（前复权 + 红涨绿跌）
python skills/kline-chart/scripts/kline_chart.py serve --symbol eastmoney:600519 --interval 1d --color-scheme red_up

# 查看宁德时代 15 分钟线（每 5 秒无闪烁刷新）
python skills/kline-chart/scripts/kline_chart.py serve --symbol eastmoney:300750 --interval 15m --color-scheme red_up --refresh 5

# 导出单文件离线交互 K 线 HTML
python skills/kline-chart/scripts/kline_chart.py export --symbol eastmoney:510300 --interval 1d --color-scheme red_up -o hs300etf.html
```

### 2. 运行多资产组合 HRP 优化
```bash
python skills/portfolio/scripts/cli.py hrp
```

### 3. 运行回测引擎验证
```bash
python skills/backtesting/scripts/backtesting.py run --prices skills/backtesting/assets/sp500_returns.csv
```
