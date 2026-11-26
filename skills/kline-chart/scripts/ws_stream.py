"""
ws_stream.py — Gate.io WebSocket v4 实时行情接入与 SSE 广播中心。

订阅 Gate.io 公开现货频道：
- ``spot.candlesticks``：权威 OHLCV 与新 K 线时间桶对齐
- ``spot.trades``：逐笔成交驱动 1 秒多次跳价
- ``spot.tickers``：自选列表 24h 实时报价与涨跌幅同步

依赖可选轻量包 ``websocket-client``；未安装时 ``HAS_WEBSOCKET=False``，
上层自动降级为 1s REST 轮询。
"""
from __future__ import annotations

import json
import queue
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

try:
    import websocket
    HAS_WEBSOCKET = True
except ImportError:
    websocket = None  # type: ignore[assignment]
    HAS_WEBSOCKET = False

GATE_WS_URL = "wss://api.gateio.ws/ws/v4/"

_WS_INTERVAL_MAP = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1wk": "7d",
    "1mo": "30d",
}


def _detect_http_proxy() -> tuple[str | None, int | None]:
    proxies = urllib.request.getproxies()
    px = proxies.get("https") or proxies.get("http")
    if not px:
        return None, None
    u = urllib.parse.urlparse(px if "://" in px else f"http://{px}")
    return u.hostname, u.port


def _bar_time_to_ts(time_val: int | str) -> int:
    if isinstance(time_val, int):
        return time_val
    s = str(time_val).strip()
    if s.isdigit():
        return int(s)
    dt = datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


class _ChartChannel:
    """单个 (pair, interval) 的上游 Gate.io WS 会话与订阅者广播组。"""

    def __init__(
        self,
        pair: str,
        interval: str,
        is_intraday: bool,
        precision_fn: Callable[[float], int],
        tail_ind_fn: Callable[[list[float], int | str], dict[str, dict[str, Any] | None]],
    ) -> None:
        self.pair = pair
        self.interval = interval
        self.gate_interval = _WS_INTERVAL_MAP.get(interval, interval)
        self.is_intraday = is_intraday
        self._precision_fn = precision_fn
        self._tail_ind_fn = tail_ind_fn

        self._lock = threading.Lock()
        self._bars: list[dict[str, Any]] = []
        self._prev_close: float = 0.0
        self._watchlist: set[str] = {pair}
        self._subs: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._next_sub_id = 1
        self._stop_timer: threading.Timer | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._new_watchlist_pairs: set[str] = set()

    def seed(self, raw_data: dict[str, Any], watchlist_pairs: list[str]) -> None:
        with self._lock:
            if not self._bars:
                seeded: list[dict[str, Any]] = []
                for b in raw_data.get("bars", []):
                    t_val = b["time"]
                    seeded.append(
                        {
                            "ts": _bar_time_to_ts(t_val),
                            "time": t_val,
                            "open": float(b["open"]),
                            "high": float(b["high"]),
                            "low": float(b["low"]),
                            "close": float(b["close"]),
                            "volume": float(b.get("volume", 0.0)),
                        }
                    )
                self._bars = seeded[-1000:]
            if not self._prev_close:
                self._prev_close = float(raw_data.get("prev_close") or (self._bars[0]["open"] if self._bars else 0.0))
            for wp in watchlist_pairs:
                if wp and wp not in self._watchlist:
                    self._watchlist.add(wp)
                    self._new_watchlist_pairs.add(wp)

    def add_subscriber(self) -> tuple[int, queue.Queue[dict[str, Any]]]:
        with self._lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
                self._stop_timer = None
            sid = self._next_sub_id
            self._next_sub_id += 1
            q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=64)
            self._subs[sid] = q
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()
            return sid, q

    def remove_subscriber(self, sid: int, on_idle: Callable[[], None]) -> None:
        with self._lock:
            self._subs.pop(sid, None)
            if not self._subs:
                if self._stop_timer is not None:
                    self._stop_timer.cancel()
                t = threading.Timer(3.0, self._shutdown_if_empty, args=(on_idle,))
                t.daemon = True
                self._stop_timer = t
                t.start()

    def _shutdown_if_empty(self, on_idle: Callable[[], None]) -> None:
        with self._lock:
            if self._subs:
                return
            self._stop_event.set()
        on_idle()

    def _broadcast(self, event_obj: dict[str, Any]) -> None:
        with self._lock:
            queues = list(self._subs.values())
        for q in queues:
            try:
                q.put_nowait(event_obj)
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(event_obj)
                except queue.Full:
                    pass

    def _build_tick_event_locked(self) -> dict[str, Any] | None:
        if not self._bars:
            return None
        last_b = self._bars[-1]
        closes = [b["close"] for b in self._bars[-120:]]
        ind_tail = self._tail_ind_fn(closes, last_b["time"])
        last_p = float(last_b["close"])
        prev_p = self._prev_close or float(self._bars[0]["open"])
        chg = last_p - prev_p
        chg_pct = (chg / prev_p * 100.0) if prev_p else 0.0
        prec = self._precision_fn(last_p)
        return {
            "type": "tick",
            "symbol": self.pair,
            "interval": self.interval,
            "candle": {
                "time": last_b["time"],
                "open": round(last_b["open"], 6),
                "high": round(last_b["high"], 6),
                "low": round(last_b["low"], 6),
                "close": round(last_b["close"], 6),
            },
            "volume": {
                "time": last_b["time"],
                "value": last_b["volume"],
            },
            "indicators": ind_tail,
            "meta": {
                "price_precision": prec,
                "last_price": round(last_p, prec),
                "change": round(chg, prec),
                "change_pct": round(chg_pct, 2),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

    def _handle_message(self, msg: dict[str, Any]) -> None:
        if msg.get("event") != "update" or not msg.get("result"):
            return
        ch = str(msg.get("channel") or "")
        res = msg["result"]
        items = res if isinstance(res, list) else [res]

        if ch == "spot.candlesticks":
            ev_out: dict[str, Any] | None = None
            with self._lock:
                for k in items:
                    if not isinstance(k, dict) or k.get("t") is None:
                        continue
                    t = int(k["t"])
                    if self._bars and t < self._bars[-1]["ts"]:
                        continue
                    o = float(k["o"])
                    h = float(k["h"])
                    l = float(k["l"])
                    c = float(k["c"])
                    h = max(h, o, c)
                    l = min(l, o, c)
                    v_raw = k.get("a") if k.get("a") is not None else k.get("v", 0.0)
                    v = float(v_raw)
                    t_key: int | str = (
                        t if self.is_intraday else datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
                    )
                    bar = {"ts": t, "time": t_key, "open": o, "high": h, "low": l, "close": c, "volume": v}
                    if self._bars and t == self._bars[-1]["ts"]:
                        self._bars[-1] = bar
                    else:
                        self._bars.append(bar)
                        if len(self._bars) > 1000:
                            self._bars = self._bars[-1000:]
                ev_out = self._build_tick_event_locked()
            if ev_out:
                self._broadcast(ev_out)

        elif ch == "spot.trades":
            latest_px: float | None = None
            for tr in items:
                if isinstance(tr, dict) and tr.get("price") is not None:
                    try:
                        latest_px = float(tr["price"])
                    except (TypeError, ValueError):
                        pass
            if latest_px is None:
                return
            ev_out = None
            with self._lock:
                if self._bars:
                    last_b = self._bars[-1]
                    last_b["close"] = latest_px
                    if latest_px > last_b["high"]:
                        last_b["high"] = latest_px
                    if latest_px < last_b["low"]:
                        last_b["low"] = latest_px
                    ev_out = self._build_tick_event_locked()
            if ev_out:
                self._broadcast(ev_out)

        elif ch == "spot.tickers":
            for tk in items:
                if not isinstance(tk, dict):
                    continue
                cp = str(tk.get("currency_pair") or "").upper()
                if not cp or tk.get("last") is None:
                    continue
                try:
                    last_p = float(tk["last"])
                    chg_pct = round(float(tk.get("change_percentage") or 0.0), 2)
                except (TypeError, ValueError):
                    continue
                if cp == self.pair and (1.0 + chg_pct / 100.0) > 0:
                    with self._lock:
                        self._prev_close = last_p / (1.0 + chg_pct / 100.0)
                self._broadcast(
                    {
                        "type": "quote",
                        "provider": "gate",
                        "symbol": cp,
                        "resolved_spec": f"gate:{cp}",
                        "last_price": last_p,
                        "change_pct": chg_pct,
                    }
                )

    def _connect_ws(self) -> Any:
        assert websocket is not None
        px_host, px_port = _detect_http_proxy()
        kwargs: dict[str, Any] = {"timeout": 10}
        if px_host and px_port:
            kwargs["http_proxy_host"] = px_host
            kwargs["http_proxy_port"] = px_port
            kwargs["proxy_type"] = "http"
        return websocket.create_connection(GATE_WS_URL, **kwargs)

    def _run_loop(self) -> None:
        backoff = 1.0
        while not self._stop_event.is_set():
            ws = None
            try:
                ws = self._connect_ws()
                ws.settimeout(1.0)
                backoff = 1.0

                with self._lock:
                    wl_list = sorted(self._watchlist)
                    self._new_watchlist_pairs.clear()

                now = int(time.time())
                subs = [
                    ("spot.candlesticks", [self.gate_interval, self.pair]),
                    ("spot.trades", [self.pair]),
                ]
                if wl_list:
                    subs.append(("spot.tickers", wl_list))
                for ch, pl in subs:
                    ws.send(json.dumps({"time": now, "channel": ch, "event": "subscribe", "payload": pl}))

                self._broadcast({"type": "status", "status": "connected"})
                last_ping = time.time()

                while not self._stop_event.is_set():
                    with self._lock:
                        extra_pairs = sorted(self._new_watchlist_pairs)
                        self._new_watchlist_pairs.clear()
                    if extra_pairs:
                        ws.send(
                            json.dumps(
                                {
                                    "time": int(time.time()),
                                    "channel": "spot.tickers",
                                    "event": "subscribe",
                                    "payload": extra_pairs,
                                }
                            )
                        )

                    if time.time() - last_ping >= 15.0:
                        ws.send(json.dumps({"time": int(time.time()), "channel": "spot.ping"}))
                        last_ping = time.time()

                    try:
                        raw = ws.recv()
                    except Exception as recv_exc:
                        if websocket is not None and isinstance(recv_exc, websocket.WebSocketTimeoutException):
                            continue
                        if isinstance(recv_exc, TimeoutError):
                            continue
                        raise

                    if not raw:
                        break
                    self._handle_message(json.loads(raw))

            except Exception as exc:
                if self._stop_event.is_set():
                    break
                self._broadcast({"type": "status", "status": "reconnecting", "error": str(exc)})
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2.0, 15.0)
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass


class GateStreamHub:
    """管理所有活跃的 Gate.io WebSocket 行情订阅频道。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._channels: dict[tuple[str, str], _ChartChannel] = {}

    def subscribe(
        self,
        pair: str,
        interval: str,
        raw_data: dict[str, Any],
        watchlist_pairs: list[str],
        precision_fn: Callable[[float], int],
        tail_ind_fn: Callable[[list[float], int | str], dict[str, dict[str, Any] | None]],
    ) -> tuple[_ChartChannel, int, queue.Queue[dict[str, Any]]]:
        key = (pair, interval)
        with self._lock:
            chan = self._channels.get(key)
            if chan is None:
                chan = _ChartChannel(
                    pair=pair,
                    interval=interval,
                    is_intraday=bool(raw_data.get("is_intraday", True)),
                    precision_fn=precision_fn,
                    tail_ind_fn=tail_ind_fn,
                )
                self._channels[key] = chan
        chan.seed(raw_data, watchlist_pairs)
        sid, q = chan.add_subscriber()
        return chan, sid, q

    def unsubscribe(self, pair: str, interval: str, chan: _ChartChannel, sid: int) -> None:
        key = (pair, interval)

        def _cleanup() -> None:
            with self._lock:
                if self._channels.get(key) is chan:
                    self._channels.pop(key, None)

        chan.remove_subscriber(sid, _cleanup)


HUB = GateStreamHub()
