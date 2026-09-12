# E015 preregistration — BTC response after forced-liquidation bursts (frozen 2026-09-12 12:00 UTC, before any outcome was examined)

Inherits the project's 2026-08-01 preregistration (`PREREGISTRATION_liquidations.md`
in KinoliveLines, H4a/H4b/H4c). Amendments below are forced by the data span
and by the owner's horizon request; they are recorded here before results.

## Data
- Events: `recorder/data/liquidations_BTC.csv` — OKX BTC-USDT-SWAP forced
  liquidations, one row per fill (ts_ms, side, posSide, sz contracts, bkPx),
  2026-07-31 23:58 → 2026-09-12 07:09 UTC (74 695 rows). `posSide=long` =
  forced selling, `posSide=short` = forced buying. Size in BTC = sz × 0.01.
- Context (optional, descriptive only): `derivs_BTC.csv` 5-min open interest,
  taker buy/sell volume.
- Price: Exness Pro BTCUSD bid M1 from the public archive (Jul–Sep 2026) —
  the instrument we would trade — with the per-bar spread ($7.00).
- Overlap window: 2026-07-31 23:58 → 2026-09-11 23:59 (42 days).

## Frozen definitions
- Bucket: 5-minute UTC bucket; total = Σ sz×0.01 (BTC) of all fills; net
  direction = sign(short-liq BTC − long-liq BTC) (forced buying minus forced
  selling); direction of the cascade = sign of the larger side.
- **Large event ("cascade")**: bucket total ≥ 95th percentile of the trailing
  **7-day** distribution of non-empty buckets (AMENDMENT: the original said
  30-day; with a 43-day feed a 30-day trailing window leaves ~13 scorable days.
  The 30-day version is reported as well on the days it can score). Buckets
  are scored only when the trailing window is complete. Consecutive large
  buckets are one episode; the entry uses the LAST large bucket of the episode
  (no entry inside a cascade).
- Entry: the first M1 close after the episode's last bucket ends. Direction
  of the test trade: CONTINUATION = with the cascade (forced selling → sell),
  REVERSAL = against it. Both evaluated on every event, symmetric.
- Horizons: 1, 5, 15, 30, 60 minutes (close-to-close), plus MFE/MAE over
  60 min and first passage of ±1 ATR14(M1) within 60 min.
- Costs: $7 spread (entry on the ask for buys, exit on the ask for sells)
  + $5 round-trip slippage, i.e. $12 per round trip at 1 lot = 12 points.
- Sizing for dollar figures: 0.02 lot (net = points × 0.02).
- Splits: cascade direction (forced selling vs forced buying); size tertiles
  of the cascade within the large set (descriptive only).

## Controls (mandatory)
- 1 000 draws of matched random timestamps: for each event, a random
  non-event 5-min bucket with the same hour-of-day, drawn from the overlap
  window, excluding event buckets and the 60 minutes after any event.
  Same entry rule, same horizons, same costs.
- Reported per horizon and direction: real mean net points, random mean, sd,
  p95, max, percentile, z.

## Pass rule (frozen)
- A: the better of CONTINUATION / REVERSAL has mean net move after costs
  > 0 AND above the 99.5th percentile of the matched random distribution at
  a predeclared horizon (10 tests: 2 directions × 5 horizons → 0.5% each),
  AND the same direction holds in both halves of the window (first 21 days
  / last 21 days), AND a fixed-lot sequence of those trades is harvestable in
  the $500 / +$100 / −$60 model.
- B: mean move beats random at the 95th percentile but fails costs or a half.
- C: otherwise.
Only if A: test whether Owl structure (pending-dot stop, BOS timing)
improves execution — structure as a tool, never as the signal.

## Not allowed
No threshold or horizon search after results; no re-ranking against the
full sample; V4 untouched; production unchanged.
