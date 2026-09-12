# Regime research pass (2026-09-11 evening): can a "CLEAN" gate complement the AWAKE gate?

Question from the account owner: using only information available before
entry, can Owl tell a statistically hostile (choppy) regime from a clean
one, without fitting the current 3-day out-of-sample loss? Production was
not touched.

## Setup (frozen before any result was looked at)

- Baseline = the live rule set: flip-BOS + continuation on candle close,
  awake gate 2h, SL at the pending dot, TP 0.8R, one position, **flat 0.02,
  no war-chest / fighters / adds**, tick execution (`../audit/exec_audit.py`,
  poll 1 s, min_dist 10).
- TRAIN = in-sample trades before the midpoint 2026-08-04 21:53 (259
  trades, +$102). TEST = after it to 2026-09-08 07:11 (265 trades, +$135).
  OOS = untouched 2026-09-08 07:12 → 09-11 (47 trades, −$26).
- Bucket cuts = train quartiles. One preregistered rule per feature:
  "block the 25% bucket on the bad side" (bad side stated before looking:
  weak break, low efficiency, high disturbance; for risk geometry the tail
  that is negative in train). Blocked-trade accounting is list-based; the
  one survivor was re-simulated inside the engine.
- Choices tried: 16 bucket rules + 4 breaker candidates = 20. With 20
  tests at this sample size, one or two "survivors" by luck are expected.

Files: `regime_features.py` (features), `trades_insample.csv`,
`trades_oos.csv` (one row per trade, every feature), `regime_buckets.py`
→ `results_buckets.txt` (sections 1-4, full tables), `regime_stopdist_resim.py`
→ `results_stopdist_resim.txt`, `regime_breaker.py` → `results_breaker.txt`.

## 1. BOS break quality — hypothesis REVERSED

| overshoot / stop (train cuts 0.058 / 0.240) | TRAIN | TEST | OOS |
|---|---|---|---|
| weakest 25% (tiny close beyond structure) | n 65, wr 72%, **+$96** | n 70, wr 61%, **+$74** | n 11, wr 36%, −$28 |
| middle 50% | +$4 | +$50 | −$14 |
| strongest 25% (big overshoot) | n 65, wr 46%, +$2 | n 75, wr 55%, +$11 | n 6, +$16 |

The tiny breaks are the BEST trades in both halves, not the worst. Same
picture for raw overshoot, body/range and close location (blocking the
weakest quartile costs $70–$100 per half). "Tiny close with a huge stop
behind it" (weakest overshoot × widest stop): train +$70 on 21, test +$45
on 29, OOS −$26 on 3. The 3-day loss sits exactly on the trades that were
the strategy's best for 69 days. No rule.

## 2. Trade ordinal after the last flip — no stable pattern

| ordinal | TRAIN | TEST | OOS |
|---|---|---|---|
| 1st (the flip) | n 147, wr 58%, +$44, PF 1.19 | n 156, wr 55%, +$40, PF 1.14 | n 27, wr 63%, +$4 |
| 2nd | n 41, wr 63%, +$43, PF 1.80 | n 54, wr 63%, +$33, PF 1.29 | n 10, +$2 |
| 3rd | n 35, wr 69%, +$41, PF 2.03 | n 27, wr 81%, +$52, PF 3.36 | n 5, wr 0%, −$22 |
| 4th+ | n 36, wr 44%, −$25, PF 0.65 | n 28, wr 50%, +$10, PF 1.23 | n 5, −$9 |

The 2nd and 3rd trades of a trend are the best in both halves; the flip
trade is the weakest but positive; 4th+ flips sign between halves. The OOS
loss is concentrated in continuations (−$30 on 20) while flips held (+$4).
Nothing here is stable enough for a rule and none was preregistered.

## 3. Structure efficiency — REVERSED or neutral

- `se_flip` (net progress / total M1 travel since the last flip,
  continuations only; train cuts 0.14 / 0.29): lowest quartile train +$21
  (wr 57%), TEST **+$84 (wr 76%)**, OOS −$3. Low efficiency is the best
  bucket in test. Blocking it: test +$51 vs +$135.
- `se_60` (same over the last 60 bars, all entries): blocking the lowest
  quartile: train +$78 vs +$102, test +$122 vs +$135, OOS **−$42 vs −$26**.
  Worse everywhere.
- `disturb_2h` (CHoCHs + repairs in the last 2 h; block ≥ 2): train kept
  +$67 vs +$102, test kept +$114 vs +$135, OOS kept **+$12 vs −$26**. This
  is the rule that "fixes" the OOS, and it costs $35 + $21 in the two
  halves where the blocked trades were profitable. It is the 3 days
  talking, not a regime. Rejected by the methodology.
- `prog_per_disturb`: lowest quartile is the best bucket in both halves
  (+$44, +$86). Reversed.

Chop, measured Owl's own way, is where the strategy has been making its
money. The awake gate already selects for "structure recently moved";
asking additionally for clean directional progress removes the good
trades.

## 4. Risk geometry — one small survivor

`stop_atr`, `stop_range60`, `stop_med60`: no negative tail in train, so no
rule (the narrow tail is negative in test for two of them, but that was
not preregistered).

`stop_dist` absolute (train q25 = 98 pts): the narrowest quartile is
negative in all three periods.

| block stops ≤ 98 pts (in-engine re-simulation, ticks) | TRAIN | TEST | OOS | FULL 69d |
|---|---|---|---|---|
| baseline | n 259, +$102, PF 1.26, wr 58% | n 265, +$135, PF 1.30, wr 59% | n 47, −$26 | n 524, +$237 |
| rule | n 194, **+$117**, PF 1.34, wr 62% | n 198, **+$146**, PF 1.36, wr 62% | n 40, −$22 | n 392, **+$263** |
| blocked set (list-based) | n 65, −$15, wr 48% | n 69, −$11, wr 49% | n 7, −$4 | |
| permutation: P(random same-size subset ≤ blocked) | 0.081 | 0.115 | | |

Honest reading: consistent sign in three periods, +$15 / +$11 / +$4, but
each half alone is p ≈ 0.1 against random removal, the mechanism check is
not monotone (0–60 pt stops are flat, 60–98 are the bad band, 150–250 are
mixed in train), and it is 1 of 16 rules. It is a candidate for a forward
watch, not a proven gate. It is also not a "market clean" gate: it says
"do not take stops narrower than ~100 points", which is a cost-geometry
statement (a $7 spread is 7–12% of such a stop).

## 5. Shadow circuit breaker — the OOS loss is inside the normal distribution

Thresholds from a bootstrap of TRAIN trades (100 000 draws): for N = 20
the 5th / 10th / 50th percentiles of a 20-trade sum are −$22.5 / −$15.7 /
+$8.1. States: REDUCED (half size) below p10, PAUSED below p5, NORMAL
again at the median. Shadow keeps trading; real size follows the state
computed from trades strictly before each trade.

| window | TEST shadow → real | TEST cost (paused P&L not taken / reduced) | OOS shadow → real | OOS transitions |
|---|---|---|---|---|
| N = 20 | +$134.6 → +$133.4 | 21 paused (+$5.7 missed), 65 reduced (−$4.5 saved) | −$25.6 → **−$16.6** | REDUCED 09-09 16:03, PAUSED 09-09 21:05, back to REDUCED 09-11 08:08 |
| N = 30 | +$134.6 → +$122.6 | 26 paused (+$16.5 missed) | −$25.6 → −$26.5 | PAUSED 09-10 03:04 |
| N = 40 | +$134.6 → +$106.7 | 37 paused (+$15.5 missed) | −$25.6 → −$34.1 | PAUSED 09-10 16:17 |
| CUSUM (k = μ/2, h = p99) | +$134.6 → +$110.0 | 51 reduced (+$24.7 missed) | never triggers | – |

Only N = 20 is neutral on the blind test half and it saves $9 of the $26
OOS loss, triggering after two thirds of it had already happened. The
underlying fact: the strategy's own 20-trade sums have a 5th percentile of
−$22.5. A −$26 stretch over 47 trades is not statistically inconsistent
with the strategy; it is what its normal distribution produces roughly one
window in twenty. A breaker cannot separate what the distribution does not
separate. False-positive cost of the longer windows in the profitable test
half: $12–$28 of the $135.

## Verdict

**No "CLEAN" gate survives blind testing.** Every progress/efficiency
definition points the wrong way: the tiny breaks and the low-efficiency
stretches are where the 69-day profit came from, and the OOS lost money on
exactly those trades. The only rule that "repairs" the 3 days (block ≥ 2
disturbances in 2 h) is negative in both research halves, which is the
signature of fitting the OOS. The one geometry survivor (skip stops under
~100 points) is small, p ≈ 0.1 per half, and is a cost rule rather than a
regime rule; worth watching forward, not worth deploying on this evidence.
The circuit breaker shows the deeper point: a −$26 / 47-trade stretch is
inside the strategy's own 5–10% tail, so no honest monitor flags it early.

AWAKE stays the only gate. Production unchanged.
