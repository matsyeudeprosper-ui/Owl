# E016 preregistration — real-time detection of forced-liquidation bursts (frozen 2026-09-12 12:15 UTC, before any result)

Mechanism under test is E015's, frozen: after forced SELLING buy the
snap-back; after forced BUYING sell it. No direction search.

## Data (discovery — NOT blind)
- Raw OKX BTC-USDT-SWAP liquidation fills from `recorder/data/liquidations_BTC.csv`
  (exchange timestamp `ts_ms`, side, posSide, sz contracts × 0.01 BTC, bkPx),
  2026-07-31 → 2026-09-11 (the part overlapping our tick data).
- Exness Pro BTCUSD ticks (`study/data/ticks_btcusd.npz`, MT5, ms, bid/ask).
- Everything recorded after the freeze timestamp of the candidate rule is
  forward validation and is not to be looked at while designing.

## Real-time burst definition (only information up to t)
- burst_W(t) = Σ liquidated BTC of fills with exchange time in (t − W, t],
  W ∈ {15 s, 30 s, 60 s}. Evaluated at each fill time t.
- Threshold_W(t) = 95th percentile of burst_W over all fills in the trailing
  7 days before t (primary). Robustness: 97.5th percentile only.
  No scoring until 7 days of feed exist.
- Detection = first fill with burst_W ≥ threshold_W. Direction = the larger
  forced side within the window (long liquidations = forced selling → BUY).
- Cooldown (frozen): after a detection, no new detection for 300 s. A
  detection inside the cooldown does not restart it.

## Entry / exit / costs
- Entry delays: 0, 5, 10, 20, 30, 60 s after the detection fill's exchange
  time; fill at the first Exness tick at or after that time, ask for buys,
  bid for sells, plus $5 slippage per round trip.
- Exits: 30 s, 60 s, 120 s, 300 s after entry, at the first tick at or after,
  bid for buys / ask for sells.
- MFE / MAE over 300 s from the entry tick.

## Controls
- Matched random timestamps (1000 draws): same number of events, same
  hour-of-day, non-event times (excluding 10 min after any detection),
  direction inherited; same delay/horizon/costs.
- Price-only control: |Exness mid move over the previous W s| ≥ its trailing
  7-day 95th percentile (sampled every second), reversal against the move,
  same cooldown, same delays/horizons. Split into "with a liquidation burst
  within the previous W s" and "without".

## Reporting (fixed)
Per W, per delay, per horizon: n, mean net points, wr, and z vs random;
sell-cascade and buy-cascade separately; size tertiles of the burst
(descriptive); halves (before / after 2026-08-21); event frequency
(events/day, days with none, p90, longest gap).

## Graduation rule (frozen)
ONE candidate graduates iff, at W chosen as the window with the highest
mean net at 20 s delay and 60 s horizon (3 windows, one pick, stated):
mean net > 0 at 20 s delay for horizons 60 s and 120 s, above the 99.5th
random percentile at both, both halves > 0, not dependent on the top-2
events (still > 0 with them removed), price-only control not positive.
The graduated rule is committed with its exact parameters and the
forward-validation start time; no retuning afterwards.
Otherwise: B (mechanism confirmed under real-time detection but not at a
realistic delay) or C (not reproduced under real-time detection).

## Not allowed
Additional windows, percentiles, cooldowns, delays or horizons after
seeing results; production changes; touching V4.
