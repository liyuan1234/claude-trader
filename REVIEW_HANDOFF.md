# Trading Review Handoff

This workspace does not contain `.git`, so this review is against the current source tree rather than a real diff.

## Highest-priority findings

### 1. Short backtest accounting is incorrect and can report gains on losing shorts

Files:
- `trading/backtesting/engine.py:197`
- `trading/backtesting/engine.py:209`
- `trading/backtesting/engine.py:225`
- `trading/backtesting/engine.py:236`

Problem:
- Short entry adds sale proceeds to `capital`.
- While the short is open, equity is marked as `capital + (position_side * (close_price - entry_price) * shares)`.
- On short exit, the code subtracts the buy-to-cover cash outflow and then adds `pnl` again.
- This double-counts short PnL and also overstates open-short equity because the short liability is not subtracted from equity.

Observed repro:
- Command used:
```bash
./.venv/bin/python -m trading.main backtest --symbols AAPL --period 2y --strategy ensemble
```
- Reported output included:
  - `Total Return: 302.30%`
  - `Profit Factor: 0.25`
  - `Avg Trade P&L: -679.14`
- Those metrics are internally inconsistent and match broken accounting rather than a real strategy edge.

Minimal repro used:
```bash
./.venv/bin/python - <<'PY'
from trading.config import TradingConfig
from trading.backtesting.engine import BacktestEngine
from trading.strategies.base import BaseStrategy, Signal
import polars as pl
from datetime import date, timedelta

class OneShort(BaseStrategy):
    name='one_short'
    def generate_signals(self, df):
        sig=[Signal.HOLD]*len(df)
        sig[20]=Signal.STRONG_SELL
        sig[25]=Signal.BUY
        return df.with_columns(pl.Series('signal', sig))

cfg=TradingConfig(initial_capital=1000, commission_bps=0, slippage_bps=0, mr_bb_window=5, mr_zscore_window=5)
engine=BacktestEngine(cfg)
start=date(2024,1,1)
opens=[]; closes=[]; highs=[]; lows=[]
for i in range(40):
    p=100.0
    if 21 <= i <= 24:
        p=90.0
    opens.append(p); closes.append(p); highs.append(p+1); lows.append(p-1)
df=pl.DataFrame({
    'date':[start + timedelta(days=i) for i in range(40)],
    'open':opens, 'high':highs, 'low':lows, 'close':closes, 'volume':[1000.0]*40,
})
res=engine.run(df, OneShort(), symbol='TEST')
print('total_return', res.total_return)
print('trade_pnl', res.trades[0].pnl)
print('last_equity', res.equity_curve['equity'][-1])
PY
```
- Result:
  - `trade_pnl -20.0`
  - `last_equity 1240.0`
  - `total_return 0.24`
- A losing short should not end with positive portfolio return.

Expected fix direction:
- Track cash and position market value separately.
- For shorts, equity should be `cash + position_market_value`, where short market value is negative.
- Do not add `pnl` on top of the cash settlement when covering a short.
- Add regression tests for long and short round-trips, including stop-loss and end-of-data exits.

### 2. Paper-trading daily loss protection resets every cycle, so it cannot enforce a true daily halt

Files:
- `trading/paper_trading/ibkr.py:113`
- `trading/paper_trading/ibkr.py:116`

Problem:
- `run_once()` calls `self.risk.reset_daily()` at the start of every cycle.
- The loop runs every few minutes, so realized losses from previous cycles on the same trading day are discarded before `check_daily_limit()` runs.
- That means the configured daily circuit breaker only applies within a single polling cycle, not across the day.

Expected fix direction:
- Reset daily state only when the calendar trading day changes, not every loop iteration.
- Store the last trading date in the paper trader or risk state.
- Add a test that closes losing trades across two cycles on the same day and verifies the second cycle halts once the threshold is exceeded.

### 3. Paper-trading market-hours gating is wrong for both DST and the 9:30 ET open

Files:
- `trading/paper_trading/ibkr.py:185`
- `trading/paper_trading/ibkr.py:186`
- `trading/paper_trading/ibkr.py:189`

Problem:
- It approximates Eastern Time with `hour_et = (now.hour - 4) % 24`.
- That is wrong during standard time, ignores minutes entirely, and starts trading at 9:00 ET even though the regular session opens at 9:30 ET.
- Result: the bot can place orders outside regular market hours.

Expected fix direction:
- Use `zoneinfo.ZoneInfo("America/New_York")`.
- Gate on an actual ET `time` window of `09:30 <= now < 16:00`.
- Add tests around DST boundaries and a 09:15 / 09:35 ET check.

## Secondary finding

### 4. Feature engineering can emit infinite values on zero-range candles

File:
- `trading/features/engineering.py:86`

Problem:
- `close_position = (close - low) / (high - low)` divides by zero when `high == low`.
- The ML path later drops nulls but not infinities, so bad rows can leak into training or prediction.

Expected fix direction:
- Guard the denominator and emit `None` or `0.5` for zero-range bars.
- Sanitize non-finite feature values before training and inference.

## Validation already run

- `./.venv/bin/python -m trading.main fetch --symbols AAPL --period 2y`
  - Passed using cached data.
- `./.venv/bin/python -m trading.main train --symbols AAPL --period 2y`
  - Passed and saved `trading/models/AAPL_xgb.pkl`.
- `./.venv/bin/python -m trading.main backtest --symbols AAPL --period 2y --strategy ensemble`
  - Ran successfully but produced suspicious metrics consistent with the short-accounting bug.

## Recommended implementation order

1. Fix backtest short accounting and add regression tests first.
2. Fix paper-trading daily halt semantics.
3. Fix ET market-hours handling with `zoneinfo`.
4. Harden feature engineering against non-finite values.
