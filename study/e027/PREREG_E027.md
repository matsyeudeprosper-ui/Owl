# E027 preregistration — first BOS of a flip only, stop at the true lowest low (frozen 2026-09-15 before any result)

Owner (2026-09-15): "only took the first BOS of a flip but SL at the very
low (lowest low) where all candles end, in a buy setup; mirror for sell."

## Two separate changes
1. **First BOS only** — take the flip-BOS entry and skip every
   continuation that follows inside the same trend.
2. **Deeper stop** — today the stop sits at the confirmed dot, which is
   the lowest low among the *kept* candles. The silence filter keeps a
   candle only when its CLOSE breaks the reference, so a candle that
   wicks lower but closes inside is dropped and its low is invisible to
   the stop. The new stop is the lowest low of **every raw M1 candle** in
   the span, from the bar after the swing high through the signal bar.
   Mirrored (highest high) for sells.

Because two things change at once, the arms below decompose them.

## Arms
1. **BASELINE** — frozen live config (flip + continuations, stop at the dot).
2. **FLIP-ONLY / dot stop** — change 1 alone.
3. **FLIP-ONLY / deep stop** (primary) — the owner's full idea.
4. **FLIP+CONT / deep stop** — change 2 alone.
5. **Primary / random direction** — coin-flip direction, geometry mirrored,
   to check the direction still carries the result.

Everything else frozen: entry at the candle close, TP 0.8R measured from
the stop in use, S_MIN_DIST 10, 2 h awake gate, fixed 0.02, one position,
no debt layer. A wider stop means a wider target in points, so R is held
constant by construction.

## Data
R0 (`data/pro_m1.npz` + `ticks_btcusd.npz`) on ticks, TRAIN < 2026-08-04
15:13 UTC ≤ TEST; consumed eras 2022, 2023, 2024, 2025, 2026-01→06 in M1
"pess" mode at the era's median spread. No tuning per era.

## Reported
trades, net, PF, win rate, expectancy per trade, maxDD, TRAIN/TEST, per
era; median stop distance of each arm and how much deeper the raw low
sits versus the dot; share of signals where the two differ at all.

## Pass
The primary arm beats BASELINE on expectancy per trade in TRAIN and TEST
and in ≥ 3 of 5 eras, and beats its own random-direction control.
Otherwise not adopted. Production unchanged either way.

## Not allowed
Other stop definitions, buffers, RR values or lookback spans after
results; production changes; E017 forward data; the sealed eras (2021,
2017–2020).
