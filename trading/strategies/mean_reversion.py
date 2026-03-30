"""Mean reversion strategy — Z-score + Bollinger Bands + RSI triple confirmation."""
import polars as pl

from trading.config import TradingConfig
from trading.strategies.base import BaseStrategy, Signal


class MeanReversionStrategy(BaseStrategy):
    name = "mean_reversion"

    def __init__(self, config: TradingConfig | None = None):
        self.config = config or TradingConfig()

    def generate_signals(self, df: pl.DataFrame) -> pl.DataFrame:
        cfg = self.config

        # Triple confirmation for entries, z-score reversion for exits
        # BUY: z-score < -entry AND rsi < oversold AND close < bb_lower
        # SELL: z-score > +entry AND rsi > overbought AND close > bb_upper
        # Exit long: z-score reverts above -exit_threshold
        # Exit short: z-score reverts below +exit_threshold

        signals = []
        position = 0  # 0=flat, 1=long, -1=short

        zscore = df["zscore"].to_list()
        rsi = df["rsi"].to_list()
        close = df["close"].to_list()
        bb_lower = df["bb_lower"].to_list()
        bb_upper = df["bb_upper"].to_list()

        for i in range(len(df)):
            z = zscore[i]
            r = rsi[i]
            c = close[i]
            bbl = bb_lower[i]
            bbu = bb_upper[i]

            # Handle NaN during warmup
            if z is None or r is None or bbl is None or bbu is None:
                signals.append(Signal.HOLD)
                continue

            if position == 0:
                # Triple confirmation for long entry
                if z < -cfg.mr_zscore_entry and r < cfg.mr_rsi_oversold and c < bbl:
                    signals.append(Signal.STRONG_BUY)
                    position = 1
                # Triple confirmation for short entry
                elif z > cfg.mr_zscore_entry and r > cfg.mr_rsi_overbought and c > bbu:
                    signals.append(Signal.STRONG_SELL)
                    position = -1
                # Weaker signals: only z-score + one other
                elif z < -cfg.mr_zscore_entry and (r < cfg.mr_rsi_oversold or c < bbl):
                    signals.append(Signal.BUY)
                    position = 1
                elif z > cfg.mr_zscore_entry and (r > cfg.mr_rsi_overbought or c > bbu):
                    signals.append(Signal.SELL)
                    position = -1
                else:
                    signals.append(Signal.HOLD)

            elif position == 1:  # Currently long
                if z > -cfg.mr_zscore_exit:  # Z-score reverted
                    signals.append(Signal.SELL)
                    position = 0
                else:
                    signals.append(Signal.HOLD)

            elif position == -1:  # Currently short
                if z < cfg.mr_zscore_exit:  # Z-score reverted
                    signals.append(Signal.BUY)
                    position = 0
                else:
                    signals.append(Signal.HOLD)

        return df.with_columns(pl.Series("signal", signals))
