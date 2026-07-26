from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from taifex_signal import SignalConfig, analyze_bars
from taifex_signal.yahoo_data import YAHOO_SYMBOLS, fetch_yahoo_daily


def _market_summary(results: dict[str, dict[str, Any]]) -> str:
    bullish = sum(item["bias"] == "bullish" for item in results.values())
    bearish = sum(item["bias"] == "bearish" for item in results.values())
    if bullish >= 2:
        return "bullish"
    if bearish >= 2:
        return "bearish"
    return "mixed"


def build_report(period: str = "2y") -> dict[str, Any]:
    markets: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for market, yahoo_symbol in YAHOO_SYMBOLS.items():
        try:
            bars = fetch_yahoo_daily(yahoo_symbol, period=period)
            result = analyze_bars(bars, SignalConfig())
            result.update(
                source="Yahoo Finance",
                symbol=yahoo_symbol,
                bar_count=len(bars),
                data_quality={"dropped_invalid_bars": bars.attrs.get("dropped_invalid_bars", 0)},
                latest_close=round(float(bars.iloc[-1]["close"]), 4),
                latest_volume=int(bars.iloc[-1]["volume"]),
                previous_close=round(float(bars.iloc[-2]["close"]), 4),
                daily_change_pct=round(
                    (float(bars.iloc[-1]["close"]) / float(bars.iloc[-2]["close"]) - 1) * 100,
                    4,
                ),
            )
            markets[market] = result
        except Exception as exc:
            errors[market] = str(exc)

    if not markets:
        raise RuntimeError(f"所有市場資料取得失敗: {errors}")
    dates = [item["data_time"] for item in markets.values()]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "Yahoo Finance unofficial chart endpoint",
        "status": "ok" if not errors else "partial",
        "market_bias": _market_summary(markets),
        "latest_market_date": max(dates),
        "markets": markets,
        "errors": errors,
        "disclaimer": "研究用途，不構成投資建議。Yahoo Finance 為非正式資料介面。",
    }


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (output_dir / "latest.json").write_text(rendered, encoding="utf-8")
    market_date = str(report["latest_market_date"])[:10]
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / f"{market_date}.json").write_text(rendered, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="產生 ES、NQ、YM 每日日 K 訊號")
    parser.add_argument("--period", default="2y")
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    report = build_report(period=args.period)
    write_report(report, args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
