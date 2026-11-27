#!/usr/bin/env python3
"""TradingView 加密市场与永续合约选币扫描器（免 Key 公开接口）。"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any

import requests

log = logging.getLogger("tradingview")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, Exception):
    pass

SCANNER_HOST = "https://scanner.tradingview.com"
SYMBOL_SEARCH_HOST = "https://symbol-search.tradingview.com"
NEWS_HOST = "https://news-headlines.tradingview.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
}

SCRIPT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = SCRIPT_DIR.parent / "assets"

_column_groups: dict | None = None
_scanner_columns: dict | None = None
_recommend_ratings: dict | None = None


def _load_asset(name: str) -> Any:
    fp = ASSETS_DIR / name
    if not fp.exists():
        log.warning(f"未找到资产文件: {fp}")
        return {}
    return json.loads(fp.read_text(encoding="utf-8"))


def column_groups() -> dict:
    global _column_groups
    if _column_groups is None:
        _column_groups = _load_asset("column_groups.json")
    return _column_groups


def scanner_columns() -> dict:
    global _scanner_columns
    if _scanner_columns is None:
        _scanner_columns = _load_asset("scanner_columns.json")
    return _scanner_columns


def recommend_ratings() -> dict:
    global _recommend_ratings
    if _recommend_ratings is None:
        _recommend_ratings = _load_asset("recommend_ratings.json")
    return _recommend_ratings


def _post(url: str, payload: dict, timeout: int = 20) -> Any:
    r = requests.post(url, json=payload, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _get(url: str, params: dict | None = None, timeout: int = 20) -> Any:
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _normalize_scanner_response(raw: dict, columns: list[str]) -> dict:
    if not isinstance(raw, dict) or "data" not in raw:
        return raw
    out_data = []
    for row in raw.get("data", []):
        record: dict[str, Any] = {"symbol": row.get("s")}
        vals = row.get("d", []) or []
        for col, val in zip(columns, vals):
            record[col] = val
        out_data.append(record)
    return {"totalCount": raw.get("totalCount"), "data": out_data}


def recommend_label(value: float | None) -> str | None:
    if value is None:
        return None
    for b in recommend_ratings().get("buckets", []):
        if b["min"] <= value <= b["max"]:
            return f"{b['label']} ({b['label_zh']})"
    return None


def scanner_scan(
    symbols: list[str] | None = None,
    columns: list[str] | None = None,
    filter_: list[dict] | None = None,
    market: str = "crypto",
    range_: tuple[int, int] = (0, 30),
    sort: dict | None = None,
) -> dict:
    cols = columns or column_groups().get("quote_basic", ["name", "close"])
    payload: dict[str, Any] = {"columns": cols, "range": list(range_)}
    if symbols:
        payload["symbols"] = {"tickers": symbols}
    elif filter_ is not None:
        payload["filter"] = filter_
    else:
        payload["filter"] = []
    if sort:
        payload["sort"] = sort

    url = f"{SCANNER_HOST}/{market}/scan"
    log.info(f"POST {url} (cols={len(cols)}, range={range_})")
    return _normalize_scanner_response(_post(url, payload), cols)


def scan_perps(
    exchange: str = "BINANCE",
    min_vol: float = 5_000_000.0,
    extra_filter: list[dict] | None = None,
    columns: list[str] | None = None,
    sort: dict | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    filters: list[dict] = [
        {"left": "type", "operation": "equal", "right": "swap"},
        {"left": "name", "operation": "match", "right": r"USDT\.P$"},
    ]
    if exchange and exchange.upper() != "ALL":
        filters.insert(0, {"left": "exchange", "operation": "equal", "right": exchange.upper()})
    if min_vol > 0:
        filters.append({"left": "24h_vol|5", "operation": "egreater", "right": float(min_vol)})
    if extra_filter:
        filters.extend(extra_filter)

    cols = columns or column_groups().get("quote_minimal")
    sort_cfg = sort or {"sortBy": "24h_vol|5", "sortOrder": "desc"}
    return scanner_scan(
        columns=cols,
        filter_=filters,
        market="crypto",
        range_=(offset, offset + limit),
        sort=sort_cfg,
    )


def technicals(symbol: str, market: str = "crypto") -> dict:
    res = scanner_scan(
        symbols=[symbol],
        columns=column_groups()["technicals"],
        market=market,
        range_=(0, 1),
    )
    if res.get("data"):
        row = res["data"][0]
        row["_rating"] = {
            "all": recommend_label(row.get("Recommend.All")),
            "ma": recommend_label(row.get("Recommend.MA")),
            "oscillators": recommend_label(row.get("Recommend.Other")),
        }
    return res


def symbol_search(
    query: str,
    search_type: str | None = "crypto",
    exchange: str | None = None,
    lang: str = "en",
) -> dict:
    params: dict[str, Any] = {"text": query, "hl": 1, "lang": lang, "domain": "production"}
    if search_type and search_type.lower() != "all":
        params["search_type"] = search_type
    if exchange:
        params["exchange"] = exchange.upper()
    return _get(f"{SYMBOL_SEARCH_HOST}/symbol_search/v3/", params=params)


def news_by_symbol(symbol: str, lang: str = "en") -> dict:
    return _get(f"{NEWS_HOST}/v2/headlines", params={"symbol": symbol, "client": "web", "lang": lang})


def news_global(lang: str = "en") -> dict:
    return _get(f"{NEWS_HOST}/v2/headlines", params={"client": "web", "lang": lang})


def fetch_all(symbol: str, market: str = "crypto") -> dict:
    res = {
        "symbol": symbol,
        "quote": scanner_scan(symbols=[symbol], columns=column_groups()["quote_basic"], market=market, range_=(0, 1)),
        "technicals": technicals(symbol, market=market),
        "pivots": scanner_scan(symbols=[symbol], columns=column_groups()["pivots"], market=market, range_=(0, 1)),
        "performance": scanner_scan(symbols=[symbol], columns=column_groups()["performance"], market=market, range_=(0, 1)),
        "news": news_by_symbol(symbol),
    }
    return res


MODES = [
    "perps",
    "screen",
    "market",
    "quote",
    "technicals",
    "pivots",
    "performance",
    "search",
    "news",
    "news-global",
    "columns",
    "groups",
    "all",
]


def _need(pos: list[str], n: int, mode: str, hint: str) -> None:
    if len(pos) < n:
        log.error(f"模式 '{mode}' 缺少参数: {hint}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="TradingView 加密与永续合约选币扫描器")
    parser.add_argument("mode", choices=MODES, help="运行模式")
    parser.add_argument("args", nargs="*", help="位置参数（如交易对 BINANCE:ETHUSDT.P 或搜索词）")
    parser.add_argument("--market", default="crypto", help="Scanner 市场（默认: crypto）")
    parser.add_argument("--exchange", default="BINANCE", help="交易所过滤（perps 默认 BINANCE，传 ALL 查全网）")
    parser.add_argument("--min-vol", type=float, default=5_000_000.0, help="perps 最小 24h 成交额 USDT（默认 5,000,000）")
    parser.add_argument("--perps-only", action="store_true", help="screen 模式仅筛选 USDT 永续合约")
    parser.add_argument("--columns", default=None, help="自定义逗号分隔字段列表")
    parser.add_argument("--filter", default=None, help='JSON 过滤条件，例如 \'[["RSI","less",30]]\'')
    parser.add_argument("--sort", default=None, help="排序字段，例如 24h_vol|5:desc 或 change:desc")
    parser.add_argument("--limit", type=int, default=20, help="返回条数上限（默认: 20）")
    parser.add_argument("--offset", type=int, default=0, help="分页偏移（默认: 0）")
    parser.add_argument("--type", default="crypto", help="search 资产类型（默认 crypto，传 all 不限）")
    parser.add_argument("--lang", default="en", help="search / news 语言（默认 en）")
    parser.add_argument("-o", "--output", default=None, help="输出到 JSON 文件")
    parser.add_argument("-q", "--quiet", action="store_true", help="静默日志")
    args = parser.parse_args()

    if args.quiet:
        log.setLevel(logging.WARNING)

    custom_cols = [c.strip() for c in args.columns.split(",") if c.strip()] if args.columns else None

    sort_dict: dict | None = None
    if args.sort:
        if ":" in args.sort:
            field, order = args.sort.split(":", 1)
            sort_dict = {"sortBy": field, "sortOrder": order}
        else:
            sort_dict = {"sortBy": args.sort, "sortOrder": "desc"}

    filter_list: list[dict] | None = None
    if args.filter:
        raw = json.loads(args.filter)
        if raw and isinstance(raw[0], list):
            filter_list = [{"left": x[0], "operation": x[1], "right": x[2]} for x in raw]
        else:
            filter_list = raw

    m = args.mode
    pos = args.args
    try:
        if m == "perps":
            result = scan_perps(
                exchange=args.exchange,
                min_vol=args.min_vol,
                extra_filter=filter_list,
                columns=custom_cols,
                sort=sort_dict,
                limit=args.limit,
                offset=args.offset,
            )
        elif m == "screen":
            filters = list(filter_list or [])
            if args.perps_only:
                filters.extend([
                    {"left": "type", "operation": "equal", "right": "swap"},
                    {"left": "name", "operation": "match", "right": r"USDT\.P$"},
                ])
            if args.exchange and args.exchange.upper() != "ALL" and not any(f.get("left") == "exchange" for f in filters):
                filters.append({"left": "exchange", "operation": "equal", "right": args.exchange.upper()})
            result = scanner_scan(
                columns=custom_cols or column_groups()["quote_basic"],
                filter_=filters,
                market=args.market,
                range_=(args.offset, args.offset + args.limit),
                sort=sort_dict or {"sortBy": "24h_vol|5", "sortOrder": "desc"},
            )
        elif m == "market":
            mkt = pos[0] if pos else args.market
            result = scanner_scan(
                columns=custom_cols or column_groups()["quote_minimal"],
                filter_=[],
                market=mkt,
                range_=(args.offset, args.offset + args.limit),
                sort=sort_dict or {"sortBy": "24h_vol|5", "sortOrder": "desc"},
            )
        elif m == "quote":
            _need(pos, 1, m, "SYMBOL (例如 BINANCE:ETHUSDT.P)")
            result = scanner_scan(symbols=[pos[0]], columns=custom_cols or column_groups()["quote_basic"], market=args.market, range_=(0, 1))
        elif m == "technicals":
            _need(pos, 1, m, "SYMBOL (例如 BINANCE:ETHUSDT.P)")
            result = technicals(pos[0], market=args.market)
        elif m == "pivots":
            _need(pos, 1, m, "SYMBOL (例如 BINANCE:ETHUSDT.P)")
            result = scanner_scan(symbols=[pos[0]], columns=custom_cols or column_groups()["pivots"], market=args.market, range_=(0, 1))
        elif m == "performance":
            _need(pos, 1, m, "SYMBOL (例如 BINANCE:ETHUSDT.P)")
            result = scanner_scan(symbols=[pos[0]], columns=custom_cols or column_groups()["performance"], market=args.market, range_=(0, 1))
        elif m == "search":
            _need(pos, 1, m, "QUERY (例如 NIO 或 BTC)")
            ex = None if args.exchange.upper() == "ALL" else args.exchange
            result = symbol_search(" ".join(pos), search_type=args.type, exchange=ex, lang=args.lang)
        elif m == "news":
            _need(pos, 1, m, "SYMBOL (例如 BINANCE:BTCUSDT.P)")
            result = news_by_symbol(pos[0], lang=args.lang)
        elif m == "news-global":
            result = news_global(lang=args.lang)
        elif m == "columns":
            grp = pos[0] if pos else None
            if grp:
                cols = column_groups().get(grp)
                result = {"group": grp, "columns": cols} if cols else {"error": f"未知分组: {grp}", "groups": list(column_groups().keys())}
            else:
                result = scanner_columns()
        elif m == "groups":
            cg = column_groups()
            result = {k: {"count": len(v), "sample": v[:5]} for k, v in cg.items() if not k.startswith("_")}
        elif m == "all":
            _need(pos, 1, m, "SYMBOL (例如 BINANCE:ETHUSDT.P)")
            result = fetch_all(pos[0], market=args.market)
        else:
            parser.print_help()
            sys.exit(1)
    except requests.HTTPError as e:
        log.error(f"HTTP Error: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Error: {e}")
        sys.exit(1)

    text_out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text_out, encoding="utf-8")
        log.info(f"已保存至: {args.output}")
    else:
        print(text_out)


if __name__ == "__main__":
    main()
