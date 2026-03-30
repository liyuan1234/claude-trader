"""Fetch historical market data from yfinance with Parquet caching."""
import time
from pathlib import Path

import polars as pl
import yfinance as yf
from loguru import logger

from trading.config import TradingConfig


class DataFetcher:
    def __init__(self, config: TradingConfig | None = None):
        self.config = config or TradingConfig()
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, symbol: str, period: str) -> Path:
        return self.config.cache_dir / f"{symbol}_{period}.parquet"

    def _is_cache_valid(self, path: Path) -> bool:
        if not path.exists():
            return False
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        return age_hours < self.config.cache_ttl_hours

    def fetch(self, symbol: str, period: str | None = None) -> pl.DataFrame:
        period = period or self.config.default_period
        cache_path = self._cache_path(symbol, period)

        if self._is_cache_valid(cache_path):
            logger.info(f"Loading {symbol} from cache")
            return pl.read_parquet(cache_path)

        logger.info(f"Fetching {symbol} from yfinance (period={period})")
        ticker = yf.Ticker(symbol)
        pdf = ticker.history(period=period, auto_adjust=True)

        if pdf.empty:
            raise ValueError(f"No data returned for {symbol}")

        pdf = pdf.reset_index()
        pdf.columns = [c.lower().replace(" ", "_") for c in pdf.columns]

        # Keep only OHLCV columns
        keep_cols = ["date", "open", "high", "low", "close", "volume"]
        pdf = pdf[[c for c in keep_cols if c in pdf.columns]]

        # Build Polars DataFrame directly to avoid pyarrow dependency
        # Strip timezone and convert date
        dates = pdf["date"]
        if hasattr(dates.dt, "tz") and dates.dt.tz is not None:
            dates = dates.dt.tz_localize(None)

        columns = {
            "date": pl.Series("date", dates.values.astype("datetime64[ms]")).cast(pl.Date),
        }
        for col in ["open", "high", "low", "close", "volume"]:
            if col in pdf.columns:
                columns[col] = pl.Series(col, pdf[col].to_numpy().astype("float64"))

        df = pl.DataFrame(columns)

        df.write_parquet(cache_path)
        logger.info(f"Cached {symbol}: {len(df)} rows")
        return df

    def fetch_multiple(self, symbols: list[str] | None = None, period: str | None = None) -> dict[str, pl.DataFrame]:
        symbols = symbols or self.config.default_symbols
        period = period or self.config.default_period
        result = {}
        for sym in symbols:
            try:
                result[sym] = self.fetch(sym, period)
            except Exception as e:
                logger.error(f"Failed to fetch {sym}: {e}")
        return result
