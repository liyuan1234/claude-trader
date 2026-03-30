"""Ensemble strategy — weighted combination of all sub-strategies."""
import polars as pl
from loguru import logger

from trading.config import TradingConfig
from trading.strategies.base import BaseStrategy, Signal
from trading.strategies.mean_reversion import MeanReversionStrategy
from trading.strategies.momentum import MomentumStrategy
from trading.strategies.ml_strategy import MLStrategy


class EnsembleStrategy(BaseStrategy):
    name = "ensemble"

    def __init__(self, config: TradingConfig | None = None, use_ml: bool = True):
        self.config = config or TradingConfig()
        self.strategies: list[tuple[BaseStrategy, float]] = [
            (MeanReversionStrategy(self.config), self.config.weight_mean_reversion),
            (MomentumStrategy(self.config), self.config.weight_momentum),
        ]
        if use_ml:
            self.strategies.append(
                (MLStrategy(self.config), self.config.weight_ml)
            )
        self._normalize_weights()

    def _normalize_weights(self):
        total = sum(w for _, w in self.strategies)
        self.strategies = [(s, w / total) for s, w in self.strategies]

    def generate_signals(self, df: pl.DataFrame) -> pl.DataFrame:
        composite_scores = [0.0] * len(df)

        for strategy, weight in self.strategies:
            logger.info(f"Running {strategy.name} (weight={weight:.2f})")
            df_with_signal = strategy.generate_signals(df)
            strategy_signals = df_with_signal["signal"].to_list()

            for i, sig in enumerate(strategy_signals):
                composite_scores[i] += float(sig) * weight

        # Threshold composite score to discrete signals
        signals = []
        for score in composite_scores:
            if score >= 1.5:
                signals.append(Signal.STRONG_BUY)
            elif score >= 0.5:
                signals.append(Signal.BUY)
            elif score <= -1.5:
                signals.append(Signal.STRONG_SELL)
            elif score <= -0.5:
                signals.append(Signal.SELL)
            else:
                signals.append(Signal.HOLD)

        return df.with_columns(
            pl.Series("signal", signals),
            pl.Series("composite_score", composite_scores),
        )
