# Execution audit of the BOS strategy (2026-09-11)

Requested by the account owner after a ChatGPT review. Question: does the
continuation TOUCH backtest ignore same-minute stop-outs, and does the
strategy keep its edge under realistic execution? Nothing in the live bot
was changed for this audit.

All scripts and raw outputs are in this folder; the data they use is in
`../data/` (`pro_m1.npz` = the 69-day research M1 set, `ticks_btcusd.npz`
= 8.0M Exness Pro BTCUSD ticks 2026-07-01 → 09-11, `m1_trial9_all.npz` =
M1 2026-07-04 → 09-11 from the demo Pro terminal, includes the untouched
tail). The original evidence scripts that were missing from the repo are
preserved in `../original/` (`bt_touch.py`, `bt_chop*.py`, `bt_add.py`,
`bt_full.py`, …), unchanged except for the data path.

## Headline numbers (0.02 lot, spread $7, 69 days in-sample)

| | Net 69d | Trades | Win rate | Note |
|---|---|---|---|---|
| CURRENT reported TOUCH result (touch part of the +255 replica) | **+$208** | 296 | | `bt_invert.py` style replica, no entry-bar check |
| Original touch evidence (`bt_touch.py`, entry bar checked SL-first) | +$216 (total +$263) | 296 | | the +263 that was deployed on |
| CORRECTED tick-aware TOUCH result (1 s poll, real ticks) | **+$136** | 283 | | −35% vs reported; ±$40 depending on poll phase |
| TOUCH with observed live slippage (2.5 pt entry + 2.5 pt SL) | +$123 | 280 | | |
| FLIP-BOS corrected (tick) | **+$70** (M1: +$47) | 326 | | flips are not hurt by ticks |
| AWAKE + corrected execution (= live config, tick, min_dist 10) | **+$206** | 609 | 56.8% | PF 1.22, maxDD $61, exp +$0.34/trade |
| same + observed slippage (2.5 / 2.5) | +$161 | 606 | 55.3% | PF 1.17 |
| Random-direction controls, 1000 seeds | see below | | | |
| OUT-OF-SAMPLE (2026-09-08 07:12 → 09-11 13:39, never used in research), tick, live config | **−$33** | 52 | 50.0% | touch −$37 on 25, flip +$4 on 27 |

## 1. Is there a same-minute bias in the touch backtest?

Yes in the replica scripts, no in the original evidence, and it is small
on M1 either way.

- `bt_touch.py` (the script that produced the deployed +263) DOES check
  the entry bar: after a touch it tests `low <= SL` first (loss), then
  `high >= TP` (win), else the position carries over. Pessimistic.
- Every later replica (`bt_invert.py`, `bt_multi.py`, `bt_pbentry*.py`,
  `bt_choch.py`, i.e. the "+255 baseline") opens the touch position and
  starts SL/TP evaluation at the NEXT bar. That is the bias the review
  suspected. `exec_audit.py` reproduces both exactly:
  legacy +255.12 / 622 trades, pessimistic +263.14 / 622.
- Size of the bias on M1: pessimistic is $8 HIGHER than legacy, because
  38 touch trades resolve inside their entry bar (24 wins, 14 losses) and
  the pessimistic rule books them immediately. "Optimistic" (TP first,
  ties = TP) gives the same +263.14: in this strategy only 1 of 622 exits
  happens on a bar that also contains the other level (stops are ~170 pt
  wide, M1 ranges rarely cover 1.8× that). So on M1 there is no
  optimistic/pessimistic gap to speak of.
- The REAL gap only shows on ticks (section 3).

## 2. Flip-BOS

Enters on the bar close, evaluated from the next bar. That is what
production does (it acts 0.2 s after the minute boundary). On ticks the
flip part is +$70 vs +$47 on M1: no optimistic bias in the flip entries.

## 3. Corrected execution test (`exec_audit.py`, mode `tick`)

Assumptions, stated explicitly:
- Structure engine steps on closed M1 bars (as production).
- Touch: first tick whose bid crosses the level while flat and the level
  is unused; the bot polls about once per second, so the fill is the
  ask/bid of the first tick ≥ `poll_delay` later. Sensitivity run at 0,
  0.5, 1, 2, 3, 5 s.
- SL: filled at the first tick through it, at that tick's price (real
  gaps count against us). TP: filled at the TP price.
- Flip-BOS: filled at the first tick after bar close + poll delay.
- Min-distance check on the actual ask (production `S_MIN_DIST`).
- One position at a time enforced on tick time.
- Spread is the real per-tick spread (constant $7.00 on all 8.0M ticks).

Results (live config, min_dist 10):

| poll delay | net | touch part | flip part |
|---|---|---|---|
| 0 ms | +$201 | +$163 | +$39 |
| 500 ms | +$169 | +$100 | +$69 |
| 1000 ms | +$206 | +$136 | +$70 |
| 2000 ms | +$217 | +$132 | +$84 |
| 3000 ms | +$166 | +$120 | +$47 |
| 5000 ms | +$139 | +$50 | +$89 |

Reading: a 1-second change in when the bot happens to look moves the
result by $30–40. That is the noise floor of this signal on this sample.

## 4. Entry types, gate, halves (tick, 1 s poll)

See `results/main.txt` section 1 for the full table (legacy / pess / opt
/ tick × flip-only / touch-only / both / both+gate × full / h1 / h2).

## 5. Costs

- Spread: $7.00 flat across the whole window (tick data), so the research
  assumption was right. M1 stress at $10 / $14 / $20: `results/main.txt`
  section 6.
- Live execution measured from MT5 deals (`results/bos/trades_live_canonical.csv`):
  entry slippage median 0, mean +2.5 pt (one 155-pt outlier on
  2026-09-11 12:29, a touch in a burst with 200-pt deviation allowed);
  SL slippage mean −2.3 pt, worst −12 pt; order latency median 2 s.
- Stress grid on ticks (`results/main.txt` section 5): with 2.5 / 2.5 the
  in-sample net is +$161; 5 / 5 → +$103; 10 / 0 → +$87. Every cell stays
  positive in-sample, PF falls from 1.22 to 1.07 at 5 / 10.

## 6. `S_MIN_DIST` 10 vs research 7

Zero effect. min_dist 7, 10, 15 give identical trade lists; at 20 two
trades drop. Stop distances are almost never that small.

## 7. Awake-gate evidence

`../original/bt_chop.py` … `bt_chop4.py` are the scripts (2026-09-08).
`bt_chop4.py` reproduces +206.85 / 520 trades for the gated close-entry
config (the "+207" in the bot's comments). The gate is what carries the
strategy in every execution mode: without it the tick result is in
`results/main.txt` section 1 ("FLIP+TOUCH, NO gate").

## 8. Random controls (1000 seeds, direction coin-flipped per trade,
full re-simulation with the one-position rule)

M1 pessimistic execution (`results/rand_m1.txt`):

| config | real | random mean | sd | p95 | beats controls | z |
|---|---|---|---|---|---|---|
| flip only, gated | +$31 | −$27 | 80 | +$111 | 77.0% | +0.72 |
| touch only, gated | +$109 | −$63 | 70 | +$51 | 99.4% | +2.44 |
| both, no gate | +$158 | −$72 | 134 | +$150 | 95.2% | +1.71 |
| both + gate (live) | +$263 | −$48 | 98 | +$116 | 99.9% | +3.17 |

Tick execution (`results/rand_tick.txt`): RUNNING at the time of this
commit (1000 seeds × 4 configs, ~4 s per seed). Interim after 400 seeds
for the live config: random mean −$46; the real tick result is +$206.
This file will be updated when the run completes.

## 9. Out-of-sample and the live window

Untouched period: bars after 2026-09-08 07:12 (the research set ended
there; the touch/gate/add decisions were all taken on data before it).

| config (tick) | n | wr | net | touch | flip |
|---|---|---|---|---|---|
| flip only, gated | 28 | 64% | +$7 | | +$7 |
| touch only, gated | 38 | 42% | −$30 | −$30 | |
| both, no gate | 59 | 47% | −$47 | −$52 | +$4 |
| both + gate (live) | 52 | 50% | −$33 | −$37 | +$4 |

Live window (2026-09-08 19:30 → 09-11 13:39), tick backtest vs the real
account (`align_live.py`, `results/align_live.txt`): 37 of the 39 real
base trades have a backtest twin within 3 minutes, 36/37 same entry kind,
35/37 same outcome. Live −$45.5 vs backtest −$30.2 on the matched pairs;
the $15 gap is three trades (the 155-pt entry slip, and two flips where
the tick path went to TP in the sim but to SL live). So: the replica is
the bot, and the live loss is what this rule set does in this regime,
plus about $0.40/trade of execution drag.

Anchor noise: the same rules on the second M1 source (series starting
2026-07-04 instead of 07-01) give +$251 vs +$234 over the overlap, a ±$17
floor.

## 10. Verdict

INTERIM (tick controls still running). What is already established:

1. The same-minute bias exists in the replica scripts but is worth ~$0
   on M1. The real optimistic bias is at TICK level: the reported touch
   part (+$208 to +$216) is +$136 on ticks at a 1 s poll, and it swings
   between +$50 and +$163 depending on the poll phase. Touch ALONE on
   ticks is +$7 to +$73 (PF 1.01-1.12), second half negative in 4 of 5
   poll settings.
2. Flip-BOS has no execution bias (+$47 M1 → +$70 tick) but alone it is
   not distinguishable from random (77th percentile).
3. The live config on ticks is +$161 to +$217 in-sample (PF 1.17-1.23)
   and beats 99.9% of M1 random controls. Most of that profit comes from
   the INTERACTION of the two entry types under the one-position rule
   (parts alone: ~+$50 and ~+$8; together +$206), which is the kind of
   structure that does not travel well.
4. Out-of-sample (3.3 days, 52 trades, never used in research): −$33,
   touch −$37, flip +$4. The tick replica reproduces the real account
   trade for trade (37/39 matched, 35/37 same outcome), so the live
   drawdown is the strategy in this regime, plus ~$0.40/trade execution
   drag, not a bot defect.

Provisional reading: B leaning C — the touch backtest WAS optimistic
(tick execution removes roughly a third of its in-sample profit and all
of its stand-alone edge); the remaining gated flip+touch system keeps a
statistically real in-sample edge but a thin one (+$0.27 to +$0.34 per
trade at 0.02 lots, i.e. under $3/day) that the first untouched 3 days
did not confirm. Final call after the tick controls.

## Files

- `exec_audit.py` – engine (signal logic frozen; execution modes legacy / pess / opt / tick; random control).
- `audit_run.py` – the matrix; sections main, rand_m1, rand_tick, oos.
- `align_live.py` – backtest-vs-real trade alignment.
- `results/main.txt`, `results/rand_m1.txt`, `results/rand_tick.txt`, `results/oos.txt`, `results/align_live.txt`, `results/rand_*.npy` (the control distributions), `results/trades_tick_live_config.csv` (per-trade list of the tick run), `results/trades_tick_live_window.csv`.
- `../../results/bos/trades_live_canonical.csv` – the real account's trades from MT5 deals (position_id join), with entry type from the log, entry/exit slippage, order latency. `deals_223995441_raw.csv` is the raw deal pull, `canonical_trades.py` builds the table.
