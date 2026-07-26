from __future__ import annotations

import argparse
import json

import pandas as pd

from taifex_signal import SignalConfig, analyze_bars


def main() -> None:
    parser = argparse.ArgumentParser(description="偵測台指期極大量與均線事件")
    parser.add_argument("csv", help="含 timestamp/open/high/low/close/volume 的 CSV")
    parser.add_argument("--volume-multiple", type=float, default=2.0)
    parser.add_argument("--volume-lookback", type=int, default=20)
    parser.add_argument("--ma", type=int, nargs="+", default=[5, 10, 20, 60, 120, 240])
    parser.add_argument("--touch-tolerance", type=float, default=0.002)
    parser.add_argument("--reclaim-lookback", type=int, default=3)
    args = parser.parse_args()

    bars = pd.read_csv(args.csv)
    if "timestamp" in bars.columns:
        bars["timestamp"] = pd.to_datetime(bars["timestamp"], errors="raise")
        bars = bars.set_index("timestamp")

    config = SignalConfig(
        moving_averages=tuple(args.ma),
        volume_lookback=args.volume_lookback,
        extreme_volume_multiple=args.volume_multiple,
        ma_touch_tolerance=args.touch_tolerance,
        reclaim_lookback=args.reclaim_lookback,
    )
    print(json.dumps(analyze_bars(bars, config), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
