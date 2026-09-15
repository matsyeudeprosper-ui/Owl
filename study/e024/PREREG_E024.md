# E024 preregistration — no 2h rule, and "a touch of the previous H1 high/low resets the structure" (frozen 2026-09-15 before any result)

Owner (2026-09-15): "Test without the 2-hour rule. And also, at each H1
high or low touch, wait for a new pattern (BOS) to form and enter. So when
a touch happens we clear all existing patterns and wait for a new one to
form and we take that new one."

E023 tested the touch as an *eligibility window* and it failed (0.5th
percentile of random masks). E024 tests something different: the touch
**destroys the pending structure**, so only a pattern built after it can
trade.

## Touch event (frozen)
Reference = the previous completed clock hour's high and low, from that
hour's M1 bars (past-only). Within each hour, the **first** bar that
reaches the previous hour's high is one event, and the **first** bar that
reaches its low is another: at most two events per hour. (E023 showed a
per-bar definition arms ~99% of bars, which is no rule at all.)

## Arms (all on the frozen live configuration otherwise: candle-close
continuations, SL at the pending dot, TP 0.8R, S_MIN_DIST 10, fixed 0.02,
one position, no debt layer)
1. **BASELINE** — live config with the 2 h awake gate.
2. **SANS 2h** — the same, awake gate removed. (the owner's first ask)
3. **RESET / tous** — at every touch event the structure engine is wiped
   (`Struct()` re-instantiated, the touch bar becomes the first bar of the
   new pattern); every signal the rebuilt engine produces is tradable; no
   awake gate.
4. **RESET / 1er signal** (primary for the new idea) — same reset, but
   only the **first** signal produced after each reset is taken, which is
   the literal "we take that new one".
5. **RESET + porte 2h** — arm 3 with the 2 h gate still on, to separate
   the reset effect from the gate effect.

## Controls
200 random per-bar masks at the same pass rate as arm 4, on the rebuilt
signal stream, M1 "pess" mode → percentile of arm 4's net. Signal counts
before/after the reset are reported: a rule that mostly destroys signals
must not be read as a rule that picks better ones.

## Data
R0 (`data/pro_m1.npz` + `ticks_btcusd.npz`) on ticks, TRAIN < 2026-08-04
15:13 UTC ≤ TEST; consumed eras 2022, 2023, 2024, 2025, 2026-01→06 in M1
"pess" mode at the era's median spread. No tuning per era.

## Pass
An arm is worth a forward watch only if it beats BASELINE in TRAIN and
TEST and in ≥ 3 of 5 eras, and arm 4 lands ≥ 95th percentile of the random
masks. Otherwise not adopted. Production unchanged either way.

## Not allowed
Other touch definitions, reset timings, or "first N signals" variants
after results; production changes; E017 forward data; the sealed eras
(2021, 2017–2020).
