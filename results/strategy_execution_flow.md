# Strategy Execution Flow

This file explains how a signal becomes a trade in the current backtest engine.

## 1. Features are computed first

Before any strategy runs, the engine computes indicators such as:

- `zscore`, `bb_upper`, `bb_lower`, `rsi`
- `ema_diff`, `ema_diff_prev`, `adx`, `di_plus`, `di_minus`
- ML features such as returns, volatility, oscillators, and microstructure fields

## 2. The strategy emits a signal on day `t`

Possible signals:

- `STRONG_BUY = 2`
- `BUY = 1`
- `HOLD = 0`
- `SELL = -1`
- `STRONG_SELL = -2`

## 3. The engine executes on the next day's open

The backtest does not buy or sell on the same bar that generated the signal.

If a strategy emits a signal on Monday's close data:

- the order is executed at Tuesday's open
- execution price includes slippage and commission

Current defaults:

- slippage: `5 bps`
- commission: `10 bps`
- total execution adjustment: `15 bps`

Examples:

- long buy at raw open `100.00` becomes `100.15`
- long sell at raw open `100.00` becomes `99.85`
- short sell at raw open `100.00` becomes `99.85`
- buy-to-cover at raw open `100.00` becomes `100.15`

## 4. Position size is computed from risk settings

Position sizing uses:

- `kelly_fraction = 0.25`
- `max_position_pct = 0.20`

Effectively:

- `STRONG_*` signals target up to `20%` of portfolio
- normal `BUY` and `SELL` target half that, so about `10%`

Shares are computed as:

- `int(portfolio_value * allocation_pct / price)`

## 5. Stop-loss is checked before a new signal is acted on

Current stop setting:

- `stop_loss_pct = 5%`

Trailing logic:

- long: track the highest price seen since entry, exit if price falls `5%` or more from that high
- short: track the lowest price seen since entry, exit if price rises `5%` or more from that low

If stop-loss triggers:

- the position is closed at the current day's open, with costs applied
- the trade reason is stored as `stop_loss`
- that happens before any fresh signal for the same day is processed

## 6. Daily loss halt

Current daily protection:

- `daily_loss_limit_pct = 3%`

If realized daily P&L falls below `-3%` of portfolio value:

- trading halts for that trading day
- the paper trader resets this only when the ET calendar day changes

## 7. Exit types in trade logs

Trades can close for three reasons:

- `signal`
- `stop_loss`
- `end_of_data`

## 8. Worked long example

Starting assumptions:

- cash: `$100,000`
- Monday close data produces `STRONG_BUY`
- Tuesday open is `100.00`

Execution:

- buy price after costs: `100.15`
- target allocation: `20%`
- shares: `int(100000 * 0.20 / 100.00) = 200`
- cash after entry: `100000 - 200 * 100.15 = 79,970`

If price later rises to `110`:

- trailing high becomes `110`
- stop level becomes `104.50`

If a later open is `104.00`:

- stop-loss fires
- sell price after costs: `103.844`
- position closes with reason `stop_loss`

## 9. Worked short example

Starting assumptions:

- cash: `$100,000`
- Monday close data produces `STRONG_SELL`
- Tuesday open is `100.00`

Execution:

- short sale price after costs: `99.85`
- shares: `200`
- cash after entry: `100000 + 200 * 99.85 = 119,970`

If price drops to `92`:

- trailing low becomes `92`
- short stop level becomes `96.60`

If a later open is `97.00`:

- buy-to-cover after costs: `97.1455`
- stop-loss fires because price rose more than `5%` off the best low
- trade closes with reason `stop_loss`
