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
        "title": defaults.get("title", "加密货币桌面行情客户端"),
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
    parser.add_argument("--port", type=int, default=0, help="指定端口；默认 0 自动优先使用 8765 或空闲端口")
    parser.add_argument("--backend", default="auto", choices=["auto", "webview", "edge", "chrome"])
    parser.add_argument("--dry-run", action="store_true", help="仅检测窗口后端并打印启动参数，不实际弹窗")
    args = parser.parse_args()
    launch_desktop(args)


if __name__ == "__main__":
    main()
