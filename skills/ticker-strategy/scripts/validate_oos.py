#!/usr/bin/env python3
"""Walk-forward out-of-sample (OOS) validation and parameter plateau check."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from arena import FAMILY_SPECS, compute_metrics, expand_param_grid, run_perp_backtest


def _dedupe_candidates(candidates: list[dict[str, Any]], max_groups: int = 8) -> list[dict[str, Any]]:
    """Keep top unique (timeframe, family, direction) groups."""
    seen: set[tuple[str, str, str]] = set()
    groups: list[dict[str, Any]] = []
    for c in candidates:
        key = (c["timeframe"], c["family"], c["direction"])
        if key not in seen:
            seen.add(key)
            groups.append(c)
            if len(groups) >= max_groups:
                break
    return groups


def walk_forward_group(
    df: pd.DataFrame,
    timeframe: str,
    family: str,
    direction: str,
    funding_df: pd.DataFrame | None = None,
    fee_rate: float = 0.0005,
    slippage: float = 0.0003,
    n_folds: int = 4,
    gap_bars: int = 8,
    min_train_ratio: float = 0.45,
) -> dict[str, Any] | None:
    """Anchored expanding-window Walk-Forward CV for one (timeframe, family, direction) group."""
    spec = FAMILY_SPECS[family]
    grid = expand_param_grid(spec)
    n = len(df)
    train_start_end = int(n * min_train_ratio)
    remaining = n - train_start_end
    if remaining < n_folds * 40 or train_start_end < 150:
        return None

    fold_len = remaining // n_folds
    if fold_len < 30:
        return None

    folds: list[dict[str, Any]] = []
    oos_equity_segments: list[np.ndarray] = []
    oos_closes: list[np.ndarray] = []
    oos_trades: list[dict[str, Any]] = []
    is_sharpes: list[float] = []
    selected_params_list: list[dict[str, Any]] = []

    for f_idx in range(n_folds):
        tr_end = train_start_end + f_idx * fold_len
        te_start = tr_end + gap_bars
        te_end = n if f_idx == n_folds - 1 else min(n, tr_end + fold_len)
        if te_end - te_start < 20:
            continue

        tr_df = df.iloc[:tr_end].reset_index(drop=True)
        te_df = df.iloc[te_start:te_end].reset_index(drop=True)

        best_train_score = -1e9
        best_params = grid[0]
        best_train_sharpe = 0.0

        for params in grid:
            sigs = spec.signal_fn(tr_df, params)
            cfg = {
                "direction": direction,
                "fee_rate": fee_rate,
                "slippage": slippage,
                "interval": timeframe,
                **spec.default_risk,
                "atr_sl_mult": params.get("atr_sl_mult", 2.0),
            }
            res = run_perp_backtest(tr_df, sigs, cfg, funding_df=funding_df)
            m = res["metrics"]
            if m["trades"] < 6:
                continue
            sc = m["sharpe"] + 0.25 * min(m["profit_factor"] - 1.0, 2.0) - max(0.0, abs(m["max_drawdown"]) - 0.25)
            if sc > best_train_score:
                best_train_score = sc
                best_params = params
                best_train_sharpe = m["sharpe"]

        is_sharpes.append(best_train_sharpe)
        selected_params_list.append(best_params)

        te_sigs = spec.signal_fn(te_df, best_params)
        te_cfg = {
            "direction": direction,
            "fee_rate": fee_rate,
            "slippage": slippage,
            "interval": timeframe,
            **spec.default_risk,
            "atr_sl_mult": best_params.get("atr_sl_mult", 2.0),
        }
        te_res = run_perp_backtest(te_df, te_sigs, te_cfg, funding_df=funding_df)
        te_m = te_res["metrics"]

        eq = te_res["equity"]
        if len(oos_equity_segments) == 0:
            oos_equity_segments.append(eq)
        else:
            scale = oos_equity_segments[-1][-1] / max(eq[0], 1e-12)
            oos_equity_segments.append(eq[1:] * scale)
        oos_closes.append(te_df["close"].to_numpy(dtype=float))
        oos_trades.extend(te_res["trades"])

        folds.append({
            "fold": f_idx + 1,
            "train_bars": int(len(tr_df)),
            "test_bars": int(len(te_df)),
            "test_start_utc": str(te_df["datetime"].iloc[0]),
            "test_end_utc": str(te_df["datetime"].iloc[-1]),
            "params": best_params,
            "train_sharpe": round(best_train_sharpe, 3),
            "test_return": te_m["total_return"],
            "test_sharpe": te_m["sharpe"],
            "test_max_drawdown": te_m["max_drawdown"],
            "test_trades": te_m["trades"],
        })

    if not folds:
        return None

    stitched_eq = np.concatenate(oos_equity_segments)
    stitched_close = np.concatenate(oos_closes)
    oos_metrics = compute_metrics(
        stitched_eq,
        stitched_close,
        oos_trades,
        timeframe,
        exposure_bars=sum(t["hold_bars"] for t in oos_trades),
        total_fees_pct=0.0,
        total_funding_pct=0.0,
    )
    pos_folds = sum(1 for f in folds if f["test_return"] > 0.0)
    pos_fold_ratio = pos_folds / len(folds)
    avg_is_sharpe = float(np.mean(is_sharpes)) if is_sharpes else 0.0
    is_oos_ratio = (oos_metrics["sharpe"] / avg_is_sharpe) if avg_is_sharpe > 0.05 else 0.0

    # Use most recent fold's best params as production candidate params
    prod_params = selected_params_list[-1]

    return {
        "timeframe": timeframe,
        "family": family,
        "family_zh": spec.label_zh,
        "direction": direction,
        "prod_params": prod_params,
        "risk": {**spec.default_risk, "atr_sl_mult": prod_params.get("atr_sl_mult", 2.0)},
        "oos_metrics": oos_metrics,
        "positive_fold_ratio": round(pos_fold_ratio, 3),
        "avg_is_sharpe": round(avg_is_sharpe, 3),
        "oos_is_sharpe_ratio": round(is_oos_ratio, 3),
        "folds": folds,
    }


def check_parameter_plateau(
    df: pd.DataFrame,
    timeframe: str,
    family: str,
    direction: str,
    target_params: dict[str, Any],
    funding_df: pd.DataFrame | None = None,
    fee_rate: float = 0.0005,
    slippage: float = 0.0003,
) -> dict[str, Any]:
    """Check +/-1 step neighbor parameters around target_params for robustness plateau."""
    spec = FAMILY_SPECS[family]
    axes = spec.param_axes
    axis_keys = list(axes.keys())

    neighbors: list[dict[str, Any]] = []
    for k in axis_keys:
        vals = axes[k]
        if target_params.get(k) not in vals:
            continue
        idx = vals.index(target_params[k])
        for delta in (-1, 1):
            ni = idx + delta
            if 0 <= ni < len(vals):
                cand = dict(target_params)
                cand[k] = vals[ni]
                if family == "ema_trend" and cand["fast_len"] >= cand["slow_len"]:
                    continue
                if family == "donchian_breakout" and cand["exit_len"] >= cand["entry_len"]:
                    continue
                neighbors.append(cand)

    if not neighbors:
        return {"neighbor_count": 0, "plateau_ratio": 0.0, "neighbors": []}

    results = []
    healthy = 0
    for p in neighbors:
        sigs = spec.signal_fn(df, p)
        cfg = {
            "direction": direction,
            "fee_rate": fee_rate,
            "slippage": slippage,
            "interval": timeframe,
            **spec.default_risk,
            "atr_sl_mult": p.get("atr_sl_mult", 2.0),
        }
        res = run_perp_backtest(df, sigs, cfg, funding_df=funding_df)
        m = res["metrics"]
        is_ok = (m["total_return"] > 0.0) and (m["sharpe"] >= 0.3) and (m["trades"] >= 10)
        if is_ok:
            healthy += 1
        results.append({
            "params": p,
            "total_return": m["total_return"],
            "sharpe": m["sharpe"],
            "max_drawdown": m["max_drawdown"],
            "trades": m["trades"],
            "healthy": is_ok,
        })

    return {
        "neighbor_count": len(results),
        "healthy_count": healthy,
        "plateau_ratio": round(healthy / len(results), 3),
        "neighbors": results,
    }


def judge_verdict(oos_metrics: dict[str, Any], positive_fold_ratio: float, plateau_ratio: float) -> str:
    """Honest quality gate: PASS / WATCHLIST / NO_EDGE."""
    sharpe = oos_metrics["sharpe"]
    pf = oos_metrics["profit_factor"]
    mdd = oos_metrics["max_drawdown"]
    trades = oos_metrics["trades"]

    if (
        sharpe >= 0.60
        and pf >= 1.15
        and mdd >= -0.30
        and trades >= 15
        and positive_fold_ratio >= 0.50
        and plateau_ratio >= 0.40
    ):
        return "PASS"
    if sharpe >= 0.20 and pf >= 1.05 and trades >= 10:
        return "WATCHLIST"
    return "NO_EDGE"


def validate_candidates(
    klines_by_tf: dict[str, pd.DataFrame],
    arena_candidates: list[dict[str, Any]],
    funding_df: pd.DataFrame | None = None,
    fee_rate: float = 0.0005,
    slippage: float = 0.0003,
    top_groups: int = 8,
) -> list[dict[str, Any]]:
    """Run Walk-Forward OOS + plateau validation on top arena groups and rank by OOS score."""
    groups = _dedupe_candidates(arena_candidates, max_groups=top_groups)
    validated: list[dict[str, Any]] = []

    for g in groups:
        tf = g["timeframe"]
        df = klines_by_tf.get(tf)
        if df is None or len(df) < 300:
            continue

        wf = walk_forward_group(
            df,
            tf,
            g["family"],
            g["direction"],
            funding_df=funding_df,
            fee_rate=fee_rate,
            slippage=slippage,
        )
        if wf is None:
            continue

        plateau = check_parameter_plateau(
            df,
            tf,
            g["family"],
            g["direction"],
            wf["prod_params"],
            funding_df=funding_df,
            fee_rate=fee_rate,
            slippage=slippage,
        )

        # Full-sample metrics for prod_params
        spec = FAMILY_SPECS[g["family"]]
        full_sigs = spec.signal_fn(df, wf["prod_params"])
        full_cfg = {
            "direction": g["direction"],
            "fee_rate": fee_rate,
            "slippage": slippage,
            "interval": tf,
            **wf["risk"],
        }
        full_res = run_perp_backtest(df, full_sigs, full_cfg, funding_df=funding_df)

        oos_m = wf["oos_metrics"]
        verdict = judge_verdict(oos_m, wf["positive_fold_ratio"], plateau["plateau_ratio"])
        oos_score = (
            oos_m["sharpe"]
            + 0.4 * wf["positive_fold_ratio"]
            + 0.3 * plateau["plateau_ratio"]
            + 0.25 * min(oos_m["profit_factor"] - 1.0, 2.0)
            - 1.2 * max(0.0, abs(oos_m["max_drawdown"]) - 0.25)
        )

        validated.append({
            **wf,
            "full_metrics": full_res["metrics"],
            "plateau": plateau,
            "verdict": verdict,
            "oos_score": round(float(oos_score), 4),
        })

    verdict_rank = {"PASS": 2, "WATCHLIST": 1, "NO_EDGE": 0}
    validated.sort(key=lambda x: (verdict_rank.get(x["verdict"], 0), x["oos_score"]), reverse=True)
    return validated
