# E020 preregistration — downside shock → flush → reclaim (frozen 2026-09-12 before any result)

Question: after a large 5-minute BTC drop, does waiting for a flush BELOW
the shock low and an M1 close back ABOVE it identify the rebounds better
than buying the drop immediately (E019)? Structure is used only as an
entry confirmation; BOS is not assumed to be the edge.

## Data
- Development (consumed): Exness Pro BTCUSD M1 bars with per-bar mean
  spread built from the public tick archive — 2022, 2023, 2024 (V4), 2025
  (V3), 2026-01 → 06 (V2) and 2026-07-01 → 09-11 (archive slice). Bars are
  bid OHLC; ask = bid + the bar's mean spread.
- Blind: 2021 archive (era B1), imported only after this file, the code
  and the pass criteria are committed. 2017–2020 (U0) untouched.
- E017's forward stream is not opened.
- Resolution: M1 for all eras (the same convention everywhere so the eras
  are comparable). The tick file for 2026-07 → 09 is used once, to measure
  how far the M1 approximation of the immediate-entry control is from the
  tick result of E019 (cross-check only).

## Definitions (all past-only)
- 5-min windows on the clock (bars :00–:04, :05–:09, …). r5 = close of the
  window's last M1 bar over the close of the previous window's last bar
  − 1. Window low L = lowest bid low of its bars; shock close and high
  recorded; ATR = mean true range of the previous 14 windows.
- Threshold: trailing 7-day 5th percentile of r5 over the windows in
  (T − 7 d, T), needs ≥ 1 000 windows.
- **Shock** = window with r5 ≤ p5, and no other shock in the previous
  60 minutes (first of cluster).
- **Flush** = within 60 minutes after the shock close, an M1 bar whose bid
  low < L. flush_low = lowest bid low from the breach bar up to and
  including the reclaim bar.
- **Reclaim** = the first completed M1 bar, from the breach bar onward,
  whose close > L. (The breach bar itself may be the reclaim bar; the
  share of such same-bar reclaims is reported.) The reclaim bar must
  close no later than 60 minutes after the shock close; otherwise no trade.
- **Entry** = open of the bar after the reclaim bar, at the ask (bid open +
  that bar's mean spread). Costs: that spread (in the ask) + $5 per round
  trip. Exits at the bid close of the bar N minutes after entry
  (N = 5, 15, 30, 60). **Primary horizon = 30 min.**
- **R = entry − flush_low.** First passage within 60 min to +0.5R / +1R /
  +1.5R (bid high) versus −1R (bid low ≤ flush_low); if both are touched
  in the same bar the adverse side counts first.

## Controls
- A — immediate entry: same shock events, BUY at the open ask of the bar
  after the shock window (the M1 version of E019's "first ask ≥ 30 s after
  the close"), net at 5/15/30/60 min.
- B — flush without reclaim within 60 min: bid path from the 60-minute
  deadline (close-to-close move over the next 30 and 60 min, MFE/MAE),
  descriptive.
- C — generic sweep/reclaim without a p5 shock: at every 5-min window
  with r5 > p5, not within 60 min after a shock, apply the identical
  flush/reclaim/entry rule to that window's low; first of cluster 60 min.
- D — matched random entries: 1 000 draws, same n as the reclaim trades,
  same hour-of-day, random M1 bars not within 120 min after any shock,
  BUY at the open ask, net at the same horizons (R-matching not practical
  on M1; stated).

## Reported (descriptive, never a filter)
minutes shock → flush and flush → reclaim; flush depth below L in points
and ATR; reclaim bar body and range; R; spread at entry; 24 h median M1
range; hour of day; whether the reclaim close exceeds the highest high of
the three bars before it (M1 structure break proxy). Anti-outlier on the
primary horizon: without best 1, best 2, top 10% winners; median; win
rate. Frequency: shocks/day, % flushing, % of flushed reclaiming, trades/day
and /week, longest no-trade period, median shock → entry time. Per year
2022, 2023, 2024, 2025, 2026 and pooled; no tuning by year.

## Freeze before 2021
If, on the consumed eras, the rule is not clearly dead (pooled 30-min
mean > 0 AND above control A in at least 3 of the 5 years), the identical
rule/code (this file, `e020.py`, its commit hash) is run once on 2021.
Nothing is adjusted from 2021.

## Blind 2021 pass criteria (primary 30 min)
mean net > 0; better than control A; win rate > 50% or payoff clearly
compensating; > 0 without the best 2 and without the top 10% winners;
≥ 95th percentile of control D; median not strongly negative; practical
frequency; reasonable max drawdown; no single month responsible for the
result (month-by-month reported).

## Not allowed
Threshold, reclaim-timing, depth, candle-shape or horizon changes after
results; filters from the descriptive variables; OI/liquidation/HTF
conditions; money-management layers; production changes; any use of
2017–2020 or of E017 forward data.

## Verdict
A — shock → flush → reclaim shows a robust edge and survives blind 2021.
B — interesting structure but blind evidence weak / insufficient.
C — reclaim confirmation does not create a durable edge.
