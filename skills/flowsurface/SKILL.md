---
name: flowsurface
description: "原生 Rust/GPU 币安 U 本位与 TradFi 永续合约看盘桌面终端（Flowsurface）。支持毫秒级 WebSocket 逐笔成交、盘口深度 (DOM)、挂单热力图、Footprint K 线与自定义 .ind 策略指标叠加，内置系统代理自动配置、本地编译与多开启动。"
license: GPL-3.0-or-later
---

# Flowsurface — 原生永续合约订单流与 K 线看盘终端

基于开源 Rust 原生桌面行情平台 **Flowsurface**（`iced` + `wgpu` GPU 渲染）构建，专用于 **Binance U 本位加密与 TradFi 永续合约**（同时涵盖 `PERPETUAL` 与 `TRADIFI_PERPETUAL`，如 `BTCUSDT`、`ETHUSDT`、`NIOUSDT`、`XAUUSDT` 等）。

---

## 目录结构

```text
flowsurface/                                 ← Flowsurface Rust 源码 (GPL-3.0-or-later)
skills/flowsurface/
├── SKILL.md                                 ← 本说明文档
└── scripts/
    └── launch_flowsurface.py                ← 系统代理/时区同步、多开隔离与本地编译启动器
```

---

## 核心能力

- **直连币安 U 本位永续**：毫秒级 WebSocket 逐笔成交、盘口深度与 K 线实时更新。
- **多维度看盘面板**：
  - **Candlestick / Footprint**：实时 K 线、订单流足迹图、TPO / Volume Profile 与自定义 `.ind` 指标叠加。
  - **Heatmap**：历史盘口挂单热力图（`wgpu` GPU 着色器渲染）。
  - **DOM Ladder & Time & Sales**：实时盘口深度梯子与逐笔成交流明细。
  - **收藏夹快捷切换**：星标收藏与侧边栏一键切换标的。
- **代理与多开管理**：自动读取本机 HTTP/SOCKS 代理并同步本地时区（`Local`），支持 `--profile <name>` 独立配置多开实例。

---

## 快速上手

```bash
# 直接启动本地编译版客户端（若未编译将自动触发编译）
python skills/flowsurface/scripts/launch_flowsurface.py

# 修改 Rust 源码后重新编译 release 版并启动
python skills/flowsurface/scripts/launch_flowsurface.py --build

# 启动独立多开实例（数据与布局隔离）
python skills/flowsurface/scripts/launch_flowsurface.py --profile 2

# 更新根目录快捷方式
python skills/flowsurface/scripts/launch_flowsurface.py --create-shortcut
```

---

## 编译环境要求

- `Rust 1.95.0`（见 `flowsurface/rust-toolchain.toml`）及 Windows MSVC C++ Build Tools。
