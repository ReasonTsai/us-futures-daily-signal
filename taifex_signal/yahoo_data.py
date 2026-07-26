from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd


YAHOO_SYMBOLS = {"ES": "ES=F", "NQ": "NQ=F", "YM": "YM=F"}


def parse_yahoo_chart(payload: dict[str, Any]) -> pd.DataFrame:
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise ValueError(f"Yahoo Finance 回傳錯誤: {chart['error']}")

    results = chart.get("result") or []
    if not results:
        raise ValueError("Yahoo Finance 沒有回傳行情資料")
    result = results[0]
    timestamps = result.get("timestamp") or []
    quotes = ((result.get("indicators") or {}).get("quote") or [])
    if not timestamps or not quotes:
        raise ValueError("Yahoo Finance 回傳資料缺少 timestamp 或 quote")

    values = quotes[0]
    frame = pd.DataFrame(
        {
            "open": values.get("open"),
            "high": values.get("high"),
            "low": values.get("low"),
            "close": values.get("close"),
            "volume": values.get("volume"),
        },
        index=pd.to_datetime(timestamps, unit="s", utc=True),
    )
    frame = frame.dropna(subset=["open", "high", "low", "close", "volume"])
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    valid_high = frame["high"] >= frame[["open", "close", "low"]].max(axis=1)
    valid_low = frame["low"] <= frame[["open", "close", "high"]].min(axis=1)
    dropped_invalid_bars = int((~(valid_high & valid_low)).sum())
    frame = frame[valid_high & valid_low]
    if frame.empty:
        raise ValueError("Yahoo Finance 日 K 全部為空值")
    frame.attrs["dropped_invalid_bars"] = dropped_invalid_bars
    return frame


def fetch_yahoo_daily(
    symbol: str,
    *,
    period: str = "2y",
    timeout: int = 30,
    opener: Callable[..., Any] = urlopen,
) -> pd.DataFrame:
    encoded_symbol = quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
        f"?range={period}&interval=1d&includePrePost=false&events=div%2Csplits"
    )
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 daily-futures-signal/1.0",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.load(response)
    except Exception as exc:
        raise RuntimeError(f"無法取得 {symbol} 的 Yahoo Finance 日 K: {exc}") from exc
    return parse_yahoo_chart(payload)
