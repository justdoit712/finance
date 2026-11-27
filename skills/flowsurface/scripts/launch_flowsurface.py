#!/usr/bin/env python3
"""Flowsurface 原生桌面端启动器：自动同步系统代理与本地时区、多开隔离与源码编译启动。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

ROOT_DIR = Path(__file__).resolve().parents[3]
FLOWSURFACE_DIR = ROOT_DIR / "flowsurface"
LOCAL_RELEASE_EXE = FLOWSURFACE_DIR / "target" / "release" / "flowsurface.exe"
ICON_PATH = FLOWSURFACE_DIR / "assets" / "app-icon" / "flowsurface.ico"
SHORTCUT_PATH = ROOT_DIR / "客户端.lnk"
LAUNCH_BAT = ROOT_DIR / "launch_client.bat"


def _flowsurface_data_dir(profile: str | None = None) -> Path:
    override = os.environ.get("FLOWSURFACE_DATA_PATH", "").strip()
    if override and not profile:
        return Path(override)
    appdata = os.environ.get("APPDATA", "").strip()
    base = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
    if profile:
        safe = "".join(ch for ch in profile.strip() if ch.isalnum() or ch in ("-", "_"))
        if not safe:
            raise ValueError(f"无效的实例名称: {profile!r}")
        return base / f"flowsurface-{safe}"
    return base / "flowsurface"


def detect_system_proxy() -> dict[str, object] | None:
    """读取当前系统 HTTP/HTTPS/SOCKS 代理并转为 Flowsurface Proxy JSON 结构。"""
    proxies = urllib.request.getproxies()
    raw_url = proxies.get("https") or proxies.get("http") or proxies.get("all") or ""
    raw_url = raw_url.strip()
    if not raw_url:
        return None
    if "://" not in raw_url:
        raw_url = f"http://{raw_url}"
    parsed = urllib.parse.urlparse(raw_url)
    if not parsed.hostname or not parsed.port:
        return None
    scheme_map = {
        "http": "Http",
        "https": "Https",
        "socks5": "Socks5",
        "socks5h": "Socks5h",
        "socks": "Socks5",
    }
    scheme = scheme_map.get(parsed.scheme.lower(), "Http")
    return {
        "scheme": scheme,
        "host": parsed.hostname,
        "port": int(parsed.port),
        "auth": None,
    }


def ensure_flowsurface_config(data_dir: Path | None = None) -> Path:
    """首次运行前写入本地时区(Local)、Binance 永续默认过滤与系统代理设置，不覆盖已有布局与主题。"""
    target_dir = data_dir or _flowsurface_data_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    state_file = target_dir / "saved-state.json"

    proxy_cfg = detect_system_proxy()
    data: dict[str, object] = {}
    changed = False

    if state_file.exists():
        try:
            loaded = json.loads(state_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            return state_file
    else:
        changed = True

    if "timezone" not in data:
        data["timezone"] = "Local"
        changed = True

    if "cache_market_metadata" not in data:
        data["cache_market_metadata"] = True
        changed = True

    sidebar = data.get("sidebar")
    if isinstance(sidebar, dict):
        tt = sidebar.get("tickers_table")
        if isinstance(tt, dict):
            if tt.get("selected_exchanges") != ["Binance"]:
                tt["selected_exchanges"] = ["Binance"]
                changed = True
            if tt.get("selected_markets") != ["LinearPerps"]:
                tt["selected_markets"] = ["LinearPerps"]
                changed = True

    mw = data.get("main_window")
    if isinstance(mw, dict) and (
        (mw.get("width") or 0) < 200
        or (mw.get("height") or 0) < 200
        or (mw.get("pos_x") or 0) <= -10000
        or (mw.get("pos_y") or 0) <= -10000
    ):
        data["main_window"] = {"width": 1400.0, "height": 900.0, "pos_x": 100.0, "pos_y": 80.0}
        changed = True

    net = data.get("network")
    if not isinstance(net, dict):
        net = {"proxy": None, "trade_fetch_mode": {"type": "Off"}}
        data["network"] = net
        changed = True

    if net.get("proxy") is None and proxy_cfg is not None:
        net["proxy"] = proxy_cfg
        changed = True

    if "trade_fetch_mode" not in net:
        net["trade_fetch_mode"] = {"type": "Off"}
        changed = True

    if changed:
        tmp_path = state_file.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(state_file)
    return state_file


def build_from_source() -> Path:
    cargo = shutil.which("cargo")
    if not cargo:
        exe_name = "cargo.exe" if sys.platform == "win32" else "cargo"
        candidates: list[Path] = []
        cargo_home = os.environ.get("CARGO_HOME", "").strip()
        if cargo_home:
            candidates.append(Path(cargo_home) / "bin" / exe_name)
        candidates.extend(
            [
                Path(r"D:\DevEnvs\Rust\cargo\bin") / exe_name,
                Path.home() / ".cargo" / "bin" / exe_name,
            ]
        )
        for candidate in candidates:
            if candidate.exists():
                cargo = str(candidate)
                break
    if not cargo:
        raise RuntimeError(
            "未检测到 Rust/Cargo 环境。请先安装 Rust (https://rustup.rs/) 及 MSVC Build Tools。"
        )
    env = os.environ.copy()
    cargo_bin = str(Path(cargo).parent)
    if cargo_bin not in env.get("PATH", ""):
        env["PATH"] = f"{cargo_bin}{os.pathsep}{env.get('PATH', '')}"
    print(f"→ 正在编译 {FLOWSURFACE_DIR} (cargo build --release) ...")
    subprocess.run([cargo, "build", "--release"], cwd=str(FLOWSURFACE_DIR), env=env, check=True)
    if not LOCAL_RELEASE_EXE.exists():
        raise FileNotFoundError(f"编译完成但未找到输出文件: {LOCAL_RELEASE_EXE}")
    return LOCAL_RELEASE_EXE


def create_shortcut(profile: str | None = None) -> None:
    if sys.platform != "win32":
        print("非 Windows 系统跳过 .lnk 快捷方式创建。")
        return
    if not LAUNCH_BAT.exists():
        raise FileNotFoundError(f"未找到启动脚本: {LAUNCH_BAT}")
    icon_arg = f"{ICON_PATH},0" if ICON_PATH.exists() else ""
    if profile:
        safe = "".join(ch for ch in profile.strip() if ch.isalnum() or ch in ("-", "_"))
        if not safe:
            raise ValueError(f"无效的实例名称: {profile!r}")
        shortcut_path = ROOT_DIR / f"客户端{safe}.lnk"
        cmd_args = f'/c ""{LAUNCH_BAT}" --profile {safe}"'
        desc = f"客户端 {safe} (Flowsurface 独立多开实例)"
    else:
        shortcut_path = SHORTCUT_PATH
        cmd_args = f'/c ""{LAUNCH_BAT}""'
        desc = "客户端 (Flowsurface 实时行情终端)"
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{shortcut_path}'); "
        "$sc.TargetPath = 'cmd.exe'; "
        f"$sc.Arguments = '{cmd_args}'; "
        f"$sc.WorkingDirectory = '{ROOT_DIR}'; "
        "$sc.WindowStyle = 7; "
        f"$sc.Description = '{desc}'; "
        + (f"$sc.IconLocation = '{icon_arg}'; " if icon_arg else "")
        + "$sc.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    print(f"✓ 已更新快捷方式: {shortcut_path}")


def launch_flowsurface(exe_path: Path) -> None:
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        )
    cwd = str(FLOWSURFACE_DIR if FLOWSURFACE_DIR.exists() else exe_path.parent)
    subprocess.Popen([str(exe_path)], cwd=cwd, creationflags=creationflags)
    print(f"✓ 已启动 Flowsurface: {exe_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Flowsurface 桌面终端启动器")
    parser.add_argument("--build", action="store_true", help="从本地 flowsurface/ Rust 源码重新编译 release 版")
    parser.add_argument("--no-launch", action="store_true", help="只准备配置与编译检查，不拉起窗口")
    parser.add_argument("--create-shortcut", action="store_true", help="更新根目录快捷方式（配合 --profile 可生成独立多开快捷方式）")
    parser.add_argument("--profile", type=str, default=None, help="独立多开实例名（如 2 / 3），自动隔离数据目录与布局配置")
    args = parser.parse_args()

    data_dir = _flowsurface_data_dir(args.profile)
    os.environ["FLOWSURFACE_DATA_PATH"] = str(data_dir)
    state_file = ensure_flowsurface_config(data_dir)
    print(f"→ 配置文件就绪: {state_file}")

    if args.build or not LOCAL_RELEASE_EXE.exists():
        exe_path = build_from_source()
    else:
        exe_path = LOCAL_RELEASE_EXE

    if args.create_shortcut:
        create_shortcut(args.profile)

    if not args.no_launch:
        launch_flowsurface(exe_path)


if __name__ == "__main__":
    main()
