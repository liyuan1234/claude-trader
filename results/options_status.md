# Options Status

There is currently no options strategy or options backtesting engine in this repository.

What exists today:

- equity feature engineering
- equity signal generation
- equity backtesting
- IBKR paper trading for stocks

What does not exist yet:

- options chain data ingestion
- strike and expiry selection logic
- Greeks-aware risk management
- options order simulation
- options-specific P&L and assignment handling

Because of that, I did not create a fake "options strategy" explanation file.

If you want options support, the minimum design work would be:

1. Add options data fetching and caching.
2. Define an `OptionContract` model with strike, expiry, type, premium, and multiplier.
3. Add execution and accounting rules for long calls, long puts, short premium, or spreads.
4. Extend the risk layer for premium-at-risk, expiry decay, and assignment/exercise handling.
5. Add dedicated backtests and result artifacts for those strategies.
