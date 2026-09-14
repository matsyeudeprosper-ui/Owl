# E022 preregistration — previous-H1-candle direction gate on the live BOS configuration (frozen 2026-09-14 before any result)

Owner's hypothesis (2026-09-14): "only allow trades in the direction of the
previous H1 candle's close, in addition to the existing configuration;
for example in a buy setup, if the previous H1 candle closed up, take buy
trades above the close of that H1 candle."

## Frozen rule
At the signal bar j (M1 close at T[j]+60), the previous completed H1
candle is the clock hour before the hour containing T[j]: open = first M1
open of that hour, close = last M1 close of that hour (past-only).
- **R2 (owner's rule, primary)**: BUY signals allowed only if H1 closed
  up (close > open) AND the signal bar's close is above that H1 close;
  SELL signals only if H1 closed down AND the signal bar's close is below
  that H1 close. Flat H1 → no trade.
- **R1 (direction only)**: BUY only if H1 closed up, SELL only if H1
  closed down. No price condition.
- Applies to every entry (flip-BOS and continuation); everything else
  is the frozen live configuration (candle-close continuations, awake
  2 h gate, S_MIN_DIST 10, SL at the pending dot, TP 0.8R, fixed 0.02,
  one position). No debt/war-chest layer.

## Controls
- Baseline: the frozen configuration without the H1 gate (+237 net on
  R0 ticks in E001).
- P1 (polarity placebo): the opposite rule — BUY only if H1 closed DOWN,
  SELL only if it closed UP (R1 mirrored). If P1 ≈ R1 the H1 direction
  carries no information and only the trade-count reduction matters.
- P2 (random masks): 200 random per-bar eligibility masks with the same
  pass rate as R2, M1 "pess" mode, → percentile of R2's net.
- R1 vs R2 isolates the price-above/below-close condition.

## Data and modes
- Discovery: R0 (`data/pro_m1.npz` + `data/ticks_btcusd.npz`,
  2026-07-01 → 2026-09-07), tick execution, split at the frozen E005
  midpoint (TRAIN < 2026-08-04 15:13 UTC ≤ TEST); the untouched tail V1
  (2026-09-07 → 09-11) reported separately.
- Consumed eras, M1 "pess" mode with the era's median spread as S:
  2022, 2023, 2024 (V4), 2025 (V3), 2026-01 → 06 (V2). Per era, no
  tuning. (The eras are consumed; this is a consistency check, not a
  validation.)

## Reported
trades, net, PF, win rate, expectancy, max drawdown, per kind (flip /
cont), TRAIN / TEST / V1, per era; share of signals passed by each
gate; R2 − baseline attributable to removed trades (the P&L of the
trades the gate removed).

## Pass (what would make the gate worth a forward watch)
R2 net > baseline in TRAIN and TEST and ≥ 3 of 5 consumed eras, R2 >
P1 in the same places, R2 ≥ 95th percentile of P2, and the removed
trades have negative P&L in both halves. Otherwise the gate is not
adopted; production unchanged either way (owner decides).

## Not allowed
Other H1 definitions, offsets, timeframes or price margins after
results; production changes; use of E017's forward stream or of the
sealed eras (2021, 2017–2020).
