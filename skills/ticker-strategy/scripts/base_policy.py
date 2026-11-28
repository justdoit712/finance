#!/usr/bin/env python3
"""Layer-1 base policy loader for per-ticker strategies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICIES_PATH = REPO_ROOT / "strategies" / "_base_policies.yaml"

DEFAULT_POLICY_TEMPLATES: dict[str, dict[str, Any]] = {
    "crypto_major": {
        "label_zh": "加密主流合约基石",
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"],
        "max_leverage": 1.0,
        "entry_tranches": [1.0],
        "add_tranche_atr_step": 0.6,
        "max_chase_atr": 3.0,
        "cooldown_bars_after_sl": 2,
        "notes_zh": "低倍稳健底座；偏离 20 均线超过 3 倍 ATR 禁止追单；后续可按实战习惯调整分仓比例与杠杆上限",
    },
    "crypto_alt": {
        "label_zh": "加密山寨合约基石",
        "symbols": [],
        "max_leverage": 1.0,
        "entry_tranches": [1.0],
        "add_tranche_atr_step": 0.8,
        "max_chase_atr": 2.6,
        "cooldown_bars_after_sl": 3,
        "notes_zh": "山寨币插针剧烈，严控杠杆与追高偏离度，止损后强制冷静期防连续扫损",
    },
    "tradfi_stock": {
        "label_zh": "股票与传统资产合约基石",
        "symbols": [
            "XAUUSDT", "XAGUSDT", "NIOUSDT", "TSLAUSDT", "AAPLUSDT",
            "NVDAUSDT", "COINUSDT", "MSTRUSDT", "AMZNUSDT", "GOOGLUSDT",
            "METAUSDT", "MSFTUSDT",
        ],
        "max_leverage": 1.0,
        "entry_tranches": [1.0],
        "add_tranche_atr_step": 0.5,
        "max_chase_atr": 2.5,
        "cooldown_bars_after_sl": 2,
        "notes_zh": "受美股与传统盘交易时段影响明显，严禁开盘脉冲追单",
    },
}


def load_all_policies(policies_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load all asset-class base policies, merging built-in defaults gracefully."""
    path = policies_path or DEFAULT_POLICIES_PATH
    merged: dict[str, dict[str, Any]] = {k: dict(v) for k, v in DEFAULT_POLICY_TEMPLATES.items()}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            for key, val in raw.items():
                if not isinstance(val, dict):
                    continue
                base = dict(merged.get(key, merged["crypto_alt"]))
                base.update({k: v for k, v in val.items() if v is not None})
                merged[key] = base
    return merged


def infer_asset_class(symbol: str, policies: dict[str, dict[str, Any]] | None = None) -> str:
    """Infer asset class from symbol membership in _base_policies.yaml (default: crypto_alt)."""
    sym = symbol.strip().upper()
    all_pols = policies or load_all_policies()
    for cls_name in ("tradfi_stock", "crypto_major", "crypto_alt"):
        cfg = all_pols.get(cls_name, {})
        syms = [str(s).strip().upper() for s in cfg.get("symbols", [])]
        if sym in syms:
            return cls_name
    for cls_name, cfg in all_pols.items():
        syms = [str(s).strip().upper() for s in cfg.get("symbols", [])]
        if sym in syms:
            return cls_name
    return "crypto_alt"


def load_base_policy(
    symbol: str,
    asset_class_override: str | None = None,
    policies_path: Path | None = None,
) -> dict[str, Any]:
    """Load normalized Layer-1 base policy for a given symbol."""
    all_pols = load_all_policies(policies_path)
    asset_class = asset_class_override or infer_asset_class(symbol, all_pols)
    if asset_class not in all_pols:
        raise ValueError(f"未知的底层资产大类: {asset_class!r}，可选: {list(all_pols.keys())}")

    raw = dict(all_pols[asset_class])
    tranches_raw = raw.get("entry_tranches", [1.0])
    tranches = [float(x) for x in tranches_raw if float(x) > 0.0] if isinstance(tranches_raw, list) else [1.0]
    if not tranches:
        tranches = [1.0]
    total_w = sum(tranches)
    if total_w > 1.0:
        tranches = [round(x / total_w, 4) for x in tranches]

    return {
        "asset_class": asset_class,
        "label_zh": str(raw.get("label_zh", asset_class)),
        "max_leverage": max(float(raw.get("max_leverage", 1.0)), 0.1),
        "entry_tranches": tranches,
        "add_tranche_atr_step": max(float(raw.get("add_tranche_atr_step", 0.6)), 0.1),
        "max_chase_atr": float(raw["max_chase_atr"]) if raw.get("max_chase_atr") is not None else None,
        "cooldown_bars_after_sl": max(int(raw.get("cooldown_bars_after_sl", 2)), 0),
        "notes_zh": str(raw.get("notes_zh", "")),
    }
