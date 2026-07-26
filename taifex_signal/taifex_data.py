from __future__ import annotations

from pathlib import Path
from typing import IO

import pandas as pd


COLUMN_ALIASES = {
    "date": ("交易日期", "成交日期", "date", "trade_date"),
    "product": ("商品代號", "商品", "product", "product_id"),
    "contract": ("到期月份(週別)", "到期月份", "契約月份", "contract", "contract_month"),
    "time": ("成交時間", "時間", "time", "trade_time"),
    "price": ("成交價格", "成交價", "price", "trade_price"),
    "volume": ("成交數量(B+S)", "成交數量", "成交量", "volume", "trade_volume"),
}


def _normalize_name(value: object) -> str:
    return str(value).strip().replace("\ufeff", "").replace(" ", "")


def _resolve_columns(frame: pd.DataFrame) -> dict[str, str]:
    normalized = {_normalize_name(column): str(column) for column in frame.columns}
    resolved: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            match = normalized.get(_normalize_name(alias))
            if match is not None:
                resolved[canonical] = match
                break
    missing = [name for name in COLUMN_ALIASES if name not in resolved]
    if missing:
        raise ValueError(f"期交所逐筆 CSV 缺少欄位: {', '.join(missing)}")
    return resolved


def read_taifex_ticks(
    source: str | Path | IO[bytes] | IO[str],
    product: str = "TX",
    contract: str | None = None,
) -> pd.DataFrame:
    """讀取期交所逐筆 CSV，篩選商品及契約並回傳標準化成交資料。"""
    last_error: Exception | None = None
    frame: pd.DataFrame | None = None
    for encoding in ("utf-8-sig", "big5", "cp950"):
        try:
            if hasattr(source, "seek"):
                source.seek(0)
            frame = pd.read_csv(source, encoding=encoding, low_memory=False)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    if frame is None:
        raise ValueError("無法辨識 CSV 編碼") from last_error

    columns = _resolve_columns(frame)
    ticks = frame[[columns[name] for name in COLUMN_ALIASES]].copy()
    ticks.columns = list(COLUMN_ALIASES)
    ticks["product"] = ticks["product"].astype(str).str.strip()
    ticks["contract"] = ticks["contract"].astype(str).str.strip()
    ticks = ticks[ticks["product"].eq(product)]
    if ticks.empty:
        raise ValueError(f"CSV 中找不到商品 {product}")

    ticks["price"] = pd.to_numeric(
        ticks["price"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )
    ticks["volume"] = pd.to_numeric(
        ticks["volume"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )
    ticks = ticks.dropna(subset=["price", "volume"])
    ticks = ticks[ticks["volume"] > 0]

    if contract is None:
        totals = ticks.groupby("contract", observed=True)["volume"].sum()
        if totals.empty:
            raise ValueError("找不到有效成交資料")
        contract = str(totals.idxmax())
    ticks = ticks[ticks["contract"].eq(contract)]
    if ticks.empty:
        raise ValueError(f"找不到契約 {contract}")

    date_text = ticks["date"].astype(str).str.replace(r"\D", "", regex=True).str[:8]
    time_text = (
        ticks["time"]
        .astype(str)
        .str.replace(r"\D", "", regex=True)
        .str.zfill(6)
        .str[:6]
    )
    ticks["timestamp"] = pd.to_datetime(
        date_text + time_text,
        format="%Y%m%d%H%M%S",
        errors="coerce",
    )
    ticks = ticks.dropna(subset=["timestamp"]).sort_values("timestamp")
    return ticks[["timestamp", "product", "contract", "price", "volume"]].reset_index(drop=True)


def ticks_to_bars(
    ticks: pd.DataFrame,
    interval: str = "5min",
    session: str = "all",
) -> pd.DataFrame:
    """把成交資料合成 OHLCV；session 可用 all、day 或 night。"""
    required = {"timestamp", "price", "volume"}
    missing = sorted(required.difference(ticks.columns))
    if missing:
        raise ValueError(f"成交資料缺少欄位: {', '.join(missing)}")
    if session not in {"all", "day", "night"}:
        raise ValueError("session 必須是 all、day 或 night")

    frame = ticks.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
    clock = frame["timestamp"].dt.time
    day_start = pd.Timestamp("08:45").time()
    day_end = pd.Timestamp("13:45").time()
    if session == "day":
        frame = frame[(clock >= day_start) & (clock <= day_end)]
    elif session == "night":
        frame = frame[(clock < day_start) | (clock > day_end)]
    if frame.empty:
        raise ValueError(f"{session} 時段沒有成交資料")

    bars = (
        frame.set_index("timestamp")
        .resample(interval)
        .agg(
            open=("price", "first"),
            high=("price", "max"),
            low=("price", "min"),
            close=("price", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )
    return bars
