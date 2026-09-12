# E018 preregistration — tradable forced-deleveraging shock (frozen 2026-09-12 before any result)

Hypothesis: a BTC 5-minute downside shock accompanied by a contraction of
open interest (leveraged longs being closed/liquidated rather than fresh
shorts opening) is followed by a short-term rebound over the next 1–60
minutes that survives Exness costs. The decisive comparison is PRICE DOWN +
OI DOWN versus PRICE DOWN WITHOUT OI DOWN: if they behave the same, OI adds
nothing and E018 fails.

## 1. Data audit (consumed data only; E017's forward stream untouched)

| field | source | resolution | coverage used | quality |
|---|---|---|---|---|
| BTC price (bid/ask) | Exness Pro BTCUSD ticks, MT5 (`study/data/ticks_btcusd.npz`) | tick, ms | 2026-07-01 → 2026-09-11 13:39 UTC (8.0 M ticks) | consumed by E001/E015/E016 |
| open interest | OKX `rubik/stat/contracts/open-interest-volume?ccy=BTC&period=5m` (aggregate USD OI of OKX BTC contracts), polled by `recorder/derivs_recorder.py` every 300 s, last completed slot stored (`recorder/data/derivs_BTC.csv`) | 5 min | 2026-07-31 20:10 → 2026-09-11 13:35 UTC, 11 384 rows | 634 missing slots (5.6%), 626 gaps of 10–20 min, no gap > 20 min; 39 rows with OI = 0 (outage 2026-09-03 06:05–06:55) treated as missing; 81 consecutive identical values kept as reported |
| taker buy / sell volume | OKX `rubik/stat/taker-volume?ccy=BTC&instType=CONTRACTS&period=5m` (USD), same recorder | 5 min | same | 1 blank |
| long/short account ratio, funding | same recorder | 5 min / 8 h | same | not used in E018 |
| liquidation fills | OKX REST `public/liquidation-orders` BTC-USDT-SWAP, 60 s poll (`recorder/data/liquidations_BTC.csv`) | per fill, exchange ms | 2026-07-31 02:02 → 2026-09-11 13:37 UTC, 72 787 fills | descriptive only |

No interpolation. A slot whose OI or previous-slot OI is missing/zero is
not scorable and cannot be an event; only consecutive 5-min slots define an
OI change. Data END for E018 = 2026-09-11 13:39:53 UTC (tick file end);
nothing recorded after it is read. E017's blind stream (from 2026-09-12
13:07 UTC) is not opened.

Timestamp convention: the OKX row with slot timestamp T describes the
window [T, T+5 min); it is treated as known only after T+5 min. The BTC
return of the same window is Exness mid at the last tick before T+5 min
over the mid at the last tick before T.

## 2. Event definitions (rolling, past-only, trailing 7 days)
At each slot end T+5: r5 = 5-min BTC return, dOI = OI(T)/OI(T−5) − 1.
Thresholds: percentiles of r5 and dOI over the scorable slots in
(T+5 − 7 days, T+5), requiring ≥ 1 000 slots (so scoring starts ~2026-08-07).
- **PRIMARY — downside deleveraging**: r5 ≤ p5(r5) AND dOI ≤ p20(dOI) → BUY.
- **Robustness (the only variant)**: r5 ≤ p2.5 AND dOI ≤ p20 → BUY.
- Control A — price shock without OI contraction: r5 ≤ p5 AND dOI > p20 → BUY.
- Control B — OI contraction without price shock: dOI ≤ p20 AND r5 > p5 → BUY.
- Control C — matched random slot ends: same n as primary, same hour-of-day,
  not within 60 min after any primary/A/B trigger, BUY, 1 000 draws.
- Control D — symmetric upside (descriptive): r5 ≥ p95 AND dOI ≤ p20; the
  path after it is reported as the BUY-side net (continuation) — the SELL
  side is its negative.
Event = triggering slot with no other trigger of the same set in the
previous 60 minutes (first of cluster; raw trigger counts also reported).

## 3. Entry, exit, costs
Entry: first Exness tick at or after T+5 min + 30 s (30 s data/processing
latency; the recorder itself polls every 300 s, so live use would need a
faster poll — reported, not assumed), at the ASK. Exits at the first tick
at or after entry + 1 / 5 / 15 / 30 / 60 min, at the BID. $5 per round
trip slippage/drag on top (the Owl convention since E001). Primary horizon
for the pass test = **15 min** (fixed now; 5 and 30 min must carry the
same sign as a coherence check). MFE/MAE over 60 min from the entry tick
(bid). ATR = 14-slot average true range of 5-min mid bars, past-only at
T+5; first passage to +0.5 / −0.5 ATR and +1 / −1 ATR within 60 min
(bid vs entry ask), reported as favourable-first / adverse-first / neither.

## 4. Descriptive context (never a trigger)
Taker imbalance (buy − sell)/(buy + sell) in the event slot and its
percentile within the trailing 7 days; liquidated BTC in the event slot,
and events split at large vs not-large liquidation (slot total ≥ trailing
7-day p95 of non-empty slot totals, as in E015). Burst-size and
return-size tertiles descriptive only.

## 5. Chronological split (fixed now)
Discovery = slot ends before **2026-08-25 00:00 UTC**; internal check =
from 2026-08-25 00:00 UTC to END. Reported separately; the split does not
move.

## 6. Pass criteria (primary, 15 min, after costs)
mean net > 0; same sign in both halves; mean net > Control A's mean at the
same horizon; ≥ 95th percentile of Control C; > 0 without the top-2 events;
> 0 after removing the top 10% most profitable events; frequency reported
(events/day, /week, share of days with none, longest gap, median spacing);
max drawdown reported against the mean gain. Economic read (0.01 / 0.02 /
0.05 lot; $1 per point per 1.00 lot) only for cells that pass.

## 7. Not allowed
Other thresholds, windows, cooldowns, delays or horizons after seeing
results; taker-flow or liquidation triggers; BOS/HTF structure; debt,
war-chest, recovery or withdrawal logic; production changes; any read of
E017 forward data.

## Verdict
A — downside forced-deleveraging has a repeatable, latency-realistic rebound edge.
B — evidence exists but weak, unstable, or sample insufficient.
C — OI/deleveraging adds no tradable information beyond the price move.
