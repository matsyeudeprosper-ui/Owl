# E017 preregistration — forward test of the forced-SELLING snap-back (frozen 2026-09-12, before any forward outcome was read)

Narrow follow-up to E015/E016. Not a reopening of the liquidation search.
Forced-selling and forced-buying events are never merged.

## Hypothesis
After a large forced-selling liquidation burst on BTC-USDT-SWAP, Exness
BTCUSD has a short-lived buy-side snap-back that is tradable after realistic
costs, even though the combined (both-side) E016 rule failed. Motivation:
the asymmetry appeared in E015 (all horizons) and again in E016's post-hoc
forced-selling subset (23 events, 120–300 s cells positive) — twice
observed, never validated.

## Forward validation stream (blind)
Everything received by `live/liq_shadow.py` from **2026-09-12 13:07:04 UTC**
onward (`liq_shadow_fills.csv`, `liq_shadow_events.csv`). Nothing before it
is scored. No forward outcome is used to choose anything below.

## Frozen rule (identical to the E016 shadow configuration, no retuning)
- source: OKX v5 websocket `liquidation-orders`, BTC-USDT-SWAP, sz × 0.01 BTC
- burst: rolling 60 s liquidated BTC evaluated at every fill (exchange time)
- threshold: 95th percentile of the fill-sampled burst over the trailing
  7 days (seeded from the REST archive at observer start, then live)
- detection: first fill at which burst ≥ threshold; no waiting for the
  episode to end; cooldown 300 s (a detection inside it does not restart it)
- forced side = larger side inside the 60 s window; **PRIMARY = forced
  SELLING (long liquidations) → BUY**
- entry: **+20 s after the detection fill's exchange time**, at the ask
  (+10 s and +30 s reported descriptively, never selected)
- exit: **300 s after entry**, at the bid (120 s reported descriptively)
- costs: actual Exness Pro bid/ask (spread inside the quotes) + $5 per
  round trip slippage/drag (the E001/E016 convention); no zero-cost headline

## What is logged per detection (shadow, no orders)
exchange ts, receive ts, detection ts, feed latency, detection latency,
threshold, burst size, Exness bid/ask at detection, spread at detection,
quote age at detection, theoretical +20 s entry (price, delay, spread,
quote age), net at 5/10/30/60/120/300 s, MFE, MAE.

## Scoring (`e017_forward.py`, frozen; run only for reports)
Two outcome sources, both reported: (i) the observer's live quotes
(primary, what a bot would have seen); (ii) a tick replay from the MT5
tick history at exchange time + delay (cross-check, gives +10/+30 s and the
controls on identical ticks).
Controls on the same forward period:
- A. matched random timestamps, same hour-of-day, same n, excluding 10 min
  after any detection, BUY, 1000 draws → percentile of the real mean
- B. large 60 s BTC DOWN-moves (|mid move| ≥ trailing-7-day p95 of 60 s
  moves, 1 s grid, threshold refreshed every 5 min, 300 s cooldown) without
  a forced-selling detection in the previous 60 s → BUY, same delay/exit
- C. forced-BUYING detections → SELL, descriptive only (asymmetry check)
Descriptive: burst-size tertiles (no filtering), halves by event count.

## Sample discipline
No verdict before 30 forward forced-selling events (early read); 50+
before any production discussion. The threshold is never weakened to
create events. Expected rate ≈ 0.5/day (E016: 23 in 42 days).

## Pass criteria (primary cell: forced selling, +20 s, 300 s exit)
mean net points > 0 after costs; win rate > 50%; not dominated by the
top 1–2 events (still > 0 without them); both chronological halves > 0
(once n ≥ 30); above the 95th percentile of control A (99th preferred at
larger n); still > 0 with the top 10% largest-|P&L| events removed;
max drawdown economically acceptable relative to the average gain
(reported, judged by the owner).

## Economic read (descriptive)
events/day, mean net points, net $ at 0.01 / 0.02 / 0.05 lot ($1 per point
per 1.00 lot), max DD, longest losing streak, expected trades/month,
illustrative monthly P&L at the observed rate. No lot scaling to flatter.

## Harvest model (only after ≥ 30 events, descriptive)
$500 start, fixed 0.02 lot, withdraw $100 whenever equity ≥ post-withdrawal
baseline + $100, stop at net-from-start ≤ −$60 (the live kill rule).
Report withdrawals, ending equity, withdrawn vs starting capital, max
capital at risk.

## Not allowed
Retuning W / percentile / cooldown / delay / exit; size filters (a strong
size relation becomes a separate preregistered experiment); merging the
two sides; BOS/structure inside E017; live orders; production changes.

## Verdict
A — forward forced-selling snap-back confirms and is potentially tradable.
B — positive clue but sample too small / unstable / marginal after costs.
C — the historical asymmetry fails forward.
