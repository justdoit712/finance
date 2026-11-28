#!/usr/bin/env python3
"""Persistent per-ticker main-force observation notebook manager."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

BJ_TZ = timezone(timedelta(hours=8))

SECTION_LOG = "## 一、 主力操盘习性观察日志"
SECTION_LEVELS = "## 二、 关键护盘/砸盘价位与作息特征"
SECTION_HYPOTHESES = "## 三、 待回测验证的盘感假设"
SECTION_TABOOS = "## 四、 实战纪律与该币种禁忌"

NOTES_TEMPLATE = """# {symbol} 主力行为与操盘观察笔记

- **所属底层基石**：`{asset_class_zh}`
- **使用说明**：本笔记由人工盯盘长期沉淀，系统在重新跑策略与更新报告时**绝不覆盖**本文件内容。可使用以下命令追加记录：
  `python skills/ticker-strategy/scripts/build_strategy.py note --symbol {symbol} --add "观察内容" --tag "插针/护盘/骗炮/复盘"`

---

## 一、 主力操盘习性观察日志

<!-- 在此按时间记录该币种庄家/主力的典型行为，例如假突破诱多、定点插针洗盘、护盘放量特征等 -->

---

## 二、 关键护盘/砸盘价位与作息特征

- **重点观察时段（北京时间）**：
- **主力常守均线 / 结构位置**：
- **常见挂单/扫损区间**：

---

## 三、 待回测验证的盘感假设

- （例：美盘开盘后若放量下插前低并迅速收回，做多胜率是否显著高于追突破？）

---

## 四、 实战纪律与该币种禁忌

- （写明针对该币种的禁止操作，例如禁止追突破、避开高插针时段等）
"""


def ensure_notes_file(symbol: str, out_dir: Path, asset_class_zh: str = "加密合约基石") -> Path:
    """Create strategies/<SYMBOL>/notes.md if absent; NEVER overwrite an existing notebook."""
    sym = symbol.strip().upper()
    out_dir.mkdir(parents=True, exist_ok=True)
    notes_path = out_dir / "notes.md"
    if not notes_path.exists():
        notes_path.write_text(
            NOTES_TEMPLATE.format(symbol=sym, asset_class_zh=asset_class_zh or "加密合约基石"),
            encoding="utf-8",
        )
    return notes_path


def append_note(symbol: str, out_dir: Path, text: str, tag: str = "盯盘观察", asset_class_zh: str = "") -> Path:
    """Append a Beijing-timestamped main-force observation under Section 1 of notes.md."""
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("笔记内容不能为空。")
    clean_tag = tag.strip() or "盯盘观察"

    notes_path = ensure_notes_file(symbol, out_dir, asset_class_zh=asset_class_zh)
    content = notes_path.read_text(encoding="utf-8")
    stamp = datetime.now(BJ_TZ).strftime("%Y-%m-%d %H:%M BJ")
    entry_line = f"- **[{stamp} | {clean_tag}]** {clean_text}"

    lines = content.splitlines()
    insert_idx: int | None = None
    in_log_section = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(SECTION_LOG):
            in_log_section = True
            continue
        if in_log_section and stripped.startswith("## "):
            insert_idx = idx
            break

    if insert_idx is not None:
        # Insert before trailing separator `---` or next heading
        target = insert_idx
        while target > 0 and lines[target - 1].strip() in ("", "---"):
            if lines[target - 1].strip() == "---":
                target -= 1
                break
            target -= 1
        lines.insert(target, entry_line)
        if target > 0 and lines[target - 1].strip().startswith("<!--"):
            lines.insert(target, "")
        updated = "\n".join(lines).rstrip() + "\n"
    elif in_log_section:
        updated = content.rstrip() + "\n" + entry_line + "\n"
    else:
        updated = content.rstrip() + f"\n\n{SECTION_LOG}\n\n{entry_line}\n"

    notes_path.write_text(updated, encoding="utf-8")
    return notes_path


def extract_recent_notes(notes_path: Path, limit: int = 8) -> list[str]:
    """Extract user-recorded observation entries from notes.md for inclusion in report.md."""
    if not notes_path.exists():
        return []
    lines = notes_path.read_text(encoding="utf-8").splitlines()
    entries: list[str] = []
    in_log = False
    for line in lines:
        s = line.strip()
        if s.startswith(SECTION_LOG):
            in_log = True
            continue
        if in_log and s.startswith("## "):
            break
        if in_log and s.startswith("- "):
            body = s[2:].strip()
            if body and not body.startswith("（"):
                entries.append(body)
    return entries[-limit:]


def sync_notes_to_report(report_path: Path, symbol: str, notes_path: Path) -> bool:
    """Refresh Section 2 (人工盯盘观察笔记摘录) inside report.md when notes.md changes."""
    if not report_path.exists():
        return False
    lines = report_path.read_text(encoding="utf-8").splitlines()
    target_heading = "## 二、 人工盯盘观察笔记摘录"
    start_idx: int | None = None
    end_idx: int | None = None
    for idx, line in enumerate(lines):
        s = line.strip()
        if s.startswith(target_heading):
            start_idx = idx
            continue
        if start_idx is not None and s.startswith("## "):
            end_idx = idx
            break
    if start_idx is None:
        return False

    recent = extract_recent_notes(notes_path)
    new_body = (
        [f"- {item}" for item in recent]
        if recent
        else [
            f"- 暂无人工观察记录。平时盯盘发现该币庄家规律后，可写入 `strategies/{symbol}/notes.md` 或执行："
            f"`python skills/ticker-strategy/scripts/build_strategy.py note --symbol {symbol} --add \"观察内容\"`"
        ]
    )

    if end_idx is None:
        updated_lines = lines[: start_idx + 1] + [""] + new_body + [""]
    else:
        tail_sep = ["", "---", ""] if end_idx > 0 and lines[end_idx - 1].strip() == "---" else [""]
        # Check if there is a `---` separator right before end_idx
        has_sep = any(lines[k].strip() == "---" for k in range(start_idx + 1, end_idx))
        middle = [""] + new_body + (["", "---", ""] if has_sep else [""])
        updated_lines = lines[: start_idx + 1] + middle + lines[end_idx:]

    report_path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
    return True
