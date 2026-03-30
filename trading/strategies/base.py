"""Abstract base class for all trading strategies."""
from abc import ABC, abstractmethod
from enum import IntEnum

import polars as pl


class Signal(IntEnum):
    STRONG_SELL = -2
    SELL = -1
    HOLD = 0
    BUY = 1
    STRONG_BUY = 2


class BaseStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate_signals(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add a 'signal' column (Signal enum values) to the dataframe.

        Input df must already have features computed by FeatureEngine.
        """
        ...
