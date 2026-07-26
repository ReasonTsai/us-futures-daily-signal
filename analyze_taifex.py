from __future__ import annotations

import argparse
import json

from taifex_signal import SignalConfig, analyze_bars
from taifex_signal.taifex_data import read_taifex_ticks, ticks_to_bars


def main() -> None:
    parser = argparse.ArgumentParser(description="分析期交所逐筆成交 CSV")
    parser.add_argument("csv", help="從期交所下載的期貨逐筆成交 CSV")
    parser.add_argument("--product", default="TX", help="商品代號，預設 TX")
    parser.add_argument("--contract", help="契約月份；省略時選成交量最大的契約")
    parser.add_argument("--interval", default="5min", help="K 棒週期，預設 5min")
    parser.add_argument("--session", choices=["all", "day", "night"], default="all")
    parser.add_argument("--volume-multiple", type=float, default=2.0)
    args = parser.parse_args()

    ticks = read_taifex_ticks(args.csv, product=args.product, contract=args.contract)
    bars = ticks_to_bars(ticks, interval=args.interval, session=args.session)
    result = analyze_bars(
        bars,
        SignalConfig(extreme_volume_multiple=args.volume_multiple),
    )
    result["market"] = {
        "product": args.product,
        "contract": str(ticks["contract"].iloc[0]),
        "interval": args.interval,
        "session": args.session,
        "bar_count": len(bars),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
