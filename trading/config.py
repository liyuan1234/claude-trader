"""Central configuration for the trading system."""
from pathlib import Path
from pydantic_settings import BaseSettings


class TradingConfig(BaseSettings):
    model_config = {"env_prefix": "TRADING_"}

    # Capital & costs
    initial_capital: float = 100_000.0
    commission_bps: float = 10.0  # 10 basis points per trade
    slippage_bps: float = 5.0  # 5 basis points slippage

    # Risk
    max_position_pct: float = 0.20  # 20% max single position
    stop_loss_pct: float = 0.05  # 5% trailing stop
    daily_loss_limit_pct: float = 0.03  # 3% daily loss halt
    kelly_fraction: float = 0.25  # quarter-Kelly

    # Strategy ensemble weights
    weight_mean_reversion: float = 0.30
    weight_momentum: float = 0.30
    weight_ml: float = 0.40

    # Mean reversion params
    mr_zscore_window: int = 20
    mr_zscore_entry: float = 2.0
    mr_zscore_exit: float = 0.5
    mr_rsi_period: int = 14
    mr_rsi_oversold: float = 30.0
    mr_rsi_overbought: float = 70.0
    mr_bb_window: int = 20
    mr_bb_std: float = 2.0

    # Momentum params
    mom_ema_fast: int = 12
    mom_ema_slow: int = 26
    mom_adx_period: int = 14
    mom_adx_threshold: float = 25.0

    # ML params
    ml_train_window: int = 252  # 1 year rolling
    ml_retrain_interval: int = 21  # retrain monthly
    ml_signal_threshold_bps: float = 50.0  # 50bps minimum predicted return
    ml_max_depth: int = 4
    ml_n_estimators: int = 200
    ml_learning_rate: float = 0.05

    # Data
    default_symbols: list[str] = ["AAPL", "MSFT", "GOOGL", "AMZN", "SPY"]
    default_period: str = "2y"
    cache_dir: Path = Path("trading/.cache")
    cache_ttl_hours: int = 24

    # IBKR paper trading
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497  # paper trading default
    ibkr_client_id: int = 1

    # Output
    output_dir: Path = Path("trading/output")
    model_dir: Path = Path("trading/models")
