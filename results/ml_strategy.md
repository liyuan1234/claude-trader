# ML Strategy

File: `trading/strategies/ml_strategy.py`

This strategy uses a rolling XGBoost regressor to predict next-day return, then maps that prediction to a discrete trading signal.

## Training setup

- rolling train window: `252` rows
- retrain interval: `21` rows
- model: `XGBRegressor`
- scaling: `StandardScaler`

The model retrains repeatedly during walk-forward backtesting.

## Features used

The model uses engineered inputs including:

- recent log returns
- realized volatility and vol ratio
- EMA spread and trend metrics
- z-score, RSI, Bollinger `%B`
- volume ratio
- MACD histogram
- stochastic oscillator
- Williams %R
- CCI
- daily range percent
- close position inside the day range

Rows with null or non-finite features are ignored.

## Signal thresholds

Current base threshold:

- `ml_signal_threshold_bps = 50`
- decimal threshold = `0.005`

Signal mapping:

- predicted return `> 0.010` -> `STRONG_BUY`
- predicted return `> 0.005` -> `BUY`
- predicted return `< -0.010` -> `STRONG_SELL`
- predicted return `< -0.005` -> `SELL`
- otherwise -> `HOLD`

## Example long walkthrough

Suppose after scaling the current row, the model predicts:

- next-day return = `0.0075`

Interpretation:

- predicted return is above `0.005`
- but below `0.010`

Signal:

- `BUY`

Execution:

- the order is executed at the next day's open
- because this is not a strong signal, sizing is about half of a strong signal allocation

## Example short walkthrough

Suppose the model predicts:

- next-day return = `-0.013`

Interpretation:

- prediction is below `-0.010`

Signal:

- `STRONG_SELL`

Execution:

- the engine opens a short at the next day's open

## Exit behavior

This strategy does not have a separate handcrafted exit rule like mean reversion does.

In practice a position closes when:

- the model later emits the opposite-side signal
- or the trailing stop-loss is hit
- or backtest data ends

Example:

- model predicts `-0.013` and opens a short
- later prediction rises to `0.006`
- strategy emits `BUY`
- engine uses that next open to cover the short

## Stop-loss behavior

The same `5%` trailing stop is applied.

For a short:

- track the lowest price since entry
- if price rallies `5%` or more off that low, cover the short

## What this strategy is really betting on

It is betting that the engineered feature set contains enough short-horizon signal for a boosted-tree model to estimate next-day returns better than chance.
