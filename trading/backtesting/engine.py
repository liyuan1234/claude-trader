"""Backtesting engine — event-driven simulation with realistic costs."""
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import polars as pl
from loguru import logger

from trading.config import TradingConfig
from trading.features.engineering import FeatureEngine
from trading.risk.manager import RiskManager
from trading.strategies.base import BaseStrategy, Signal


@dataclass
class Trade:
    symbol: str
    entry_date: date
    exit_date: date
    side: int  # 1=long, -1=short
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    pnl_pct: float
    reason: str  # "signal", "stop_loss", "end_of_data"


@dataclass
class BacktestResult:
    symbol: str
    total_return: float
    annual_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade_pnl: float
    equity_curve: pl.DataFrame
    trades: list[Trade] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"\n{'=' * 60}\n"
            f"  Backtest Results: {self.symbol}\n"
            f"{'=' * 60}\n"
            f"  Total Return:    {self.total_return:>10.2%}\n"
            f"  Annual Return:   {self.annual_return:>10.2%}\n"
            f"  Sharpe Ratio:    {self.sharpe_ratio:>10.2f}\n"
            f"  Sortino Ratio:   {self.sortino_ratio:>10.2f}\n"
            f"  Max Drawdown:    {self.max_drawdown:>10.2%}\n"
            f"  Calmar Ratio:    {self.calmar_ratio:>10.2f}\n"
            f"  Win Rate:        {self.win_rate:>10.2%}\n"
            f"  Profit Factor:   {self.profit_factor:>10.2f}\n"
            f"  Total Trades:    {self.total_trades:>10d}\n"
            f"  Avg Trade P&L:   ${self.avg_trade_pnl:>9.2f}\n"
            f"{'=' * 60}\n"
        )

    def plot_equity_curve(self, save_path: str | None = None):
        import matplotlib.pyplot as plt

        eq = self.equity_curve
        dates = eq["date"].to_list()
        equity = eq["equity"].to_list()

        fig, axes = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [3, 1]})

        # Equity curve
        axes[0].plot(dates, equity, linewidth=1.5, color="#2196F3")
        axes[0].fill_between(dates, equity, alpha=0.1, color="#2196F3")
        axes[0].set_title(f"{self.symbol} — Equity Curve", fontsize=14)
        axes[0].set_ylabel("Portfolio Value ($)")
        axes[0].grid(True, alpha=0.3)

        # Drawdown
        peak = np.maximum.accumulate(equity)
        dd = [(e - p) / p if p > 0 else 0 for e, p in zip(equity, peak)]
        axes[1].fill_between(dates, dd, color="#F44336", alpha=0.4)
        axes[1].set_title("Drawdown", fontsize=12)
        axes[1].set_ylabel("Drawdown %")
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            logger.info(f"Equity curve saved to {save_path}")
        plt.show()


class BacktestEngine:
    def __init__(self, config: TradingConfig | None = None):
        self.config = config or TradingConfig()
        self.feature_engine = FeatureEngine(self.config)

    @staticmethod
    def _position_market_value(position_side: int, price: float, shares: int) -> float:
        return position_side * price * shares if shares > 0 else 0.0

    def _apply_costs(self, price: float, side: int) -> float:
        """Apply slippage and commission to execution price."""
        slippage = price * self.config.slippage_bps / 10_000
        commission = price * self.config.commission_bps / 10_000
        # Buying: pay more. Selling: receive less.
        return price + side * (slippage + commission)

    def run(self, df: pl.DataFrame, strategy: BaseStrategy, symbol: str = "UNKNOWN") -> BacktestResult:
        """Run backtest on a single symbol."""
        logger.info(f"Running backtest for {symbol} with {strategy.name} strategy")

        # Compute features
        df = self.feature_engine.compute(df)

        # Generate signals
        df = strategy.generate_signals(df)

        # Event-driven simulation
        risk = RiskManager(self.config)
        cash = self.config.initial_capital
        equity = cash
        shares = 0
        position_side = 0
        entry_price = 0.0
        entry_date = None

        equity_records = []
        trades: list[Trade] = []
        prev_date = None

        dates = df["date"].to_list()
        opens = df["open"].to_list()
        closes = df["close"].to_list()
        signals = df["signal"].to_list()

        for i in range(1, len(df)):
            current_date = dates[i]
            # Execute at today's open based on yesterday's signal
            exec_price = opens[i]
            signal = signals[i - 1]  # Previous day's signal
            close_price = closes[i]

            # Reset daily P&L on new day
            if prev_date is not None and current_date != prev_date:
                risk.reset_daily()
            prev_date = current_date

            # Check stop-loss on open position
            if shares > 0 and risk.has_position(symbol):
                risk.get_position(symbol).update_extremes(exec_price)
                if risk.check_stop_loss(symbol, exec_price):
                    exit_p = self._apply_costs(exec_price, -position_side)
                    pnl = position_side * (exit_p - entry_price) * shares
                    cash += position_side * exit_p * shares
                    trades.append(Trade(
                        symbol=symbol, entry_date=entry_date, exit_date=current_date,
                        side=position_side, entry_price=entry_price, exit_price=exit_p,
                        shares=shares, pnl=pnl, pnl_pct=pnl / (entry_price * shares),
                        reason="stop_loss",
                    ))
                    risk.close_position(symbol, exit_p)
                    shares = 0
                    position_side = 0

            # Check daily loss limit
            if risk.check_daily_limit(equity):
                equity = cash + self._position_market_value(position_side, close_price, shares)
                equity_records.append({"date": current_date, "equity": equity})
                continue

            # Process signal
            if signal in (Signal.BUY, Signal.STRONG_BUY) and shares == 0:
                # Enter long
                n_shares = risk.compute_position_size(signal, exec_price, cash)
                if n_shares > 0:
                    cost_price = self._apply_costs(exec_price, 1)
                    cash -= cost_price * n_shares
                    shares = n_shares
                    position_side = 1
                    entry_price = cost_price
                    entry_date = current_date
                    risk.open_position(symbol, 1, cost_price, n_shares)

            elif signal in (Signal.SELL, Signal.STRONG_SELL) and shares > 0 and position_side == 1:
                # Exit long
                exit_p = self._apply_costs(exec_price, -1)
                pnl = (exit_p - entry_price) * shares
                cash += exit_p * shares
                trades.append(Trade(
                    symbol=symbol, entry_date=entry_date, exit_date=current_date,
                    side=1, entry_price=entry_price, exit_price=exit_p,
                    shares=shares, pnl=pnl, pnl_pct=pnl / (entry_price * shares),
                    reason="signal",
                ))
                risk.close_position(symbol, exit_p)
                shares = 0
                position_side = 0

            elif signal in (Signal.SELL, Signal.STRONG_SELL) and shares == 0:
                # Enter short
                n_shares = risk.compute_position_size(signal, exec_price, cash)
                if n_shares > 0:
                    cost_price = self._apply_costs(exec_price, -1)
                    cash += cost_price * n_shares
                    shares = n_shares
                    position_side = -1
                    entry_price = cost_price
                    entry_date = current_date
                    risk.open_position(symbol, -1, cost_price, n_shares)

            elif signal in (Signal.BUY, Signal.STRONG_BUY) and shares > 0 and position_side == -1:
                # Exit short
                exit_p = self._apply_costs(exec_price, 1)
                pnl = (entry_price - exit_p) * shares
                cash -= exit_p * shares
                trades.append(Trade(
                    symbol=symbol, entry_date=entry_date, exit_date=current_date,
                    side=-1, entry_price=entry_price, exit_price=exit_p,
                    shares=shares, pnl=pnl, pnl_pct=pnl / (entry_price * shares),
                    reason="signal",
                ))
                risk.close_position(symbol, exit_p)
                shares = 0
                position_side = 0

            # Mark to market
            equity = cash + self._position_market_value(position_side, close_price, shares)
            equity_records.append({"date": current_date, "equity": equity})

        # Close any remaining position at last close
        if shares > 0:
            last_close = closes[-1]
            exit_p = self._apply_costs(last_close, -position_side)
            pnl = position_side * (exit_p - entry_price) * shares
            cash += position_side * exit_p * shares
            trades.append(Trade(
                symbol=symbol, entry_date=entry_date, exit_date=dates[-1],
                side=position_side, entry_price=entry_price, exit_price=exit_p,
                shares=shares, pnl=pnl, pnl_pct=pnl / (entry_price * shares),
                reason="end_of_data",
            ))
            risk.close_position(symbol, exit_p)
            if equity_records:
                equity_records[-1]["equity"] = cash
            else:
                equity_records.append({"date": dates[-1], "equity": cash})

        equity_df = pl.DataFrame(equity_records)
        return self._compute_metrics(symbol, equity_df, trades)

    def _compute_metrics(self, symbol: str, equity_df: pl.DataFrame, trades: list[Trade]) -> BacktestResult:
        if len(equity_df) == 0:
            return BacktestResult(
                symbol=symbol, total_return=0, annual_return=0, sharpe_ratio=0,
                sortino_ratio=0, max_drawdown=0, calmar_ratio=0, win_rate=0,
                profit_factor=0, total_trades=0, avg_trade_pnl=0,
                equity_curve=equity_df, trades=trades,
            )

        equity = equity_df["equity"].to_numpy()
        initial = self.config.initial_capital

        # Returns
        total_return = (equity[-1] - initial) / initial
        n_days = len(equity)
        annual_return = (1 + total_return) ** (252 / max(n_days, 1)) - 1

        # Daily returns
        daily_returns = np.diff(equity) / equity[:-1]
        daily_returns = daily_returns[~np.isnan(daily_returns)]

        # Sharpe (annualized, assuming rf=0)
        if len(daily_returns) > 1 and np.std(daily_returns) > 0:
            sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
        else:
            sharpe = 0.0

        # Sortino (downside deviation only)
        downside = daily_returns[daily_returns < 0]
        if len(downside) > 1 and np.std(downside) > 0:
            sortino = np.mean(daily_returns) / np.std(downside) * np.sqrt(252)
        else:
            sortino = 0.0

        # Max drawdown
        peak = np.maximum.accumulate(equity)
        drawdowns = (equity - peak) / peak
        max_dd = abs(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Calmar
        calmar = annual_return / max_dd if max_dd > 0 else 0.0

        # Trade metrics
        n_trades = len(trades)
        if n_trades > 0:
            wins = [t for t in trades if t.pnl > 0]
            losses = [t for t in trades if t.pnl <= 0]
            win_rate = len(wins) / n_trades
            gross_profit = sum(t.pnl for t in wins) if wins else 0
            gross_loss = abs(sum(t.pnl for t in losses)) if losses else 1
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
            avg_pnl = sum(t.pnl for t in trades) / n_trades
        else:
            win_rate = 0.0
            profit_factor = 0.0
            avg_pnl = 0.0

        return BacktestResult(
            symbol=symbol,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            calmar_ratio=calmar,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=n_trades,
            avg_trade_pnl=avg_pnl,
            equity_curve=equity_df,
            trades=trades,
        )
