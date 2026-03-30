# Momentum Strategy

File: `trading/strategies/momentum.py`

This strategy trades trend continuation using EMA crossovers, but only when ADX says the market is trending.

## Core inputs

- `ema_diff = ema_12 - ema_26`
- `ema_diff_prev`
- `adx`
- `di_plus`
- `di_minus`

Current thresholds:

- fast EMA: `12`
- slow EMA: `26`
- ADX threshold: `25`

## Market filter

No new trend trade is allowed unless:

- `adx >= 25`

If `adx < 25`:

- the strategy treats the market as choppy
- if already in a position, it exits
- if flat, it stays flat

## Buy conditions

Bullish crossover:

- previous `ema_diff <= 0`
- current `ema_diff > 0`

Strong buy:

- bullish crossover
- and `di_plus > di_minus`

Normal buy:

- bullish crossover
- but no directional DI confirmation

## Sell / short conditions

Bearish crossover:

- previous `ema_diff >= 0`
- current `ema_diff < 0`

Strong sell:

- bearish crossover
- and `di_minus > di_plus`

Normal sell:

- bearish crossover
- but no directional DI confirmation

## Example long walkthrough

Suppose the latest completed bar has:

- previous EMA diff: `-0.10`
- current EMA diff: `0.18`
- ADX: `31`
- DI+: `28`
- DI-: `17`

Interpretation:

- fast EMA crossed above slow EMA
- ADX says trend strength is acceptable
- DI confirms bullish direction

Signal:

- `STRONG_BUY`

Execution:

- engine buys at the next day's open

If next open is `150.00`:

- actual long entry becomes `150.225`

## Example exit due to weak trend

Suppose you are long and then:

- ADX drops to `19`

Result:

- strategy emits `SELL`
- it does this even without a bearish EMA crossover
- the idea is to stop holding trend trades in non-trending conditions

## Stop-loss behavior

The risk layer still applies a `5%` trailing stop.

Example:

- long entry: `150.225`
- highest price reached: `160`
- stop level: `152`

If the next open is `151.50`:

- stop-loss exits before the strategy can keep holding

## What this strategy is really betting on

It assumes price trends persist after confirmed moving-average crossovers, but only when trend strength is high enough to avoid chop.
