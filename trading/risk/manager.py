"""Risk management — position sizing, stop-losses, and daily loss limits."""
from dataclasses import dataclass, field
from datetime import date

from loguru import logger

from trading.config import TradingConfig
from trading.strategies.base import Signal


@dataclass
class Position:
    symbol: str
    side: int  # 1=long, -1=short
    entry_price: float
    shares: int
    highest_price: float = 0.0  # for trailing stop (long)
    lowest_price: float = float("inf")  # for trailing stop (short)

    def update_extremes(self, price: float):
        self.highest_price = max(self.highest_price, price)
        self.lowest_price = min(self.lowest_price, price)

    def unrealized_pnl(self, price: float) -> float:
        return self.side * (price - self.entry_price) * self.shares

    def check_stop_loss(self, price: float, stop_pct: float) -> bool:
        if self.side == 1:  # long trailing stop
            drawdown = (self.highest_price - price) / self.highest_price
            return drawdown >= stop_pct
        else:  # short trailing stop
            drawup = (price - self.lowest_price) / self.lowest_price if self.lowest_price > 0 else 0
            return drawup >= stop_pct


@dataclass
class RiskState:
    daily_pnl: float = 0.0
    daily_halted: bool = False
    last_reset_date: date | None = None
    positions: dict[str, Position] = field(default_factory=dict)


class RiskManager:
    def __init__(self, config: TradingConfig | None = None):
        self.config = config or TradingConfig()
        self.state = RiskState()

    def reset_daily(self):
        self.state.daily_pnl = 0.0
        self.state.daily_halted = False

    def reset_daily_if_needed(self, current_date: date):
        if self.state.last_reset_date != current_date:
            self.reset_daily()
            self.state.last_reset_date = current_date

    def compute_position_size(self, signal: Signal, price: float, portfolio_value: float) -> int:
        """Quarter-Kelly position sizing based on signal strength."""
        if signal == Signal.HOLD or self.state.daily_halted:
            return 0

        cfg = self.config

        # Base allocation: Kelly fraction of portfolio
        base_pct = cfg.kelly_fraction

        # Scale by signal strength
        if abs(signal) == 2:  # STRONG
            alloc_pct = base_pct
        else:  # Normal
            alloc_pct = base_pct * 0.5

        # Cap at max position
        alloc_pct = min(alloc_pct, cfg.max_position_pct)

        # Compute shares
        dollar_amount = portfolio_value * alloc_pct
        shares = int(dollar_amount / price)
        return max(shares, 0)

    def check_stop_loss(self, symbol: str, current_price: float) -> bool:
        """Returns True if position should be stopped out."""
        pos = self.state.positions.get(symbol)
        if pos is None:
            return False
        pos.update_extremes(current_price)
        return pos.check_stop_loss(current_price, self.config.stop_loss_pct)

    def check_daily_limit(self, portfolio_value: float) -> bool:
        """Returns True if daily loss limit is breached."""
        if self.state.daily_halted:
            return True
        if self.state.daily_pnl < 0:
            loss_pct = abs(self.state.daily_pnl) / portfolio_value
            if loss_pct >= self.config.daily_loss_limit_pct:
                logger.warning(f"Daily loss limit breached: {loss_pct:.2%} >= {self.config.daily_loss_limit_pct:.2%}")
                self.state.daily_halted = True
                return True
        return False

    def record_trade_pnl(self, pnl: float):
        self.state.daily_pnl += pnl

    def open_position(self, symbol: str, side: int, entry_price: float, shares: int):
        self.state.positions[symbol] = Position(
            symbol=symbol, side=side, entry_price=entry_price,
            shares=shares, highest_price=entry_price, lowest_price=entry_price,
        )

    def close_position(self, symbol: str, exit_price: float) -> float:
        pos = self.state.positions.pop(symbol, None)
        if pos is None:
            return 0.0
        pnl = pos.unrealized_pnl(exit_price)
        self.record_trade_pnl(pnl)
        return pnl

    def has_position(self, symbol: str) -> bool:
        return symbol in self.state.positions

    def get_position(self, symbol: str) -> Position | None:
        return self.state.positions.get(symbol)
