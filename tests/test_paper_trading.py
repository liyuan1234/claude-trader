from datetime import date, datetime
import unittest
from unittest.mock import Mock

from trading.config import TradingConfig
from trading.paper_trading.ibkr import IBKRPaperTrader
from trading.risk.manager import RiskManager
from trading.strategies.base import BaseStrategy, Signal


class HoldStrategy(BaseStrategy):
    name = "hold"

    def generate_signals(self, df):
        return df.with_columns()


class PaperTradingTests(unittest.TestCase):
    def test_daily_state_only_resets_on_new_trading_day(self):
        trader = IBKRPaperTrader(HoldStrategy(), TradingConfig(), ["AAPL"])
        trader.risk = RiskManager(trader.config)

        trader._sync_daily_state(datetime(2026, 3, 30, 10, 0, tzinfo=trader.MARKET_TZ))
        trader.risk.record_trade_pnl(-100.0)
        trader._sync_daily_state(datetime(2026, 3, 30, 15, 0, tzinfo=trader.MARKET_TZ))

        self.assertEqual(trader.risk.state.daily_pnl, -100.0)

        trader._sync_daily_state(datetime(2026, 3, 31, 9, 31, tzinfo=trader.MARKET_TZ))
        self.assertEqual(trader.risk.state.daily_pnl, 0.0)

    def test_market_hours_respect_open_time_and_dst(self):
        trader = IBKRPaperTrader(HoldStrategy(), TradingConfig(), ["AAPL"])

        self.assertFalse(trader._is_market_open(datetime(2026, 1, 5, 9, 15, tzinfo=trader.MARKET_TZ)))
        self.assertTrue(trader._is_market_open(datetime(2026, 1, 5, 9, 35, tzinfo=trader.MARKET_TZ)))
        self.assertTrue(trader._is_market_open(datetime(2026, 7, 6, 9, 35, tzinfo=trader.MARKET_TZ)))

    def test_run_once_halts_after_same_day_losses_across_cycles(self):
        trader = IBKRPaperTrader(
            HoldStrategy(),
            TradingConfig(initial_capital=1_000.0, daily_loss_limit_pct=0.03),
            ["AAPL"],
        )
        trader.ib = Mock()
        trader.ib.accountSummary.return_value = [Mock(tag="NetLiquidation", currency="USD", value="1000")]
        trader.ib.positions.return_value = []
        trader._generate_signal_for_symbol = Mock(return_value=Signal.HOLD)
        trader._get_contract = Mock(return_value=Mock(symbol="AAPL"))
        trader._get_current_price = Mock(return_value=100.0)
        trader._now_et = Mock(side_effect=[
            datetime(2026, 3, 30, 9, 35, tzinfo=trader.MARKET_TZ),
            datetime(2026, 3, 30, 10, 0, tzinfo=trader.MARKET_TZ),
        ])

        trader.risk.state.last_reset_date = date(2026, 3, 30)
        trader.risk.record_trade_pnl(-40.0)
        trader.run_once()

        trader._generate_signal_for_symbol.assert_not_called()


if __name__ == "__main__":
    unittest.main()
