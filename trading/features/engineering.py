"""Technical indicator computation and feature engineering for ML models."""
import polars as pl
import numpy as np
import ta
import pandas as pd

from trading.config import TradingConfig


class FeatureEngine:
    def __init__(self, config: TradingConfig | None = None):
        self.config = config or TradingConfig()

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute all features. Input must have: date, open, high, low, close, volume."""
        # Convert to pandas for ta library, compute indicators, convert back
        pdf = df.to_pandas()
        close = pdf["close"]
        high = pdf["high"]
        low = pdf["low"]
        volume = pdf["volume"].astype(float)

        # === 1. Returns & Volatility ===
        pdf["log_return_1d"] = np.log(close / close.shift(1))
        pdf["log_return_5d"] = np.log(close / close.shift(5))
        pdf["log_return_10d"] = np.log(close / close.shift(10))
        pdf["log_return_21d"] = np.log(close / close.shift(21))
        pdf["volatility_10d"] = pdf["log_return_1d"].rolling(10).std()
        pdf["volatility_21d"] = pdf["log_return_1d"].rolling(21).std()
        pdf["vol_ratio"] = pdf["volatility_10d"] / pdf["volatility_21d"]

        # === 2. Trend Indicators ===
        pdf["ema_12"] = ta.trend.EMAIndicator(close, window=self.config.mom_ema_fast).ema_indicator()
        pdf["ema_26"] = ta.trend.EMAIndicator(close, window=self.config.mom_ema_slow).ema_indicator()
        pdf["sma_50"] = ta.trend.SMAIndicator(close, window=50).sma_indicator()
        pdf["sma_200"] = ta.trend.SMAIndicator(close, window=200).sma_indicator()

        adx_ind = ta.trend.ADXIndicator(high, low, close, window=self.config.mom_adx_period)
        pdf["adx"] = adx_ind.adx()
        pdf["di_plus"] = adx_ind.adx_pos()
        pdf["di_minus"] = adx_ind.adx_neg()

        # EMA crossover signal
        pdf["ema_diff"] = pdf["ema_12"] - pdf["ema_26"]
        pdf["ema_diff_prev"] = pdf["ema_diff"].shift(1)

        # === 3. Mean Reversion Indicators ===
        sma_20 = close.rolling(self.config.mr_zscore_window).mean()
        std_20 = close.rolling(self.config.mr_zscore_window).std()
        pdf["zscore"] = (close - sma_20) / std_20

        bb = ta.volatility.BollingerBands(close, window=self.config.mr_bb_window, window_dev=self.config.mr_bb_std)
        pdf["bb_upper"] = bb.bollinger_hband()
        pdf["bb_lower"] = bb.bollinger_lband()
        pdf["bb_mid"] = bb.bollinger_mavg()
        pdf["bb_pct"] = bb.bollinger_pband()  # %B

        rsi_ind = ta.momentum.RSIIndicator(close, window=self.config.mr_rsi_period)
        pdf["rsi"] = rsi_ind.rsi()

        # RSI divergence: price making new low but RSI not
        pdf["price_low_5d"] = close.rolling(5).min()
        pdf["rsi_low_5d"] = pdf["rsi"].rolling(5).min()

        # === 4. Volume Indicators ===
        pdf["obv"] = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()
        pdf["volume_sma_20"] = volume.rolling(20).mean()
        pdf["volume_ratio"] = volume / pdf["volume_sma_20"]
        pdf["ad"] = ta.volume.AccDistIndexIndicator(high, low, close, volume).acc_dist_index()

        # === 5. Momentum Oscillators ===
        macd_ind = ta.trend.MACD(close)
        pdf["macd"] = macd_ind.macd()
        pdf["macd_signal"] = macd_ind.macd_signal()
        pdf["macd_hist"] = macd_ind.macd_diff()

        stoch = ta.momentum.StochasticOscillator(high, low, close)
        pdf["stoch_k"] = stoch.stoch()
        pdf["stoch_d"] = stoch.stoch_signal()

        pdf["williams_r"] = ta.momentum.WilliamsRIndicator(high, low, close).williams_r()
        pdf["cci"] = ta.trend.CCIIndicator(high, low, close).cci()

        # === 6. Microstructure ===
        pdf["daily_range_pct"] = (high - low) / close
        intraday_range = high - low
        pdf["close_position"] = np.where(intraday_range != 0, (close - low) / intraday_range, 0.5)

        numeric_cols = pdf.select_dtypes(include=[np.number]).columns
        pdf[numeric_cols] = pdf[numeric_cols].replace([np.inf, -np.inf], np.nan)

        # Convert back to polars
        result = pl.from_pandas(pdf, nan_to_null=True)
        return result

    def add_target(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add next-day log return as ML target (forward-shifted). Only for training."""
        return df.with_columns(
            pl.col("log_return_1d").shift(-1).alias("target")
        )

    def get_feature_columns(self) -> list[str]:
        """Return the list of feature column names for ML."""
        return [
            # Returns & volatility
            "log_return_1d", "log_return_5d", "log_return_10d", "log_return_21d",
            "volatility_10d", "volatility_21d", "vol_ratio",
            # Trend
            "ema_diff", "adx", "di_plus", "di_minus",
            # Mean reversion
            "zscore", "bb_pct", "rsi",
            # Volume
            "volume_ratio",
            # Momentum oscillators
            "macd_hist", "stoch_k", "stoch_d", "williams_r", "cci",
            # Microstructure
            "daily_range_pct", "close_position",
        ]
