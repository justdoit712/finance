# FRED 时间序列参考手册 — 100+ 条核心时间序列

圣路易斯联储（FRED）核心宏观经济时间序列速查指南，按专业经济金融领域分类组织。每个条目包含：`时序代码 (ID)`、`描述`、`更新频率 (Freq)`、`统计单位` 及 `数据起始年份 (Desde)`。

> **注意：** FRED API 返回值中的 `"."` 表示该观测点数据缺失（N/A）。  
> **更新与重新生成：** 可运行脚本 `search_series.py --output-catalog` 自动重新生成全量目录。

---

## 1. 国内生产总值 (GDP & National Accounts)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `GDP` | 名义 GDP（Nominal GDP） | 季度 | 十亿美元 | 1947 |
| `GDPC1` | 实际 GDP（Real GDP, 2017 链式价格） | 季度 | 十亿美元 | 1947 |
| `A191RL1Q225SBEA` | 实际 GDP 环比折年率（Real GDP QoQ annualized） | 季度 | % | 1947 |
| `GDPPOT` | 潜在 GDP（CBO 测算） | 季度 | 十亿美元 | 1949 |
| `GDPSAV` | 国民总储蓄（Gross National Saving） | 季度 | 十亿美元 | 1947 |
| `GPDI` | 国内私人投资总额（Gross Private Domestic Investment） | 季度 | 十亿美元 | 1947 |
| `GCEC1` | 政府实际消费支出与投资（Real Government Consumption & Investment） | 季度 | 十亿美元 | 1947 |
| `IMPGSC1` | 实际商品与服务进口额 | 季度 | 十亿美元 | 1947 |
| `EXPGSC1` | 实际商品与服务出口额 | 季度 | 十亿美元 | 1947 |

---

## 2. 通货膨胀 — CPI（消费者物价指数）

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `CPIAUCSL` | 总体 CPI（所有项目，季调） | 月度 | 指数 1982=100 | 1947 |
| `CPILFESL` | 核心 CPI（剔除食品与能源，季调） | 月度 | 指数 1982=100 | 1957 |
| `CPIENGSL` | 能源分项 CPI | 月度 | 指数 1982=100 | 1957 |
| `CPIFABSL` | 食品与饮料分项 CPI | 月度 | 指数 1982=100 | 1967 |
| `CPITRNSL` | 交通运输分项 CPI | 月度 | 指数 1982=100 | 1935 |
| `CUSR0000SAD` | 住房居住分项 CPI（Shelter） | 月度 | 指数 1982=100 | 1967 |
| `CPIAUCNS` | 总体 CPI（非季调） | 月度 | 指数 1982=100 | 1913 |
| `CPIYOY` | CPI 同比变动率 | 月度 | % | 1914 |

---

## 3. 通货膨胀 — PCE（个人消费支出物价指数）

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `PCE` | 名义个人消费支出（PCE） | 月度 | 十亿美元 | 1959 |
| `PCEC96` | 实际个人消费支出 | 月度 | 十亿美元 | 2002 |
| `PCECTPI` | PCE 物价指数（PCE Price Index） | 月度 | 指数 2017=100 | 1959 |
| `PCEPILFE` | 核心 PCE 物价指数（剔除食品/能源，美联储主要通胀盯住目标） | 月度 | 指数 2017=100 | 1960 |
| `PCEPILFE_YOY` | 核心 PCE 物价指数同比增速 | 月度 | % | 1960 |

---

## 4. 利率 — 美联储政策与银行间市场

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `FEDFUNDS` | 联邦基金目标利率（Federal Funds Target Rate） | 日度 | % | 1954 |
| `DFF` | 联邦基金有效利率（日度实际成交，Effective Federal Funds Rate） | 日度 | % | 1954 |
| `EFFR` | 联邦基金有效成交加权利率（EFFR） | 日度 | % | 2000 |
| `SOFR` | 有担保隔夜融资利率（Secured Overnight Financing Rate） | 日度 | % | 2018 |
| `IORB` | 准备金存款余额利率（Interest on Reserve Balances） | 日度 | % | 2008 |
| `PRIME` | 银行最优惠贷款利率（Bank Prime Loan Rate） | 日度 | % | 1949 |
| `DISCBORR` | 贴现窗口一级信贷贴现率（Discount Window Rate） | 日度 | % | 1934 |

---

## 5. 利率 — 美国国债与收益率曲线

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `DGS1MO` | 1 个月期国债名义收益率 | 日度 | % | 2001 |
| `DGS3MO` | 3 个月期国债名义收益率 | 日度 | % | 1981 |
| `DGS6MO` | 6 个月期国债名义收益率 | 日度 | % | 1981 |
| `DGS1` | 1 年期国债名义收益率 | 日度 | % | 1962 |
| `DGS2` | 2 年期国债名义收益率 | 日度 | % | 1976 |
| `DGS3` | 3 年期国债名义收益率 | 日度 | % | 1962 |
| `DGS5` | 5 年期国债名义收益率 | 日度 | % | 1962 |
| `DGS7` | 7 年期国债名义收益率 | 日度 | % | 1969 |
| `DGS10` | 10 年期国债名义收益率（全球无风险资产基准锚） | 日度 | % | 1962 |
| `DGS20` | 20 年期国债名义收益率 | 日度 | % | 1993 |
| `DGS30` | 30 年期国债名义收益率 | 日度 | % | 1977 |
| `T10Y2Y` | 10 年期与 2 年期美债利差（经典收益率曲线倒挂指标） | 日度 | % | 1976 |
| `T10Y3M` | 10 年期与 3 个月期美债利差（衰退前瞻指示器） | 日度 | % | 1982 |
| `T5YIE` | 5 年期通胀保值债券盈亏平衡通胀率（5y Breakeven Inflation / 通胀预期） | 日度 | % | 2003 |
| `T10YIE` | 10 年期通胀保值债券盈亏平衡通胀率（10y Breakeven Inflation / 通胀预期） | 日度 | % | 2003 |
| `BAA10Y` | 穆迪 BAA 级企业债与 10 年期国债信用利差 | 日度 | % | 1986 |

---

## 6. 就业与劳动力市场 (Labor Market)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `UNRATE` | 官方失业率（U-3 失业率，季调） | 月度 | % | 1948 |
| `PAYEMS` | 非农就业总人数（Nonfarm Payrolls） | 月度 | 千人 | 1939 |
| `CIVPART` | 劳动参与率（Labor Force Participation Rate） | 月度 | % | 1948 |
| `EMRATIO` | 就业人口比率（Employment-Population Ratio） | 月度 | % | 1948 |
| `LNS14000006` | 男性失业率 | 月度 | % | 1948 |
| `LNS14000002` | 女性失业率 | 月度 | % | 1948 |
| `U6RATE` | 广义失业率（U-6，含边缘劳动力与不充分就业） | 月度 | % | 1994 |
| `AWHMAN` | 制造业每周平均工作时长 | 月度 | 小时 | 1939 |
| `CES0500000003` | 私营部门平均时薪（Average Hourly Earnings） | 月度 | 美元 | 1964 |
| `JTSJOL` | JOLTS 职位空缺总数（Job Openings） | 月度 | 千个 | 2000 |
| `JTSQUR` | JOLTS 自主离职率（Quits Rate） | 月度 | % | 2000 |
| `ICSA` | 初次申请失业金人数（Weekly Initial Jobless Claims） | 周度 | 千人 | 1967 |

---

## 7. 货币与信贷金融 (Money & Banking)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `M1SL` | M1 货币供应量 | 月度 | 十亿美元 | 1959 |
| `M2SL` | M2 货币供应量 | 月度 | 十亿美元 | 1959 |
| `M2V` | M2 货币流通速度（Velocity of M2） | 季度 | 比率 | 1959 |
| `M1V` | M1 货币流通速度（Velocity of M1） | 季度 | 比率 | 1959 |
| `REALLN` | 商业银行住宅不动产抵押贷款总额 | 月度 | 十亿美元 | 1947 |
| `BUSLOANS` | 工商业贷款（Commercial and Industrial Loans） | 周度 | 十亿美元 | 1947 |
| `CONSUMER` | 消费者消费信贷总额 | 月度 | 十亿美元 | 1943 |
| `TOTBKCR` | 商业银行信贷总额（Bank Credit） | 周度 | 十亿美元 | 1973 |
| `BOGMBASE` | 圣路易斯联储基础货币（Monetary Base） | 周度 | 十亿美元 | 1984 |
| `WRESBAL` | 存款机构在美联储的准备金余额（Reserve Balances） | 周度 | 十亿美元 | 1984 |

---

## 8. 权益与金融市场资产 (Financial Markets)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `VIXCLS` | CBOE 波动率指数（VIX，标普500期权隐含波动率，收盘价） | 日度 | 指数 | 1990 |
| `SP500` | 标普 500 价格指数（S&P 500） | 日度 | 指数 | 1957 |
| `NASDAQCOM` | 纳斯达克综合指数（NASDAQ Composite） | 日度 | 指数 | 1971 |
| `DJIA` | 道琼斯工业平均指数（Dow Jones Industrial Average） | 日度 | 指数 | 1896 |
| `WILL5000PR` | 威尔希尔 5000 全市场总市值指数（Wilshire 5000） | 日度 | 指数 | 1971 |
| `DEXUSEU` | 欧元兑美元即期汇率（EUR/USD） | 日度 | 美元 | 1999 |
| `DEXJPUS` | 美元兑日元即期汇率（USD/JPY） | 日度 | 日元 | 1971 |
| `DTWEXBGS` | 美元贸易加权广义汇率指数（Nominal Broad Dollar Index） | 日度 | 指数 | 2006 |
| `DTWEXM` | 美元对主要货币贸易加权汇率指数（Major Currencies Dollar Index） | 日度 | 指数 | 1973 |
| `REAINTRATREARAT1YE` | 1 年期实际利率期望水平 | 年度 | % | 1948 |

---

## 9. 房地产与建筑施工 (Housing & Real Estate)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `HOUST` | 新屋开工总数（Housing Starts） | 月度 | 千套 | 1959 |
| `HOUST1F` | 单户住宅新屋开工量 | 月度 | 千套 | 1959 |
| `HOUST5F` | 5 户及以上多户住宅新屋开工量 | 月度 | 千套 | 1959 |
| `PERMIT` | 营建许可总发放数（Building Permits） | 月度 | 千套 | 1960 |
| `EXHOSLUSM495S` | 成屋销售量（Existing Home Sales） | 月度 | 千套 | 1999 |
| `CSUSHPISA` | 标普/凯斯-席勒全美房价指数（Case-Shiller Home Price Index） | 月度 | 指数 | 1987 |
| `MORTGAGE30US` | 30 年期固定房贷平均利率（房地美统计） | 周度 | % | 1971 |
| `MORTGAGE15US` | 15 年期固定房贷平均利率（房地美统计） | 周度 | % | 1991 |
| `OBMMIC30YF` | 30 年期固定房贷即期利率（Optimal Blue） | 日度 | % | 2016 |

---

## 10. 消费支出与零售业 (Consumption & Retail)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `TOTALSA` | 零售总销售额（Retail Sales Total） | 月度 | 百万美元 | 1992 |
| `MRTSSM44000USS` | 机动车与零部件经销商零售额 | 月度 | 百万美元 | 1992 |
| `MRTSSM448USS` | 服装与服饰零售额 | 月度 | 百万美元 | 1992 |
| `MRTSSM445USS` | 食品与饮料商店零售额 | 月度 | 百万美元 | 1992 |
| `PCESV` | 服务类个人消费支出 | 月度 | 十亿美元 | 1959 |
| `PCDG` | 耐用品个人消费支出 | 月度 | 十亿美元 | 1959 |
| `PCND` | 非耐用品个人消费支出 | 月度 | 十亿美元 | 1959 |
| `PSAVERT` | 个人储蓄率（Personal Saving Rate） | 月度 | % | 1959 |
| `UMCSENT` | 密歇根大学消费者信心指数 | 月度 | 指数 | 1978 |

---

## 11. 工业景气与产能产出 (Industry & Output)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `INDPRO` | 工业生产总指数（Industrial Production Index） | 月度 | 指数 2017=100 | 1919 |
| `CAPUTL` | 工业综合产能利用率（Capacity Utilization） | 月度 | % | 1967 |
| `TCU` | 总产能利用率（Total Capacity Utilization） | 月度 | % | 1967 |
| `IPMAN` | 制造业生产指数 | 月度 | 指数 2017=100 | 1919 |
| `IPBUSEQ` | 商业设备生产指数 | 月度 | 指数 2017=100 | 1947 |
| `IPDCONGD` | 耐用消费品生产指数 | 月度 | 指数 2017=100 | 1919 |
| `BUSINV` | 全社会商业总库存 | 月度 | 百万美元 | 1947 |
| `AMTMNO` | 制造业耐用品新增订单 | 月度 | 百万美元 | 1992 |

---

## 12. 财政政策与政府债务 (Government & Debt)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `GFDEBTN` | 联邦公共债务总额（Total Public Debt） | 季度 | 十亿美元 | 1966 |
| `FYFSD` | 联邦财政年度预算赤字/盈余 | 年度 | 十亿美元 | 1901 |
| `FGEXPND` | 联邦政府现期支出总额 | 季度 | 十亿美元 | 1901 |
| `FGRECPT` | 联邦政府现期财政收入总额 | 季度 | 十亿美元 | 1901 |
| `MTSDS133FMS` | 公众持有的联邦债务总额 | 季度 | 十亿美元 | 1998 |
| `SLGPRI` | 州与地方政府支出 | 月度 | 十亿美元 | 1959 |

---

## 13. 国际贸易与对外收支 (International Trade)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `BOPGSTB` | 商品与服务贸易差额（Trade Balance） | 月度 | 百万美元 | 1992 |
| `BOPCAT` | 经常账户差额（Current Account Balance） | 季度 | 十亿美元 | 1960 |
| `IMPGS` | 商品与服务进口总额 | 月度 | 百万美元 | 1992 |
| `EXPGS` | 商品与服务出口总额 | 月度 | 百万美元 | 1992 |
| `M0892AUS000NNBR` | 贸易条件指数（Terms of Trade） | 季度 | 指数 | 1953 |

---

## 14. 能源与大宗商品 (Energy & Commodities)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `OILPRICE` | WTI 原油即期现货价格（Spot Crude Oil Price） | 日度 | 美元/桶 | 1946 |
| `GASREGCOV` | 全美常规汽油零售均价 | 周度 | 美元/加仑 | 1992 |
| `DHHNGSP` | 亨利港天然气现货价格（Henry Hub Natural Gas Spot） | 日度 | 美元/MMBTU | 1997 |
| `APU0000708111` | 居民用电平均价格 | 月度 | 美元/kWh | 1978 |
| `PI0120211` | 美国玉米价格 | 月度 | 美元/蒲式耳 | 1935 |
| `PI0120212` | 美国小麦价格 | 月度 | 美元/蒲式耳 | 1935 |
| `PI0120411` | 美国大豆价格 | 月度 | 美元/蒲式耳 | 1935 |

---

## 15. 衍生利差与量化模型衍生指标 (Calculated Spreads & Indicators)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `RECESSION` | NBER 经济衰退期间标志 | 月度 | 0/1 | 1854 |
| `USREC` | 美国经济衰退指标（1=衰退期） | 月度 | 0/1 | 1947 |
| `T10Y2Y` | 10 年期与 2 年期国债利差 | 日度 | % | 1976 |
| `T10Y3M` | 10 年期与 3 个月期国债利差 | 日度 | % | 1982 |
| `BAA10Y` | 穆迪 BAA 级企业债信用利差 | 日度 | % | 1986 |
| `T5YIE` | 5 年期通胀保值债券盈亏平衡通胀预期（5y Breakeven） | 日度 | % | 2003 |
| `T10YIE` | 10 年期通胀保值债券盈亏平衡通胀预期（10y Breakeven） | 日度 | % | 2003 |
| `STLFSI` | 圣路易斯联储金融压力指数（St. Louis Financial Stress Index） | 周度 | 指数 | 1993 |
| `NFCI` | 芝加哥联储全国金融状况指数（National Financial Conditions Index） | 周度 | 指数 | 1973 |

---

## 16. 经济衰退与系统性危机指标 (Recession & Crisis Indicators)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `USREC` | 官方经济衰退指示器（1=衰退，0=扩张） | 月度 | 0/1 | 1854 |
| `USRECDM` | NBER 官方衰退月度判定指示器 | 月度 | 0/1 | 1854 |
| `STLFSI` | 圣路易斯联储金融压力指数 | 周度 | 指数 | 1993 |
| `NFCI` | 全国金融状况指数（NFCI，低于 0 为宽松，高于 0 为紧缩） | 周度 | 指数 | 1973 |
| `TEDRATE` | TED 利差（3 个月期 LIBOR 利率减去 3 个月期美债收益率） | 日度 | % | 1986 |
| `DFII10` | 10 年期通胀保值国债（TIPS）实际收益率（10-Year TIPS Real Yield） | 日度 | % | 2003 |
| `EXPINF1YR` | 密歇根大学 1 年期预期通胀率（Expected Inflation 1-year） | 月度 | % | 1978 |
| `EXPINF10YR` | 密歇根大学 10 年期长期预期通胀率（Expected Inflation 10-year） | 月度 | % | 1978 |

---

## 17. 企业信用债券 (Corporate Bonds)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `BAA` | 穆迪 BAA 级投资级企业债平均收益率 | 日度 | % | 1919 |
| `AAA` | 穆迪 AAA 级高评级企业债平均收益率 | 日度 | % | 1919 |
| `BAA10Y` | 穆迪 BAA 级企业债与 10 年期国债信用利差 | 日度 | % | 1986 |
| `AAA10Y` | 穆迪 AAA 级企业债与 10 年期国债信用利差 | 日度 | % | 1986 |
| `MBAA` | 抵押贷款银行家协会综合指数（Mortgage Bankers Association Index） | 周度 | 指数 | 1990 |

---

## 18. 景气调查与情绪指标 (Sentiment & Surveys)

| 时序代码 | 描述 | 频率 | 单位 | 起始 |
|----------|------|------|------|------|
| `UMCSENT` | 密歇根大学消费者信心指数 | 月度 | 指数 | 1978 |
| `CSCICP03USM665S` | OECD 美国消费者信心指数（Consumer Confidence Index） | 月度 | 指数 | 1960 |
| `NAPM` | ISM 制造业采购经理人指数（ISM Manufacturing PMI） | 月度 | 指数 | 1948 |
| `ISM.NMI` | ISM 非制造业/服务业采购经理人指数（ISM Services PMI） | 月度 | 指数 | 1997 |
| `BPPRIV` | 私营企业生产景气指数 | 月度 | 指数 | 2003 |
| `NFCI` | 芝加哥联储全国金融状况指数 | 周度 | 指数 | 1973 |

---

## 19. 重点区域经济指标（精选）

| 时序代码 | 描述 | 频率 | 单位 |
|----------|------|------|------|
| `NYURSA` | 纽约州失业率（季调） | 月度 | % |
| `CAURSA` | 加利福尼亚州失业率（季调） | 月度 | % |
| `TXURSA` | 得克萨斯州失业率（季调） | 月度 | % |
| `FLURSA` | 佛罗里达州失业率（季调） | 月度 | % |
| `NYBPPRIV` | 纽约州私营企业生产指数 | 月度 | 指数 |
| `CAHOUST` | 加利福尼亚州新屋开工量 | 月度 | 千套 |

---

## 如何检索更多时间序列

调用 FRED 搜索端点 `series/search`，设置 `search_type=full_text`：

```python
import requests
API_KEY = "YOUR_API_KEY"
params = {
    "api_key": API_KEY,
    "file_type": "json",
    "search_text": "unemployment rate youth",
    "search_type": "full_text",
    "limit": 50
}
r = requests.get("https://api.stlouisfed.org/fred/series/search", params=params)
```

或直接使用配套脚本 [`search_series.py`](../scripts/search_series.py)。

---

## 常用筛选过滤标签 (Useful Tags)

| 标签 (Tag) | 描述 |
|------------|------|
| `daily` | 日度更新频率 |
| `monthly` | 月度更新频率 |
| `quarterly` | 季度更新频率 |
| `annual` | 年度更新频率 |
| `weekly` | 周度更新频率 |
| `seasonally adjusted` | 季调数据（SA） |
| `not seasonally adjusted` | 非季调数据（NSA） |
| `nation` | 全美全国性数据 |
| `regional` | 区域/州级数据 |
| `industry` | 行业细分数据 |
| `money` | 货币与流动性 |
| `interest rate` | 利率与收益率 |
| `inflation` | 通胀指标 |
| `employment` | 就业与失业 |
| `gdp` | 国内生产总值相关 |
| `housing` | 房地产与建筑 |
