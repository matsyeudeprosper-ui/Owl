# E025 preregistration — pullback entry AT the trend's pending dot, stop at the previous dot (frozen 2026-09-15 before any result)

Owner (2026-09-15): "Entry at the glowing dot of a trend. SL at the next
lower low (next lower dot) in a buy trend. Mirror the same for sell."

## What the dot is
In `bt_bos.Struct`, when the close breaks the swing high in an uptrend the
engine confirms a low dot at `m[3]` (the lowest low of the span) and emits
the BOS signal with that dot as its stop (`prot_lo`). That confirmed dot
is what the chart draws and highlights. So:
- **uptrend**: the glowing dot = the protected LOW. Entry level.
- the **previous** confirmed low dot = the stop.
- **downtrend**: mirrored on the protected HIGH.

This is a different entry mechanism from production, not a filter:
production enters at the BOS candle close with the stop AT the dot; E025
waits for price to come back DOWN to the dot and puts the stop one dot
lower.

## Frozen rule
While a trend is confirmed and at least two dots on the trend side exist:
- arm a limit at `dot_cur`; if price reaches it (bid ≤ dot_cur for a buy,
  bid ≥ dot_cur for a sell) enter at the next tick after a 1 s poll delay,
  ask for buys / bid for sells (the same execution convention as E001).
- **SL = `dot_prev`** (the previous confirmed dot on the same side).
- **TP = entry + 0.8 × |entry − SL|**, the frozen RR.
- one position at a time; `|entry − SL| > 10` (S_MIN_DIST) or no trade;
  fixed 0.02; no debt/war-chest layer.
- a newly confirmed dot replaces the armed level; a trend flip disarms it;
  each dot level may be used at most once.

## Arms
1. **BASELINE** — the frozen live configuration (BOS at candle close, SL
   at the dot, 2 h awake gate).
2. **DOT** (primary) — the rule above, no awake gate.
3. **DOT + 2 h gate** — the same with the production awake gate.
4. **DOT / random direction** — same entries and levels, direction drawn
   by a coin flip: separates the level mechanics from the direction call.

## Data
R0 (`data/pro_m1.npz` + `ticks_btcusd.npz`) on ticks, TRAIN < 2026-08-04
15:13 UTC ≤ TEST; consumed eras 2022, 2023, 2024, 2025, 2026-01→06 in M1
"pess" mode (stop checked before target on the entry bar) at the era's
median spread. No tuning per era.

## Reported
trades, fill rate of the armed level, net, PF, win rate, expectancy,
maxDD, TRAIN/TEST, per era, median distance entry→SL versus production's,
and MFE/MAE over 60 min.

## Pass
The primary arm beats BASELINE in TRAIN and TEST and in ≥ 3 of 5 eras on
expectancy per trade, and beats its own random-direction control.
Otherwise not adopted. Production unchanged either way.

## Not allowed
Other RR values, buffers around the dot, dot-selection variants or
re-arming rules after results; production changes; E017 forward data; the
sealed eras (2021, 2017–2020).
