from datetime import date, timedelta
import unittest

import polars as pl

from trading.backtesting.engine import BacktestEngine
from trading.config import TradingConfig
from trading.strategies.base import BaseStrategy, Signal


class StaticSignalStrategy(BaseStrategy):
    name = "static"

    def __init__(self, signals: dict[int, Signal]):
        self.signals = signals

    def generate_signals(self, df: pl.DataFrame) -> pl.DataFrame:
        series = [self.signals.get(i, Signal.HOLD) for i in range(len(df))]
        return df.with_columns(pl.Series("signal", series))


def make_ohlcv(closes: list[float]) -> pl.DataFrame:
    start = date(2024, 1, 1)
    return pl.DataFrame({
        "date": [start + timedelta(days=i) for i in range(len(closes))],
        "open": closes,
        "high": [price + 1 for price in closes],
        "low": [price - 1 for price in closes],
        "close": closes,
        "volume": [1_000.0] * len(closes),
    })


class BacktestRegressionTests(unittest.TestCase):
    def test_losing_short_reduces_equity(self):
        closes = [100.0] * 40
        for idx in range(22, 27):
            closes[idx] = 110.0

        config = TradingConfig(
            initial_capital=1_000.0,
            commission_bps=0.0,
            slippage_bps=0.0,
            stop_loss_pct=1.0,
            daily_loss_limit_pct=1.0,
            kelly_fraction=1.0,
            max_position_pct=1.0,
            mr_bb_window=5,
            mr_zscore_window=5,
        )
        engine = BacktestEngine(config)
        strategy = StaticSignalStrategy({20: Signal.STRONG_SELL, 25: Signal.BUY})

        result = engine.run(make_ohlcv(closes), strategy, symbol="TEST")

        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].side, -1)
        self.assertAlmostEqual(result.trades[0].pnl, -100.0)
        self.assertAlmostEqual(result.equity_curve["equity"][-1], 900.0)
        self.assertAlmostEqual(result.total_return, -0.1)

    def test_end_of_data_exit_updates_last_equity_after_costs(self):
        closes = [100.0] * 40
        config = TradingConfig(
            initial_capital=1_000.0,
            commission_bps=100.0,
            slippage_bps=100.0,
            daily_loss_limit_pct=1.0,
            kelly_fraction=1.0,
            max_position_pct=1.0,
            mr_bb_window=5,
            mr_zscore_window=5,
        )
        engine = BacktestEngine(config)
        strategy = StaticSignalStrategy({20: Signal.STRONG_BUY})

        result = engine.run(make_ohlcv(closes), strategy, symbol="TEST")

        self.assertEqual(result.trades[0].reason, "end_of_data")
        self.assertAlmostEqual(result.trades[0].pnl, -40.0)
        self.assertAlmostEqual(result.equity_curve["equity"][-1], 960.0)

    def test_stop_loss_exit_records_loss_without_double_counting(self):
        closes = [100.0] * 40
        closes[22] = 94.0
        closes[23] = 94.0

        config = TradingConfig(
            initial_capital=1_000.0,
            commission_bps=0.0,
            slippage_bps=0.0,
            stop_loss_pct=0.05,
            daily_loss_limit_pct=1.0,
            kelly_fraction=1.0,
            max_position_pct=1.0,
            mr_bb_window=5,
            mr_zscore_window=5,
        )
        engine = BacktestEngine(config)
        strategy = StaticSignalStrategy({20: Signal.STRONG_BUY})

        result = engine.run(make_ohlcv(closes), strategy, symbol="TEST")

        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].reason, "stop_loss")
        self.assertAlmostEqual(result.trades[0].pnl, -60.0)
        self.assertAlmostEqual(result.equity_curve["equity"][-1], 940.0)


if __name__ == "__main__":
    unittest.main()
