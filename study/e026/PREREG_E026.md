# E026 preregistration — stop trading the Asian and Australian sessions (frozen 2026-09-15 before any result)

Owner (2026-09-15): "Test if stop trading the Asia and Australia session
improves anything to the current live bot."

## Session definition (frozen, UTC)
BTC trades 24/7, so a "session" here is a clock window, not an exchange
calendar.
- Sydney 21:00 → 06:00, Tokyo 00:00 → 09:00.
- **BLOCKED (primary) = 21:00 → 08:59 UTC inclusive**, i.e. the bot only
  takes entries whose signal bar closes between **09:00 and 20:59 UTC**
  (London + New York).
- **Robustness (the only variant): block 00:00 → 08:59 UTC** (Tokyo
  only), leaving the Sydney overlap tradable.
An entry is judged by the hour of its signal bar. A position opened
before a blocked hour is never closed early by the filter; only new
entries are blocked. Everything else is the frozen live configuration.

## Arms
1. **BASELINE** — the live configuration, all hours.
2. **NO-ASIA (primary)** — entries only 09:00–20:59 UTC.
3. **NO-TOKYO** — entries only 09:00–23:59 UTC.
4. **ASIA-ONLY** — the mirror: entries only during the blocked window.
   If the blocked hours are where the money is, this shows it at once.

## Controls
- 200 random per-bar masks at the same pass rate as the primary arm
  (M1 "pess" mode) → percentile of the primary arm's net. A filter that
  merely trades less must not be read as a filter that trades better.
- The P&L of the trades the filter removes, reported explicitly.
- Hour-by-hour net of the BASELINE, reported for R0 and for every era.
  This is the diagnostic the question really asks.

## Data
R0 (`data/pro_m1.npz` + `ticks_btcusd.npz`) on ticks, TRAIN < 2026-08-04
15:13 UTC ≤ TEST; consumed eras 2022, 2023, 2024, 2025, 2026-01→06 in M1
"pess" mode at the era's median spread. No tuning per era.

## Pass
The primary arm beats BASELINE on expectancy per trade in TRAIN and TEST
and in ≥ 3 of 5 eras, and lands ≥ 95th percentile of the random masks.
Otherwise not adopted. Production unchanged either way; the owner decides.

## Not allowed
Other hour windows, per-era windows, or day-of-week variants after
results; production changes; E017 forward data; the sealed eras (2021,
2017–2020). If the hour breakdown suggests a different window, that is a
new experiment on data not used here, not an edit of this one.
