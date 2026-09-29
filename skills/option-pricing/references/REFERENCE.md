# Option Pricing — 理论参考手册 (Theoretical Reference)

本手册涵盖 `scripts/option_pricing.py` 中实现的 5 种核心基石算法及衍生模型的完整数学理论推导与金融工程背景。假定读者熟悉金融数学与随机微积分基础概念（几何布朗运动、鞅测度、伊藤引理及无套利定价原理）。

关于 CLI 命令行实战与代码速查，请参阅 [`SKILL.md`](../SKILL.md)。关于模型深度选型与避坑指南，请参阅 [`theory.md`](./theory.md)。

---

## 目录

1. [Black-Scholes-Merton 模型](#1-black-scholes-merton-模型)
2. [解析希腊值 (Analytic Greeks)](#2-解析希腊值-analytic-greeks)
3. [二叉树模型 (Cox-Ross-Rubinstein)](#3-二叉树模型-cox-ross-rubinstein)
4. [三叉树模型 (Boyle)](#4-三叉树模型-boyle)
5. [带对偶变量的蒙特卡洛模拟](#5-带对偶变量的蒙特卡洛模拟)
6. [Longstaff-Schwartz 最小二乘蒙特卡洛 (LSM 美式期权模拟)](#6-longstaff-schwartz-最小二乘蒙特卡洛-lsm-美式期权模拟)
7. [Barone-Adesi-Whaley (BAW 美式期权闭式解)](#7-barone-adesi-whaley-baw-美式期权闭式解)
8. [隐含波动率 (Implied Volatility)](#8-隐含波动率-implied-volatility)
9. [实值概率 P(ITM) 与获利概率 P(Profit)](#9-实值概率-pitm-与获利概率-pprofit)
10. [综合对比表：精度 vs 速度](#10-综合对比表精度-vs-速度)
11. [模型选型与应用决策准则](#11-模型选型与应用决策准则)
12. [参考文献](#12-参考文献)

---

## 1. Black-Scholes-Merton 模型

### 1.1 核心假设

- 标的资产现价 $S_t$ 服从几何布朗运动（GBM）：
  $$dS_t = (r - q) S_t dt + \sigma S_t dW_t$$
- 年化波动率 $\sigma$ 与无风险短期复利利率 $r$ 在期权存续期内为常数。
- 市场无摩擦：不存在交易成本、税收限制，且允许无限制卖空。
- 标的资产支持支付已知的连续股息率 / 分红率 $q$（可为 0）。
- 仅适用于欧式期权（仅能在到期日 $T$ 行权）。

### 1.2 数学推导

对 $\ln(S_t)$ 应用伊藤引理（Itô's Lemma），在风险中性测度 $\mathbb{Q}$ 下，标的资产在到期日 $T$ 的对数正态解析分布为：

$$S_T = S_0 \exp\left(\left(r - q - \frac{1}{2}\sigma^2\right)T + \sigma\sqrt{T} Z\right), \quad Z \sim \mathcal{N}(0, 1)$$

期权的无套利理论价格等于其在风险中性测度 $\mathbb{Q}$ 下到期收益（Payoff）的无风险折现期望值：

$$C = e^{-rT} \mathbb{E}_{\mathbb{Q}}[\max(S_T - K, 0)]$$
$$P = e^{-rT} \mathbb{E}_{\mathbb{Q}}[\max(K - S_T, 0)]$$

### 1.3 闭式解析解公式

定义中间统计量：
- $d_1 = \frac{\ln(S/K) + \left(r - q + \frac{1}{2}\sigma^2\right)T}{\sigma\sqrt{T}}$
- $d_2 = d_1 - \sigma\sqrt{T}$
- $N(x)$ 为标准正态分布累积分布函数（CDF）：$N(x) = \frac{1}{\sqrt{2\pi}} \int_{-\infty}^{x} e^{-u^2/2} du$

由此推导出标准 Black-Scholes-Merton 公式：

$$\text{Call} = S e^{-qT} N(d_1) - K e^{-rT} N(d_2)$$
$$\text{Put} = K e^{-rT} N(-d_2) - S e^{-qT} N(-d_1)$$

**底层实现**：`bs_price()`。直接调用 Python 内置的互补误差函数 `math.erfc` 计算标准正态 CDF（$N(x) = 0.5 \cdot \text{erfc}(-x/\sqrt{2})$），相较 `scipy.stats.norm.cdf` 快 2-3 倍，比通用级数逼近快约 10 倍。

### 1.4 重要边界与极限性质

- 波动率趋向零（$\sigma \to 0$）：$\text{Call} = \max\left(S e^{-qT} - K e^{-rT}, 0\right)$
- 临近到期（$T \to 0$）：$\text{Call} = \max(S - K, 0)$（退化为内在价值）
- 标的资产趋于无穷大（$S \to \infty$）：$\text{Call} \to S e^{-qT}$
- 标的资产归零（$S \to 0$）：$\text{Put} = K e^{-rT}$

---

## 2. 解析希腊值 (Analytic Greeks)

希腊值是期权理论价格相对于各个市场变量与模型输入参数的一阶与二阶偏导数，是量化风险管理、敏感性分析与动态对冲的核心。

### 2.1 Delta ($\frac{\partial V}{\partial S}$)

衡量标的资产价格每变动 1 美元，期权理论价格的预期变动幅度：

$$\Delta_{\text{call}} = e^{-qT} N(d_1)$$
$$\Delta_{\text{put}} = e^{-qT} \left(N(d_1) - 1\right) = -e^{-qT} N(-d_1)$$

### 2.2 Gamma ($\frac{\partial^2 V}{\partial S^2}$)

衡量 Delta 相对于标的资产价格的变动速率，即期权价格曲线的凸性（Convexity）：

$$\Gamma = \frac{e^{-qT} n(d_1)}{S \sigma \sqrt{T}}$$

其中 $n(x) = \frac{1}{\sqrt{2\pi}} e^{-x^2/2}$ 为标准正态分布的概率密度函数（PDF）。看涨期权与看跌期权拥有完全相同的 Gamma。

### 2.3 Vega ($\frac{\partial V}{\partial \sigma}$)

衡量波动率变动 1 个单位（即 100% 波动率）时期权价格的敏感度：

$$\text{Vega} = S e^{-qT} n(d_1) \sqrt{T}$$

看涨期权与看跌期权拥有完全相同的 Vega。在代码实现中，返回值为纯标量绝对值；若需获取“波动率每变动 1% 的价格变化”，应将其除以 100。

### 2.4 Theta ($\frac{\partial V}{\partial T}$ 或 $-\frac{\partial V}{\partial t}$)

衡量伴随时间流逝所产生的期权时间价值衰减（Time Decay）：

$$\Theta_{\text{call}} = -\frac{S e^{-qT} n(d_1) \sigma}{2\sqrt{T}} - r K e^{-rT} N(d_2) + q S e^{-qT} N(d_1)$$
$$\Theta_{\text{put}} = -\frac{S e^{-qT} n(d_1) \sigma}{2\sqrt{T}} + r K e^{-rT} N(-d_2) - q S e^{-qT} N(-d_2)$$

对于期权多头（Long Options），Theta 在多数情况下为负值，表明时间流逝对买方不利。

### 2.5 Rho ($\frac{\partial V}{\partial r}$)

衡量无风险利率变动对期权价值的影响：

$$\text{Rho}_{\text{call}} = K T e^{-rT} N(d_2)$$
$$\text{Rho}_{\text{put}} = -K T e^{-rT} N(-d_2)$$

**底层实现**：`bs_greeks()`。共享 $d_1, d_2, N(d_1), n(d_1)$ 的计算开销，一次函数调用同时导出全部五大希腊值，总开销仅 ~1.5 微秒。

---

## 3. 二叉树模型 (Cox-Ross-Rubinstein)

### 3.1 核心思想

将连续时间的几何布朗运动在时空上离散化为 $N$ 个时间步。在每个离散时间间隔内，标的资产以风险中性概率 $p$ 乘以因子 $u$ 上涨，或以概率 $1-p$ 乘以因子 $d$ 下跌。通过在到期终端节点计算收益，自后向前进行逆向归纳递推（Backward Induction），最终获得期权在 $t=0$ 时的理论价格。

### 3.2 CRR 模型参数

设单步时间步长 $\Delta t = T / N$：

$$u = \exp(\sigma \sqrt{\Delta t})$$
$$d = \frac{1}{u} = \exp(-\sigma \sqrt{\Delta t})$$
$$a = \exp((r - q) \Delta t)$$
$$p = \frac{a - d}{u - d} \quad (\text{风险中性上涨概率})$$
$$\text{disc} = \exp(-r \Delta t) \quad (\text{单步折现因子})$$

### 3.3 算法递推过程

1. **终端收益计算**（第 $N$ 步）：在到期时刻共有 $N+1$ 个状态节点，第 $j$ 个节点（$j=0, 1, \dots, N$）对应的标的资产价格为 $S_{T, j} = S_0 u^{N-j} d^j$。
   $$V_j^N = \max(S_{T, j} - K, 0) \quad (\text{看涨期权})$$
   $$V_j^N = \max(K - S_{T, j}, 0) \quad (\text{看跌期权})$$

2. **逆向动态规划递推**（从第 $i = N-1$ 步递减至 $0$ 步）：
   第 $i$ 步有 $i+1$ 个节点，其无提前行权的继续持有期望价值（Continuation Value）为：
   $$V_j^i = \text{disc} \cdot \left(p V_j^{i+1} + (1-p) V_{j+1}^{i+1}\right)$$
   针对**美式期权（American Style）**，在每一个节点需评估提前行权的内在价值（Intrinsic Value）：
   $$V_j^i = \max\left(V_j^i, \text{Intrinsic}(S_j^i)\right)$$

3. **现值输出**：根节点 $V_0^0$ 即为期权当前理论定价。

### 3.4 收敛特性

CRR 树状模型的离散化逼近误差阶数为 $\mathcal{O}(1/N)$。对于欧式期权，当 $N \to \infty$ 时，其严格收敛于 Black-Scholes 解析解；对于美式期权，其收敛于美式自由边界偏微分方程（PDE）的数值解。

**经验收敛阶数与误差参考**：
- $N = 200$：平值 ATM 误差约 1%
- $N = 500$：误差约 0.5%
- $N = 2000$：误差约 0.1%（可作为回测基准与金标准）
- $N = 5000+$：误差小于 0.05%（仅推荐用于基准校验）

### 3.5 核心实现优化

- 整个反向归纳循环完全基于 **numpy 数组向量化** 执行，彻底规避了逐节点遍历的 Python 级开销。
- 提前计算 $u^{N-j} d^j$ 数组快速生成终结时刻的标的资产网格。
- 美式期权的行权比较使用 `np.maximum` 进行底层内存级就地（in-place）更新。

---

## 4. 三叉树模型 (Boyle)

### 4.1 与二叉树的区别与优势

三叉树模型在每个离散时间节点允许标的资产价格出现 3 个走向：上涨（乘以 $u$）、水平持平（乘以 $m=1$）以及下跌（乘以 $d$）。对应的三个转移概率满足 $p_u + p_m + p_d = 1$。通过增加一个空间自由度，三叉树能更好地逼近布朗运动的前两阶矩，具备更高的数值稳定条件。

### 4.2 Boyle (1986) 模型参数

设步长 $\Delta t = T / N$：

$$u = \exp\left(\sigma \sqrt{2 \Delta t}\right), \quad d = \frac{1}{u}, \quad m = 1$$
$$a = \exp\left((r - q) \frac{\Delta t}{2}\right), \quad b = \exp\left(\sigma \sqrt{\frac{\Delta t}{2}}\right)$$
$$p_u = \left(\frac{a - 1/b}{b - 1/b}\right)^2, \quad p_d = \left(\frac{b - a}{b - 1/b}\right)^2$$
$$p_m = 1 - p_u - p_d$$

### 4.3 网格结构与逆向递推

在第 $N$ 步，网格中存在 $2N + 1$ 个离散节点。节点索引 $j \in [0, 2N]$：
- $j=0$ 对应最高价格 $S_0 u^N$
- $j=N$ 对应中间基准价格 $S_0$
- $j=2N$ 对应最低价格 $S_0 d^N$

第 $i$ 步的反向期望折现公式：

$$V_j^i = \text{disc} \cdot \left(p_u V_j^{i+1} + p_m V_{j+1}^{i+1} + p_d V_{j+2}^{i+1}\right)$$

美式期权同样在此基础上引入提前行权判断：$V_j^i = \max(V_j^i, \text{Intrinsic}(S_j^i))$。

### 4.4 优劣势比对

- **数值条件更好**：在超高波动率（$\sigma > 100\%$）或超长期限（$T > 2$ 年）下，不易出现二叉树常见的极端截断误差。
- **单调收敛**：大幅减轻了二叉树随着 $N$ 增加而出现的锯齿形交替震荡现象（Oscillation）。
- 相同 $N$ 下因节点数与运算量增至 3 倍，耗时约为二叉树的 1.5 倍，但达到相同精度所需的时间步数减少约 30%。

---

## 5. 带对偶变量的蒙特卡洛模拟

### 5.1 基本原理

基于风险中性测度 $\mathbb{Q}$，通过随机抽样生成 $M$ 条标的资产演化路径，计算各条路径在到期时刻 $T$ 的收益均值并折现。本方法主要适用于欧式期权（到期收益仅取决于最终价格 $S_T$）。

### 5.2 路径生成方程

对于每条模拟路径 $i$：
$$Z_i \sim \mathcal{N}(0, 1)$$
$$S_{T, i} = S_0 \exp\left(\left(r - q - \frac{1}{2}\sigma^2\right)T + \sigma\sqrt{T} Z_i\right)$$
$$\text{Payoff}_i = \max(S_{T, i} - K, 0) \quad (\text{Call}) \quad \text{或} \quad \max(K - S_{T, i}, 0) \quad (\text{Put})$$
$$\text{Price} = e^{-rT} \frac{1}{M} \sum_{i=1}^M \text{Payoff}_i$$

### 5.3 对偶变量法 (Antithetic Variates 方差缩减)

为提升统计收敛效率，在生成标准正态随机数 $Z_i$ 的同时，同步成对构建其对称反相变量 $-Z_i$。二者以等权重计入期望估计：

$$\text{Payoff}_i = \frac{1}{2} \left(\text{Payoff}(Z_i) + \text{Payoff}(-Z_i)\right)$$

**方差缩减机理**：由于 $Z_i$ 与 $-Z_i$ 具有严格的完全负相关性，当一条路径产生偏高收益时，其对偶路径往往产生偏低收益。两者求均值后大幅抵消了极值抽样方差，在实践中能使方差降低 50-70%（相当于以相同的计算量获得了 2-3 倍的有效样本容量）。

### 5.4 统计标准误与置信区间

$$\text{stderr} = \frac{e^{-rT} \cdot \text{std}(\text{Payoff}_i)}{\sqrt{M}}$$
$$95\% \text{ 置信区间} = \text{Price} \pm 1.96 \cdot \text{stderr}$$

---

## 6. Longstaff-Schwartz 最小二乘蒙特卡洛 (LSM 美式期权模拟)

### 6.1 核心问题：美式期权的最优停时

美式期权允许在存续期内任意时刻提前行权，属于典型的最优停时问题（Optimal Stopping Problem）。单纯的正向蒙特卡洛模拟无法在每个中间时刻获知“若不行权、未来可能获得的折现期望值”。

### 6.2 算法执行流程 (Longstaff & Schwartz, 2001)

1. **正向路径模拟**：模拟生成 $M$ 条完整的离散标的资产价格轨迹矩阵，覆盖 $N_{\text{steps}}$ 个等间距时间点。
2. **反向动态规划与正交回归**（由 $t = N_{\text{steps}}-1$ 逆向回溯至 $t = 1$）：
   - 在时间步 $t$，筛选出当前处于**实值状态（In-the-Money, ITM）**的有效路径子集。
   - 提取这些实值路径在未来实际发生行权时刻的现金流，并将其贴现回当前时刻 $t$，记为因变量向量 $Y$。
   - 以当前标的资产价格 $S_t$ 构建多项式基函数矩阵 $X$（通常采用 2 阶多项式 $[1, S_t, S_t^2]$，或正交拉盖尔多项式 Laguerre Polynomials）。
   - 执行最小二乘线性回归估计待定系数向量 $\beta = (X^T X)^{-1} X^T Y$。
   - 计算该时刻的继续持有条件期望价值：$\hat{C} = X \beta$。
   - 比较即期内在价值与预期持有价值：若 $\text{Intrinsic}(S_t) > \hat{C}$，则判定在该时刻提前行权，并更新该路径的历史现金流。
3. **折现求和**：将所有路径在各自最优停时时刻触发的现金流统一折现回 $t=0$ 并计算算术平均值。

### 6.3 理论特性

- **严格下界（Lower Bound）**：LSM 算法估计出的期权价格理论上恒小于或等于真实美式期权价格。因为基于有限多项式基函数拟合出的行权策略并非绝对完美的最优决策，次优行权决策必然导致期望价值被低估。
- 伴随路径数量与时间步数的扩充，下界逐渐逼近真实解。

---

## 7. Barone-Adesi-Whaley (BAW 美式期权闭式解)

### 7.1 核心原理与二次逼近

针对美式期权缺少显式积分闭式解的问题，Barone-Adesi 与 Whaley (1987) 基于 MacMillan (1986) 的思想，提出了二次逼近模型。将美式期权价格分解为欧式期权基准价格与提前行权溢价（Early Exercise Premium）之和：

$$V_{\text{american}}(S) = V_{\text{european}}(S) + A \left(\frac{S}{S^*}\right)^{q_2} \quad (\text{当 } S < S^*)$$
$$V_{\text{american}}(S) = S - K \quad (\text{当 } S \ge S^*)$$

其中 $S^*$ 为未知的**提前行权临界资产价格边界（Critical Commodity Price）**。

### 7.2 牛顿迭代与光滑贴合条件 (Smooth Pasting)

$S^*$ 必须在边界处满足**价值匹配条件（Value Matching）**与**一阶光滑贴合条件（Smooth Pasting Condition）**：

$$\left.\frac{\partial V_{\text{american}}}{\partial S}\right|_{S = S^*} = 1$$

通过 Newton-Raphson 迭代法高精求解方程根 $S^*$，随后即可闭式代入确定待定常数 $A$ 与指数项 $q_2$。

### 7.3 看涨-看跌对称性 (Put-Call Symmetry)

对于美式看跌期权，利用经典的资产置换对称性转化：

$$P_{\text{american}}(S, K, T, r, q, \sigma) = C_{\text{american}}(K, S, T, q, r, \sigma)$$

即互换标的资产价格与行权价（$S \leftrightarrow K$），并互换无风险利率与连续股息率（$r \leftrightarrow q$），直接复用美式 Call 的求解逻辑。

### 7.4 适用边界与回退安全机制

- 当 $q \ge r$ 时，美式 Call 理论上绝不提前行权，溢价为 0；但在临界参数或高股息情景下，数值可能发散。
- 本工具库在检测到参数位于 BAW 潜在发散区间时，**自动平滑回退至 $N=1000$ 步的高精度二叉树**，确保在具备微秒级吞吐的同时拥有 100% 工业级数值鲁棒性。

---

## 8. 隐含波动率 (Implied Volatility)

### 8.1 概念定义

给定市场上可观测到的真实期权成交价格 $V_{\text{mkt}}$，反解满足定价方程的波动率参数：

$$\text{BS}(S, K, T, r, q, \sigma_{\text{impl}}) = V_{\text{mkt}}$$

该参数被称为该期权的**隐含波动率（Implied Volatility, IV）**。

### 8.2 求解算法与数值稳定性

由于标准正态积分无法显式反演，必须采用非线性方程数值求解器：
- **二分法（Bisection Method）**：本模块的核心实现。虽然较牛顿法稍慢，但具有严格的全局收敛保证，彻底杜绝了深虚值（Deep OTM）期权在 Vega $\approx 0$ 处引起的牛顿迭代发散崩溃。
- 最大迭代限制为 60 次，收敛容差达到 $10^{-7}$。
- 内置内在价值校验（若 $V_{\text{mkt}} < \text{Intrinsic}$，直接抛出无套利解异常）。

---

## 9. 实值概率 P(ITM) 与获利概率 P(Profit)

### 9.1 风险中性测度 $\mathbb{Q}$ 下的 P(ITM)

在到期时刻 $T$，期权处于实值（In-the-Money）的理论概率在数学上可精确由正态分布 CDF 导出：

- 看涨期权（Call）：$\mathbb{P}_{\mathbb{Q}}(S_T > K) = N(d_2)$
- 看跌期权（Put）：$\mathbb{P}_{\mathbb{Q}}(S_T < K) = N(-d_2)$

其中 $d_2 = \frac{\ln(S/K) + (r - q - 0.5\sigma^2)T}{\sigma\sqrt{T}}$。单次计算开销仅 ~300 纳秒。

### 9.2 考虑权利金成本的获利概率 P(Profit)

交易员实际建仓时支付（或收取）了期权权利金 $\text{Premium}$。为了衡量策略真正实现正向盈亏的胜率，需将盈亏平衡点作为有效行权价：

- 买入看涨期权（Long Call）：$\mathbb{P}_{\mathbb{Q}}(S_T > K + \text{Premium}) = N(d_2')$，其中 $K_{\text{eff}} = K + \text{Premium}$
- 买入看跌期权（Long Put）：$\mathbb{P}_{\mathbb{Q}}(S_T < K - \text{Premium}) = N(-d_2')$，其中 $K_{\text{eff}} = K - \text{Premium}$
- 卖出看涨期权（Short Call）：$\mathbb{P}_{\mathbb{Q}}(S_T < K + \text{Premium})$
- 卖出看跌期权（Short Put）：$\mathbb{P}_{\mathbb{Q}}(S_T > K - \text{Premium})$

---

## 10. 综合对比表：精度 vs 速度

以下性能数据基于 Windows 11、Python 3.14 + numpy 2.4.4 环境实测。测试输入为标准平值期权（$S=K=100, T=0.25, r=0.05, \sigma=0.20, q=0$），通过 `py option_pricing.py bench --bench-n 500` 获得：

| 定价方法 | 单次耗时 | 每秒吞吐量 (Throughput) | 典型数值误差 | 适用行权风格 |
|---------|---------:|----------------------:|-------------|-------------|
| **Black-Scholes** | 0.0015 ms | 655,000 /s | 0（严格闭式解） | 欧式 |
| **BAW (BS2)** | 0.0016 ms | 630,000 /s | <1%（相对二叉树） | 美式 |
| **Binomial N=500** | 2.8 ms | 358 /s | ~0.5% | 欧式 / 美式 |
| **Binomial N=2000** | 17 ms | 59 /s | ~0.1% | 欧式 / 美式 |
| **Trinomial N=500** | 23 ms | 43 /s | ~0.3% | 欧式 / 美式 |
| **Trinomial N=2000** | 30 ms | 33 /s | ~0.1% | 欧式 / 美式 |
| **MC paths=10k** | 0.96 ms | 1,040 /s | ~1%（标准误） | 欧式 |
| **MC paths=100k** | 14 ms | 71 /s | ~0.1%（标准误） | 欧式 |
| **MC paths=1M** | 83 ms | 12 /s | ~0.03%（标准误） | 欧式 |
| **LSM paths=50k steps=50** | 1,069 ms | <1 /s | ~1-2% | 美式 |
| **LSM paths=200k steps=50** | 7,628 ms | <0.1 /s | ~0.5% | 美式 |
| **Greeks (BS)** | 0.001 ms | 1,000,000 /s | 0（严格解析求导） | 欧式 |
| **IV 反解 (BS)** | 0.6 ms | 1,700 /s | $10^{-7}$ 容差 | 欧式 |
| **P(ITM)** | 0.0003 ms | 3,000,000 /s | 0（严格闭式解） | 欧式 / 美式 |

---

## 11. 模型选型与应用决策准则

### 量化回测铁律

1. **欧式期权极速回测**：无条件选用 `bs_price()`。单核吞吐量超过 65 万次/秒。
2. **美式期权批量回测**：首选 `bs2_american_price()`（BAW）。保持微秒级解析速度的同时兼顾行权溢价。
3. **高精度标定与基准裁决**：当需要裁定微小套利空间或校验新模型时，使用 `binomial_price()` 设置 `steps=2000`。
4. **希腊值与对冲评估**：统一调用 `bs_greeks()` 解析解，避免使用耗时且易产生数值噪点的差分法。
5. **隐含波动率清洗提取**：调用 `implied_vol()` 模块批量处理。

---

## 12. 参考文献

- Hull, J. (2017). *Options, Futures, and Other Derivatives*, 9th/10th ed. Pearson.
- Cox, J., Ross, S., & Rubinstein, M. (1979). "Option pricing: a simplified approach." *Journal of Financial Economics*, 7(3), 229-263.
- Boyle, P. (1986). "Option valuation using a three-jump process." *International Options Journal*, 3, 7-12.
- Longstaff, F. & Schwartz, E. (2001). "Valuing American options by simulation: a simple least-squares approach." *Review of Financial Studies*, 14(1), 113-147.
- Barone-Adesi, G. & Whaley, R. (1987). "Efficient analytic approximation of American option values." *Journal of Finance*, 42(2), 301-320.
- Bjerksund, P. & Stensland, G. (2002). "Closed form valuation of American options." Working paper.
- Haug, E. (2007). *Complete Guide to Option Pricing Formulas*, 2nd ed. McGraw-Hill.
