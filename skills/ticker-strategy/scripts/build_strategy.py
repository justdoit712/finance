#!/usr/bin/env python3
"""Two-layer per-ticker main-force profiler, observation notebook, strategy builder & rerun CLI."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
STRATEGIES_DIR = REPO_ROOT / "strategies"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from arena import FAMILY_SPECS, build_backtest_config, run_arena, run_perp_backtest  # noqa: E402
from base_policy import apply_policy_overrides, load_base_policy  # noqa: E402
from export_ind import generate_ind_source, install_to_flowsurface  # noqa: E402
from fetch_binance import fetch_funding_rate, fetch_klines, fetch_metrics  # noqa: E402
from notes_manager import append_note, ensure_notes_file, extract_recent_notes, sync_notes_to_report  # noqa: E402
from profile_ticker import build_ticker_profile, format_pretty_profile  # noqa: E402
from validate_oos import validate_candidates  # noqa: E402


STRATEGY_TEMPLATE = '''#!/usr/bin/env python3
"""{symbol} 专属主力战术策略 ({family_zh}) — 遵循底层基石，可针对该标的独立定制。"""

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
ASSET_CLASS = "{asset_class}"
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
    if family == "sweep_fade":
        return """    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)

    lookback = int(p["lookback"])
    min_wick = float(p["min_wick"])

    hi, lo = donchian(h, l, lookback)
    prev_hi = np.roll(hi, 1)
    prev_lo = np.roll(lo, 1)
    prev_hi[0] = np.nan
    prev_lo[0] = np.nan

    bar_range = np.maximum(h - l, 1e-12)
    lower_wick = (np.minimum(o, c) - l) / bar_range
    upper_wick = (h - np.maximum(o, c)) / bar_range
    mid_exit = sma(c, lookback)

    entry_long = (l < prev_lo) & (c > prev_lo) & (lower_wick >= min_wick)
    entry_short = (h > prev_hi) & (c < prev_hi) & (upper_wick >= min_wick)
    exit_long = c >= mid_exit
    exit_short = c <= mid_exit
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }"""

    if family == "ema_defense_pullback":
        return """    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)

    pullback_low = float(p["pullback_low"])
    pullback_high = 100.0 - pullback_low

    trend_ema = ema(c, int(p["trend_len"]))
    rsi_arr = rsi(c, int(p["rsi_len"]))
    atr_arr = atr(h, l, c, 14)
    prev_rsi = np.roll(rsi_arr, 1)
    prev_rsi[0] = np.nan

    near_sup = (c >= trend_ema * 0.99) & (c <= trend_ema + 2.2 * atr_arr)
    near_res = (c <= trend_ema * 1.01) & (c >= trend_ema - 2.2 * atr_arr)

    entry_long = near_sup & (prev_rsi < pullback_low) & (rsi_arr >= pullback_low)
    entry_short = near_res & (prev_rsi > pullback_high) & (rsi_arr <= pullback_high)
    exit_long = (rsi_arr > 72.0) | (c < trend_ema * 0.985)
    exit_short = (rsi_arr < 28.0) | (c > trend_ema * 1.015)
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }"""

    if family == "squeeze_ignition":
        return """    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    mid, upper, lower = bollinger_bands(c, int(p["bb_len"]), float(p["bb_std"]))
    bw = (upper - lower) / np.maximum(mid, 1e-12)
    bw_q = pd.Series(bw).rolling(100, min_periods=40).quantile(0.35).to_numpy()
    prev_bw = np.roll(bw, 1)
    prev_bw_q = np.roll(bw_q, 1)
    prev_bw[0] = np.nan
    prev_bw_q[0] = np.nan

    vol_ma = sma(vol, 20)
    atr_arr = atr(h, l, c, 14)
    squeeze_ready = (prev_bw <= prev_bw_q) | (bw <= bw_q * 1.15)
    vol_ok = vol >= (vol_ma * float(p["vol_mult"]))
    not_overextended = (h - l) <= (2.5 * atr_arr)

    entry_long = (c > upper) & squeeze_ready & vol_ok & not_overextended
    entry_short = (c < lower) & squeeze_ready & vol_ok & not_overextended
    exit_long = c < mid
    exit_short = c > mid
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }"""

    if family == "climax_reversal":
        return """    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    rsi_os = float(p["rsi_os"])
    rsi_ob = 100.0 - rsi_os
    vol_spike = float(p.get("vol_spike", 1.5))

    mid, upper, lower = bollinger_bands(c, int(p["bb_len"]), float(p["bb_std"]))
    rsi_arr = rsi(c, 14)
    macro_ema = ema(c, 200)
    vol_ma = sma(vol, 20)

    bar_range = np.maximum(h - l, 1e-12)
    lower_wick = (np.minimum(o, c) - l) / bar_range
    upper_wick = (h - np.maximum(o, c)) / bar_range

    exhaust_long = (vol >= vol_ma * vol_spike) | (lower_wick >= 0.35)
    exhaust_short = (vol >= vol_ma * vol_spike) | (upper_wick >= 0.35)

    entry_long = (c < lower) & (rsi_arr <= rsi_os) & exhaust_long & (c >= macro_ema * 0.92)
    entry_short = (c > upper) & (rsi_arr >= rsi_ob) & exhaust_short & (c <= macro_ema * 1.08)
    exit_long = c >= mid
    exit_short = c <= mid
    return {
        "entry_long": np.nan_to_num(entry_long, nan=False),
        "entry_short": np.nan_to_num(entry_short, nan=False),
        "exit_long": np.nan_to_num(exit_long, nan=False),
        "exit_short": np.nan_to_num(exit_short, nan=False),
    }"""

    # trend_breakout
    return """    c = df["close"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    fast = ema(c, int(p["fast_len"]))
    slow = ema(c, int(p["slow_len"]))
    adx_arr = adx(h, l, c, 14)
    vol_ma = sma(vol, 20)
    adx_min = float(p.get("adx_min", 18.0))
    vol_mult = float(p.get("vol_mult", 1.0))

    prev_fast = np.roll(fast, 1)
    prev_slow = np.roll(slow, 1)
    prev_fast[0] = np.nan
    prev_slow[0] = np.nan

    vol_ok = vol >= (vol_ma * vol_mult)
    entry_long = (fast > slow) & (prev_fast <= prev_slow) & (adx_arr >= adx_min) & vol_ok
    entry_short = (fast < slow) & (prev_fast >= prev_slow) & (adx_arr >= adx_min) & vol_ok
    exit_long = fast < slow
    exit_short = fast > slow
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
    base_policy: dict[str, Any],
    profile: dict[str, Any],
    validated: list[dict[str, Any]],
    winner: dict[str, Any],
    recent_notes: list[str],
    fee_rate: float,
    slippage: float,
) -> str:
    diag = profile["diagnosis"]
    whale = profile.get("whale_diagnosis", {})
    anchor_tf = profile.get("anchor_timeframe")
    anchor = profile["timeframes"].get(anchor_tf, {})
    funding = profile.get("funding", {})
    oos = winner["oos_metrics"]
    full = winner["full_metrics"]
    plat = winner["plateau"]

    verdict_zh = {
        "PASS": "通过（顺应主力习性且样本外与参数高原均达标，可用于跟踪/模拟）",
        "WATCHLIST": "观察（具备一定样本外正期望，但未全部达到稳健门槛）",
        "NO_EDGE": "暂无稳健策略（样本外收益或回撤未达门槛，不建议直接实盘）",
    }.get(winner["verdict"], winner["verdict"])

    tags_str = " · ".join(f"`{t}`" for t in whale.get("style_tags", [])) or "`暂无`"
    rec_str = " > ".join(f"`{p}`" for p in whale.get("recommended_playbooks", []))
    tranches_str = str(base_policy.get("entry_tranches", [1.0]))
    chase_str = f"{base_policy['max_chase_atr']} ATR" if base_policy.get("max_chase_atr") is not None else "不限"

    lines = [
        f"# {symbol} 主力行为拆解与专属策略报告",
        "",
        f"- **生成时间 (UTC)**：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **底层基石（第一层）**：`{base_policy['label_zh']}`（`{base_policy['asset_class']}`）| 最大杠杆 `{base_policy['max_leverage']}x` | 分仓比例 `{tranches_str}` | 防追高上限 `{chase_str}` | 止损冷静期 `{base_policy['cooldown_bars_after_sl']}` 根",
        f"- **综合结论**：`{winner['verdict']}` — {verdict_zh}",
        f"- **胜出战术剧本（第二层）**：`{winner['family']}` ({winner['family_zh']}) | 周期 `{winner['timeframe']}` | 方向 `{winner['direction']}`",
        f"- **交易成本假设**：单边手续费 `{fee_rate * 100:.3f}%` + 滑点 `{slippage * 100:.3f}%` + 8h 历史资金费率",
        "",
        "---",
        "",
        f"## 一、 主力行为六维技术拆解（基准周期 `{anchor_tf}`）",
        "",
        f"- **主力画像标签**：{tags_str}",
        f"- **市场体制 (Regime)**：`{diag['regime']}`（Hurst `{anchor.get('hurst_rs', '-')}` | ADX `{anchor.get('adx_mean', '-')}` | 年化波动 `{anchor.get('ann_volatility', 0) * 100:.1f}%`）",
        f"- **日均成交额**：`{anchor.get('avg_daily_quote_volume_usdt', 0):,.0f} USDT` | **样本内买入持有**：`{_fmt_pct(anchor.get('buy_hold_return', 0.0))}`（最大回撤 `{_fmt_pct(anchor.get('buy_hold_max_drawdown', 0.0))}`）",
        f"- **推荐战术顺位**：{rec_str}",
    ]
    if funding.get("records", 0) > 0:
        lines.append(
            f"- **资金费率**：年化均值 `{funding['annualized_pct']:+.2f}%` | 正费率占比 `{funding['positive_ratio'] * 100:.1f}%`"
        )
    lines.append("")
    for line in whale.get("summary_lines_zh", []):
        lines.append(f"- {line}")
    lines.append("")
    lines.append("### 该币种实战禁忌")
    for taboo in whale.get("taboos_zh", []):
        lines.append(f"- ⚠️ {taboo}")

    lines.extend([
        "",
        "---",
        "",
        "## 二、 人工盯盘观察笔记摘录",
        "",
    ])
    if recent_notes:
        for note_item in recent_notes:
            lines.append(f"- {note_item}")
    else:
        lines.append(
            f"- 暂无人工观察记录。平时盯盘发现该币庄家规律后，可写入 `strategies/{symbol}/notes.md` 或执行："
            f"`python skills/ticker-strategy/scripts/build_strategy.py note --symbol {symbol} --add \"观察内容\"`"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 三、 五大主力战术剧本样本外对比 (Walk-Forward OOS)",
        "",
        "| 排名 | 周期 | 战术剧本 | 方向 | 结论 | OOS 收益 | OOS 夏普 | OOS 最大回撤 | OOS PF | 正收益折比 | 参数高原 | OOS 交易数 |",
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
        "## 四、 胜出策略详情与风控参数",
        "",
        f"- **策略参数**：`{json.dumps(winner['prod_params'], ensure_ascii=False)}`",
        f"- **风控配置**：`{json.dumps(winner['risk'], ensure_ascii=False)}`",
        f"- **全样本参考**：收益 `{_fmt_pct(full['total_return'])}`（同期持有 `{_fmt_pct(full['buy_hold_return'])}`），"
        f"夏普 `{full['sharpe']:.2f}`，最大回撤 `{_fmt_pct(full['max_drawdown'])}`，胜率 `{full['win_rate'] * 100:.1f}%`，"
        f"盈亏比 `{full['payoff_ratio']:.2f}`，PF `{full['profit_factor']:.2f}`，交易 `{full['trades']}` 笔（拦截追高 `{full.get('chase_filtered', 0)}` 次）。",
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
        "## 五、 本地产物与复跑指引",
        "",
        f"- 专属策略代码：`strategies/{symbol}/strategy.py`（可直接修改信号逻辑后复跑验证）",
        f"- 观察笔记本：`strategies/{symbol}/notes.md`（长期记录主力规律，重跑不被覆盖）",
        f"- 参数配置文件：`strategies/{symbol}/config.yaml`",
        f"- Flowsurface 图表脚本：`strategies/{symbol}/{symbol.lower()}.ind`",
        f"- 一键复跑命令：`python skills/ticker-strategy/scripts/build_strategy.py rerun --symbol {symbol}`",
        "",
    ])
    return "\n".join(lines)


def cmd_profile(args: argparse.Namespace) -> None:
    symbol = args.symbol.strip().upper()
    tfs = [tf.strip() for tf in args.timeframes.split(",") if tf.strip()]
    out_dir = STRATEGIES_DIR / symbol
    cache_dir = out_dir / ".cache"
    out_dir.mkdir(parents=True, exist_ok=True)

    base_policy = load_base_policy(symbol, asset_class_override=args.asset_class)
    ensure_notes_file(symbol, out_dir, asset_class_zh=base_policy["label_zh"])

    klines_by_tf = {
        tf: fetch_klines(symbol, tf, args.days, cache_dir=cache_dir, refresh=args.refresh)
        for tf in tfs
    }
    funding_df = fetch_funding_rate(symbol, args.days, cache_dir=cache_dir, refresh=args.refresh)
    metrics_df = fetch_metrics(symbol, min(args.days, 30), cache_dir=cache_dir, refresh=args.refresh)

    profile = build_ticker_profile(symbol, klines_by_tf, funding_df, metrics_df)
    (out_dir / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    print(format_pretty_profile(profile))
    print(f"\n已更新画像: {out_dir / 'profile.json'}")


def cmd_note(args: argparse.Namespace) -> None:
    symbol = args.symbol.strip().upper()
    out_dir = STRATEGIES_DIR / symbol
    base_policy = load_base_policy(symbol, asset_class_override=args.asset_class)
    notes_path = ensure_notes_file(symbol, out_dir, asset_class_zh=base_policy["label_zh"])

    if args.add:
        append_note(symbol, out_dir, args.add, tag=args.tag, asset_class_zh=base_policy["label_zh"])
        sync_notes_to_report(out_dir / "report.md", symbol, notes_path)
        print(f"✓ 已追加 {symbol} 主力观察笔记 -> {notes_path}")
    if args.show or not args.add:
        print(notes_path.read_text(encoding="utf-8"))


def cmd_build(args: argparse.Namespace) -> None:
    symbol = args.symbol.strip().upper()
    tfs = [tf.strip() for tf in args.timeframes.split(",") if tf.strip()]
    out_dir = STRATEGIES_DIR / symbol
    cache_dir = out_dir / ".cache"
    out_dir.mkdir(parents=True, exist_ok=True)

    base_policy = load_base_policy(symbol, asset_class_override=args.asset_class)
    notes_path = ensure_notes_file(symbol, out_dir, asset_class_zh=base_policy["label_zh"])

    print(f"[1/5] 拉取 {symbol} 行情、资金费率与持仓量数据 (基石={base_policy['label_zh']}, days={args.days}, tfs={tfs}) ...")
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

    print(f"[2/5] 生成 {symbol} 主力行为六维技术拆解 ...")
    profile = build_ticker_profile(symbol, klines_by_tf, funding_df, metrics_df)
    (out_dir / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[3/5] 运行五大主力战术剧本竞技场 ({len(FAMILY_SPECS)} 个战术 × {list(sufficient_tfs.keys())}) ...")
    candidates = run_arena(
        klines_by_tf,
        funding_df=funding_df,
        fee_rate=args.fee,
        slippage=args.slippage,
        profile=profile,
        base_policy=base_policy,
    )
    if not candidates:
        raise RuntimeError(f"{symbol} 所有战术剧本成交笔数均不足，未产生有效候选策略。")

    print("[4/5] 执行 Walk-Forward 样本外交叉验证与参数高原检测 ...")
    validated = validate_candidates(
        klines_by_tf,
        candidates,
        funding_df=funding_df,
        fee_rate=args.fee,
        slippage=args.slippage,
        top_groups=8,
        profile=profile,
        base_policy=base_policy,
    )
    if not validated:
        raise RuntimeError(f"{symbol} 数据长度不足以完成 Walk-Forward 验证。")

    winner = validated[0]
    whale = profile.get("whale_diagnosis", {})

    print(f"[5/5] 输出 {symbol} 独立策略包 -> {out_dir}")
    config_obj = {
        "symbol": symbol,
        "asset_class": base_policy["asset_class"],
        "base_policy": {
            "label_zh": base_policy["label_zh"],
            "max_leverage": base_policy["max_leverage"],
            "entry_tranches": base_policy["entry_tranches"],
            "add_tranche_atr_step": base_policy["add_tranche_atr_step"],
            "max_chase_atr": base_policy["max_chase_atr"],
            "cooldown_bars_after_sl": base_policy["cooldown_bars_after_sl"],
        },
        "base_policy_overrides": {},
        "timeframe": winner["timeframe"],
        "family": winner["family"],
        "family_zh": winner["family_zh"],
        "direction": winner["direction"],
        "verdict": winner["verdict"],
        "params": winner["prod_params"],
        "risk": winner["risk"],
        "costs": {"fee_rate": args.fee, "slippage": args.slippage},
        "days": args.days,
        "whale_summary": {
            "style_tags": whale.get("style_tags", []),
            "best_support_ema": whale.get("best_support_ema"),
            "best_resistance_ema": whale.get("best_resistance_ema"),
            "recommended_playbooks": whale.get("recommended_playbooks", []),
        },
    }
    (out_dir / "config.yaml").write_text(yaml.safe_dump(config_obj, allow_unicode=True, sort_keys=False), encoding="utf-8")

    strategy_code = STRATEGY_TEMPLATE.format(
        symbol=symbol,
        asset_class=base_policy["asset_class"],
        family_zh=winner["family_zh"],
        timeframe=winner["timeframe"],
        direction=winner["direction"],
        family=winner["family"],
        params_repr=json.dumps(winner["prod_params"], ensure_ascii=False, indent=4),
        signal_body=_signal_body_for_family(winner["family"]),
    )
    (out_dir / "strategy.py").write_text(strategy_code, encoding="utf-8")

    ind_src = generate_ind_source(symbol, winner["family"], winner["direction"], winner["prod_params"], risk=winner["risk"])
    ind_path = out_dir / f"{symbol.lower()}.ind"
    ind_path.write_text(ind_src, encoding="utf-8")

    if args.install_ind:
        installed_paths = install_to_flowsurface(ind_path, symbol)
        for p in installed_paths:
            print(f"  -> 已安装 Flowsurface 指标: {p}")

    recent_notes = extract_recent_notes(notes_path)
    report_md = _render_report(symbol, base_policy, profile, validated, winner, recent_notes, args.fee, args.slippage)
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

    # Load latest Layer-1 policy from _base_policies.yaml and merge optional per-ticker overrides
    base_policy = apply_policy_overrides(
        load_base_policy(symbol, asset_class_override=cfg.get("asset_class")),
        cfg.get("base_policy_overrides"),
    )

    cache_dir = out_dir / ".cache"
    df = fetch_klines(symbol, tf, days, cache_dir=cache_dir, refresh=args.refresh)
    funding_df = fetch_funding_rate(symbol, days, cache_dir=cache_dir, refresh=args.refresh)

    mod = _load_strategy_module(strat_path)
    full_sigs = mod.generate_signals(df, params)
    bt_cfg: dict[str, Any] = {
        "direction": cfg.get("direction", "both"),
        "fee_rate": fee_rate,
        "slippage": slippage,
        "interval": tf,
        **risk,
        "max_leverage": base_policy["max_leverage"],
        "entry_tranches": base_policy["entry_tranches"],
        "add_tranche_atr_step": base_policy["add_tranche_atr_step"],
        "max_chase_atr": base_policy["max_chase_atr"],
        "cooldown_bars_after_sl": base_policy["cooldown_bars_after_sl"],
    }
    res = run_perp_backtest(df, full_sigs, bt_cfg, funding_df=funding_df)
    m = res["metrics"]

    # Slice precomputed causal signals per OOS segment so long-window EMAs do not suffer warmup truncation
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
        sub_sigs = {key: np.asarray(val, dtype=bool)[s_idx:e_idx] for key, val in full_sigs.items()}
        sub_res = run_perp_backtest(sub_df, sub_sigs, bt_cfg, funding_df=funding_df)
        fold_rets.append(sub_res["metrics"]["total_return"])

    pos_folds = sum(1 for r in fold_rets if r > 0.0)
    pos_ratio = (pos_folds / len(fold_rets)) if fold_rets else 0.0

    family = cfg.get("family", "")
    if family in FAMILY_SPECS:
        ind_src = generate_ind_source(symbol, family, bt_cfg["direction"], params, risk=risk)
        ind_path = out_dir / f"{symbol.lower()}.ind"
        ind_path.write_text(ind_src, encoding="utf-8")
        if args.install_ind:
            for p in install_to_flowsurface(ind_path, symbol):
                print(f"  -> 已更新 Flowsurface 指标: {p}")

    sync_notes_to_report(out_dir / "report.md", symbol, out_dir / "notes.md")

    print(
        f"[RERUN {symbol}] tf={tf} dir={bt_cfg['direction']} | 基石={base_policy['label_zh']} ({base_policy['max_leverage']}x) | "
        f"ret={_fmt_pct(m['total_return'])} (B&H={_fmt_pct(m['buy_hold_return'])}) | "
        f"sharpe={m['sharpe']:.2f} mdd={_fmt_pct(m['max_drawdown'])} PF={m['profit_factor']:.2f} "
        f"win={m['win_rate']*100:.1f}% trades={m['trades']} | OOS分段正收益={pos_folds}/{len(fold_rets)} ({pos_ratio*100:.0f}%)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Two-layer per-ticker main-force profiler & strategy factory.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prof = sub.add_parser("profile", help="Run 6-dimension main-force technical dissection for a ticker.")
    p_prof.add_argument("--symbol", required=True, help="Binance UM symbol e.g. ETHUSDT, TAUSDT, NIOUSDT")
    p_prof.add_argument("--timeframes", default="15m,1h,4h", help="Comma-separated kline intervals")
    p_prof.add_argument("--days", type=int, default=180, help="Historical lookback days")
    p_prof.add_argument("--asset-class", default=None, help="Optional override: crypto_major / crypto_alt / tradfi_stock")
    p_prof.add_argument("--refresh", action="store_true", help="Force re-download bypassing local cache")
    p_prof.set_defaults(func=cmd_profile)

    p_note = sub.add_parser("note", help="Record or view persistent main-force observations in notes.md.")
    p_note.add_argument("--symbol", required=True, help="Symbol folder under strategies/")
    p_note.add_argument("--add", default=None, help="Observation text to append with Beijing timestamp")
    p_note.add_argument("--tag", default="盯盘观察", help="Short label e.g. 插针 / 护盘 / 骗炮 / 复盘")
    p_note.add_argument("--show", action="store_true", help="Print current notes.md content")
    p_note.add_argument("--asset-class", default=None, help="Optional asset class if creating notes.md for the first time")
    p_note.set_defaults(func=cmd_note)

    p_build = sub.add_parser("build", help="Profile main-force habits, run 5 playbooks & OOS validation, emit standalone strategy.")
    p_build.add_argument("--symbol", required=True, help="Binance UM symbol e.g. ETHUSDT, NIOUSDT, TAUSDT")
    p_build.add_argument("--timeframes", default="15m,1h,4h", help="Comma-separated kline intervals")
    p_build.add_argument("--days", type=int, default=180, help="Historical lookback days")
    p_build.add_argument("--fee", type=float, default=0.0005, help="Per-side taker fee rate")
    p_build.add_argument("--slippage", type=float, default=0.0003, help="Per-side slippage rate")
    p_build.add_argument("--asset-class", default=None, help="Optional override: crypto_major / crypto_alt / tradfi_stock")
    p_build.add_argument("--install-ind", action="store_true", help="Copy generated .ind into Flowsurface user indicators folder")
    p_build.add_argument("--refresh", action="store_true", help="Force re-download bypassing local cache")
    p_build.set_defaults(func=cmd_build)

    p_rerun = sub.add_parser("rerun", help="Rerun a ticker's standalone strategy.py + config.yaml.")
    p_rerun.add_argument("--symbol", required=True, help="Symbol folder under strategies/")
    p_rerun.add_argument("--days", type=int, default=None, help="Override lookback days")
    p_rerun.add_argument("--install-ind", action="store_true", help="Sync regenerated .ind into Flowsurface user indicators folder")
    p_rerun.add_argument("--refresh", action="store_true", help="Force re-download bypassing local cache")
    p_rerun.set_defaults(func=cmd_rerun)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
