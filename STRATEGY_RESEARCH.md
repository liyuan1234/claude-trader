# Strategy Research Memo

Date: 2026-03-30
Scope: equity strategies that are both academically grounded and realistically implementable in this repository with daily OHLCV data, cached history, backtesting, and optional ML support.

## Executive summary

The best strategies to implement next are:

1. Time-series momentum with volatility targeting
2. Cross-sectional momentum on a stock universe
3. Statistical arbitrage / pairs trading
4. Short-term reversal with liquidity and volatility filters
5. Regime-switched trend + mean-reversion ensemble

If the goal is highest research credibility with the current codebase, start with:

1. Time-series momentum
2. Pairs trading
3. Cross-sectional momentum

The main reason is practical fit. These strategies have strong academic support, map cleanly to daily bars, and do not require fundamental data or intraday microstructure data.

## Research base

### 1. Time-series momentum

Primary source:
- Moskowitz, Ooi, Pedersen, "Time Series Momentum," Journal of Financial Economics, 2012.
- Source: https://econpapers.repec.org/RePEc:eee:jfinec:v:104:y:2012:i:2:p:228-250

What the paper supports:
- Past own-asset returns over roughly 1 to 12 months positively predict future returns.
- The effect was documented across 58 liquid futures instruments and performed especially well in extreme markets.

Why it matters here:
- The current repo already computes trend features and has a backtester that works at daily frequency.
- A stock-level or ETF-level time-series momentum strategy is straightforward to implement without adding new datasets.

Recommended implementation:
- Universe: liquid large-cap stocks or sector/index ETFs.
- Signal:
  - Compute 1m, 3m, 6m, and 12m excess or raw returns.
  - Long if weighted return score > threshold.
  - Short or flat if score < negative threshold.
- Risk:
  - Volatility target each position using 20d or 60d realized volatility.
  - Optional trend confirmation with moving-average filter.
- Rebalance:
  - Weekly is preferable to daily to reduce turnover.

Key design choices:
- Use skip-most-recent-week logic if turnover becomes too high.
- Normalize by realized volatility before ranking signal strength.

Implementation difficulty: low
Research strength: high
Fit with current repo: very high

### 2. Cross-sectional momentum

Primary source:
- Jegadeesh and Titman, "Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency," Journal of Finance, 1993.
- Source: https://www.researchgate.net/publication/4992307_Returns_to_Buying_Winners_and_Selling_Losers_Implications_for_Stock_Market_Efficiency

Supporting source:
- Jegadeesh, "Evidence of Predictable Behavior of Security Returns," Journal of Finance, 1990.
- Source: https://econpapers.repec.org/RePEc:bla:jfinan:v:45:y:1990:i:3:p:881-98

What the papers support:
- Stocks with strong intermediate-horizon past performance tend to keep outperforming over the next several months.
- The classic formation/holding region is roughly 3 to 12 months.

Why it matters here:
- This is one of the highest-signal strategies available on daily equity data.
- It complements time-series momentum: one ranks stocks against each other, the other evaluates each asset versus its own history.

Recommended implementation:
- Universe: at least 50 to 200 liquid stocks. The current default symbol list is too small.
- Signal:
  - 12-1 momentum score: total return over the last 12 months excluding the most recent month.
  - Rank universe cross-sectionally.
  - Go long top decile/quintile, short bottom decile/quintile or stay market-neutral/long-only.
- Risk:
  - Dollar-neutral or beta-neutral if shorting is enabled.
  - Sector-neutral ranking is preferable if the universe is broad enough.
- Rebalance:
  - Monthly is the research-standard baseline.

Key design choices:
- Excluding the most recent month usually improves robustness.
- Cap weights by inverse volatility or equal risk contribution to avoid concentration.

Implementation difficulty: medium
Research strength: high
Fit with current repo: medium-high, but only after expanding the universe

### 3. Statistical arbitrage / pairs trading

Primary source:
- Gatev, Goetzmann, Rouwenhorst, "Pairs Trading: Performance of a Relative-Value Arbitrage Rule," Review of Financial Studies, 2006.
- Source: https://ideas.repec.org/a/oup/rfinst/v19y2006i3p797-827.html
- NBER version: https://www.nber.org/papers/w7032

What the paper supports:
- Matching stocks into economically similar or price-similar pairs and trading relative dislocations produced economically meaningful excess returns in the historical sample.

Why it matters here:
- The repo already handles per-symbol backtests and feature generation; extending it to spread trading is feasible.
- Pairs trading diversifies the existing directional strategies because it depends more on relative mispricing than on outright market direction.

Recommended implementation:
- Universe:
  - Same sector or highly correlated stocks first.
  - Start with mega-cap tech, banks, semis, or ETF pairs.
- Signal:
  - Build normalized price spread or residual spread from rolling OLS hedge ratio.
  - Enter when z-score of spread exceeds threshold.
  - Exit near mean or on stop.
- Validation:
  - Require rolling correlation and cointegration or at least persistent spread stationarity checks.
- Risk:
  - Dollar-neutral sizing using hedge ratio.
  - Hard stop on spread widening and max holding period.

Key design choices:
- Do not rely on static pairs selected once and never refreshed.
- Re-estimate pair eligibility and hedge ratio on a rolling basis.

Implementation difficulty: medium-high
Research strength: high
Fit with current repo: high if multi-asset backtest support is added

### 4. Short-term reversal

Primary sources:
- Lehmann, "Fads, Martingales, and Market Efficiency," Quarterly Journal of Economics, 1990.
- Source: https://academic.oup.com/qje/article/105/1/1/1928416
- Jegadeesh, 1990 short-horizon predictability evidence.
- Source: https://econpapers.repec.org/RePEc:bla:jfinan:v:45:y:1990:i:3:p:881-98

What the papers support:
- Very recent winners and losers can reverse over short horizons.
- The effect is often linked to liquidity provision, temporary price pressure, and microstructure.

Why it matters here:
- The repo already contains a mean-reversion strategy, but it is indicator-driven rather than research-faithful reversal.
- A cleaner reversal implementation would be more defensible than raw Bollinger/RSI rules.

Recommended implementation:
- Universe: highly liquid large caps only.
- Signal:
  - Rank 5-day or 1-week returns cross-sectionally.
  - Long recent losers, short recent winners.
- Filters:
  - Only trade when realized volatility is not extreme.
  - Avoid earnings days and major gaps if event data is added later.
- Rebalance:
  - Weekly or every few days.

Key design choices:
- This strategy is much more fragile after costs than medium-term momentum.
- It should only be implemented with strict liquidity and turnover controls.

Implementation difficulty: medium
Research strength: medium-high
Fit with current repo: medium

### 5. Volatility-managed overlays

Primary source:
- Moreira and Muir, "Volatility-Managed Portfolios," Journal of Finance, 2017.
- NBER version: https://www.nber.org/papers/w22208

What the paper supports:
- Reducing exposure when realized volatility is high can improve Sharpe ratio because expected returns do not rise enough to offset volatility spikes.

Why it matters here:
- This is not a standalone alpha source in this repo; it is a portfolio construction overlay.
- It is likely the highest-value risk improvement to add once the base signals are fixed.

Recommended implementation:
- Apply to every directional strategy.
- Target constant annualized volatility, for example 10% to 15%.
- Scale gross exposure by inverse recent realized variance.
- Add leverage caps and minimum/maximum exposure bounds.

Implementation difficulty: low
Research strength: high
Fit with current repo: very high

## What to implement first

### Tier 1: implement immediately

#### A. Time-series momentum with vol targeting

Why first:
- Best balance of evidence, simplicity, and deployability.
- Works with current data model.
- Easy to compare against existing momentum code.

Suggested spec:
- Features:
  - 21d, 63d, 126d, 252d returns
  - 20d and 60d realized vol
- Signal score:
  - `0.4 * sign(252d) + 0.3 * sign(126d) + 0.2 * sign(63d) + 0.1 * sign(21d)`
  - Or standardized weighted returns divided by vol
- Position:
  - Long if score > 0.5
  - Short if score < -0.5
  - Otherwise flat
- Overlay:
  - Scale by inverse 20d realized vol

#### B. Pairs trading

Why second:
- Strong academic grounding and diversifying return profile.
- More robust than naive single-name mean reversion.

Suggested spec:
- Preselect candidate pairs by sector and rolling correlation.
- Estimate rolling hedge ratio over 60 to 120 days.
- Compute spread z-score over 20 to 60 days.
- Enter at `|z| >= 2`, exit at `|z| <= 0.5`.
- Add max holding period and stop on `|z| >= 3.5`.

#### C. Cross-sectional momentum

Why third:
- Very credible strategy, but needs a broader universe and portfolio-level engine.

Suggested spec:
- Build monthly rebalance engine.
- Rank by 12-1 return.
- Long top quintile, short bottom quintile.
- Apply inverse-vol or equal-weight sizing.

## What not to prioritize yet

### 1. Pure indicator stacks without economic rationale

Examples:
- RSI + Bollinger + MACD combinations chosen ad hoc

Reason:
- Easy to overfit.
- Harder to defend than momentum, reversal, or relative-value frameworks from the literature.

### 2. Fundamental quality/value strategies right now

Reason:
- The research case is strong, but this repo currently does not ingest accounting fundamentals.
- Delay until a proper fundamentals pipeline exists.

### 3. Intraday alpha

Reason:
- The data and execution model here are daily.
- Intraday signals would need different market data, slippage modeling, and broker logic.

## Architecture recommendations for this repository

### 1. Separate signal generation from portfolio construction

Right now the code mixes per-symbol signal logic with execution assumptions. For the next strategy wave:
- `signal_model`: computes raw expected direction/score
- `portfolio_model`: converts scores into target weights
- `risk_model`: volatility target, exposure caps, turnover caps, stops
- `execution_model`: next-open or close-to-close fill assumptions

### 2. Add portfolio-level backtesting

Cross-sectional momentum and pairs trading need:
- shared capital across symbols
- simultaneous positions
- portfolio gross/net exposure tracking
- realistic borrow and turnover costs for short legs

### 3. Fix accounting before adding new strategies

The backtester currently needs repair before strategy comparisons are trustworthy, especially for short positions.

### 4. Add robust validation

Every new strategy should support:
- train / validation / test date splits
- walk-forward re-estimation
- turnover reporting
- exposure reporting
- sector concentration reporting
- cost sensitivity analysis

## Concrete roadmap

### Phase 1

1. Repair backtest accounting and short-side equity math
2. Add portfolio-level metrics and turnover metrics
3. Add realized-volatility targeting as a reusable overlay

### Phase 2

1. Implement `TimeSeriesMomentumStrategy`
2. Compare against current momentum strategy
3. Add parameter sweep for lookbacks and rebalance frequency

### Phase 3

1. Add pair-selection module
2. Add spread-based backtest mode
3. Implement `PairsTradingStrategy`

### Phase 4

1. Expand stock universe
2. Add monthly cross-sectional rebalance engine
3. Implement `CrossSectionalMomentumStrategy`

## Recommended default strategy stack

If only one production-grade strategy is needed soon:
- Time-series momentum with volatility targeting

If two are needed:
- Time-series momentum with volatility targeting
- Pairs trading

If building a diversified research platform:
- Time-series momentum
- Cross-sectional momentum
- Pairs trading
- Short-term reversal
- Volatility-managed portfolio overlay across all of them

## Source links

- Moskowitz, Ooi, Pedersen (2012), Time Series Momentum:
  - https://econpapers.repec.org/RePEc:eee:jfinec:v:104:y:2012:i:2:p:228-250
- Jegadeesh and Titman (1993), Returns to Buying Winners and Selling Losers:
  - https://www.researchgate.net/publication/4992307_Returns_to_Buying_Winners_and_Selling_Losers_Implications_for_Stock_Market_Efficiency
- Jegadeesh (1990), Evidence of Predictable Behavior of Security Returns:
  - https://econpapers.repec.org/RePEc:bla:jfinan:v:45:y:1990:i:3:p:881-98
- Gatev, Goetzmann, Rouwenhorst (2006), Pairs Trading:
  - https://ideas.repec.org/a/oup/rfinst/v19y2006i3p797-827.html
  - https://www.nber.org/papers/w7032
- Lehmann (1990), Fads, Martingales, and Market Efficiency:
  - https://academic.oup.com/qje/article/105/1/1/1928416
- Moreira and Muir (2017), Volatility-Managed Portfolios:
  - https://www.nber.org/papers/w22208
