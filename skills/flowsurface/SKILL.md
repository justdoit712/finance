---
name: flowsurface
description: "原生 Rust/GPU 加密货币桌面看盘终端技能（集成 Flowsurface v0.9.0）。支持 Binance、Bybit、Hyperliquid、OKX 与 MEXC 毫秒级 WebSocket 逐笔成交、盘口深度 (DOM)、订单流热力图与 Footprint K 线，内置系统代理自动配置与一键启动。"
license: GPL-3.0-or-later
---

# Flowsurface — 原生加密货币订单流与 K 线桌面终端

基于开源 Rust 原生桌面行情平台 **Flowsurface**（`iced` + `wgpu` GPU 渲染）深度集成，直接连接交易所 WebSocket，无需浏览器中转。

---

## 目录结构

```text
flowsurface/                                 ← Flowsurface 完整 Rust 源码 (v0.9.0, GPL-3.0-or-later)
skills/flowsurface/
├── SKILL.md                                 ← 本说明文档
└── scripts/
    └── launch_flowsurface.py                ← 代理自动注入、包检查/安装与客户端启动器
```

---

## 支持交易所与核心能力

- **原生直连交易所**：`Binance`（现货 / U 本位 / 币本位合约）、`Bybit`、`Hyperliquid`、`OKX`、`MEXC`。
- **实时看板面板**：
  - **Candlestick / Footprint**：实时 K 线、订单流足迹图、成交量分布与内置 `.ind` 技术指标脚本。
  - **Time & Sales**：多币对毫秒级逐笔成交流明细与大单音效提醒。
  - **DOM / Ladder & Heatmap**：实时盘口深度梯子与历史订单簿挂单热力图。
- **自动网络代理与时区同步**：首次启动自动读取本机 HTTP/SOCKS 代理写入 `%APPDATA%\flowsurface\saved-state.json`，并默认启用本地时区（`Local` / UTC+8）。

---

## 快速上手

```bash
# 直接启动桌面端（已集成至根目录 launch_client.bat 与 客户端.lnk）
python skills/flowsurface/scripts/launch_flowsurface.py

# 仅确保安装包与代理配置就绪（不拉起窗口）
python skills/flowsurface/scripts/launch_flowsurface.py --install --no-launch

# 若本机已安装 Rust 工具链，从 flowsurface/ 源码本地编译并启动
python skills/flowsurface/scripts/launch_flowsurface.py --build

# 刷新桌面/目录快捷方式图标与入口
python skills/flowsurface/scripts/launch_flowsurface.py --create-shortcut
```

---

## 依赖说明

- **默认免编译运行**：Windows x64 自动识别或校验下载官方签名的 `Flowsurface` v0.9.0 MSIX 包（SHA-256 校验，无需安装 Rust）。
- **源码二次开发/编译**：如需修改 [flowsurface/](../../flowsurface/) 下 Rust 源码，需安装 `Rust 1.95.0`（见 `rust-toolchain.toml`）及 MSVC C++ Build Tools。
