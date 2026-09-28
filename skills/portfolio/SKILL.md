---
name: portfolio
description: "量化投资组合构建与优化框架：马科维茨均值-方差优化（scipy.optimize + 蒙特卡洛模拟）、黑-莱特曼（Black-Litterman）模型（CAPM市场均衡先验、绝对/相对主观观点、贝叶斯后验更新）、HRP/HERC/NCO（层次聚类、风险平价、带约束NCO嵌套聚类优化）。纯NumPy与SciPy平坦化实现，无需Riskfolio-Lib或PyPortfolioOpt依赖。"
license: MIT
---

# Portfolio — 投资组合量化构建与优化技能

本技能基于课程理论体系（教学笔记本 `Clase_08_teoria_2025_portafolio.ipynb` 与课件讲义 `Portafolios 2025 Ucema.pdf`），完整实现了 **3 种主流投资组合优化范式**：

1. **马科维茨现代投资组合理论（MPT / 均值-方差优化）** — 基于 `scipy.optimize` 的凸优化求解器 + 蒙特卡洛海量随机权重模拟 + 有效前沿（Efficient Frontier）绘制 + 资本市场线（CML）杠杆/去杠杆配置。
2. **黑-莱特曼（Black-Litterman）模型** — 贝叶斯统计推断框架，将反向 CAPM 计算的市场均衡先验收益率与投资者的绝对/相对主观观点相融合，集成基于 Idzorek 方法的主观观点不确定性协方差矩阵 $\Omega$ 标定。
3. **层次化投资组合构建（HRP / HERC / NCO）** — 基于图论与机器学习层次聚类（单联动/全联动/平均/Ward 方法）、分层风险平价（Risk Parity）以及带约束条件的嵌套聚类优化（Nested Clustered Optimization, NCO）。

所有脚本仅依赖 `numpy`、`pandas` 和 `scipy`，无任何庞大第三方黑盒库。
本技能具备**高度自治性**：无需依赖 `skills/backtesting` 即可独立运行。

组合优化求解完成后的多维绩效比率评估（夏普、索提诺、VaR、回撤分析等），可无缝衔接姊妹技能：
[`skills/backtesting`](https://github.com/gauss314/skills/tree/main/skills/backtesting)。

项目属于 [Gauss314 Skills 技能代码库](https://github.com/gauss314/skills)。

---

## 目录结构映射

```
skills/portfolio/
├── SKILL.md                           ← 本说明文档
├── references/
│   ├── PORTFOLIO_THEORY.md            ← 现代投资组合理论（MPT）、马科维茨模型、有效前沿推导
│   ├── BLACK_LITTERMAN.md             ← 黑-莱特曼模型：先验推导、主观观点、贝叶斯后验与 Omega 矩阵
│   ├── HIERARCHICAL.md                ← 层次化机器学习方法：HRP、HERC、NCO 与层次聚类
│   └── RISK_MEASURES.md               ← 组合风险度量：VaR、CVaR、MAD、MSV、分散化比率、最大回撤
├── assets/
│   ├── sample_prices.csv              ← 示例用多资产历史价格数据
│   ├── sample_returns.csv             ← 示例用多资产收益率数据
│   ├── sample_mcaps.json              ← 用于黑-莱特曼反向推导的市场基准流通市值
│   └── defaults.json                  ← 默认超参数配置
├── scripts/
│   ├── __init__.py
│   ├── portfolio.py                   ← 核心算法：马科维茨优化、最大夏普、蒙特卡洛模拟、有效前沿
│   ├── black_litterman.py             ← 黑-莱特曼完整算法：先验均衡、观点矩阵、后验收益、Idzorek Omega
│   ├── hierarchical.py                ← 层次化组合算法：HRP、HERC、NCO、分层风险平价、约束优化
│   ├── risk_measures.py               ← 风险度量库：VaR、CVaR、MAD、MSV、MDD、分散化比率
│   ├── covariance.py                  ← 协方差估计：样本协方差、Ledoit-Wolf 收缩、OAS 收缩、EWMA
│   └── cli.py                         ← 统一命令行 CLI（提供 12 种运行模式）
└── tests/
    ├── __init__.py
    └── test_portfolio.py              ← 自动化单元测试与对照验证
```

### 各脚本职责分工

| 脚本文件 | 角色说明 | 核心函数 |
|--------|-----|----------------|
| `portfolio.py` | 马科维茨均值-方差优化核心 | `max_sharpe_optim`, `min_variance_optim`, `random_portfolios`, `efficient_frontier`, `cml_portfolio`, `asset_stats` |
| `black_litterman.py` | 黑-莱特曼（Black-Litterman）全流程 | `market_implied_risk_aversion`, `market_implied_prior_returns`, `bl_posterior_returns`, `omega_idzorek` |
| `hierarchical.py` | 机器学习层次化组合（HRP / HERC / NCO） | `hrp_portfolio`, `herc_portfolio`, `nco_portfolio`, `nco_with_constraints`, `hrp_constraints` |
| `risk_measures.py` | 投资组合风险度量指标计算 | `var_historic`, `cvar`, `max_drawdown`, `cdar`, `diversification_ratio`, `risk_contribution` |
| `covariance.py` | 稳健协方差矩阵估计与收缩技术 | `cov_hist`, `cov_ledoit_wolf`, `cov_oas`, `cov_ewma` |

---

## 快速上手

### 马科维茨均值-方差优化（基于 scipy.optimize）

```bash
# 求解多资产的最大夏普比率（Max Sharpe）最优投资组合
py scripts/cli.py markowitz --assets assets/sample_returns.csv

# 指定自定义无风险利率 rf
py scripts/cli.py markowitz --assets assets/sample_returns.csv --rf 0.05

# 输出各单资产的基础统计量（年化收益率、年化波动率、个别夏普）
py scripts/cli.py stats --assets assets/sample_returns.csv
```

### 蒙特卡洛随机模拟（Monte Carlo）

```bash
# 随机模拟生成 10,000 个随机权重组合
py scripts/cli.py montecarlo --assets assets/sample_returns.csv

# 将模拟计算生成的有效前沿散点导出为 CSV 文件
py scripts/cli.py montecarlo --assets assets/sample_returns.csv --save frontier.csv
```

### 有效前沿精确计算（Efficient Frontier）

```bash
# 沿着目标收益率区间精确数值求解 50 个有效前沿边界点
py scripts/cli.py frontier --assets assets/sample_returns.csv --n 50
```

### 资本市场线（CML）— 杠杆借贷与去杠杆

切点投资组合（即最大夏普组合）与无风险资产进行线性组合，即可在保持夏普比率完全不变的前提下，在资本市场线（CML）上任意滑动定制预期风险收益：

```bash
# 纯切点组合（风险资产权重 w = 1.0）
py scripts/cli.py cml --assets assets/sample_returns.csv --weight 1.0

# 去杠杆（Deleverage）：60% 配置于切点组合，40% 配置于无风险资产（更低波动，夏普不变）
py scripts/cli.py cml --assets assets/sample_returns.csv --weight 0.6

# 杠杆借贷（Leverage）：以无风险利率借入 50% 本金，总计 150% 资金投资于切点组合（承担更高波动博取超额回报，夏普不变）
py scripts/cli.py cml --assets assets/sample_returns.csv --weight 1.5
```

### 黑-莱特曼（Black-Litterman）模型

```bash
# 仅计算先验：基于 CAPM 反向求解全市场均衡隐含预期收益率
py scripts/cli.py bl-prior --assets assets/sample_returns.csv --market-prices assets/sample_prices.csv --mcaps assets/sample_mcaps.json

# 完整黑-莱特曼贝叶斯更新：融入绝对/相对主观观点与置信度，并执行最优资产配置
py scripts/cli.py bl --assets assets/sample_returns.csv --market-prices assets/sample_prices.csv --mcaps assets/sample_mcaps.json --views '{"BMA": 0.25, "LOMA": 0.4, "MELI": -0.1}' --confidences "0.3,0.5,0.8" --optimize
```

### 层次化投资组合优化（HRP / HERC / NCO）

```bash
# 层次化风险平价（Hierarchical Risk Parity, HRP）
py scripts/cli.py hrp --assets assets/sample_returns.csv

# 嵌套聚类优化（Nested Clustered Optimization, NCO，指定 3 个主聚类簇）
py scripts/cli.py nco --assets assets/sample_returns.csv --clusters 3

# 融入行业分类与权重上下限约束的 NCO 求解
py scripts/cli.py nco-con --assets assets/sample_returns.csv --constraints assets/sample_constraints.csv --classes assets/sample_classes.csv
```

### 投资组合风险度量

```bash
# 一键计算全套风险度量指标
py scripts/cli.py risk --prices assets/sample_prices.csv

# 仅计算指定的单项风险指标（如 VaR）
py scripts/cli.py risk --prices assets/sample_prices.csv --measure var
```

---

## 作为 Python 代码库调用

```python
from scripts.portfolio import *
from scripts.black_litterman import *
from scripts.hierarchical import *

import numpy as np
import pandas as pd

# --- 马科维茨均值-方差优化 ---
rets = pd.read_csv('assets/sample_returns.csv', index_col=0)
result = max_sharpe_optim(rets, rf=0.045)
print(result['weights'], result['sharpe'])  # 最优配置权重、最优夏普比率

# --- 资本市场线 (CML): 杠杆与去杠杆 ---
# 60% 权重配置于切点组合，40% 配置于无风险资产 (去杠杆)
cml = cml_portfolio(rets, rf=0.045, weight_tangency=0.6)
print(cml['ret'], cml['vol'], cml['sharpe'])  # 夏普比率与切点组合严格保持一致

# 150% 权重配置于切点组合 (以无风险利率借入 50% 资金杠杆)
cml2 = cml_portfolio(rets, rf=0.045, weight_tangency=1.5)
print(cml2['ret'], cml2['vol'], cml2['sharpe'])  # 夏普比率完全一致

# --- 蒙特卡洛随机模拟 ---
port_df = random_portfolios(rets, n_portfolios=10000, rf=0.045)
best = port_df.loc[port_df['sharpe'].idxmax()]
print(best['weights'])  # 蒙特卡洛抽样中的最佳权重组合

# --- 黑-莱特曼模型 ---
import json
with open('assets/sample_mcaps.json') as f:
    mcaps = json.load(f)
spy = pd.read_csv('assets/sample_prices.csv')['SPY'].pct_change().dropna()
bl_result = bl_pipeline(rets, spy.values, mcaps,
                        view_dict={'BMA': 0.25, 'LOMA': 0.4},
                        view_confidences=[0.3, 0.5], rf=0.045)
print(bl_result['posterior'])  # 输出经贝叶斯更新后的后验期望收益率

# --- 层次化风险平价 (HRP) ---
hrp_result = hrp_portfolio(rets, linkage_method='ward')
print(hrp_result['weights'])  # 输出 HRP 层次风险平价分配的资产权重
```

---

## 环境依赖说明

| 依赖库 | 是否必需 | 主要用途 |
|----------|:---------:|-----|
| `numpy` | ✅ | 纯向量化数值计算、线性代数矩阵运算 |
| `pandas` | ✅ | 数据读写解析、时间序列对齐、DataFrame 操作 |
| `scipy` | ✅ | `optimize`（凸优化求解）、`cluster.hierarchy`（HRP/NCO 层次聚类）、`stats` |

**完全无需依赖** Riskfolio-Lib, PyPortfolioOpt, sklearn, cvxpy 或 arch。

如需绘制可视化图表（聚类树状图、有效前沿曲线），可选用 `matplotlib`。参考 notebook 中提供了丰富的绘图算例。

---

## 经典学术理论文献

- **Markowitz (1952)**: "Portfolio Selection", *Journal of Finance*.
- **Black & Litterman (1992)**: "Global Portfolio Optimization", *Financial Analysts Journal*.
- **Idzorek (2005)**: "A Step-by-Step Guide to the Black-Litterman Model".
- **Lopez de Prado (2016)**: "Building Diversified Portfolios that Outperform Out of Sample" (HRP).
- **De Prado (2019)**: "Nested Clustered Optimization", [SSRN 3469961](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3469961).
- **Pfitzinger & Katzke (2019)**: "NCO with Constraints", [SSRN 4409173](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4409173).
- **Meucci (2006)**: "Beyond Black-Litterman: Views on Non-Normal Markets", [SSRN 1213325](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1213325).
- **Avramov (2004)**: "Bayesian Variable Selection in Portfolio Analysis", [SSRN 3326617](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3326617).

若需进一步计算**组合绩效比率**（30+ 项指标：夏普、索提诺、VaR、cVaR、凯利公式、拉切夫比率、利润因子等）以及执行完整的**策略回测**：
请参阅姊妹技能 [`skills/backtesting`](https://github.com/gauss314/skills/tree/main/skills/backtesting)。

---

## 参考教学 Notebook

本技能的理论推导与数值基准算例取材自：
- `temp/Clase_08_teoria_2025_portafolio.ipynb` — Markowitz、Monte Carlo、NCO（Riskfolio-Lib）、Black-Litterman（PyPortfolioOpt）的教学实现。
- `temp/Portafolios 2025 Ucema.pdf` — 完整理论概念框架：现代资产组合理论（MPT）、CAPM 资本资产定价模型、Fama-French 多因子、层次聚类算法、NCO、黑-莱特曼模型。

位于 `scripts/` 下的**纯 NumPy 平坦化实现**在完全剥离复杂外部黑盒依赖的同时，完美复现了前述教学资料的所有量化计算结果。
