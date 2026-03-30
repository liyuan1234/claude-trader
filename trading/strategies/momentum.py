"""Momentum strategy — Dual EMA crossover with ADX trend filter."""
import polars as pl

from trading.config import TradingConfig
from trading.strategies.base import BaseStrategy, Signal


class MomentumStrategy(BaseStrategy):
    name = "momentum"

    def __init__(self, config: TradingConfig | None = None):
        self.config = config or TradingConfig()

    def generate_signals(self, df: pl.DataFrame) -> pl.DataFrame:
        cfg = self.config

        signals = []
        position = 0  # 0=flat, 1=long, -1=short

        ema_diff = df["ema_diff"].to_list()
        ema_diff_prev = df["ema_diff_prev"].to_list()
        adx = df["adx"].to_list()
        di_plus = df["di_plus"].to_list()
        di_minus = df["di_minus"].to_list()

        for i in range(len(df)):
            ed = ema_diff[i]
            edp = ema_diff_prev[i]
            a = adx[i]
            dip = di_plus[i]
            dim = di_minus[i]

            # Handle NaN during warmup
            if ed is None or edp is None or a is None:
                signals.append(Signal.HOLD)
                continue

            # Only trade when market is trending (ADX > threshold)
            if a < cfg.mom_adx_threshold:
                # Choppy market — exit any position, don't enter
                if position != 0:
                    signals.append(Signal.BUY if position == -1 else Signal.SELL)
                    position = 0
                else:
                    signals.append(Signal.HOLD)
                continue

            # Bullish crossover: EMA fast crosses above slow
            bullish_cross = edp <= 0 and ed > 0
            # Bearish crossover: EMA fast crosses below slow
            bearish_cross = edp >= 0 and ed < 0

            if bullish_cross and dip > dim:
                # Strong signal when DI+ confirms direction
                signals.append(Signal.STRONG_BUY)
                position = 1
            elif bullish_cross:
                signals.append(Signal.BUY)
                position = 1
            elif bearish_cross and dim > dip:
                signals.append(Signal.STRONG_SELL)
                position = -1
            elif bearish_cross:
                signals.append(Signal.SELL)
                position = -1
            else:
                # Trend continuation — hold
                signals.append(Signal.HOLD)

        return df.with_columns(pl.Series("signal", signals))
