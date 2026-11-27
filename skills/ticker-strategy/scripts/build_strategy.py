#!/usr/bin/env python3
"""Per-ticker quantitative strategy builder and rerun CLI."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
STRATEGIES_DIR = REPO_ROOT / "strategies"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from arena import FAMILY_SPECS, run_arena, run_perp_backtest  # noqa: E402
from export_ind import generate_ind_source, install_to_flowsurface  # noqa: E402
from fetch_binance import fetch_funding_rate, fetch_klines, fetch_metrics  # noqa: E402
from profile_ticker import build_ticker_profile  # noqa: E402
from validate_oos import check_parameter_plateau, judge_verdict, validate_candidates, walk_forward_group  # noqa: E402


STRATEGY_TEMPLATE = '''#!/usr/bin/env python3
"""{symbol} 专属量化策略 ({family_zh}) — 自动生成后可针对该标的独立定制。"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLKIT_SCRIPTS = REPO_ROOT / "skills" / "ticker-strategy" / "scripts"
if str(TOOLKIT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TOOLKIT_SCRIPTS))

from arena import adx, atr, bollinger_bands, donchian, ema, rsi, sma  # noqa: E402

SYMBOL = "{symbol}"
TIMEFRAME = "{timeframe}"
DIRECTION = "{direction}"
FAMILY = "{family}"

DEFAULT_PARAMS: dict[str, Any] = {params_repr}


def generate_signals(df: pd.DataFrame, params: dict[str, Any] | None = None) -> dict[str, np.ndarray]:
    """返回 {{entry_long, entry_short, exit_long, exit_short}} 布尔信号数组。"""
    p = {{**DEFAULT_PARAMS, **(params or {{}})}}
{signal_body}


if __name__ == "__main__":
    import subprocess

    cli = TOOLKIT_SCRIPTS / "build_strategy.py"
    subprocess.run([sys.executable, str(cli), "rerun", "--symbol", SYMBOL], check=True)
'''


def _signal_body_for_family(family: str) -> str:
    if family == "ema_trend":
        return """    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)

    fast = ema(close, int(p["fast_len"]))
    slow = ema(close, int(p["slow_len"]))
    adx_arr = adx(high, low, close, 14)
    adx_min = float(p.get("adx_min", 18.0))

    prev_fast = np.roll(fast, 1)
    prev_slow = np.roll(slow, 1)
    prev_fast[0] = np.nan
    prev_slow[0] = np.nan

    entry_long = (fast > slow) & (prev_fast <= prev_slow) & (adx_arr >= adx_min)
    entry_short = (fast < slow) & (prev_fast >= prev_slow) & (adx_arr >= adx_min)
    exit_long = fast < slow
    exit_short = fast > slow
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }"""

    if family == "donchian_breakout":
        return """    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    hi_in, lo_in = donchian(high, low, int(p["entry_len"]))
    hi_out, lo_out = donchian(high, low, int(p["exit_len"]))
    vol_ma = sma(vol, 20)

    prev_hi_in = np.roll(hi_in, 1)
    prev_lo_in = np.roll(lo_in, 1)
    prev_hi_out = np.roll(hi_out, 1)
    prev_lo_out = np.roll(lo_out, 1)
    prev_hi_in[0] = np.nan
    prev_lo_in[0] = np.nan
    prev_hi_out[0] = np.nan
    prev_lo_out[0] = np.nan

    vol_ok = vol >= (vol_ma * float(p.get("vol_mult", 1.1)))
    entry_long = (close > prev_hi_in) & vol_ok
    entry_short = (close < prev_lo_in) & vol_ok
    exit_long = close < prev_lo_out
    exit_short = close > prev_hi_out
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }"""

    if family == "bb_squeeze_breakout":
        return """    close = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    mid, upper, lower = bollinger_bands(close, int(p["bb_len"]), float(p["bb_std"]))
    bw = (upper - lower) / np.maximum(mid, 1e-12)
    bw_q = pd.Series(bw).rolling(100, min_periods=40).quantile(float(p.get("squeeze_pct", 0.40))).to_numpy()
    prev_bw = np.roll(bw, 1)
    prev_bw_q = np.roll(bw_q, 1)
    prev_bw[0] = np.nan
    prev_bw_q[0] = np.nan

    vol_ma = sma(vol, 20)
    squeeze_ready = (prev_bw <= prev_bw_q) | (bw <= bw_q * 1.15)
    vol_ok = vol >= (vol_ma * float(p.get("vol_mult", 1.2)))

    entry_long = (close > upper) & squeeze_ready & vol_ok
    entry_short = (close < lower) & squeeze_ready & vol_ok
    exit_long = close < mid
    exit_short = close > mid
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }"""

    if family == "bb_mean_reversion":
        return """    close = df["close"].to_numpy(dtype=float)
    rsi_os = float(p["rsi_os"])
    rsi_ob = 100.0 - rsi_os

    mid, upper, lower = bollinger_bands(close, int(p["bb_len"]), float(p["bb_std"]))
    rsi_arr = rsi(close, 14)
    macro_ema = ema(close, int(p.get("trend_ema", 200)))

    entry_long = (close < lower) & (rsi_arr <= rsi_os) & (close >= macro_ema * 0.94)
    entry_short = (close > upper) & (rsi_arr >= rsi_ob) & (close <= macro_ema * 1.06)
    exit_long = close >= mid
    exit_short = close <= mid
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }"""

    return """    close = df["close"].to_numpy(dtype=float)
    pullback_low = float(p["pullback_low"])
    pullback_high = 100.0 - pullback_low

    trend_ema = ema(close, int(p["trend_len"]))
    rsi_arr = rsi(close, int(p["rsi_len"]))
    prev_rsi = np.roll(rsi_arr, 1)
    prev_rsi[0] = np.nan

    entry_long = (close > trend_ema) & (prev_rsi < pullback_low) & (rsi_arr >= pullback_low)
    entry_short = (close < trend_ema) & (prev_rsi > pullback_high) & (rsi_arr <= pullback_high)
    exit_long = (rsi_arr > 72.0) | (close < trend_ema * 0.99)
    exit_short = (rsi_arr < 28.0) | (close > trend_ema * 1.01)
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }"""


def _fmt_pct(v: float) -> str:
    return f"{v * 100:+.2f}%"


def _render_report(
    symbol: str,
    profile: dict[str, Any],
    validated: list[dict[str, Any]],
    winner: dict[str, Any],
    fee_rate: float,
    slippage: float,
) -> str:
    diag = profile["diagnosis"]
    anchor_tf = profile.get("anchor_timeframe")
    anchor = profile["timeframes"].get(anchor_tf, {})
    funding = profile.get("funding", {})
    oos = winner["oos_metrics"]
    full = winner["full_metrics"]
    plat = winner["plateau"]

    verdict_zh = {
        "PASS": "通过（样本外与参数高原均达标，可用于跟踪/模拟）",
        "WATCHLIST": "观察（具备一定样本外正期望，但未全部达到稳健门槛）",
        "NO_EDGE": "暂无稳健策略（样本外收益或回撤未达门槛，不建议直接实盘）",
    }.get(winner["verdict"], winner["verdict"])

    lines = [
        f"# {symbol} 专属量化策略研究报告",
        "",
        f"- **生成时间 (UTC)**：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **综合结论**：`{winner['verdict']}` — {verdict_zh}",
        f"- **胜出策略**：`{winner['family']}` ({winner['family_zh']}) | 周期 `{winner['timeframe']}` | 方向 `{winner['direction']}`",
        f"- **交易成本假设**：单边手续费 `{fee_rate * 100:.3f}%` + 滑点 `{slippage * 100:.3f}%` + 8h 历史资金费率",
        "",
        "---",
        "",
        "## 一、 标的体检画像",
        "",
        f"- **市场体制 (Regime)**：`{diag['regime']}`（基准周期 `{anchor_tf}`）",
        f"- **Hurst 指数**：`{anchor.get('hurst_rs', '-')}` | **ADX 均值**：`{anchor.get('adx_mean', '-')}` | **效率比 (ER20)**：`{anchor.get('efficiency_ratio_20', '-')}`",
        f"- **年化波动率**：`{anchor.get('ann_volatility', 0) * 100:.1f}%` | **ATR% 中位数 / P95**：`{anchor.get('atr_pct_median', 0) * 100:.2f}% / {anchor.get('atr_pct_p95', 0) * 100:.2f}%`",
        f"- **插针风险**：`{diag['wick_risk']}`（平均影线占比 `{anchor.get('wick_ratio_mean', 0) * 100:.1f}%`，极端长影线频率 `{anchor.get('extreme_wick_pct', 0) * 100:.1f}%`）",
        f"- **时段特征**：`{diag['session_pattern']}`（最活跃 6 个 UTC 小时成交占比 `{diag.get('top_6h_volume_share')}`，活跃小时 UTC `{diag.get('top_active_utc_hours')}`）",
        f"- **日均成交额**：`{anchor.get('avg_daily_quote_volume_usdt', 0):,.0f} USDT` | **样本内买入持有收益**：`{_fmt_pct(anchor.get('buy_hold_return', 0.0))}`（最大回撤 `{_fmt_pct(anchor.get('buy_hold_max_drawdown', 0.0))}`）",
    ]
    if funding.get("records", 0) > 0:
        lines.append(
            f"- **资金费率**：年化均值 `{funding['annualized_pct']:+.2f}%` | 正费率占比 `{funding['positive_ratio'] * 100:.1f}%`"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 二、 多策略家族样本外对比 (Walk-Forward OOS)",
        "",
        "| 排名 | 周期 | 策略家族 | 方向 | 结论 | OOS 收益 | OOS 夏普 | OOS 最大回撤 | OOS PF | 正收益折比 | 参数高原 | OOS 交易数 |",
        "|:---:|:---:|:---|:---:|:---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for idx, item in enumerate(validated, 1):
        m = item["oos_metrics"]
        lines.append(
            f"| {idx} | {item['timeframe']} | {item['family_zh']} (`{item['family']}`) | {item['direction']} | "
            f"`{item['verdict']}` | {_fmt_pct(m['total_return'])} | {m['sharpe']:.2f} | {_fmt_pct(m['max_drawdown'])} | "
            f"{m['profit_factor']:.2f} | {item['positive_fold_ratio'] * 100:.0f}% | {item['plateau']['plateau_ratio'] * 100:.0f}% | {m['trades']} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 三、 胜出策略详情与风控参数",
        "",
        f"- **策略参数**：`{json.dumps(winner['prod_params'], ensure_ascii=False)}`",
        f"- **风控配置**：`{json.dumps(winner['risk'], ensure_ascii=False)}`",
        f"- **全样本参考**：收益 `{_fmt_pct(full['total_return'])}`（同期持有 `{_fmt_pct(full['buy_hold_return'])}`），"
        f"夏普 `{full['sharpe']:.2f}`，最大回撤 `{_fmt_pct(full['max_drawdown'])}`，胜率 `{full['win_rate'] * 100:.1f}%`，"
        f"盈亏比 `{full['payoff_ratio']:.2f}`，PF `{full['profit_factor']:.2f}`，交易 `{full['trades']}` 笔。",
        f"- **样本外拼接 (OOS)**：收益 `{_fmt_pct(oos['total_return'])}`，夏普 `{oos['sharpe']:.2f}`，"
        f"最大回撤 `{_fmt_pct(oos['max_drawdown'])}`，PF `{oos['profit_factor']:.2f}`，交易 `{oos['trades']}` 笔，"
        f"IS/OOS 夏普保留比 `{winner['oos_is_sharpe_ratio']:.2f}`。",
        f"- **参数高原检测**：邻域 `{plat['neighbor_count']}` 组参数中 `{plat.get('healthy_count', 0)}` 组保持正期望健康（高原率 `{plat['plateau_ratio'] * 100:.0f}%`）。",
        "",
        "### 各折走步向前交叉验证明细",
        "",
        "| Fold | 训练 Bar 数 | 测试 Bar 数 | 测试区间 (UTC) | 样本内夏普 | 样本外收益 | 样本外夏普 | 样本外回撤 | 交易数 |",
        "|:---:|---:|---:|:---|---:|---:|---:|---:|---:|",
    ])
    for f in winner["folds"]:
        lines.append(
            f"| {f['fold']} | {f['train_bars']} | {f['test_bars']} | "
            f"{f['test_start_utc'][:10]} ~ {f['test_end_utc'][:10]} | "
            f"{f['train_sharpe']:.2f} | {_fmt_pct(f['test_return'])} | {f['test_sharpe']:.2f} | "
            f"{_fmt_pct(f['test_max_drawdown'])} | {f['test_trades']} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 四、 本地产物与复跑方式",
        "",
        f"- 专属策略代码：`strategies/{symbol}/strategy.py`（可直接修改后复跑验证）",
        f"- 参数配置文件：`strategies/{symbol}/config.yaml`",
        f"- Flowsurface 图表脚本：`strategies/{symbol}/{symbol.lower()}.ind`",
        f"- 一键复跑命令：`python skills/ticker-strategy/scripts/build_strategy.py rerun --symbol {symbol}`",
        "",
    ])
    return "\n".join(lines)


def cmd_build(args: argparse.Namespace) -> None:
    symbol = args.symbol.strip().upper()
    tfs = [tf.strip() for tf in args.timeframes.split(",") if tf.strip()]
    out_dir = STRATEGIES_DIR / symbol
    cache_dir = out_dir / ".cache"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/5] 拉取 {symbol} 行情、资金费率与持仓量数据 (days={args.days}, tfs={tfs}) ...")
    klines_by_tf = {
        tf: fetch_klines(symbol, tf, args.days, cache_dir=cache_dir, refresh=args.refresh)
        for tf in tfs
    }
    sufficient_tfs = {tf: len(df) for tf, df in klines_by_tf.items() if len(df) >= 300}
    if not sufficient_tfs:
        counts = {tf: len(df) for tf, df in klines_by_tf.items()}
        raise RuntimeError(f"{symbol} 可用 K 线不足 300 根，无法完成有效建模与样本外验证: {counts}")

    funding_df = fetch_funding_rate(symbol, args.days, cache_dir=cache_dir, refresh=args.refresh)
    metrics_df = fetch_metrics(symbol, min(args.days, 30), cache_dir=cache_dir, refresh=args.refresh)

    print(f"[2/5] 生成 {symbol} 标的体检画像 ...")
    profile = build_ticker_profile(symbol, klines_by_tf, funding_df, metrics_df)
    (out_dir / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[3/5] 运行多策略家族竞技场 ({len(FAMILY_SPECS)} 个家族 × {list(sufficient_tfs.keys())}) ...")
    candidates = run_arena(
        klines_by_tf,
        funding_df=funding_df,
        fee_rate=args.fee,
        slippage=args.slippage,
    )
    if not candidates:
        raise RuntimeError(f"{symbol} 所有策略家族成交笔数均不足，未产生有效候选策略。")

    print("[4/5] 执行 Walk-Forward 样本外交叉验证与参数高原检测 ...")
    validated = validate_candidates(
        klines_by_tf,
        candidates,
        funding_df=funding_df,
        fee_rate=args.fee,
        slippage=args.slippage,
        top_groups=8,
    )
    if not validated:
        raise RuntimeError(f"{symbol} 数据长度不足以完成 Walk-Forward 验证。")

    winner = validated[0]

    print(f"[5/5] 输出 {symbol} 独立策略包 -> {out_dir}")
    config_obj = {
        "symbol": symbol,
        "timeframe": winner["timeframe"],
        "family": winner["family"],
        "family_zh": winner["family_zh"],
        "direction": winner["direction"],
        "verdict": winner["verdict"],
        "params": winner["prod_params"],
        "risk": winner["risk"],
        "costs": {"fee_rate": args.fee, "slippage": args.slippage},
        "days": args.days,
    }
    (out_dir / "config.yaml").write_text(yaml.safe_dump(config_obj, allow_unicode=True, sort_keys=False), encoding="utf-8")

    strategy_code = STRATEGY_TEMPLATE.format(
        symbol=symbol,
        family_zh=winner["family_zh"],
        timeframe=winner["timeframe"],
        direction=winner["direction"],
        family=winner["family"],
        params_repr=json.dumps(winner["prod_params"], ensure_ascii=False, indent=4),
        signal_body=_signal_body_for_family(winner["family"]),
    )
    (out_dir / "strategy.py").write_text(strategy_code, encoding="utf-8")

    ind_src = generate_ind_source(symbol, winner["family"], winner["direction"], winner["prod_params"])
    ind_path = out_dir / f"{symbol.lower()}.ind"
    ind_path.write_text(ind_src, encoding="utf-8")

    if args.install_ind:
        installed_paths = install_to_flowsurface(ind_path, symbol)
        for p in installed_paths:
            print(f"  -> 已安装 Flowsurface 指标: {p}")

    report_md = _render_report(symbol, profile, validated, winner, args.fee, args.slippage)
    (out_dir / "report.md").write_text(report_md, encoding="utf-8")

    oos_m = winner["oos_metrics"]
    print(
        f"完成 [{symbol}] verdict={winner['verdict']} | {winner['family']} ({winner['timeframe']}, {winner['direction']}) | "
        f"OOS_ret={_fmt_pct(oos_m['total_return'])} OOS_sharpe={oos_m['sharpe']:.2f} "
        f"OOS_mdd={_fmt_pct(oos_m['max_drawdown'])} plateau={winner['plateau']['plateau_ratio']*100:.0f}%"
    )


def _load_strategy_module(strategy_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("custom_ticker_strategy", strategy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载策略文件: {strategy_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cmd_rerun(args: argparse.Namespace) -> None:
    symbol = args.symbol.strip().upper()
    out_dir = STRATEGIES_DIR / symbol
    cfg_path = out_dir / "config.yaml"
    strat_path = out_dir / "strategy.py"
    if not cfg_path.exists() or not strat_path.exists():
        raise FileNotFoundError(f"未找到 {symbol} 独立策略目录或配置文件: {out_dir}")

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    tf = cfg["timeframe"]
    days = int(args.days or cfg.get("days", 180))
    fee_rate = float(cfg.get("costs", {}).get("fee_rate", 0.0005))
    slippage = float(cfg.get("costs", {}).get("slippage", 0.0003))
    params = dict(cfg.get("params", {}))
    risk = dict(cfg.get("risk", {}))

    cache_dir = out_dir / ".cache"
    df = fetch_klines(symbol, tf, days, cache_dir=cache_dir, refresh=args.refresh)
    funding_df = fetch_funding_rate(symbol, days, cache_dir=cache_dir, refresh=args.refresh)

    mod = _load_strategy_module(strat_path)
    sigs = mod.generate_signals(df, params)
    bt_cfg = {
        "direction": cfg.get("direction", "both"),
        "fee_rate": fee_rate,
        "slippage": slippage,
        "interval": tf,
        **risk,
    }
    res = run_perp_backtest(df, sigs, bt_cfg, funding_df=funding_df)
    m = res["metrics"]

    # Also evaluate strict fixed-parameter Walk-Forward splits on the custom strategy
    n = len(df)
    n_folds = 4
    split_start = int(n * 0.45)
    fold_len = max((n - split_start) // n_folds, 1)
    fold_rets = []
    for k in range(n_folds):
        s_idx = split_start + k * fold_len
        e_idx = n if k == n_folds - 1 else min(n, s_idx + fold_len)
        if e_idx - s_idx < 25:
            continue
        sub_df = df.iloc[s_idx:e_idx].reset_index(drop=True)
        sub_sigs = mod.generate_signals(sub_df, params)
        sub_res = run_perp_backtest(sub_df, sub_sigs, bt_cfg, funding_df=funding_df)
        fold_rets.append(sub_res["metrics"]["total_return"])

    pos_folds = sum(1 for r in fold_rets if r > 0.0)
    pos_ratio = (pos_folds / len(fold_rets)) if fold_rets else 0.0

    print(
        f"[RERUN {symbol}] tf={tf} dir={bt_cfg['direction']} | "
        f"ret={_fmt_pct(m['total_return'])} (B&H={_fmt_pct(m['buy_hold_return'])}) | "
        f"sharpe={m['sharpe']:.2f} mdd={_fmt_pct(m['max_drawdown'])} PF={m['profit_factor']:.2f} "
        f"win={m['win_rate']*100:.1f}% trades={m['trades']} | OOS分段正收益={pos_folds}/{len(fold_rets)} ({pos_ratio*100:.0f}%)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or rerun per-ticker quantitative strategies.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Profile a ticker, run strategy arena & OOS validation, emit standalone strategy.")
    p_build.add_argument("--symbol", required=True, help="Binance UM symbol e.g. ETHUSDT, NIOUSDT, TAUSDT")
    p_build.add_argument("--timeframes", default="15m,1h,4h", help="Comma-separated kline intervals")
    p_build.add_argument("--days", type=int, default=180, help="Historical lookback days")
    p_build.add_argument("--fee", type=float, default=0.0005, help="Per-side taker fee rate")
    p_build.add_argument("--slippage", type=float, default=0.0003, help="Per-side slippage rate")
    p_build.add_argument("--install-ind", action="store_true", help="Copy generated .ind into Flowsurface user indicators folder")
    p_build.add_argument("--refresh", action="store_true", help="Force re-download bypassing local cache")
    p_build.set_defaults(func=cmd_build)

    p_rerun = sub.add_parser("rerun", help="Rerun a ticker's standalone strategy.py + config.yaml.")
    p_rerun.add_argument("--symbol", required=True, help="Symbol folder under strategies/")
    p_rerun.add_argument("--days", type=int, default=None, help="Override lookback days")
    p_rerun.add_argument("--refresh", action="store_true", help="Force re-download bypassing local cache")
    p_rerun.set_defaults(func=cmd_rerun)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
