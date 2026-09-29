# 投资组合风险度量指标

## 离散度与波动性度量（Dispersion Measures）

| 风险指标 | 数学公式 | 概念说明 |
|--------|---------|-------------|
| **波动率（MV）** | $\sqrt{w^T \Sigma w}$ | 投资组合收益率的加权总体标准差 |
| **平均绝对偏差（MAD）** | $\text{mean}(\|r - \text{mean}(r)\|)$ | 各期收益率偏离期望均值的平均绝对距离，对离群异常值不如方差敏感 |
| **下行半离差（MSV）** | $\sqrt{\text{mean}(r_{\text{neg}}^2)}$ | 仅对低于目标（负收益）的下行亏损部分计算标准差，排除了向上波动 |

## 风险价值（Value at Risk, VaR）

在给定的 $(1 - \alpha)$ 置信水平下，资产组合在特定时间区间内预期的最大可能损失幅度：

| 计算方法 | 算法机制与说明 |
|--------|-------------|
| `var_historic` | 历史模拟法：直接基于历史收益率经验样本的第 $\alpha$ 分位数计算 |
| `var_gaussian` | 参数正态法：假设收益率服从正态分布，利用 $\mu - z_{\alpha} \cdot \sigma$ 解析求解 |

## 条件风险价值（CVaR / Expected Shortfall）

在最恶劣的 $\alpha\%$ 极端尾部暴跌情形下，投资组合发生亏损的条件期望均值：

```
CVaR = mean(r[r <= VaR(alpha)])
```

CVaR 满足一致性风险度量（Coherent Risk Measure）的次可加性公理，且其损失数值在任何时候都比单纯的 VaR 更具破坏性（数值绝对值更大）。

## 回撤度量（Drawdown Measures）

| 风险指标 | 数学公式与定义 | 金融意义 |
|--------|-------------|-------------|
| **最大回撤（MDD）** | $\min(P / \text{cummax}(P) - 1)$ | 从历史累计最高点到后续最低谷底的最大跌幅百分比 |
| **条件回撤风险（CDaR）** | 最差 $\alpha\%$ 深度回撤样本的条件期望均值 | 评估投资组合在极端危机下的平均回撤深度，比单点 MDD 更具统计稳定性 |
| **卡玛比率（Calmar Ratio）** | 年化复合收益率 / \|MDD\| | 每承担一单位历史最大极端回撤所换取的年化收益补偿 |

## 资产分散化与风险贡献度量（Diversification）

| 评估指标 | 数学公式与机制 | 说明与用途 |
|--------|-------------|-------------|
| **分散化比率（DR）** | $\sum (w_i \cdot \sigma_i) / \sigma_p$ | 资产独立波动率加权和与整体组合波动率的比值（$\text{DR} \ge 1$），数值越高代表资产间相关性越低、分散化分散风险效果越强 |
| **边际风险贡献（Risk Contribution）** | $RC_i = w_i \cdot \frac{(\Sigma w)_i}{\sigma_p}$ | 单个资产对组合总波动率的边际贡献额，满足 $\sum RC_i = \sigma_p$ |
| **百分比风险贡献（Risk Contribution %）** | $RC_i / \sigma_p$ | 各资产风险贡献占组合总风险的百分比，风险平价（Risk Parity）要求各资产的该数值相等 |

## 教学 Notebook 与 Riskfolio-Lib 体系对应度量字典表

| 指标键名 | 风险指标名称与描述 |
|-------|-------------|
| `'vol'` | 总体标准差 / 年化波动率 |
| `'MV'` | 组合方差（Variance） |
| `'KT'` | 收益率峰度平方根（Square Root of Kurtosis） |
| `'MAD'` | 平均绝对偏差（Mean Absolute Deviation） |
| `'MSV'` | 下行半离差 / 下行半标准差（Semi-Standard Deviation） |
| `'SKT'` | 下行半峰度平方根（Square Root of Semi-Kurtosis） |
| `'FLPM'` | 一阶下行偏矩（First Lower Partial Moment，对应 Omega 比率） |
| `'SLPM'` | 二阶下行偏矩（Second Lower Partial Moment，对应 Sortino 比率） |
| `'VaR'` | 风险价值（Value at Risk） |
| `'CVaR'` | 条件风险价值 / 期望亏损（Conditional Value at Risk / Expected Shortfall） |
| `'TG'` | 尾部基尼系数（Tail Gini） |
| `'EVaR'` | 熵风险价值（Entropic Value at Risk） |
| `'RLVaR'` | 相对论风险价值（Relativistic Value at Risk） |
| `'WR'` | 最坏样本极值（Worst Realization / Minimax 极小极大化准则） |
| `'RG'` | 收益率波动极差范围（Range of Returns） |
| `'CVRG'` | 条件风险价值区间（CVaR Range） |
| `'MDD'` | 最大回撤（Maximum Drawdown，常用于最大化 Calmar 目标） |
| `'DaR'` | 回撤风险价值（Drawdown at Risk） |
| `'CDaR'` | 条件回撤风险价值（Conditional Drawdown at Risk） |
| `'EDaR'` | 熵回撤风险价值（Entropic Drawdown at Risk） |
| `'UCI'` | 溃疡指数（Ulcer Index，综合考虑回撤深度与持续时间的复合惩罚指标） |
| `'DR'` | 分散化比率（Diversification Ratio） |
| `'DD'` | 分散化增量（Diversification Delta） |
| `'RCE'` | 风险集中度等价数（Risk Concentration Equivalent） |
| `'NBE'` | 统计正交有效独立押注次数（Effective Number of Bets） |
