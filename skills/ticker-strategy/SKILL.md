---
name: ticker-strategy
description: "单标的专属量化策略工厂（一标一策）。自动拉取币安 U 本位/TradFi 永续历史 K 线、资金费率与持仓量，完成标的统计画像、多策略家族竞技寻优、走步向前交叉验证（Walk-Forward CV）与参数高原检验，并为每个标的生成独立的策略代码、配置文件、研究报告及 Flowsurface 自定义指标 (.ind)。"
license: MIT
---

# Ticker Strategy — 单标的专属量化策略工厂

遵循 **一标一策、独立目录、样本外淘汰** 原则，为每一个加密或 TradFi 永续标的单独建立画像、筛选最优策略机理并生成可独立迭代的策略包。

---

## 目录结构

```text
skills/ticker-strategy/
├── SKILL.md                      # 技能说明
└── scripts/
    ├── __init__.py
    ├── fetch_binance.py          # 拉取币安 UM 永续 K 线、资金费率与 OI 指标（带本地缓存）
    ├── profile_ticker.py         # 标的统计画像（体制诊断、插针率、UTC 时段活跃度、资金费率）
    ├── arena.py                  # 多策略家族竞技场与永续回测引擎（无未来函数、含费率/滑点/ATR风控）
    ├── validate_oos.py           # 走步向前交叉验证（Walk-Forward CV）与参数高原检测
    ├── export_ind.py             # 导出 Flowsurface language(1) 图表叠加指标 (.ind)
    └── build_strategy.py         # 主入口：build 生成策略包 / rerun 复跑定制策略

strategies/<SYMBOL>/              # 每个标的独立产物目录
├── profile.json                  # 标的体检数据
├── config.yaml                   # 周期、方向、参数与风控配置
├── strategy.py                   # 该标的专属策略代码（可单独定制修改）
├── report.md                     # 策略家族横向对比与样本外回测报告
└── <symbol>.ind                  # Flowsurface K 线信号叠加指标
```

---

## 快速使用

### 1. 为单个标的生成专属策略

```bash
python skills/ticker-strategy/scripts/build_strategy.py build --symbol ETHUSDT --timeframes 15m,1h,4h --days 180
```

如需同时把 `.ind` 指标安装到本机 Flowsurface 用户指标目录：

```bash
python skills/ticker-strategy/scripts/build_strategy.py build --symbol ETHUSDT --timeframes 15m,1h,4h --days 180 --install-ind
```

### 2. 单独定制某个标的策略并复跑验证

直接修改 `strategies/<SYMBOL>/strategy.py` 中的 `generate_signals` 或 `strategies/<SYMBOL>/config.yaml` 参数后执行：

```bash
python skills/ticker-strategy/scripts/build_strategy.py rerun --symbol ETHUSDT
```

### 3. 仅查看标的体检画像

```bash
python skills/ticker-strategy/scripts/profile_ticker.py --symbol NIOUSDT --timeframes 15m,1h,4h --days 60
```

---

## 内置策略家族与准入门槛

- **5 类独立机理**：`ema_trend`（EMA 趋势跟踪）、`donchian_breakout`（Donchian 通道突破）、`bb_squeeze_breakout`（布林缩口放量突破）、`bb_mean_reversion`（布林+RSI 均值回归）、`rsi_momentum_pullback`（趋势回踩 RSI 恢复），均同时评测 `both` / `long_only` / `short_only`。
- **结论分级**：
  - `PASS`：样本外夏普 `>= 0.60`、盈亏比因子（PF）`>= 1.15`、最大回撤 `>= -30%`、样本外交易 `>= 15` 笔、正收益折比 `>= 50%`、邻域参数高原率 `>= 40%`。
  - `WATCHLIST`：样本外夏普 `>= 0.20` 且 PF `>= 1.05`，但未满足全部稳健门槛。
  - `NO_EDGE`：样本外无显著统计优势，明确提示不建议直接实盘。
