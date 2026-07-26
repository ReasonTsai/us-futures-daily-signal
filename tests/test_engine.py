import unittest
from io import StringIO

import pandas as pd

from taifex_signal import SignalConfig, analyze_bars
from taifex_signal.taifex_data import read_taifex_ticks, ticks_to_bars
from taifex_signal.yahoo_data import parse_yahoo_chart


class SignalEngineTest(unittest.TestCase):
    def test_extreme_volume_and_ma_reclaim(self) -> None:
        closes = [100.0] * 20 + [98.0, 98.5, 101.0]
        bars = pd.DataFrame(
            {
                "open": [100.0] * 20 + [99.0, 98.0, 98.5],
                "high": [101.0] * 20 + [99.5, 99.0, 102.0],
                "low": [99.0] * 20 + [97.5, 97.8, 98.4],
                "close": closes,
                "volume": [100.0] * 22 + [250.0],
            },
            index=pd.date_range("2026-01-01", periods=23, freq="5min"),
        )
        config = SignalConfig(
            moving_averages=(5,),
            volume_lookback=20,
            extreme_volume_multiple=2.0,
            reclaim_lookback=3,
        )

        result = analyze_bars(bars, config)
        event_types = {event["type"] for event in result["events"]}

        self.assertIn("extreme_volume", event_types)
        self.assertIn("ma_reclaim", event_types)
        self.assertEqual(result["bias"], "bullish")

    def test_ma_hold(self) -> None:
        bars = pd.DataFrame(
            {
                "open": [100.0] * 5,
                "high": [101.0] * 5,
                "low": [99.85] * 5,
                "close": [100.0, 100.0, 100.0, 100.0, 100.2],
                "volume": [100.0] * 5,
            }
        )
        result = analyze_bars(
            bars,
            SignalConfig(moving_averages=(5,), volume_lookback=2),
        )

        self.assertIn("ma_hold", {event["type"] for event in result["events"]})

    def test_taifex_csv_to_five_minute_bars(self) -> None:
        source = StringIO(
            "交易日期,商品代號,到期月份(週別),成交時間,成交價格,成交數量(B+S)\n"
            "20260724,TX,202607,084501,23000,2\n"
            "20260724,TX,202607,084730,23010,3\n"
            "20260724,TX,202607,085001,23005,4\n"
            "20260724,MTX,202607,084501,23000,99\n"
        )
        ticks = read_taifex_ticks(source)
        bars = ticks_to_bars(ticks, interval="5min", session="day")

        self.assertEqual(str(ticks["contract"].iloc[0]), "202607")
        self.assertEqual(len(bars), 2)
        self.assertEqual(float(bars.iloc[0]["open"]), 23000)
        self.assertEqual(float(bars.iloc[0]["close"]), 23010)
        self.assertEqual(float(bars.iloc[0]["volume"]), 5)

    def test_parse_yahoo_chart(self) -> None:
        payload = {
            "chart": {
                "error": None,
                "result": [
                    {
                        "timestamp": [1767225600, 1767312000],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [6000.0, 6010.0],
                                    "high": [5995.0, 6030.0],
                                    "low": [5990.0, 6000.0],
                                    "close": [6010.0, 6025.0],
                                    "volume": [100000, 250000],
                                }
                            ]
                        },
                    }
                ],
            }
        }
        bars = parse_yahoo_chart(payload)

        self.assertEqual(len(bars), 1)
        self.assertEqual(float(bars.iloc[-1]["close"]), 6025.0)
        self.assertEqual(int(bars.iloc[-1]["volume"]), 250000)
        self.assertEqual(bars.attrs["dropped_invalid_bars"], 1)


if __name__ == "__main__":
    unittest.main()
