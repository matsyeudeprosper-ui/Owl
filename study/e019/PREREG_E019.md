# E019 preregistration — pure 5-minute downside-shock rebound (frozen 2026-09-12 before any result)

Clean price-response study: after an unusually sharp 5-minute BTC drop, is
there a repeatable short-term rebound after realistic Exness costs? No OI,
no liquidation, no BOS conditions.

## Honesty note on the data
Consumed data only (Exness Pro BTCUSD ticks to 2026-09-11 13:39 UTC; the
OKX 5-min series is used only as descriptive context and to define the
same slot grid as E018). E018's control A (price ≤ p5 with OI not down,
+15.7 at 15 min) is a subset of E019's primary population, so the
discovery half is NOT blind to this hypothesis — the internal-check half
(from 2026-08-25) and the outlier controls carry the weight. Any pass on
this data is provisional until a forward or newly frozen era confirms it.
E017's forward stream is not opened.

## Events (rolling, past-only, trailing 7 days, ≥ 1 000 slots)
Slot grid = the OKX 5-min slot timestamps T (window [T, T+5)); r5 = Exness
mid at the last tick before T+5 over mid at the last tick before T. A
slot is scorable if price exists (the OI condition is dropped, so slots
with missing OI are scorable; the slot grid itself is the recorder's
5-min stamps, 5.6% of which are missing — those windows are simply not
observed).
- **PRIMARY**: r5 ≤ trailing-7-day p5 → BUY.
- **Robustness (only variant)**: r5 ≤ trailing p2.5 → BUY.
- **Upside (descriptive)**: r5 ≥ trailing p95 → continuation BUY and
  reversal SELL both reported.
- Control: matched random slot ends, same n, same hour-of-day, not within
  60 min after any primary/upside trigger, BUY, 1 000 draws.
Cluster rule (as E018): an event is a trigger with no trigger of the same
set in the previous 60 minutes; raw trigger counts reported too.

## Entry, exits, costs (as E018)
BUY at the first ask ≥ T+5 min + 30 s; exits at the first bid ≥ entry +
1 / 5 / 15 / 30 / 60 min; $5 per round trip on top. **Primary horizon =
15 min**, fixed now. MFE/MAE over 60 min from the entry tick (bid), time
to MFE and to MAE, first passage ±0.5 ATR and ±1 ATR (ATR = 14-slot
5-min true range, past-only).

## Reported per event, never gated on
spread at entry, 24 h median M1 range (past-only), hour of day, OI change
of the slot, taker imbalance, liquidated BTC in the slot, distance of the
entry from the trailing 1 h high and low (in ATR).

## Shock severity
Tertiles of the event's r5 (most / mid / least negative), descriptive; no
filter.

## Split (fixed)
Discovery = slot ends before 2026-08-25 00:00 UTC; internal check = from
2026-08-25 00:00 UTC to END.

## Anti-outlier checks (mandatory)
without the best 1 event, without the best 2, without the top 10% most
profitable, median, 10% trimmed mean.

## Pass criteria (primary, 15 min)
mean net > 0 after costs; discovery > 0 AND internal check > 0; ≥ 95th
percentile of matched random; > 0 without the best 2; > 0 without the top
10%; win rate and median not inconsistent with the mean; drawdown and
frequency reported (trades/day, /week, share of days with none, median
spacing, longest gap). Economics (0.01 / 0.02 / 0.05 lot) only if the
primary cell passes.

## Interpretation rules
If p5 rebounds but p2.5 continues down, report it as mechanism evidence
and register the next experiment separately; no threshold search inside
E019. If neither version survives the chronological check and outlier
removal, the direction is closed.

## Not allowed
Other percentiles, cooldowns, delays or horizons after results; context
filters; BOS; debt/recovery/withdrawal logic; production changes; any
read of E017 forward data.

## Verdict
A — clean downside-shock rebound survives costs, chronology and outlier controls.
B — interesting but unstable / weak / needs a narrower preregistered mechanism.
C — the E018 price-only clue was noise.
