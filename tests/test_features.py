from datetime import date, timedelta
import math
import unittest

import polars as pl

from trading.config import TradingConfig
from trading.features.engineering import FeatureEngine


class FeatureEngineeringTests(unittest.TestCase):
    def test_zero_range_candle_uses_neutral_close_position(self):
        start = date(2024, 1, 1)
        df = pl.DataFrame({
            "date": [start + timedelta(days=i) for i in range(30)],
            "open": [100.0] * 30,
            "high": [100.0] * 30,
            "low": [100.0] * 30,
            "close": [100.0] * 30,
            "volume": [1_000.0] * 30,
        })

        result = FeatureEngine(TradingConfig()).compute(df)

        self.assertEqual(result["close_position"][0], 0.5)
        self.assertFalse(math.isinf(result["close_position"][0]))


if __name__ == "__main__":
    unittest.main()
