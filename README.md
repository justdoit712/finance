# 03-a-share 分支 — 中国 A 股量化投研系统 (A-Share Quant System)

[![Branch: 03-a-share](https://img.shields.io/badge/branch-03--a--share-red.svg)](https://github.com/justdoit712/finance/tree/03-a-share)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

专用于中国 A 股市场（沪深京交易所及场内 ETF）的量化投研、回测、组合优化与 K 线可视化。

---

## 一、 标的资产池与数据映射 (A-Share Universe)

| 类别 | 标的名称 | 代表代码 | 核心用途与投研价值 |
|:---|:---|:---|:---|
| **宽基核心指数** | 上证指数 / 沪深 300 / 中证 500 / 创业板指 | `000001.SH`, `000300.SH`, `000905.SH`, `399006.SZ` | 大盘基准、市场 Beta 择时、风格强弱对比 |
| **核心蓝筹与龙头** | 贵州茅台 / 宁德时代 / 招商银行 / 中国平安 | `600519.SH`, `300750.SZ`, `600036.SH`, `601318.SH` | 消费 / 新能源 / 金融核心权重股与基本面研究 |
| **高股息红利资产** | 长江电力 / 中国神华 / 工商银行 | `600900.SH`, `601088.SH`, `601398.SH` | 防御性红利策略、低波高股息组合配置 |
| **场内宽基与行业 ETF** | 沪深300ETF / 科创50ETF / 红利ETF / 半导体ETF | `510300.SH`, `588000.SH`, `510880.SH`, `512480.SH` | 赛道轮动与组合配置，规避个股黑天鹅 |
| **ETF 期权标的** | 上证 50ETF / 沪深 300ETF | `510050.SH`, `510300.SH` | 欧式 ETF 期权定价、隐含波动率与对冲研究 |
| **海外流动性** | 美联储利率 / 美元指数 / 10 年期美债 | FRED: `FEDFUNDS`, `DTWEXBGS`, `DGS10` | 外资风险偏好、人民币汇率与 A 股估值的外部驱动 |

> 代码后缀说明：东方财富 / kline-chart 使用 `.SH` / `.SZ`（或直接 6 位代码），Yahoo Finance 使用 `.SS` / `.SZ`（如 `600519.SS`）。

---

## 二、 核心技能与功能模块 (Core Skills)

全部技能遵循 [SKILL.md](https://skills.sh) 规范，代码轻量，无重型框架绑定。

```text
skills/
├── [行情可视化与选股]
│   ├── kline-chart/        # 交互式 K 线看板与离线 HTML 导出（东方财富 A 股源、前复权、红涨绿跌）
│   └── tradingview/        # 盘后选股扫描与预计算技术指标（支持 SSE / SZSE，免费数据约延迟 15 分钟）
├── [行情备份与基本面参考]
│   ├── yahoo-finance/      # A 股日线备用源与交叉核对（600519.SS / 000858.SZ，免 Key）
│   └── simplywallst/       # 基本面估值评分、分红历史（覆盖沪深 7,000+ 只股票）
├── [宏观]
│   └── fred-macro/         # 美国宏观与全球流动性（利率、美元指数、美债收益率）
└── [量化回测、组合优化与衍生品]
    ├── backtesting/        # 5 阶段量化回测框架（待适配 A 股 T+1、涨跌停、印花税规则）
    ├── portfolio/          # 组合优化（Markowitz、Black-Litterman、HRP / HERC / NCO）
    └── option-pricing/     # 期权定价与 Greeks（适用于 50ETF / 300ETF 欧式期权）
```

| 技能 | 定位 | 当前状态 |
|:---|:---|:---|
| [kline-chart](./skills/kline-chart/) | A 股看盘主力 | 可用；默认配置仍为 `yahoo:SPY` / 绿涨红跌，待切换为 A 股默认 |
| [tradingview](./skills/tradingview/) | 盘后选股 | 可用；后续可裁剪为中国市场专用扫描器 |
| [yahoo-finance](./skills/yahoo-finance/) | 日线备份 / 交叉核对 | 可用，无需改动 |
| [simplywallst](./skills/simplywallst/) | 基本面参考 | 可用，无需改动 |
| [fred-macro](./skills/fred-macro/) | 海外宏观 | 可用；需设置 `FRED_API_KEY`（免费申请） |
| [backtesting](./skills/backtesting/) | 回测引擎 | 可用；**A 股交易规则尚未适配**，回测结果会偏乐观 |
| [portfolio](./skills/portfolio/) | 组合优化 | 可用，无需改动 |
| [option-pricing](./skills/option-pricing/) | 期权定价 | 可用；A 股期权行情数据源后续补充 |

---

## 三、 后续建设规划 (Roadmap)

1. **A 股数据源选型与打通**（进行中）
   - 候选：mootdx（通达信协议）、AKShare、东方财富直连、Tushare Pro、巨潮资讯（公告）。
   - 先做多源实测对比（复权一致性、完整性、速度、限流），再确定主备方案。
   - 统一为 `cn-data` 技能：多数据源适配器 + 本地 Parquet 缓存。
2. **kline-chart A 股默认配置**：默认东方财富源、A 股标的列表、红涨绿跌。
3. **backtesting A 股规则适配**
   - **T+1**、**涨跌停**（主板 ±10%、创业板 / 科创板 ±20%、北交所 ±30%、ST ±5%）。
   - **交易成本**（佣金 + 卖出印花税 0.05% + 过户费）、**100 股整手**、**停牌 / 退市处理**。
   - 样本数据由 S&P 500 替换为沪深 300；从 `02-crypto` 引入并改造 `ticker-strategy`。
4. **国内宏观与公告**：`cn-macro`（CPI、PMI、M2、社融、LPR）、`cninfo`（巨潮公告）。
5. **ETF 期权数据**：期权链、隐含波动率曲面，配合 `option-pricing` 使用。

> [!NOTE]
> 自 2024-08-19 起交易所不再披露北向资金每日净买入，相关日度指标已不可用。

---

## 四、 快速上手 (Quick Start)

### 1. 启动 A 股交互式 K 线看板（东方财富源）
```bash
# 贵州茅台日线（前复权 + 红涨绿跌）
python skills/kline-chart/scripts/kline_chart.py serve --symbol eastmoney:600519 --interval 1d --color-scheme red_up

# 宁德时代 15 分钟线（每 5 秒无闪烁刷新）
python skills/kline-chart/scripts/kline_chart.py serve --symbol eastmoney:300750 --interval 15m --color-scheme red_up --refresh 5

# 导出沪深300ETF 单文件离线交互 K 线 HTML
python skills/kline-chart/scripts/kline_chart.py export --symbol eastmoney:510300 --interval 1d --color-scheme red_up -o hs300etf.html
```

### 2. Yahoo Finance 拉取 A 股日线（备用源 / 交叉核对）
```bash
python skills/yahoo-finance/scripts/download_historical.py --tickers 600519.SS,000858.SZ,300750.SZ --range 1y --interval 1d
```

### 3. 获取海外流动性指标
```bash
# 需先设置环境变量 FRED_API_KEY
python skills/fred-macro/scripts/fetch_series.py --series FEDFUNDS,DTWEXBGS,DGS10 --start 2020-01-01
```

### 4. 组合优化与回测
```bash
# 层次化风险平价 (HRP)
python skills/portfolio/scripts/cli.py hrp

# 回测引擎（当前样本数据为 S&P 500，A 股规则待适配）
python skills/backtesting/scripts/backtesting.py run --prices skills/backtesting/assets/sp500_returns.csv
```

### 5. ETF 期权定价
```bash
python skills/option-pricing/scripts/option_pricing.py binomial --S 3.0 --K 3.0 --T 0.25 --r 0.02 --sigma 0.20 --style european
```
