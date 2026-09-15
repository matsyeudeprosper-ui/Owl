# E023 preregistration — replace the "awake" weather gate with a previous-H1 high/low touch gate (frozen 2026-09-15 before any result)

Owner's idea (2026-09-15): "instead of the at-least-one-flip-every-2-hours
weather rule, do this: every time price touches the high or low of the
previous H1 candle, only then we start considering a BOS entry."

## What the current gate does (the thing being replaced)
`awake_sig[j] = any flip in [T[j] - 2h, T[j]]`. A flip signal is its own
event, so in practice the 2 h rule only filters CONTINUATION entries.
E007 found it acts as a trend-age proxy and that 2 h is not special
(TRAIN +90, TEST +0).

## The new gate
Reference = the previous completed clock hour's high and low, built from
that hour's M1 bars (past-only; the hour containing T[j] is never used).
A bar j **touches** when `H[j] >= prevHigh` or `L[j] <= prevLow`. The
touch during bar j is known at its close, so bar j's own signal may use
it (no look-ahead).

Two arming windows, both frozen now:
- **A — until the end of the hour** (primary): armed from the first touch
  of the current clock hour, through the rest of that hour. The reference
  resets every hour, so the gate re-arms naturally.
- **B — 2 h rolling**: armed if any touch happened in the last 120
  minutes, the same window length as the rule it replaces.

Two scopes, both reported:
- **all** (literal reading): the gate applies to every BOS entry, flips
  included.
- **cont** (like-for-like): flips stay self-eligible, the gate only
  filters continuations — exactly how the current 2 h rule behaves.

Primary cell = **A / cont** (same scope as the rule it replaces, hourly
arming). Nothing else is selected after results.

## Controls
- BASELINE: the frozen live configuration (2 h flip gate).
- NOGATE: no eligibility gate at all.
- PLACEBO: 200 random per-bar masks with the same pass rate as the
  primary cell, M1 "pess" mode → percentile of the real net.
Pass rate of every arm is reported: a gate that simply trades less must
not be mistaken for a gate that trades better.

## Data and execution
- R0 (`data/pro_m1.npz` + `data/ticks_btcusd.npz`, 2026-07-01 → 09-07),
  tick execution, split at the frozen E005 midpoint (TRAIN < 2026-08-04
  15:13 UTC ≤ TEST).
- Consumed eras in M1 "pess" mode with the era's median spread: 2022,
  2023, 2024 (V4), 2025 (V3), 2026-01 → 06 (V2). No tuning per era.
- Everything else is the frozen live configuration: candle-close
  continuations, SL at the pending dot, TP 0.8R, S_MIN_DIST 10, fixed
  0.02, one position, no debt/war-chest layer.

## Reported
trades, net, PF, win rate, expectancy, maxDD, flips vs continuations,
TRAIN/TEST, per era, pass rate, and the P&L of the trades each gate
removes relative to NOGATE.

## Pass (what would make this worth a forward watch)
The primary cell beats BASELINE in TRAIN and TEST and in ≥ 3 of 5
consumed eras, beats NOGATE per trade, and lands ≥ 95th percentile of
the random masks. Otherwise it is not adopted. Production unchanged
either way; the owner decides.

## Not allowed
Other arming windows, other reference timeframes, margins around the
level, or scope changes after results; production changes; use of E017's
forward stream or of the sealed eras (2021, 2017–2020).
