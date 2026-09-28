# 其它特征：基本面、情绪与外生宏观特征

## A — 基本面量化分析（第 8 类）

在 `scripts/fundamental_ratios.py` 中实现的函数与指标：

- **利润表指标（Income metrics）**：毛利率（Gross Margin）、营业利润率（Operating Margin）、净利率（Net Margin）、EBITDA 利润率。
- **资产负债表指标（Balance metrics）**：产权比率 / 债资比（D/E）、资产负债率（Debt/Assets）、流动比率（Current Ratio）、速动比率（Quick Ratio）、现金比率（Cash Ratio）。
- **现金流指标（Cash flow metrics）**：自由现金流（FCF）、经营现金流对营业收入比（CFO/Revenue）、经营现金流对净利润比（CFO/Net Income，盈利含金量）。
- **估值指标（Valuation）**：市盈率（P/E）、市净率（P/B）、市销率（P/S）、企业价值倍数（EV/EBITDA）。
- **盈利能力指标（Profitability）**：净资产收益率（ROE）、总资产收益率（ROA）、投入资本回报率（ROIC）。
- **杜邦五因子分解（DuPont）**：将 ROE 拆解为 5 大驱动要素（税收负担 × 利息负担 × 营业利润率 × 资产周转率 × 权益乘数）。
- **Altman Z-Score**：财务破产风险预测（$Z > 2.99$ 为安全区，$1.81 \le Z \le 2.99$ 为灰色地带，$Z < 1.81$ 为高危财务困境区）。
- **Piotroski F-Score**：基于 9 项二元财务健康判准的综合评分（0 分为极度脆弱，9 分为极度健康）。

### 数据源

Gauss 技能生态中提供结构化财务报表数据的相关技能：

| 数据类型 | 来源技能 / 接口 |
|------|---------------|
| 利润表（Income Statement） | sec-data, macrotrends, barchart, yahoo-finance, marketwatch, google-finance |
| 资产负债表（Balance Sheet） | sec-data, macrotrends, barchart, yahoo-finance, marketwatch, google-finance |
| 现金流量表（Cash Flow） | sec-data, macrotrends, barchart, yahoo-finance, marketwatch, google-finance |
| 估值倍数比率（Valuation Ratios） | finviz, barchart, simplywallst, morningstar, companiesmarketcap |
| 机构持仓（Institutional Holdings） | nasdaq-data (13F 表格), marketscreener |
| 内部人交易（Insider Trading） | nasdaq-data, barchart, finviz, marketscreener |
| 业绩电话会纪要（Earnings Transcripts） | earningswhispers |
| 分析师评级（Analyst Ratings） | barchart, google-finance, marketwatch, finnhub, marketscreener |
| 基本面筛选器（Fundamental Screener） | morningstar（覆盖 102K+ 标的）, tradingview |

---

## B — 市场情绪（第 9 类）

本技能包未内置原生代码。以下文献与资源可作为自行扩展开发的指引。

### 经典学术文献

- **Loughran-McDonald (2011)**：面向金融自然语言处理（NLP）的专用词典。包含 6 种维度的情感词库（积极、消极、不确定性、诉讼风险、约束性、多余修饰语），其分类效果大幅超越通用通用情感词典（如 AFINN、LIWC）。
- **Tetlock (2007)**：媒体新闻情绪对股票二级市场价格压力的实证研究。
- **Bollen-Mao-Zeng (2011)**：Twitter 社交情绪对道琼斯指数走势的预测能力。
- **Hutto-Gilbert (2014)**：VADER — 专为社交网络文本设计的规则情感分析器，擅长识别反讽、标点强化和情绪词极性。

### 数据获取途径

- **金融新闻（News）**：finnhub（按股票代码聚合新闻）、tradingview（每只股票约 200 条快讯标题）、google-finance（图文新闻）、earningswhispers（完整的业绩说明会逐字稿）。
- **社交网络（Social Media）**：Reddit API（如 WallStreetBets 讨论度）、X/Twitter API、StockTwits。
- **另类数据（Alternative Data）**：Google Trends 搜索热度、SEC 申报文件的文本语言风格演化、招聘发布数据（LinkedIn, Indeed）。

### 策略优势（Edge）

情绪指标是唯一能够直接捕捉**市场叙事（Narrative）**的特征类别——即市场为当前价格上涨或下跌所编织的故事。纯粹的技术分析无法提前预见突发的情绪转向（如挤兑恐慌、FOMO 羊群效应、超预期黑天鹅）。通过将情绪特征与价格序列相结合，可以有效捕捉量价与情绪的**背离**：若价格持续上涨但舆论情绪指标骤降，往往提示动能衰竭，这是任何常规技术指标都无法提前发现的隐性信号。

---

## C — 外生宏观特征（第 10 类）

本技能包未内置原生代码。以下为构建宏观大类资产特征体系的参考资源。

### 常见宏观类别

| 宏观类别 | 核心代表指标 | 推荐数据源 |
|-----------|----------|---------|
| 利率环境 | 联邦基金利率（Fed Funds）、10年期美债收益率（T10Y）、2年期美债（T2Y）、SOFR、BADLAR | FRED, BCRA, investing |
| 通胀水平 | CPI、PCE 物价指数、核心通胀 IPC、CER | FRED, INDEC |
| 经济景气 | GDP 增长率、ISM 制造业 PMI、EMAE 经济活动指数、非农就业数据 | FRED, INDEC |
| 波动率与恐慌 | VIX 恐慌指数、VDAX、MERVAL 波动率 | CBOE, yahoo-finance |
| 流动性规模 | M2 货币供应量、商业银行超额准备金、央行基础货币 | FRED, BCRA |
| 大宗商品 | 原油（WTI/Brent）、黄金、铜、农产品期现货 | investing, yahoo-finance |
| 外汇汇率 | 美元指数（DXY）、欧元兑美元（EURUSD）、美元兑离岸人民币等 | FRED, BCRA, investing |
| 链上数据（加密资产） | 比特币算力（BTC Hash Rate）、活跃地址数、交易所充提资金流 | Glassnode, CoinMetrics |

### 策略优势（Edge）

外生宏观特征能够准确刻画**宏观体制状态（Macro Regime）**——即宏观经济所处的具体发展阶段，它从根本上决定了不同资产类别与量化策略的胜率基底。例如，债券趋势跟踪策略在利率单边下行或上行时期表现优异，但在利率拐点或震荡期将频繁止损回撤。引入外生变量可以依据宏观体制对底层量化策略进行动态轮动（Regime-based Strategy Rotation），避免在恶劣的宏观逆风下僵化运行单一策略：

- 当 VIX 指数突破 30 且呈上升趋势时：主动缩减组合头寸杠杆，大幅提高避险防御资产（黄金、短期国债）的配置权重。
- 当美债长短期利差倒挂（如 T10Y - T2Y < 0）时：经济衰退概率剧增 → 仓位由高估值成长股逐步切换为防御价值股或优质纯债。
- 当 CPI 通胀超预期加速上行时：加大抗通胀资产敞口（大宗商品、TIPS 抗通胀债券、硬资产）。
- 当央行缩表导致基础货币收缩时：全面下调风险资产组合的系统性 Beta 敞口。

### 参考相关技能

- **FRED Macro 技能**：涵盖美联储圣路易斯分行的 840,000+ 条宏观经济时间序列（利率、就业、GDP、货币流动性等）。
- **BCRA Macro 技能**：阿根廷央行官方宏观序列（外汇储备、政策利率、CER 指数、货币基础）。
- **INDEC 技能**：官方统计局经济指标（约 4,250 项时间序列：物价指数 IPC、月度经济活动 EMAE、贫困率与薪资水平）。
- **CBOE 技能**：芝加哥期权交易所的 VIX 及其子类波动率指数、VX 期货曲线数据。
- **TradingView screener 筛选器**：支持按国家与宏观列（如基准利率、通货膨胀率）进行全球宏观跨期扫描。
