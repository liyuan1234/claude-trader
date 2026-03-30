"""IBKR paper trading via ib_insync — connects to TWS/IB Gateway."""
import asyncio
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl
from loguru import logger

from trading.config import TradingConfig
from trading.data.fetcher import DataFetcher
from trading.features.engineering import FeatureEngine
from trading.risk.manager import RiskManager
from trading.strategies.base import BaseStrategy, Signal


class IBKRPaperTrader:
    MARKET_TZ = ZoneInfo("America/New_York")
    MARKET_OPEN = time(9, 30)
    MARKET_CLOSE = time(16, 0)

    def __init__(
        self,
        strategy: BaseStrategy,
        config: TradingConfig | None = None,
        symbols: list[str] | None = None,
    ):
        self.config = config or TradingConfig()
        self.strategy = strategy
        self.symbols = symbols or self.config.default_symbols
        self.feature_engine = FeatureEngine(self.config)
        self.data_fetcher = DataFetcher(self.config)
        self.risk = RiskManager(self.config)
        self.ib = None
        self.portfolio_value = self.config.initial_capital
        self.trade_log: list[dict] = []

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def _now_et(self) -> datetime:
        return self._now_utc().astimezone(self.MARKET_TZ)

    def _sync_daily_state(self, current_dt: datetime | None = None):
        current_dt = current_dt or self._now_et()
        self.risk.reset_daily_if_needed(current_dt.date())

    def _is_market_open(self, current_dt: datetime | None = None) -> bool:
        current_dt = current_dt or self._now_et()
        if current_dt.tzinfo is None:
            current_dt = current_dt.replace(tzinfo=self.MARKET_TZ)
        else:
            current_dt = current_dt.astimezone(self.MARKET_TZ)
        current_time = current_dt.time()
        return self.MARKET_OPEN <= current_time < self.MARKET_CLOSE

    def connect(self):
        """Connect to TWS/IB Gateway."""
        try:
            from ib_insync import IB
            self.ib = IB()
            self.ib.connect(
                self.config.ibkr_host,
                self.config.ibkr_port,
                clientId=self.config.ibkr_client_id,
            )
            logger.info(
                f"Connected to IBKR at {self.config.ibkr_host}:{self.config.ibkr_port} "
                f"(clientId={self.config.ibkr_client_id})"
            )
            # Get account value
            account_values = self.ib.accountSummary()
            for av in account_values:
                if av.tag == "NetLiquidation" and av.currency == "USD":
                    self.portfolio_value = float(av.value)
                    logger.info(f"Account net liquidation: ${self.portfolio_value:,.2f}")
                    break
        except Exception as e:
            logger.error(f"Failed to connect to IBKR: {e}")
            raise

    def disconnect(self):
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from IBKR")

    def _get_contract(self, symbol: str):
        from ib_insync import Stock
        contract = Stock(symbol, "SMART", "USD")
        self.ib.qualifyContracts(contract)
        return contract

    def _get_current_price(self, contract) -> float | None:
        ticker = self.ib.reqMktData(contract, "", False, False)
        self.ib.sleep(2)  # Wait for data
        price = ticker.marketPrice()
        self.ib.cancelMktData(contract)
        if price != price:  # NaN check
            return None
        return price

    def _place_order(self, contract, action: str, quantity: int) -> dict:
        from ib_insync import MarketOrder
        order = MarketOrder(action, quantity)
        trade = self.ib.placeOrder(contract, order)
        self.ib.sleep(5)  # Wait for fill

        fill_price = None
        if trade.fills:
            fill_price = trade.fills[0].execution.price

        result = {
            "timestamp": self._now_utc().isoformat(),
            "symbol": contract.symbol,
            "action": action,
            "quantity": quantity,
            "status": trade.orderStatus.status,
            "fill_price": fill_price,
        }
        self.trade_log.append(result)
        logger.info(f"Order: {action} {quantity} {contract.symbol} @ {fill_price} — {trade.orderStatus.status}")
        return result

    def _generate_signal_for_symbol(self, symbol: str) -> Signal:
        """Fetch latest data, compute features, and get signal."""
        try:
            df = self.data_fetcher.fetch(symbol, period="6mo")
            df = self.feature_engine.compute(df)
            df = self.strategy.generate_signals(df)
            last_signal = df["signal"][-1]
            logger.info(f"{symbol}: signal = {Signal(last_signal).name}")
            return Signal(last_signal)
        except Exception as e:
            logger.error(f"Signal generation failed for {symbol}: {e}")
            return Signal.HOLD

    def run_once(self):
        """Run one trading cycle across all symbols."""
        logger.info("Starting trading cycle...")
        self._sync_daily_state()

        # Update portfolio value
        account_values = self.ib.accountSummary()
        for av in account_values:
            if av.tag == "NetLiquidation" and av.currency == "USD":
                self.portfolio_value = float(av.value)
                break

        # Check daily loss limit
        if self.risk.check_daily_limit(self.portfolio_value):
            logger.warning("Daily loss limit hit — skipping cycle")
            return

        for symbol in self.symbols:
            signal = self._generate_signal_for_symbol(symbol)
            contract = self._get_contract(symbol)
            price = self._get_current_price(contract)

            if price is None:
                logger.warning(f"Could not get price for {symbol}, skipping")
                continue

            # Check existing position
            positions = {p.contract.symbol: p for p in self.ib.positions()}
            current_pos = positions.get(symbol)
            current_qty = int(current_pos.position) if current_pos else 0

            # Check stop-loss
            if current_qty != 0 and self.risk.has_position(symbol):
                if self.risk.check_stop_loss(symbol, price):
                    action = "SELL" if current_qty > 0 else "BUY"
                    self._place_order(contract, action, abs(current_qty))
                    self.risk.close_position(symbol, price)
                    logger.info(f"Stop-loss triggered for {symbol}")
                    continue

            # Execute signal
            if signal in (Signal.BUY, Signal.STRONG_BUY) and current_qty <= 0:
                # Close short if any
                if current_qty < 0:
                    self._place_order(contract, "BUY", abs(current_qty))
                    self.risk.close_position(symbol, price)

                # Enter long
                n_shares = self.risk.compute_position_size(signal, price, self.portfolio_value)
                if n_shares > 0:
                    self._place_order(contract, "BUY", n_shares)
                    self.risk.open_position(symbol, 1, price, n_shares)

            elif signal in (Signal.SELL, Signal.STRONG_SELL) and current_qty >= 0:
                # Close long if any
                if current_qty > 0:
                    self._place_order(contract, "SELL", current_qty)
                    self.risk.close_position(symbol, price)

                # Enter short
                n_shares = self.risk.compute_position_size(signal, price, self.portfolio_value)
                if n_shares > 0:
                    self._place_order(contract, "SELL", n_shares)
                    self.risk.open_position(symbol, -1, price, n_shares)

        logger.info("Trading cycle complete")

    def run_loop(self, interval_seconds: int = 300):
        """Run paper trading in a loop. Default: every 5 minutes during market hours."""
        logger.info(f"Starting paper trading loop (interval={interval_seconds}s)")
        try:
            while True:
                now_et = self._now_et()
                if self._is_market_open(now_et):
                    self.run_once()
                else:
                    logger.info(f"Market closed ({now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}), waiting...")

                self.ib.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("Paper trading stopped by user")
        finally:
            self._save_trade_log()
            self.disconnect()

    def _save_trade_log(self):
        if not self.trade_log:
            return
        output_dir = self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        log_df = pl.DataFrame(self.trade_log)
        path = output_dir / f"paper_trades_{self._now_utc().strftime('%Y%m%d_%H%M%S')}.parquet"
        log_df.write_parquet(path)
        logger.info(f"Trade log saved to {path}")
