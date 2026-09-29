---
name: backtesting
description: "用于量化研究的学术级回测框架。包含约30个风险与收益比率指标、10类量化特征指标、内置6+策略的事件驱动回测引擎、现代资产组合理论（MPT）优化器、基于Johnson SU分布与t-Copula的前瞻性模拟、走步向前交叉验证（Walk-Forward CV）、压力测试以及基本面分析（Altman Z值、Piotroski F分数、杜邦分析）。纯Python与NumPy实现。"
license: MIT
---

# Backtesting — 全功能回测技能

本技能完整实现了课程体系中的 **5阶段回测方法论**：
数据（Data）→ 研究（Research）→ 指标评估（Metrics）→ 参数化寻优（Parameterisation）→ 严谨验证（Validation）。主要功能包含：

- **30+ 个风险/收益比率指标**（平坦化函数设计，NumPy 向量化加速，无冗余面向对象开销）
- **10 类特征指标**，严格遵循课程分类法（趋势跟踪、振荡器、均值回归/反转、成交量/资金流、组合指标、离散计数、季节性/周期、统计学指标、基准参照、基本面指标）
- **事件驱动回测引擎**，内置 8 种开箱即用的经典量化策略
- **前瞻性仿真模拟**（Johnson SU 边际分布拟合 + t/高斯 Copula 联合分布建模）
- **现代投资组合理论**（马科维茨有效前沿优化、组合之组合优化）
- **走步向前交叉验证（Walk-forward CV）**，支持样本内（IS）/样本外（OOS）切分与防数据泄露隔离期（Gap）
- **压力测试**，基于参数化场景冲击模拟
- **基本面量化分析**（Altman Z-Score 破产预测、Piotroski F-Score 财务质量、杜邦五因子分解）

所有脚本仅依赖 `numpy`、`pandas` 和 `scipy`，无任何庞大笨重依赖项。

项目属于 [Gauss314 Skills 技能代码库](https://github.com/gauss314/skills)。

---

## 目录结构映射

```
skills/backtesting/
├── SKILL.md                         ← 本说明文档
├── references/
│   ├── BACKTESTING_THEORY.md        ← 理论概念框架：GIGO原则、回测不可能三角、5阶段流程
│   ├── RATIOS.md                    ← 指标数学公式、收益率计算口径惯例、实盘避坑警告
│   ├── FEATURES.md                  ← 10类量化技术与统计指标体系及 Alpha 边缘优势
│   ├── SIMULATIONS.md               ← Johnson SU + Copula 仿真建模全流程
│   ├── VALIDATION.md                ← 4层多维度回测验证测试套件
│   └── OTHER_FEATURES.md            ← 基本面因子、情绪分析与外生宏观特征
├── assets/
│   ├── sp500_returns.csv            ← 标普500基准日收益率数据（线性+对数），1980年至今
│   ├── momentum_sma50_200_returns.csv ← 双均线 SMA(50)/SMA(200) 交叉动量策略收益率
│   ├── contrarian_bbands_returns.csv  ← 布林带反转均值回归策略收益率
│   ├── sample_portfolios.json       ← 著名投资者真实投资组合持仓（巴菲特、达利欧、阿克曼、60/40）
│   ├── defaults.json                ← 默认参数配置（VaR置信度alpha、滚动窗口等）
│   └── validation_cases.json        ← 6个用于比率指标校验的基准测试算例
├── scripts/
│   ├── __init__.py
│   ├── ratios.py                    ← 30+ 纯NumPy平坦化向量计算函数（所有风险与收益指标）
│   ├── indicators.py                ← 10类技术/统计/基本面指标计算模块
│   ├── engine.py                    ← 事件驱动 BacktestEngine 回测引擎及8个内置策略
│   ├── backtesting.py               ← 核心CLI工具：run、sweep、walkforward、montecarlo、optmpt、event、validate
│   ├── simulations.py               ← 蒙特卡洛与Copula CLI：marginal、copula、run、portfolio、scenarios
│   ├── forward.py                   ← 前瞻性风险与压力测试CLI：project、risk、stress、summary
│   ├── distributions.py             ← 分布拟合与KS检验（正态分布、t分布、非中心t分布、拉普拉斯分布、Johnson SU分布）
│   ├── copulas.py                   ← t/高斯/Clayton/Gumbel/Frank Copula 联合分布拟合与随机抽样
│   ├── fundamental_ratios.py        ← 损益/资产负债/现金流指标、杜邦分析、Altman Z、Piotroski F
│   └── validate.py                  ← 4层验证套件：CLI模式、数学自洽性、极端边界值测试、回归测试
└── tests/
    └── test_ratios.py               ← 核心比率指标的18个 pytest 单元测试
```

### 各核心文件职责

| 文件 | 角色说明 | 核心函数 / 运行模式 |
|------|------|-----------------------|
| `ratios.py` | 核心指标计算库。所有指标均为接收一维数组的平坦函数。 | `sharpe_ratio`, `max_drawdown`, `var_all`, `cvar_all`, `kelly_fraction`, `payoff_ratio`, `profit_factor`, `rachev_a/b/c`, `common_sense_ratio`, `ruin_curve`, `compute_all` |
| `indicators.py` | 10类特征指标，覆盖量化特征体系的所有类型。 | `rsi`, `adx`, `bbands`, `macd`, `atr`, `cross_indicator`, `range_bound`, `zscore_norm`, `poisson_rate`, `binomial_ratio`, `fourier_terms`, `best_fit_dist` |
| `engine.py` | 事件驱动回测引擎类 `BacktestEngine` 与 8 种内置策略函数。 | `BacktestEngine`, `strategy_sma_crossover`, `strategy_rsi_cross`, `strategy_bbands_contrarian`, `strategy_growth_momentum_combo` |
| `backtesting.py` | 主命令行入口。执行完整回测、网格搜索、走步向前验证、组合优化。 | `run`, `sweep`, `walkforward`, `montecarlo`, `optmpt`, `event`, `validate`, `bench` |
| `simulations.py` | 基于 Johnson SU 边际分布与 Copula 联合分布的前瞻性模拟 CLI。 | `marginal`, `copula`, `run`, `portfolio`, `scenarios` |
| `forward.py` | 风险投射前瞻模拟与极端压力测试 CLI。 | `project`, `risk`, `stress`, `summary` |
| `distributions.py` | 统计概率分布拟合、拟合优度比较与随机抽样。 | `fit`, `best_fit`, `compare_distributions`, `sample` |
| `copulas.py` | 多资产 Copula 依赖结构拟合与联合模拟抽样。 | `fit_t`, `fit_gaussian`, `sample_t`, `sample_gaussian`, `validate_copula` |
| `fundamental_ratios.py` | 基本面量化分析与财务健康度指标计算。 | `income_metrics`, `valuation_metrics`, `dupont`, `altman_z`, `piotroski` |
| `validate.py` | 4层集成测试验证套件。 | 覆盖CLI、数学自洽性、边界条件、回归测试的33项严格检查 |

---

## 快速上手

### 基础比率指标计算

```bash
# 基于价格序列 CSV 文件计算全部 30+ 项风险/收益指标
py scripts/backtesting.py run --prices assets/sp500_returns.csv

# 结合基准收益率对比计算超额收益与相对风险指标
py scripts/backtesting.py run --prices assets/momentum_sma50_200_returns.csv --benchmark assets/sp500_returns.csv
```

### 执行回测验证（4层测试套件）

```bash
# 执行完整验证（涵盖4个维度的33项检查）
py scripts/validate.py

# 仅执行指定级别的测试（如第1层）
py scripts/validate.py --nivel 1
```

验证内容包括 CLI 各模式连通性、各指标的数学理论自洽性、极端边界值鲁棒性以及缺陷修复后的防劣化回归测试。详细检查项参见 [`references/VALIDATION.md`](./references/VALIDATION.md)。

### 事件驱动回测

```bash
# 加载包含 OHLCV（开高低收量）的行情数据并运行双均线交叉策略
py scripts/backtesting.py event --data my_stock.csv --strategy sma_crossover --fast 50 --slow 200 --commission 0.001
```

### 参数网格扫描（Parameter Sweep）

```bash
# 对快/慢均线窗口进行单参数或双参数网格搜索
py scripts/backtesting.py sweep --prices assets/sp500_returns.csv --p1-min 10 --p1-max 100 --p1-step 10
# 双参数联合扫描
py scripts/backtesting.py sweep --prices assets/sp500_returns.csv --p1-min 10 --p1-max 50 --p1-step 5 --p2-min 25 --p2-max 200 --p2-step 25
```

### 走步向前验证（Walk-Forward）

```bash
py scripts/backtesting.py walkforward --prices assets/sp500_returns.csv --splits 5 --gap 21
```

### 马科维茨组合优化（MPT Optimization）

```bash
py scripts/backtesting.py optmpt --assets assets/sp500_returns.csv --iterations 5000
```

### 前瞻仿真模拟（Forward Simulation）

```bash
py scripts/simulations.py marginal --returns assets/sp500_returns.csv
py scripts/simulations.py copula --returns assets/sp500_returns.csv --df 4
py scripts/forward.py project --returns assets/sp500_returns.csv --horizon 252 --paths 10000 --drift 0.08
py scripts/forward.py risk --returns assets/sp500_returns.csv --horizon 252 --paths 10000
```

### 投资组合模拟与场景测试

```bash
py scripts/simulations.py portfolio --name warren_buffett
py scripts/simulations.py scenarios --name warren_buffett --cagr -0.3,-0.15,0,0.2,0.35,0.5
```

---

## 作为 Python 库调用比率计算模块

```python
from scripts.ratios import *

prices = np.array([100, 105, 102, 110, 108, 115])
r = linear_returns(prices)    # [0.05, -0.0286, 0.0784, -0.0182, 0.0648]
lr = log_returns(prices)      # [0.0488, -0.0290, 0.0755, -0.0183, 0.0628]

sharpe_ratio(r)               # 0.847
max_drawdown(prices)          # -0.0370
kelly_fraction(lr)            # 0.0793
var_all(r, alpha=0.05)        # {'empirical': ..., 'normal': ..., 'johnsonsu': ...}
profit_factor(lr)             # 2.314
payoff_ratio(lr)              # 1.578
rachev_c(lr, alpha=0.05)      # 1.234
common_sense_ratio(lr)        # 2.856
```

## 使用事件驱动引擎

```python
from scripts.engine import BacktestEngine

eng = BacktestEngine(initial_capital=1.0, commission=0.001, slippage=0.0005)
eng.load_data(df_ohlcv)
result = eng.run(strategy='sma_crossover', strategy_params={'fast': 50, 'slow': 200})

print(result['metrics']['sharpe_ratio'])     # 0.847
print(result['trades'])
print(result['metrics'])
```

---

## 环境依赖

| 依赖库 | 是否必需 | 用途说明 |
|---------|:--------:|----------|
| `numpy` | ✅ | 向量化数值计算、多维数组、累计收益运算 |
| `pandas` | ✅ | CSV 数据读取、滚动窗口计算、DataFrame 数据结构 |
| `scipy.stats` | ✅ | 概率分布拟合、KS 拟合优度检验、Copula 联合分布 |
| `statsmodels` | 可选 | 用于 `indicators.py` 中的 STL 季节性趋势分解（第5类） |

若要运行完整的4层验证套件（`py scripts/validate.py`），还需要安装 `pytest` 用于执行第4层防劣化回归测试。

无需引入 `arch`、`quantlib`、`sklearn` 等重型依赖。

---

## 参考与延伸阅读

- [Gauss314 Skills 技能代码库](https://github.com/gauss314/skills) — 更多金融数据与量化技能
- `references/BACKTESTING_THEORY.md` — 回测理论概念框架（GIGO原则、不可能三角、5阶段流程）
- `references/RATIOS.md` — 指标计算公式、收益率口径、实盘陷阱
- `references/FEATURES.md` — 10类指标体系与特征工程
- `references/SIMULATIONS.md` — Johnson SU + Copula 前瞻性模拟流程
- `references/VALIDATION.md` — 4层回测验证测试体系详解
- `references/OTHER_FEATURES.md` — 基本面因子、情绪分析与外生宏观特征
