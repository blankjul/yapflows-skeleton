#!/usr/bin/env python3
# description: Stock and financial data via yfinance
# usage: {python} {path} <command> [options] — run with --help for full usage
"""
finance — Stock data CLI powered by yfinance.

Commands:
  price    Current price, change, and key stats
  history  OHLCV price history
  info     Company profile and fundamentals
  news     Recent news headlines
"""
from __future__ import annotations

import argparse
import json
import sys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        sys.exit("yfinance not installed. Run: pip install yfinance")


def _ticker(yf, symbol: str):
    t = yf.Ticker(symbol.upper())
    return t


USE_COLOR = sys.stdout.isatty()
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
RED    = "\033[31m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"


def c(code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if USE_COLOR else text


def _signed(val: float, fmt: str = "+.2f") -> str:
    color = GREEN if val >= 0 else RED
    return c(color, f"{val:{fmt}}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_price(args: argparse.Namespace) -> None:
    yf = _import_yf()
    symbols = [s.upper() for s in args.symbols]

    for symbol in symbols:
        t = _ticker(yf, symbol)
        info = t.fast_info

        try:
            price = info.last_price
            prev  = info.previous_close
            change = price - prev
            pct    = (change / prev) * 100 if prev else 0
            high52 = info.year_high
            low52  = info.year_low
            volume = info.three_month_average_volume
            mktcap = info.market_cap
        except Exception as e:
            print(f"{symbol}: error fetching data — {e}")
            continue

        if args.json:
            print(json.dumps({
                "symbol": symbol,
                "price": price,
                "change": round(change, 4),
                "change_pct": round(pct, 4),
                "prev_close": prev,
                "52w_high": high52,
                "52w_low": low52,
                "avg_volume_3m": volume,
                "market_cap": mktcap,
            }, indent=2))
            continue

        cap_str = ""
        if mktcap:
            if mktcap >= 1e12:
                cap_str = f"  mktcap {mktcap/1e12:.2f}T"
            elif mktcap >= 1e9:
                cap_str = f"  mktcap {mktcap/1e9:.1f}B"
            elif mktcap >= 1e6:
                cap_str = f"  mktcap {mktcap/1e6:.0f}M"

        print(
            c(BOLD, f"{symbol:<6}")
            + f"  {c(BOLD, f'${price:.2f}')}"
            + f"  {_signed(change, '+.2f')}  {_signed(pct, '+.2f')}%"
            + f"  52w [{low52:.2f}–{high52:.2f}]"
            + cap_str
        )


def cmd_history(args: argparse.Namespace) -> None:
    yf = _import_yf()
    symbol = args.symbol.upper()
    t = _ticker(yf, symbol)

    hist = t.history(period=args.period, interval=args.interval)
    if hist.empty:
        sys.exit(f"No history data for {symbol} (period={args.period}, interval={args.interval})")

    if args.json:
        records = []
        for dt, row in hist.iterrows():
            records.append({
                "date": str(dt.date()) if hasattr(dt, "date") else str(dt),
                "open":   round(row["Open"], 4),
                "high":   round(row["High"], 4),
                "low":    round(row["Low"], 4),
                "close":  round(row["Close"], 4),
                "volume": int(row["Volume"]),
            })
        print(json.dumps(records, indent=2))
        return

    print(c(BOLD, f"{symbol}  {args.period}  ({args.interval} bars)"))
    print(c(DIM, f"{'Date':<12}  {'Open':>8}  {'High':>8}  {'Low':>8}  {'Close':>8}  {'Volume':>12}"))
    print(c(DIM, "-" * 64))

    rows = list(hist.iterrows())
    if args.tail:
        rows = rows[-args.tail:]

    prev_close = None
    for dt, row in rows:
        date_str = str(dt.date()) if hasattr(dt, "date") else str(dt)[:10]
        close = row["Close"]
        color = ""
        if prev_close is not None:
            color = GREEN if close >= prev_close else RED
        close_str = c(color, f"{close:>8.2f}") if color else f"{close:>8.2f}"
        print(
            f"{date_str:<12}  {row['Open']:>8.2f}  {row['High']:>8.2f}"
            f"  {row['Low']:>8.2f}  {close_str}  {int(row['Volume']):>12,}"
        )
        prev_close = close


def cmd_info(args: argparse.Namespace) -> None:
    yf = _import_yf()
    symbol = args.symbol.upper()
    t = _ticker(yf, symbol)
    info = t.info

    if args.json:
        print(json.dumps(info, indent=2, default=str))
        return

    fields = [
        ("Name",            info.get("longName") or info.get("shortName")),
        ("Sector",          info.get("sector")),
        ("Industry",        info.get("industry")),
        ("Country",         info.get("country")),
        ("Employees",       f"{info.get('fullTimeEmployees', 0):,}" if info.get("fullTimeEmployees") else None),
        ("Exchange",        info.get("exchange")),
        ("Currency",        info.get("currency")),
        ("PE (trailing)",   f"{info.get('trailingPE'):.2f}" if info.get("trailingPE") else None),
        ("PE (forward)",    f"{info.get('forwardPE'):.2f}" if info.get("forwardPE") else None),
        ("EPS (ttm)",       f"{info.get('trailingEps'):.2f}" if info.get("trailingEps") else None),
        ("Div yield",       f"{info.get('dividendYield', 0)*100:.2f}%" if info.get("dividendYield") else None),
        ("Beta",            f"{info.get('beta'):.2f}" if info.get("beta") else None),
        ("Avg volume",      f"{info.get('averageVolume', 0):,}" if info.get("averageVolume") else None),
        ("Float",           f"{info.get('floatShares', 0)/1e6:.1f}M" if info.get("floatShares") else None),
        ("Short %",         f"{info.get('shortPercentOfFloat', 0)*100:.1f}%" if info.get("shortPercentOfFloat") else None),
        ("Target price",    f"${info.get('targetMeanPrice'):.2f}" if info.get("targetMeanPrice") else None),
        ("Recommendation",  info.get("recommendationKey")),
    ]

    print(c(BOLD, f"{symbol}"))
    for label, val in fields:
        if val:
            print(f"  {c(DIM, f'{label:<16}')} {val}")

    summary = info.get("longBusinessSummary", "")
    if summary and not args.no_summary:
        print()
        # Wrap at 80 chars
        words = summary.split()
        line = "  "
        for word in words:
            if len(line) + len(word) > 82:
                print(line)
                line = "  " + word + " "
            else:
                line += word + " "
        if line.strip():
            print(line)


def cmd_news(args: argparse.Namespace) -> None:
    yf = _import_yf()
    symbol = args.symbol.upper()
    t = _ticker(yf, symbol)

    try:
        news = t.news or []
    except Exception as e:
        sys.exit(f"Failed to fetch news for {symbol}: {e}")

    if not news:
        print(f"No news found for {symbol}.")
        return

    items = news[:args.n]

    if args.json:
        print(json.dumps(items, indent=2, default=str))
        return

    print(c(BOLD, f"{symbol} — recent news"))
    print()
    from datetime import datetime, timezone
    for item in items:
        content   = item.get("content") or item  # new API nests under "content"
        title     = content.get("title", "")
        publisher = (content.get("provider") or {}).get("displayName", "") or item.get("publisher", "")
        link      = (content.get("canonicalUrl") or {}).get("url", "") or item.get("link", "")
        pub_date  = content.get("pubDate", "") or ""
        if pub_date:
            try:
                dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_str = pub_date[:16]
        else:
            ts = item.get("providerPublishTime", 0)
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if ts else ""

        print(c(BOLD, title))
        print(c(DIM, f"  {publisher}  {date_str}"))
        if args.links:
            print(c(CYAN, f"  {link}"))
        print()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finance",
        description="Stock and financial data via yfinance.",
    )
    subs = parser.add_subparsers(dest="command", metavar="COMMAND")
    subs.required = True

    # --- price ---
    p_price = subs.add_parser("price", help="Current price and key stats")
    p_price.add_argument("symbols", nargs="+", help="Ticker symbol(s), e.g. AMZN AAPL MSFT")
    p_price.add_argument("--json", action="store_true", help="Output JSON")

    # --- history ---
    p_hist = subs.add_parser("history", help="OHLCV price history")
    p_hist.add_argument("symbol",                  help="Ticker symbol")
    p_hist.add_argument("--period",   default="1mo",
                        choices=["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"],
                        help="Data period (default: 1mo)")
    p_hist.add_argument("--interval", default="1d",
                        choices=["1m","2m","5m","15m","30m","60m","90m","1h","1d","5d","1wk","1mo","3mo"],
                        help="Bar interval (default: 1d)")
    p_hist.add_argument("--tail",     type=int, metavar="N", help="Show only last N bars")
    p_hist.add_argument("--json",     action="store_true", help="Output JSON")

    # --- info ---
    p_info = subs.add_parser("info", help="Company profile and fundamentals")
    p_info.add_argument("symbol",         help="Ticker symbol")
    p_info.add_argument("--no-summary",   action="store_true", help="Skip business summary")
    p_info.add_argument("--json",         action="store_true", help="Output full info JSON")

    # --- news ---
    p_news = subs.add_parser("news", help="Recent news headlines")
    p_news.add_argument("symbol",       help="Ticker symbol")
    p_news.add_argument("-n",           type=int, default=5, help="Number of headlines (default 5)")
    p_news.add_argument("--links",      action="store_true", help="Show article URLs")
    p_news.add_argument("--json",       action="store_true", help="Output JSON")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "price":
        cmd_price(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "news":
        cmd_news(args)


if __name__ == "__main__":
    try:
        main()
    except (BrokenPipeError, KeyboardInterrupt):
        sys.exit(0)
    finally:
        try:
            sys.stdout.flush()
        except BrokenPipeError:
            pass
        try:
            sys.stderr.close()
        except Exception:
            pass
