---
name: ticker-strategy
description: "双层单标的量化策略与主力行为分析工厂（一标一策）。第一层基于资产大类（加密主流/加密山寨/股票传统合约）设定可演进的底层交易基石（低杠杆、防追仓、分仓与止损冷静期）；第二层针对具体标的进行六维主力操盘技术拆解、长期沉淀人工观察笔记，并在五大主力战术剧本中执行走步向前交叉验证（Walk-Forward CV）与参数高原检验，输出独立策略代码、研究报告及 Flowsurface 自定义指标 (.ind)。"
license: MIT
---

# Ticker Strategy — 双层单标的量化与主力行为分析工厂

围绕 **“底层固定交易基石 + 单标的主力行为摸排”** 双层架构，为每一个加密或传统资产永续合约单独建立主力行为档案、长期记录盯盘心得、筛选契合该庄家习性的技术战术，并输出可独立迭代的策略包。

---

## 一、 双层架构设计

### 第一层：底层固定交易基石 (`strategies/_base_policies.yaml`)
- 按资产大类（`crypto_major` 加密主流、`crypto_alt` 加密山寨、`tradfi_stock` 股票与传统合约）提供可演进的基础底座：
  - `max_leverage`：最大允许杠杆上限；
  - `entry_tranches` & `add_tranche_atr_step`：分批建仓比例与加仓间距；
  - `max_chase_atr`：防追仓偏离上限（偏离 20 均线过远禁止顺势追单）；
  - `cooldown_bars_after_sl`：止损后强制冷静期。

### 第二层：单标的主力行为拆解、笔记沉淀与专属战术 (`strategies/<SYMBOL>/`)
1. **主力六维技术拆解 (`profile_ticker.py`)**：
   - **插针扫损习性**：统计向下假跌破前低收回后的反弹胜率，以及向上假突破诱多收回后的回落胜率；
   - **突破真假诚实度**：统计 20 周期前高低点突破的延续率 vs 4 根 K 线内骗炮率（对比放量突破与缩量突破）；
   - **主力均线记忆**：扫描 `EMA 21 / 34 / 55 / 120 / 200`，自动识别该币种主力最常护盘的支撑均线与压制均线；
   - **吸筹与巨量意图**：统计布林缩口吸筹占比、放量点火延续率，以及 2.5 倍以上巨量长影线反转率；
   - **主力作息（北京时间）**：识别放量活跃时段与长影插针高发时段；
   - **画像标签与禁忌**：生成可直接指导实战的中文结论、避坑禁忌与推荐战术顺位。
2. **人工观察笔记本 (`notes.md`)**：
   - 每个标的专属 `strategies/<SYMBOL>/notes.md` 永久沉淀盯盘笔记，重跑建模与报告时绝不覆盖。
3. **五大主力战术剧本 (`arena.py`)**：
   - `sweep_fade`（主力插针扫损反手）
   - `ema_defense_pullback`（主力护盘均线回踩承接）
   - `squeeze_ignition`（主力横盘吸筹放量点火）
   - `climax_reversal`（主力巨量派发/衰竭反转）
   - `trend_breakout`（顺庄主升浪结构跟踪）

---

## 二、 目录结构

```text
skills/ticker-strategy/
├── SKILL.md                      # 技能说明
└── scripts/
    ├── __init__.py
    ├── base_policy.py            # 第一层：资产大类底层交易基石加载器
    ├── notes_manager.py          # 第二层：单标的持久化主力观察笔记管理
    ├── fetch_binance.py          # 拉取币安 UM 永续 K 线、资金费率与 OI 指标（带本地缓存）
    ├── profile_ticker.py         # 主力行为六维技术拆解与中文画像生成器
    ├── arena.py                  # 五大主力战术剧本竞技场与永续回测引擎
    ├── validate_oos.py           # 走步向前交叉验证（Walk-Forward CV）与参数高原检测
    ├── export_ind.py             # 导出 Flowsurface language(1) 买卖点与止损线指标 (.ind)
    └── build_strategy.py         # 主入口：profile / note / build / rerun

strategies/
├── _base_policies.yaml           # 第一层：可演进的底层交易基石配置
└── <SYMBOL>/                     # 第二层：每个标的独立产物目录
    ├── profile.json              # 主力行为六维体检数据
    ├── notes.md                  # 人工观察笔记（长期沉淀，绝不覆盖）
    ├── config.yaml               # 基石映射、周期、方向、参数与风控配置
    ├── strategy.py               # 该标的专属策略代码（可单独定制修改）
    ├── report.md                 # 主力拆解、笔记摘录与样本外回测报告
    └── <symbol>.ind              # Flowsurface K 线信号与止损线叠加指标
```

---

## 三、 快速使用

### 1. 先做主力行为技术体检（看这个币庄家怎么玩）

```bash
python skills/ticker-strategy/scripts/build_strategy.py profile --symbol TAUSDT --timeframes 15m,1h,4h --days 180
```

### 2. 记录 / 查看该币的主力盯盘笔记

```bash
python skills/ticker-strategy/scripts/build_strategy.py note --symbol TAUSDT --add "美盘开盘前后常先下插前低再拉起" --tag "插针"
python skills/ticker-strategy/scripts/build_strategy.py note --symbol TAUSDT --show
```

### 3. 为单个标的生成专属策略包与研究报告

```bash
python skills/ticker-strategy/scripts/build_strategy.py build --symbol TAUSDT --timeframes 15m,1h,4h --days 180
```

如需同时把 `.ind` 指标安装到本机 Flowsurface 用户指标目录：

```bash
python skills/ticker-strategy/scripts/build_strategy.py build --symbol TAUSDT --timeframes 15m,1h,4h --days 180 --install-ind
```

### 4. 单独定制某个标的策略或调整底层基石后一键复跑验证

修改 `strategies/<SYMBOL>/strategy.py`、`config.yaml` 或 `strategies/_base_policies.yaml` 后执行：

```bash
python skills/ticker-strategy/scripts/build_strategy.py rerun --symbol TAUSDT
```

---

## 四、 准入门槛与结论分级

- `PASS`：样本外夏普 `>= 0.60`、盈亏比因子（PF）`>= 1.15`、最大回撤 `>= -30%`、样本外交易 `>= 15` 笔、正收益折比 `>= 50%`、邻域参数高原率 `>= 40%`。
- `WATCHLIST`：样本外夏普 `>= 0.20`、PF `>= 1.05` 且样本外交易 `>= 10` 笔，但未满足全部稳健门槛。
- `NO_EDGE`：样本外无显著统计优势，明确提示不建议直接实盘。
