# Mean Reversion Strategy

File: `trading/strategies/mean_reversion.py`

This strategy tries to buy oversold moves and short overbought moves.

## Core inputs

- `zscore`
- `rsi`
- `close`
- `bb_lower`
- `bb_upper`

Current thresholds:

- entry z-score: `2.0`
- exit z-score: `0.5`
- RSI oversold: `30`
- RSI overbought: `70`

## Buy conditions

Strong buy:

- `zscore < -2.0`
- `rsi < 30`
- `close < bb_lower`

Normal buy:

- `zscore < -2.0`
- and at least one of:
- `rsi < 30`
- `close < bb_lower`

## Sell / short conditions

Strong sell:

- `zscore > 2.0`
- `rsi > 70`
- `close > bb_upper`

Normal sell:

- `zscore > 2.0`
- and at least one of:
- `rsi > 70`
- `close > bb_upper`

## Exit conditions

If already long:

- exit when `zscore > -0.5`

If already short:

- exit when `zscore < 0.5`

## Example long walkthrough

Suppose the latest bar has:

- close: `95`
- z-score: `-2.4`
- RSI: `27`
- lower Bollinger band: `96`

Interpretation:

- price is far below its rolling mean
- RSI says oversold
- close is below the lower band

Signal:

- `STRONG_BUY`

Trade timing:

- signal is produced from today's bar
- the engine buys at the next day's open, not immediately

If next open is `95.50`:

- executed long price becomes `95.64325` after `15 bps` total cost

## Example exit walkthrough

After entry, imagine z-score rebounds:

- day 1 after entry: `-1.8`
- day 2 after entry: `-0.9`
- day 3 after entry: `-0.3`

At `-0.3`, the long exit condition is met:

- strategy emits `SELL`
- engine sells at the next day's open

## Stop-loss behavior

Even if z-score has not reverted yet, the risk layer can force an exit.

Example:

- long entry executed at `95.64`
- highest price reached after entry: `101.00`
- trailing stop level: `95.95`

If a later open is `95.50`:

- stop-loss closes the trade first
- reason becomes `stop_loss`
- the strategy signal for that day is ignored after the forced exit

## What this strategy is really betting on

It assumes sharp price dislocations often mean-revert. That works best in range-bound markets and tends to struggle in strong trend continuation moves.
