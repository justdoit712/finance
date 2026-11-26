"""
desktop_app.py — 加密货币独立桌面行情客户端启动器。

通过本地 ThreadingHTTPServer 托管 TradingView Lightweight Charts 交互终端，
优先使用 pywebview (WebView2) 或独立进程无地址栏 Edge/Chrome App 窗口运行，
窗口关闭时自动释放本地服务与临时配置目录。

用法:
    python skills/kline-chart/scripts/desktop_app.py
    python skills/kline-chart/scripts/desktop_app.py --symbol gate:TA_USDT --interval 15m
    python skills/kline-chart/scripts/desktop_app.py --dry-run
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import http.client
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from . import kline_chart, providers
except (ImportError, ValueError):
    import kline_chart
    import providers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, Exception):
    pass


_APP_USER_MODEL_ID = "CryptoQuant.KlineClient"
_WIN_ICON_REFS: list[int] = []


def _apply_property_store(pps: ctypes.c_void_p, prop_items: list[tuple[int, str]]) -> None:
    """写入 Windows Shell IPropertyStore 的 AppUserModel 属性并提交。"""
    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", wt.BYTE * 8)]

    class _PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", _GUID), ("pid", wt.DWORD)]

    class _PROPVARIANT(ctypes.Structure):
        _fields_ = [
            ("vt", wt.USHORT), ("r1", wt.USHORT), ("r2", wt.USHORT), ("r3", wt.USHORT),
            ("val", ctypes.c_void_p), ("pad", ctypes.c_void_p),
        ]

    fmtid_aum = _GUID(0x9F4C2855, 0x9F79, 0x4B39, (wt.BYTE * 8)(0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3))
    vtbl = ctypes.cast(pps, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    set_value = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT))(vtbl[6])
    commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtbl[7])
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
    try:
        for pid, text in prop_items:
            pk = _PROPERTYKEY(fmtid_aum, pid)
            buf = ctypes.create_unicode_buffer(text)
            pv = _PROPVARIANT(31, 0, 0, 0, ctypes.cast(buf, ctypes.c_void_p), None)  # VT_LPWSTR = 31
            set_value(pps, ctypes.byref(pk), ctypes.byref(pv))
        commit(pps)
    finally:
        release(pps)


def _make_iid_propertystore() -> ctypes.Structure:
    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", wt.BYTE * 8)]
    return _GUID(0x886D8EEB, 0x8CF2, 0x4446, (wt.BYTE * 8)(0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99))


def _set_shortcut_appid(lnk_path: Path, app_id: str) -> None:
    if sys.platform != "win32":
        return
    try:
        ole32 = ctypes.windll.ole32
        shell32 = ctypes.windll.shell32
        ole32.CoInitialize(None)
        iid = _make_iid_propertystore()
        pps = ctypes.c_void_p()
        hr = shell32.SHGetPropertyStoreFromParsingName(str(lnk_path), None, 2, ctypes.byref(iid), ctypes.byref(pps))
        if hr == 0 and pps:
            _apply_property_store(pps, [(5, app_id)])
    except Exception:
        pass


def _apply_window_identity(pid: int, ico_path: Path, relaunch_cmd: str, title: str, app_id: str) -> None:
    """为独立 App 窗口注入专属图标、任务栏分组 ID 与重启动命令，避免任务栏显示 Edge 默认图标。"""
    if sys.platform != "win32" or not ico_path.exists():
        return
    try:
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32

        hwnd = 0
        for _ in range(50):
            found: list[int] = []

            @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
            def _enum_cb(h: int, _lp: int) -> bool:
                if user32.IsWindowVisible(h):
                    win_pid = wt.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(win_pid))
                    if win_pid.value == pid:
                        found.append(h)
                return True

            user32.EnumWindows(_enum_cb, 0)
            if found:
                hwnd = found[0]
                break
            time.sleep(0.1)

        if not hwnd:
            return

        h_big = user32.LoadImageW(None, str(ico_path), 1, 48, 48, 0x0010)
        h_sml = user32.LoadImageW(None, str(ico_path), 1, 16, 16, 0x0010)
        if h_big:
            _WIN_ICON_REFS.append(h_big)
            user32.SendMessageW(hwnd, 0x0080, 1, h_big)
        if h_sml:
            _WIN_ICON_REFS.append(h_sml)
            user32.SendMessageW(hwnd, 0x0080, 0, h_sml)

        ole32.CoInitialize(None)
        iid = _make_iid_propertystore()
        pps = ctypes.c_void_p()
        hr = shell32.SHGetPropertyStoreForWindow(wt.HWND(hwnd), ctypes.byref(iid), ctypes.byref(pps))
        if hr == 0 and pps:
            _apply_property_store(
                pps,
                [
                    (5, app_id),
                    (2, relaunch_cmd),
                    (3, f"{ico_path},0"),
                    (4, title),
                ],
            )
    except Exception:
        pass


def find_browser_exe(kind: str) -> str | None:
    """查找本机 Edge 或 Chrome 可执行文件路径。"""
    local_app = os.getenv("LOCALAPPDATA", "")
    if kind == "edge":
        which = shutil.which("msedge") or shutil.which("msedge.exe")
        if which:
            return which
        candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.join(local_app, r"Microsoft\Edge\Application\msedge.exe") if local_app else "",
        ]
    elif kind == "chrome":
        which = shutil.which("chrome") or shutil.which("chrome.exe") or shutil.which("google-chrome")
        if which:
            return which
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.join(local_app, r"Google\Chrome\Application\chrome.exe") if local_app else "",
        ]
    else:
        return None

    for path in candidates:
        if path and Path(path).is_file():
            return path
    return None


def resolve_backend(requested: str) -> tuple[str, str | None]:
    """按优先级解析桌面窗口后端，返回 (backend_name, executable_path)。"""
    if requested == "webview":
        try:
            import webview  # noqa: F401
            return "webview", None
        except ImportError as exc:
            raise RuntimeError("未安装 pywebview，无法使用 webview 后端") from exc

    if requested in ("edge", "chrome"):
        exe = find_browser_exe(requested)
        if not exe:
            raise RuntimeError(f"未在本机找到 {requested} 可执行文件")
        return requested, exe

    # auto 模式: pywebview -> Edge App -> Chrome App -> 默认浏览器
    try:
        import webview  # noqa: F401
        return "webview", None
    except ImportError:
        pass

    for kind in ("edge", "chrome"):
        exe = find_browser_exe(kind)
        if exe:
            return kind, exe

    return "browser", None


class _ExclusiveHTTPServer(ThreadingHTTPServer):
    """禁用 Windows SO_REUSEADDR，防止静默抢占已监听端口导致回环请求路由到其他进程。"""

    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def _is_port_in_use(port: int) -> bool:
    if port <= 0:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.15):
            return True
    except OSError:
        return False


def _create_server(
    defaults: dict[str, Any],
    app_config: dict[str, Any],
    preferred_port: int,
) -> tuple[ThreadingHTTPServer, int]:
    """创建本地 HTTP 服务；port=0 时按序跳过已被占用的端口，必要时由系统分配空闲端口。"""
    server_holder: list[ThreadingHTTPServer] = []

    def _shutdown_cb() -> None:
        if server_holder:
            server_holder[0].shutdown()

    handler_cls = kline_chart.make_handler(defaults, app_config, shutdown_callback=_shutdown_cb)

    if preferred_port == 0:
        default_port = int(defaults.get("default_port", 8766))
        candidates: list[int] = []
        for p in (default_port, 8766, 8767, 8768, 8769, 8770, 0):
            if p not in candidates:
                candidates.append(p)
        for candidate in candidates:
            if candidate > 0 and _is_port_in_use(candidate):
                continue
            try:
                srv = _ExclusiveHTTPServer(("127.0.0.1", candidate), handler_cls)
                server_holder.append(srv)
                return srv, int(srv.server_address[1])
            except OSError:
                continue
        raise RuntimeError("无法绑定本地 HTTP 端口")

    if _is_port_in_use(preferred_port):
        raise RuntimeError(f"端口 {preferred_port} 已被其他进程占用，请改用 --port 0 自动分配")
    srv = _ExclusiveHTTPServer(("127.0.0.1", preferred_port), handler_cls)
    server_holder.append(srv)
    return srv, int(srv.server_address[1])


def _wait_for_health(url: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    health_url = f"{url.rstrip('/')}/api/health"
    # 绕过系统 HTTP 代理（如 Clash 127.0.0.1:7897），直连本地回环地址
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with opener.open(health_url, timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_err = exc
            time.sleep(0.05)
    raise RuntimeError(f"本地服务启动超时: {health_url} ({last_err})")


def launch_desktop(args: argparse.Namespace) -> None:
    defaults = kline_chart.load_defaults()
    backend, exe = resolve_backend(args.backend)

    app_config = {
        "mode": "live",
        "title": defaults.get("title", "客户端"),
        "symbol": args.symbol.strip(),
        "provider": args.provider,
        "interval": args.interval,
        "range": args.range,
        "strategy": args.strategy,
        "refresh": args.refresh,
        "color_scheme": args.color_scheme,
        "symbols": kline_chart.load_watchlist(defaults),
    }

    if args.dry_run:
        preview_port = args.port or int(defaults.get("default_port", 8765))
        print(
            json_summary := (
                f"backend={backend}"
                + (f" exe={exe}" if exe else "")
                + f" url=http://127.0.0.1:{preview_port}/"
                + f" symbol={app_config['symbol']} interval={app_config['interval']}"
            )
        )
        return

    server, port = _create_server(defaults, app_config, args.port)
    url = f"http://127.0.0.1:{port}/"
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()
    threading.Thread(target=providers.warmup, daemon=True).start()

    try:
        _wait_for_health(url)
        print(f"→ 桌面客户端已启动 ({backend}): {url}")

        if backend == "webview":
            import webview

            webview.create_window(
                app_config["title"],
                url,
                width=args.width,
                height=args.height,
                min_size=(960, 620),
            )
            webview.start()
        elif backend in ("edge", "chrome") and exe:
            profile_dir = tempfile.mkdtemp(prefix="crypto-quant-app-")
            proc: subprocess.Popen[bytes] | None = None
            try:
                cmd = [
                    exe,
                    f"--app={url}",
                    f"--user-data-dir={profile_dir}",
                    f"--window-size={args.width},{args.height}",
                    "--proxy-bypass-list=localhost;127.0.0.1;::1",
                    "--new-window",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-extensions",
                ]
                proc = subprocess.Popen(cmd)
                pyw = shutil.which("pythonw") or sys.executable
                relaunch_cmd = f'"{pyw}" "{Path(__file__).resolve()}"'
                threading.Thread(
                    target=_apply_window_identity,
                    args=(proc.pid, kline_chart.ICON_PATH, relaunch_cmd, app_config["title"], _APP_USER_MODEL_ID),
                    daemon=True,
                ).start()
                proc.wait()
            finally:
                if proc is not None and proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except Exception:
                        pass
                shutil.rmtree(profile_dir, ignore_errors=True)
        else:
            print("→ 未检测到 pywebview / Edge / Chrome，回退使用系统默认浏览器。")
            webbrowser.open(url)
            srv_thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.shutdown()
        except Exception:
            pass
        server.server_close()
        print("→ 桌面客户端已退出。")


def create_windows_shortcut(dest_dir: Path | None = None, name: str = "客户端") -> Path:
    """生成指向 pythonw.exe 的 Windows .lnk 快捷方式（带独立 K 线图标，可直接固定到任务栏）。"""
    repo_root = Path(__file__).resolve().parents[3]
    target_dir = dest_dir or repo_root
    target_dir.mkdir(parents=True, exist_ok=True)
    lnk_path = target_dir / f"{name}.lnk"

    pyw = shutil.which("pythonw") or shutil.which("python") or sys.executable
    script_rel = r"skills\kline-chart\scripts\desktop_app.py"
    ico_path = kline_chart.ICON_PATH

    def _ps_esc(s: str) -> str:
        return s.replace("'", "''")

    ps_script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{_ps_esc(str(lnk_path))}'); "
        f"$sc.TargetPath = '{_ps_esc(pyw)}'; "
        f"$sc.Arguments = '\"{script_rel}\"'; "
        f"$sc.WorkingDirectory = '{_ps_esc(str(repo_root))}'; "
        "$sc.Description = '客户端'; "
        + (f"$sc.IconLocation = '{_ps_esc(str(ico_path))},0'; " if ico_path.exists() else "")
        + "$sc.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        check=True,
        capture_output=True,
        text=True,
    )
    _set_shortcut_appid(lnk_path, _APP_USER_MODEL_ID)
    return lnk_path


def main() -> None:
    defaults = kline_chart.load_defaults()
    provider_choices = ["auto", *sorted(providers.VALID_PROVIDERS)]
    color_choices = ["green_up", "red_up"]

    parser = argparse.ArgumentParser(description="加密货币独立桌面行情客户端")
    parser.add_argument("--symbol", default=defaults.get("default_symbol", "gate:BTC_USDT"))
    parser.add_argument("--provider", default="gate", choices=provider_choices)
    parser.add_argument("--interval", default=defaults.get("default_interval", "15m"), choices=sorted(providers.VALID_INTERVALS))
    parser.add_argument("--range", default=defaults.get("default_range", "auto"), choices=sorted(providers.VALID_RANGES))
    parser.add_argument("--strategy", default=defaults.get("default_strategy", "sma_crossover"), choices=sorted(kline_chart.VALID_STRATEGIES))
    parser.add_argument("--refresh", type=int, default=int(defaults.get("default_refresh_seconds", 5)))
    parser.add_argument("--color-scheme", default=defaults.get("color_scheme", "green_up"), choices=color_choices)
    parser.add_argument("--width", type=int, default=1420)
    parser.add_argument("--height", type=int, default=880)
    parser.add_argument("--port", type=int, default=0, help="指定端口；默认 0 自动优先使用 8766 或空闲端口")
    parser.add_argument("--backend", default="auto", choices=["auto", "webview", "edge", "chrome"])
    parser.add_argument("--dry-run", action="store_true", help="仅检测窗口后端并打印启动参数，不实际弹窗")
    parser.add_argument("--create-shortcut", action="store_true", help="生成带图标的 Windows 快捷方式 (.lnk)，可直接固定到任务栏")
    parser.add_argument("--shortcut-dir", default=None, help="快捷方式生成目录（默认生成在仓库根目录，可指定桌面路径）")
    args = parser.parse_args()
    if args.create_shortcut:
        out_dir = Path(args.shortcut_dir) if args.shortcut_dir else None
        lnk = create_windows_shortcut(out_dir)
        print(f"✓ 已生成快捷方式: {lnk}")
        return
    launch_desktop(args)


if __name__ == "__main__":
    main()
