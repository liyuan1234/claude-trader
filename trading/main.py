"""CLI entry point for the trading system."""
import argparse
import sys

from loguru import logger

from trading.config import TradingConfig


def cmd_fetch(args, config: TradingConfig):
    """Fetch and cache historical data."""
    from trading.data.fetcher import DataFetcher

    fetcher = DataFetcher(config)
    symbols = args.symbols or config.default_symbols
    period = args.period or config.default_period

    data = fetcher.fetch_multiple(symbols, period)
    for sym, df in data.items():
        print(f"{sym}: {len(df)} rows, {df['date'].min()} to {df['date'].max()}")


def cmd_backtest(args, config: TradingConfig):
    """Run backtest on historical data."""
    from trading.backtesting.engine import BacktestEngine
    from trading.data.fetcher import DataFetcher
    from trading.strategies.ensemble import EnsembleStrategy
    from trading.strategies.mean_reversion import MeanReversionStrategy
    from trading.strategies.momentum import MomentumStrategy
    from trading.strategies.ml_strategy import MLStrategy

    fetcher = DataFetcher(config)
    engine = BacktestEngine(config)
    symbols = args.symbols or config.default_symbols
    period = args.period or config.default_period

    # Select strategy
    strategy_map = {
        "ensemble": lambda: EnsembleStrategy(config, use_ml=not args.no_ml),
        "mean_reversion": lambda: MeanReversionStrategy(config),
        "momentum": lambda: MomentumStrategy(config),
        "ml": lambda: MLStrategy(config),
    }
    strategy_name = args.strategy or "ensemble"
    if strategy_name not in strategy_map:
        logger.error(f"Unknown strategy: {strategy_name}. Choose from: {list(strategy_map.keys())}")
        sys.exit(1)

    strategy = strategy_map[strategy_name]()

    config.output_dir.mkdir(parents=True, exist_ok=True)

    for sym in symbols:
        try:
            df = fetcher.fetch(sym, period)
            result = engine.run(df, strategy, symbol=sym)
            print(result.summary())

            if args.plot:
                save_path = str(config.output_dir / f"{sym}_equity.png")
                result.plot_equity_curve(save_path=save_path)

            # Save trade log
            if result.trades:
                import polars as pl
                trades_data = [
                    {
                        "entry_date": str(t.entry_date),
                        "exit_date": str(t.exit_date),
                        "side": "LONG" if t.side == 1 else "SHORT",
                        "entry_price": t.entry_price,
                        "exit_price": t.exit_price,
                        "shares": t.shares,
                        "pnl": t.pnl,
                        "pnl_pct": t.pnl_pct,
                        "reason": t.reason,
                    }
                    for t in result.trades
                ]
                trades_df = pl.DataFrame(trades_data)
                trades_path = config.output_dir / f"{sym}_trades.csv"
                trades_df.write_csv(trades_path)
                logger.info(f"Trade log saved to {trades_path}")

        except Exception as e:
            logger.error(f"Backtest failed for {sym}: {e}")
            raise


def cmd_train(args, config: TradingConfig):
    """Train ML model on historical data."""
    from trading.data.fetcher import DataFetcher
    from trading.features.engineering import FeatureEngine
    from trading.strategies.ml_strategy import MLStrategy

    fetcher = DataFetcher(config)
    feature_engine = FeatureEngine(config)
    ml = MLStrategy(config)
    symbols = args.symbols or config.default_symbols
    period = args.period or "5y"

    for sym in symbols:
        try:
            df = fetcher.fetch(sym, period)
            df = feature_engine.compute(df)
            ml.train(df, symbol=sym)

            # Print feature importance
            importance = ml.get_feature_importance()
            if importance:
                print(f"\n{sym} — Top 10 Feature Importance:")
                sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)
                for feat, imp in sorted_imp[:10]:
                    print(f"  {feat:25s} {imp:.4f}")
        except Exception as e:
            logger.error(f"Training failed for {sym}: {e}")
            raise


def cmd_paper_trade(args, config: TradingConfig):
    """Start IBKR paper trading."""
    from trading.paper_trading.ibkr import IBKRPaperTrader
    from trading.strategies.ensemble import EnsembleStrategy

    symbols = args.symbols or config.default_symbols
    strategy = EnsembleStrategy(config, use_ml=not args.no_ml)

    trader = IBKRPaperTrader(strategy, config, symbols)
    try:
        trader.connect()
        if args.once:
            trader.run_once()
        else:
            trader.run_loop(interval_seconds=args.interval)
    except Exception as e:
        logger.error(f"Paper trading error: {e}")
        raise
    finally:
        trader.disconnect()


def main():
    parser = argparse.ArgumentParser(
        prog="trading",
        description="Stock Trading Analyzer — Backtest & Paper Trade",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch and cache historical data")
    p_fetch.add_argument("--symbols", nargs="+", help="Ticker symbols")
    p_fetch.add_argument("--period", help="yfinance period (e.g., 1y, 2y, 5y, max)")

    # backtest
    p_bt = subparsers.add_parser("backtest", help="Run strategy backtest")
    p_bt.add_argument("--symbols", nargs="+", help="Ticker symbols")
    p_bt.add_argument("--period", help="yfinance period")
    p_bt.add_argument("--strategy", choices=["ensemble", "mean_reversion", "momentum", "ml"],
                       default="ensemble", help="Strategy to backtest")
    p_bt.add_argument("--no-ml", action="store_true", help="Exclude ML from ensemble")
    p_bt.add_argument("--plot", action="store_true", help="Plot equity curve")

    # train
    p_train = subparsers.add_parser("train", help="Train ML model")
    p_train.add_argument("--symbols", nargs="+", help="Ticker symbols")
    p_train.add_argument("--period", default="5y", help="Training data period")

    # paper-trade
    p_pt = subparsers.add_parser("paper-trade", help="Start IBKR paper trading")
    p_pt.add_argument("--symbols", nargs="+", help="Ticker symbols")
    p_pt.add_argument("--no-ml", action="store_true", help="Exclude ML from ensemble")
    p_pt.add_argument("--once", action="store_true", help="Run single cycle then exit")
    p_pt.add_argument("--interval", type=int, default=300, help="Loop interval in seconds")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    config = TradingConfig()

    commands = {
        "fetch": cmd_fetch,
        "backtest": cmd_backtest,
        "train": cmd_train,
        "paper-trade": cmd_paper_trade,
    }
    commands[args.command](args, config)


if __name__ == "__main__":
    main()
