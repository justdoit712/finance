# Scanner 字段列 (Columns) — 详尽参考指南

> 本文详细列出了可在 `POST /{market}/scan` 请求载荷中的 `columns: []` 数组里传入的**字段列名称 (Columns)**。
> 结构化资产文件位于 [`../assets/scanner_columns.json`](../assets/scanner_columns.json)，其中包含各预置分组。

**已验证字段总数：** 130+ 列。该 API 实际上暴露出 ~300+ 个字段 —— 本清单全面涵盖了金融分析与交易实操所需的全部实用字段。

---

## 目录

1. [基础标识与元数据 (Identity & Metadata)](#1-基础标识与元数据-identity--metadata)
2. [基础行情报价 (Basic Quote)](#2-基础行情报价-basic-quote)
3. [成交量与波动率 (Volume & Volatility)](#3-成交量与波动率-volume--volatility)
4. [估值指标 (Valuation)](#4-估值指标-valuation)
5. [技术指标 — 震荡指标类 (Oscillators)](#5-技术指标--震荡指标类-oscillators)
6. [技术指标 — 移动均线类 (Moving Averages)](#6-技术指标--移动均线类-moving-averages)
7. [买卖评级 (Ratings: Recommend.*)](#7-买卖评级-ratings-recommend)
8. [月线枢轴点 (Monthly Pivots)](#8-月线枢轴点-monthly-pivots)
9. [资产负债表 (Balance Sheet)](#9-资产负债表-balance-sheet)
10. [利润表 (Income Statement)](#10-利润表-income-statement)
11. [现金流量表 (Cash Flow)](#11-现金流量表-cash-flow)
12. [财务比率 (Ratios)](#12-财务比率-ratios)
13. [成长性指标 (Growth)](#13-成长性指标-growth)
14. [股息分红 (Dividends)](#14-股息分红-dividends)
15. [财报业绩与预期 (Earnings & Forecasts)](#15-财报业绩与预期-earnings--forecasts)
16. [分析师目标价与评级 (Analyst Targets & Recommendations)](#16-分析师目标价与评级-analyst-targets--recommendations)
17. [股本与股权结构 (Shares & Ownership)](#17-股本与股权结构-shares--ownership)
18. [Beta 与相关系数 (Beta & Correlation)](#18-beta-与相关系数-beta--correlation)
19. [历史收益率与表现 (Performance Returns)](#19-历史收益率与表现-performance-returns)
20. [常见场景预设组合包 (Bundles)](#20-常见场景预设组合包-bundles)

---

## 1. 基础标识与元数据 (Identity & Metadata)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `name` | str | 简短代码 (例如: `GGAL`)，不包含交易所前缀。 |
| `description` | str | 标的完整名称 (例如: `Grupo Financiero Galicia SA Sponsored ADR Class B`) |
| `logoid` | str | 标的 Logo ID。完整图片链接为: `https://s3-symbol-logo.tradingview.com/{logoid}--big.svg` |
| `exchange` | str | 挂牌交易所代码: `NASDAQ`、`NYSE`、`BCBA`、`BME`、`BMFBOVESPA` 等 |
| `type` | str | 标的类别: `stock`, `dr` (ADR/CEDEAR), `etf`, `fund`, `structured`, `bond`, `crypto`, `forex` |
| `country` | str | 发行方所在国家 (`Argentina`, `United States` 等) |
| `sector` | str | 所属经济板块 (`Finance`, `Technology`, `Energy` 等) |
| `industry` | str | 所属细分行业 (`Regional Banks`, `Software` 等) |
| `currency` | str | 计价结算货币 (`USD`, `ARS`, `EUR`, `BRL`, `GBP` 等) |

---

## 2. 基础行情报价 (Basic Quote)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `close` | float | 最新价格 / 收盘价 |
| `open` | float | 当日开盘价 |
| `high` | float | 当日最高价 |
| `low` | float | 当日最低价 |
| `change` | float | 当日涨跌幅百分比 (例如: 1.5 表示 1.5%，非 0.015) |
| `change_abs` | float | 当日涨跌绝对额 |
| `vwap` | float | 成交量加权平均价 (Volume-Weighted Average Price) |

---

## 3. 成交量与波动率 (Volume & Volatility)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `volume` | float | 当日成交量 |
| `average_volume_30d_calc` | float | 30 日平均成交量 |
| `volume_avg_3m` | float | 3 个月平均成交量 |
| `volume_change` | float | 成交量相对均量的变化比例 (%) |
| `Volatility.D` | float | 日波动率 (%) |
| `Volatility.W` | float | 周波动率 (%) |
| `Volatility.M` | float | 月波动率 (%) |
| `High.All` | float | 历史最高价 (All-time high) |
| `Low.All` | float | 历史最低价 (All-time low) |
| `price_52_week_high` | float | 52 周最高价 |
| `price_52_week_low` | float | 52 周最低价 |

---

## 4. 估值指标 (Valuation)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `market_cap_basic` | float | 总市值 (Market Capitalization) |
| `market_cap_calc` | float | 计算总市值 (备选计算方式) |
| `enterprise_value_fq` | float | 企业价值 EV (当季) |
| `price_earnings_ttm` | float | 市盈率 P/E TTM (过去 12 个月) |
| `price_earnings_to_growth_ratio` | float | PEG 估值比率 |
| `price_sales` | float | 市销率 P/S |
| `price_book` | float | 市净率 P/B |
| `price_revenue_ttm` | float | 价格/营业收入比率 TTM |
| `enterprise_value_ebitda_ttm` | float | 企业价值与 EBITDA 比率 (EV/EBITDA) |
| `enterprise_value_to_revenue_ttm` | float | 企业价值与营业收入比率 (EV/Revenue) |
| `book_value_per_share_fq` | float | 每股净资产 (当季) |
| `earnings_per_share_basic_ttm` | float | 基本每股收益 EPS TTM |
| `earnings_per_share_diluted_ttm` | float | 稀释每股收益 EPS TTM |

---

## 5. 技术指标 — 震荡指标类 (Oscillators)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `RSI` | float | 相对强弱指标 Relative Strength Index (14) |
| `RSI[1]` | float | 前一周期 RSI |
| `Stoch.K` | float | 随机指标 Stochastic %K |
| `Stoch.D` | float | 随机指标 Stochastic %D |
| `MACD.macd` | float | MACD 快线 (DIF) |
| `MACD.signal` | float | MACD 信号线 (DEA) |
| `ADX` | float | 平均趋向指数 Average Directional Index |
| `ADX+DI` | float | ADX 正向指标 (+DI) |
| `ADX-DI` | float | ADX 负向指标 (-DI) |
| `ATR` | float | 真实波动幅度均值 Average True Range |
| `CCI20` | float | 顺势指标 Commodity Channel Index (20) |
| `BBPower` | float | 多空力量指标 (Bull/Bear Power) |
| `UO` | float | 终极指标 (Ultimate Oscillator) |
| `Mom` | float | 动量指标 (Momentum) |
| `AO` | float | 动量震荡指标 (Awesome Oscillator) |
| `W.R` | float | 威廉指标 Williams %R |

### 核心研判法则

- **RSI**：取值 0-100。>70 为超买区，<30 为超卖区。
- **Stoch.K**：取值 0-100。>80 为超买区，<20 为超卖区。
- **MACD.macd > MACD.signal**：金叉信号，看多 (Bullish cross)。
- **ADX > 25**：表明当前存在强势趋势（无论上涨或下跌趋势）。
- **W.R**：取值 -100 到 0。> -20 为超买，< -80 为超卖。

---

## 6. 技术指标 — 移动均线类 (Moving Averages)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `SMA10` | float | 10 日简单移动平均线 |
| `SMA20` | float | 20 日简单移动平均线 |
| `SMA30` | float | 30 日简单移动平均线 |
| `SMA50` | float | 50 日简单移动平均线 |
| `SMA100` | float | 100 日简单移动平均线 |
| `SMA200` | float | 200 日简单移动平均线 |
| `EMA10` | float | 10 日指数移动平均线 |
| `EMA20` | float | 20 日指数移动平均线 |
| `EMA30` | float | 30 日指数移动平均线 |
| `EMA50` | float | 50 日指数移动平均线 |
| `EMA100` | float | 100 日指数移动平均线 |
| `EMA200` | float | 200 日指数移动平均线 |
| `VWMA` | float | 成交量加权移动均线 |
| `HullMA9` | float | 赫尔移动平均线 (9) |
| `Ichimoku.BLine` | float | 一目均衡表基准线 (Base Line) |

### 经典均线研判

- **黄金交叉 (Golden Cross)**：`SMA50 > SMA200`（看涨信号）。
- **死亡交叉 (Death Cross)**：`SMA50 < SMA200`（看跌信号）。
- **价格 > EMA200**：长期多头走势。
- **价格 > EMA50 > EMA200**：稳健强劲的多头排列。

---

## 7. 买卖评级 (Ratings: Recommend.*)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `Recommend.All` | float [-1, 1] | 基于**全部**指标的综合聚合评级评分 |
| `Recommend.MA` | float [-1, 1] | 仅基于移动均线类的评级评分 |
| `Recommend.Other` | float [-1, 1] | 仅基于震荡指标类的评级评分 |

### 评分区间与分档映射

| 区间范围 | 分档标识 (Bucket) | 界面标签 (UI Label) |
|-------|--------|----------|
| -1.00 到 -0.50 | `STRONG_SELL` | 强力卖出 |
| -0.50 到 -0.10 | `SELL` | 卖出 |
| -0.10 到 +0.10 | `NEUTRAL` | 中立 |
| +0.10 到 +0.50 | `BUY` | 买入 |
| +0.50 到 +1.00 | `STRONG_BUY` | 强力买入 |

> 结构化资产文件见 [`../assets/recommend_ratings.json`](../assets/recommend_ratings.json)。

---

## 8. 月线枢轴点 (Monthly Pivots)

基于 5 种不同经典算法计算的月线支撑与阻力位。统一命名格式为 `Pivot.M.{METHOD}.{LEVEL}`。

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `Pivot.M.Classic.Middle` | float | 经典 (Classic) 月线中轴枢轴点 |
| `Pivot.M.Classic.S1` | float | 经典支撑位 1 (S1) |
| `Pivot.M.Classic.S2` | float | 经典支撑位 2 (S2) |
| `Pivot.M.Classic.S3` | float | 经典支撑位 3 (S3) |
| `Pivot.M.Classic.R1` | float | 经典阻力位 1 (R1) |
| `Pivot.M.Classic.R2` | float | 经典阻力位 2 (R2) |
| `Pivot.M.Classic.R3` | float | 经典阻力位 3 (R3) |
| `Pivot.M.Fibonacci.S1` | float | 斐波那契 (Fibonacci) 支撑位 1 |
| `Pivot.M.Fibonacci.R1` | float | 斐波那契 (Fibonacci) 阻力位 1 |
| `Pivot.M.Camarilla.S1` | float | 卡玛利拉 (Camarilla) 支撑位 1 |
| `Pivot.M.Camarilla.R1` | float | 卡玛利拉 (Camarilla) 阻力位 1 |
| `Pivot.M.Woodie.S1` | float | 伍迪 (Woodie) 支撑位 1 |
| `Pivot.M.Woodie.R1` | float | 伍迪 (Woodie) 阻力位 1 |
| `Pivot.M.DM.S1` | float | 德马克 (DeMark) 支撑位 1 |
| `Pivot.M.DM.R1` | float | 德马克 (DeMark) 阻力位 1 |

> 此外，同套语法还支持周线 `Pivot.W.{METHOD}.{LEVEL}` 与日线 `Pivot.D.{METHOD}.{LEVEL}`。

---

## 9. 资产负债表 (Balance Sheet)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `total_assets` | float | 总资产 (Total Assets) |
| `total_current_assets` | float | 流动资产总额 (Current Assets) |
| `cash_n_short_term_invest` | float | 现金及短期投资 |
| `total_debt` | float | 总负债 / 债务总额 |
| `long_term_debt` | float | 长期负债 |
| `total_liabilities_fq` | float | 负债总额 (当季) |
| `total_current_liabilities` | float | 流动负债总额 |
| `total_equity` | float | 所有者权益总额 (Total Equity) |
| `minority_interest` | float | 少数股东权益 |

> 所有金额数值均以对应资产的本币（`currency` 字段）计价。

---

## 10. 利润表 (Income Statement)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `total_revenue` | float | 营业收入 TTM |
| `gross_profit` | float | 毛利润 |
| `operating_income` | float | 营业利润 |
| `net_income` | float | 净利润 (Net Income) |
| `ebitda` | float | 息税折旧摊销前利润 (EBITDA) |
| `operating_margin` | float | 营业利润率 (%) |
| `gross_margin` | float | 毛利率 (%) |
| `net_margin` | float | 净利率 (%) |
| `ebitda_margin` | float | EBITDA 利润率 (%) |
| `pre_tax_margin` | float | 税前利润率 (%) |

---

## 11. 现金流量表 (Cash Flow)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `free_cash_flow` | float | 自由现金流 (Free Cash Flow) |
| `cash_f_operating_activities` | float | 经营活动产生的现金流量净额 |
| `cash_f_investing_activities` | float | 投资活动产生的现金流量净额 |
| `cash_f_financing_activities` | float | 筹资活动产生的现金流量净额 |
| `capital_expenditures` | float | 资本性支出 (CapEx) |

---

## 12. 财务比率 (Ratios)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `current_ratio` | float | 流动比率 (流动资产 / 流动负债) |
| `quick_ratio` | float | 速动比率 ((现金 + 应收款项) / 流动负债) |
| `debt_to_equity` | float | 产权比率 / 负债权益比 (债务 / 净资产) |
| `debt_to_assets` | float | 资产负债率 (债务 / 总资产) |
| `return_on_equity` | float | 净资产收益率 ROE (%) |
| `return_on_assets` | float | 总资产收益率 ROA (%) |
| `return_on_invested_capital` | float | 投入资本回报率 ROIC (%) |
| `asset_turnover_fy` | float | 总资产周转率 (财年) |
| `inventory_turnover_fy` | float | 存货周转率 (财年) |

---

## 13. 成长性指标 (Growth)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `revenue_yoy_growth` | float | 营业收入同比增长率 YoY (%) |
| `revenue_yoy_growth_fy` | float | 财年营业收入同比增长率 (%) |
| `earnings_per_share_diluted_yoy_growth` | float | 稀释每股收益同比增长率 (%) |
| `net_income_yoy_growth` | float | 净利润同比增长率 (%) |
| `ebitda_yoy_growth` | float | EBITDA 同比增长率 (%) |

---

## 14. 股息分红 (Dividends)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `dividend_yield_recent` | float | 最新股息收益率 (%) |
| `dividends_yield` | float | 过去 12 个月股息收益率 TTM (%) |
| `dividends_paid` | float | 派发股息总额 |
| `dps_common_stock_prim_issue_fy` | float | 财年每股股息 DPS |
| `payout_ratio_fy` | float | 财年股利支付率 (%) |
| `continuous_dividend_payout` | int | 连续派息年数 |
| `continuous_dividend_growth` | int | 连续增加派息年数 |

---

## 15. 财报业绩与预期 (Earnings & Forecasts)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `earnings_release_date` | int (unix) | 上次财报发布日期 |
| `earnings_release_next_date` | int (unix) | 下次财报发布日期 |
| `earnings_release_time` | int | 上次财报具体发布时间 (Unix 偏移量) |
| `earnings_release_next_time` | int | 下次财报具体发布时间 (Unix 偏移量) |
| `earnings_per_share_fq` | float | 当季实际报告每股收益 EPS |
| `revenue_fq` | float | 当季实际报告营业收入 |
| `earnings_per_share_forecast_fq` | float | 当季每股收益 EPS 市场预期 |
| `revenue_forecast_fq` | float | 当季营业收入市场预期 |
| `earnings_per_share_forecast_next_fq` | float | 下季度每股收益 EPS 市场预期 |
| `revenue_forecast_next_fq` | float | 下季度营业收入市场预期 |

> 所有 `earnings_release_*_date` 均为 Unix 时间戳（UTC 秒数）。使用 `datetime.fromtimestamp(ts, tz=timezone.utc)` 进行日期转换。

---

## 16. 分析师目标价与评级 (Analyst Targets & Recommendations)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `price_target_average` | float | 分析师平均目标价 |
| `price_target_high` | float | 分析师最高目标价 |
| `price_target_low` | float | 分析师最低目标价 |
| `price_target_median` | float | 分析师目标价中位数 |
| `number_of_analyst_opinions` | int | 覆盖该标的的分析师总数 |
| `recommendation_total` | int | 评级推荐总数 |
| `recommendation_buy` | int | 买入 (Buy) 推荐数量 |
| `recommendation_hold` | int | 持有 (Hold) 推荐数量 |
| `recommendation_sell` | int | 卖出 (Sell) 推荐数量 |

---

## 17. 股本与股权结构 (Shares & Ownership)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `float_shares_outstanding` | float | 流通股本 (Float shares) |
| `total_shares_outstanding_fundamental` | float | 总股本 |
| `shares_outstanding_fundamental_fq` | float | 季度已发行股份总数 |
| `shares_owned_institutions` | float | 机构持股比例 (%) |
| `shares_owned_insiders` | float | 内部人持股比例 (%) |
| `short_interest` | float | 做空持仓量 |
| `short_interest_percent` | float | 做空股数占流通股比例 (%) |
| `days_to_cover_short_interest` | float | 空头回补天数 (Days to Cover) |

---

## 18. Beta 与相关系数 (Beta & Correlation)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `beta_1_year` | float | 1 年期 Beta 系数 |
| `beta_3_year` | float | 3 年期 Beta 系数 |
| `beta_5_year` | float | 5 年期 Beta 系数 |
| `correlation_to_sp500_1m` | float | 1 个月相对标普 500 的相关系数 |

---

## 19. 历史收益率与表现 (Performance Returns)

| 字段列 | 类型 | 说明 |
|---------|------|-------------|
| `Perf.W` | float | 近 1 周收益率 (%) |
| `Perf.1M` | float | 近 1 个月收益率 (%) |
| `Perf.3M` | float | 近 3 个月收益率 (%) |
| `Perf.6M` | float | 近 6 个月收益率 (%) |
| `Perf.Y` | float | 近 1 年收益率 (%) |
| `Perf.YTD` | float | 年初至今 (YTD) 收益率 (%) |
| `Perf.5Y` | float | 近 5 年收益率 (%) |
| `Perf.All` | float | 上市以来全周期总收益率 (%) |

---

## 20. 常见场景预设组合包 (Bundles)

预置的组合包定义于 [`../assets/column_groups.json`](../assets/column_groups.json)。

| CLI 模式 | 组合包名称 (Group) | 包含列数 |
|----------|-------|-----------:|
| `quote` | `quote_basic` | 14 |
| `quote-extended` | `quote_extended` | 30 |
| `technicals` | `technicals` | 36 |
| `pivots` | `pivots` | 17 |
| `financials` | `financials` | 35 |
| `earnings` | `earnings` | 12 |
| `targets` | `targets` | 10 |
| `performance` | `performance` | 18 |
| `dividends` | `dividends` | 8 |
| `ownership` | `ownership` | 10 |
| `all` | `all_in_one` | 52 |

### 如何指定自定义列

```bash
py fetch_tradingview.py quote NASDAQ:GGAL --columns "name,close,RSI,MACD.macd,Recommend.All"
```

或在 Python 中直接调用：

```python
from fetch_tradingview import scanner_scan
data = scanner_scan(
    symbols=["NASDAQ:GGAL"],
    columns=["name", "close", "RSI", "MACD.macd", "Recommend.All"],
    market="global",
)
```

---

## 附录：如何发现与探测新字段列

TradingView 会不定期新增字段列。探测新列的通用方法如下：

1. 打开浏览器 DevTools 开发者工具，观察在 `scanner.tradingview.com/{market}/scan` 请求中的请求体载荷。
2. 将候选列名传入请求进行测试。如果对于所有标的均返回 `null`，说明该列名可能不存在。
3. 可在此 Skill 中提交更新维护。

常见命名规范模式：
- 技术指标类：`{INDICATOR}` 或 `{INDICATOR}{PERIOD}`（例如 `RSI`、`EMA50`、`CCI20`）
- 历史表现类：`Perf.{W|1M|3M|...}`
- 枢轴点类：`Pivot.{D|W|M}.{Classic|Fibonacci|Camarilla|Woodie|DM}.{S1|S2|S3|R1|R2|R3|Middle}`
- 财报业绩类：`earnings_*`（蛇形命名 snake_case）
- 预测类：`*_forecast_*`
