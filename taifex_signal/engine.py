from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class SignalConfig:
    moving_averages: tuple[int, ...] = (5, 10, 20, 60, 120, 240)
    volume_lookback: int = 20
    extreme_volume_multiple: float = 2.0
    ma_touch_tolerance: float = 0.002
    reclaim_lookback: int = 3
    close_confirmation: float = 0.001

    def validate(self) -> None:
        if not self.moving_averages or any(x <= 0 for x in self.moving_averages):
            raise ValueError("moving_averages 必須包含正整數")
        if self.volume_lookback < 2:
            raise ValueError("volume_lookback 必須至少為 2")
        if self.extreme_volume_multiple <= 1:
            raise ValueError("extreme_volume_multiple 必須大於 1")
        if self.ma_touch_tolerance < 0 or self.close_confirmation < 0:
            raise ValueError("容許值不可為負數")
        if self.reclaim_lookback < 1:
            raise ValueError("reclaim_lookback 必須至少為 1")


def _validate_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_COLUMNS if column not in bars.columns]
    if missing:
        raise ValueError(f"缺少必要欄位: {', '.join(missing)}")
    if bars.empty:
        raise ValueError("K 棒資料不可為空")

    result = bars.copy()
    for column in REQUIRED_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="raise")

    if result[list(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("OHLCV 不可包含空值")
    if (result["volume"] < 0).any():
        raise ValueError("成交量不可為負數")
    if (result["high"] < result[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("high 小於同根 K 棒的其他價格")
    if (result["low"] > result[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("low 大於同根 K 棒的其他價格")
    return result


def _event(
    kind: str,
    side: str,
    strength: str,
    reason: str,
    **details: Any,
) -> dict[str, Any]:
    return {
        "type": kind,
        "side": side,
        "strength": strength,
        "reason": reason,
        "details": details,
    }


def analyze_bars(
    bars: pd.DataFrame,
    config: SignalConfig | None = None,
) -> dict[str, Any]:
    """分析最後一根 K 棒，回傳大量及均線事件。"""
    config = config or SignalConfig()
    config.validate()
    frame = _validate_bars(bars)

    for period in config.moving_averages:
        frame[f"ma_{period}"] = frame["close"].rolling(period).mean()

    baseline = (
        frame["volume"]
        .shift(1)
        .rolling(config.volume_lookback, min_periods=config.volume_lookback)
        .median()
    )
    frame["volume_baseline"] = baseline
    frame["volume_ratio"] = frame["volume"] / baseline.replace(0, pd.NA)

    last = frame.iloc[-1]
    events: list[dict[str, Any]] = []
    volume_ratio = last["volume_ratio"]

    if pd.notna(volume_ratio) and volume_ratio >= config.extreme_volume_multiple:
        if last["close"] > last["open"]:
            side = "bullish"
        elif last["close"] < last["open"]:
            side = "bearish"
        else:
            side = "neutral"
        events.append(
            _event(
                "extreme_volume",
                side,
                "major",
                f"成交量為前 {config.volume_lookback} 根中位數的 {volume_ratio:.2f} 倍",
                ratio=round(float(volume_ratio), 4),
                baseline=round(float(last["volume_baseline"]), 4),
                volume=round(float(last["volume"]), 4),
            )
        )

    for period in config.moving_averages:
        ma_column = f"ma_{period}"
        ma_value = last[ma_column]
        if pd.isna(ma_value):
            continue

        tolerance = float(ma_value) * config.ma_touch_tolerance
        confirmation = float(ma_value) * config.close_confirmation
        touched = last["low"] <= ma_value + tolerance and last["high"] >= ma_value - tolerance
        closed_above = last["close"] >= ma_value + confirmation

        if touched and closed_above and last["low"] >= ma_value - tolerance:
            events.append(
                _event(
                    "ma_hold",
                    "bullish",
                    "major" if pd.notna(volume_ratio) and volume_ratio >= config.extreme_volume_multiple else "normal",
                    f"價格測試 MA{period} 後收在均線上方，且未有效跌破",
                    period=period,
                    ma=round(float(ma_value), 4),
                    low=round(float(last["low"]), 4),
                    close=round(float(last["close"]), 4),
                )
            )

        start = max(0, len(frame) - 1 - config.reclaim_lookback)
        recent = frame.iloc[start:-1]
        previously_below = bool(
            (recent["close"] < recent[ma_column] - recent[ma_column] * config.ma_touch_tolerance).any()
        )
        crossed_up_now = (
            len(frame) >= 2
            and frame.iloc[-2]["close"] <= frame.iloc[-2][ma_column]
            and closed_above
        )
        if previously_below and crossed_up_now:
            events.append(
                _event(
                    "ma_reclaim",
                    "bullish",
                    "major" if pd.notna(volume_ratio) and volume_ratio >= config.extreme_volume_multiple else "normal",
                    f"MA{period} 曾被跌破，最新 K 棒重新站回",
                    period=period,
                    ma=round(float(ma_value), 4),
                    close=round(float(last["close"]), 4),
                    reclaim_lookback=config.reclaim_lookback,
                )
            )

    bullish = sum(2 if event["strength"] == "major" else 1 for event in events if event["side"] == "bullish")
    bearish = sum(2 if event["strength"] == "major" else 1 for event in events if event["side"] == "bearish")
    bias = "bullish" if bullish > bearish else "bearish" if bearish > bullish else "neutral"

    timestamp = frame.index[-1]
    return {
        "data_time": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
        "bias": bias,
        "scores": {"bullish": bullish, "bearish": bearish},
        "events": events,
        "config": asdict(config),
        "warnings": (
            []
            if len(frame) >= max(max(config.moving_averages), config.volume_lookback + 1)
            else ["資料長度不足，部分長週期均線或成交量基準無法判斷"]
        ),
    }
