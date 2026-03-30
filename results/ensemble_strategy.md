# Ensemble Strategy

File: `trading/strategies/ensemble.py`

This strategy combines the other strategies into one weighted score.

## Current weights

- mean reversion: `0.30`
- momentum: `0.30`
- ML: `0.40`

If ML is disabled, the remaining weights are normalized.

## How the score is formed

Each component strategy emits one of:

- `-2`, `-1`, `0`, `1`, `2`

The ensemble multiplies each signal by its weight and sums them:

- `composite_score = mr_signal * 0.30 + momentum_signal * 0.30 + ml_signal * 0.40`

## How the score becomes a trade signal

- score `>= 1.5` -> `STRONG_BUY`
- score `>= 0.5` -> `BUY`
- score `<= -1.5` -> `STRONG_SELL`
- score `<= -0.5` -> `SELL`
- otherwise -> `HOLD`

## Example 1: bullish agreement

Suppose the strategies say:

- mean reversion: `BUY` = `1`
- momentum: `STRONG_BUY` = `2`
- ML: `BUY` = `1`

Score:

- `1 * 0.30 + 2 * 0.30 + 1 * 0.40 = 1.30`

Signal:

- `BUY`

Why not strong buy:

- it did not reach `1.5`

## Example 2: conflict between models

Suppose:

- mean reversion: `STRONG_BUY` = `2`
- momentum: `SELL` = `-1`
- ML: `HOLD` = `0`

Score:

- `2 * 0.30 + (-1) * 0.30 + 0 * 0.40 = 0.30`

Signal:

- `HOLD`

Interpretation:

- disagreement is strong enough that the ensemble stands aside

## Example 3: bearish alignment

Suppose:

- mean reversion: `SELL`
- momentum: `SELL`
- ML: `STRONG_SELL`

Score:

- `-1 * 0.30 + -1 * 0.30 + -2 * 0.40 = -1.40`

Signal:

- `SELL`

## Trade timing and risk

Like every other strategy:

- the signal is generated on one bar
- the trade executes at the next open
- the same risk manager applies trailing stops and daily loss halts

## What this strategy is really betting on

It assumes combining independent weak signals is more robust than trusting any one model. In the current AAPL `2y` result set, that assumption did not pay off, which is why the ensemble underperformed the components in the saved backtest outputs.
