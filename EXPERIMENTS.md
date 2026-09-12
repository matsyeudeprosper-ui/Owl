# Experiment registry

Workflow since 2026-09-11 evening: ChatGPT proposes and reviews, Claude
Code implements, runs, commits and reports (including failures), and
challenges flawed methodology. Production changes only on the owner's
explicit approval after both have reviewed the evidence.

Every experiment gets a row BEFORE it is run. Data eras are defined in
`DATA_ERAS.md`. "Params" = number of distinct choices/thresholds tried.

| ID | Proposed (UTC) | Hypothesis | Discovery data | Validation data | Params | Result | Status | Production changed |
|---|---|---|---|---|---|---|---|---|
| E000 | 2026-09-08 → 09-10 | Pre-registry work on the M1 replica (SL at visible dot, trail, breakeven, skip flips, pullback-limit flips, whipsaw, rising dots, ER/ADX regime gates, pause-after-loss, multi-slot, inversion, pullback entries, CHoCH entry). See `README.md` graveyard and `study/bt_*.py`. | R0 | R0 halves | many | all rejected | rejected | no |
| E001 | 2026-09-11 13:00 | Continuation TOUCH backtest has same-minute optimistic bias; strategy edge under tick execution | R0 | R0 halves, V1 | modes 4, poll 6, slip grid 20, min_dist 4 | touch +208 → +136 on ticks, alone ≈ 0; live config +206 (98.8th pct of 1000 tick controls); V1 −33 | B-with-warning (`study/audit/AUDIT.md`) | no |
| E002 | 2026-09-11 15:30 | Remove touch: flip-only vs candle-close continuation | R0 | R0 halves, V1 | 2 variants | flip-only +50 (80th pct); candle-close +237 (99.3rd), V1 −26 | candle-close ACCEPTED by owner | **yes** 17:26 UTC (touch → candle close) |
| E003 | 2026-09-11 22:00 | Candle-close entry with the touch rule's nearer TP | R0 | R0 halves, V1 | 1 | +166 vs +237; +120 vs +199 with slippage | rejected | no |
| E004 | 2026-09-11 22:30 | Higher win rate helps the war-chest recovery | R0 | R0 halves, V1 | 3 configs × 3 layers | full system: live +389, nearer-TP +245, old touch +348 | rejected | no |
| E005 | 2026-09-11 23:00 | A pre-entry "CLEAN" gate (break quality, ordinal, structure efficiency, risk geometry) + shadow breaker | R0-TRAIN | R0-TEST, V1 | 16 rules + 4 breakers | all reversed/neutral; stop ≤ 98 pt weak survivor (+15/+11/+4, p ≈ 0.1); rolling-20 breaker neutral on TEST, saves 9 of 26 on V1, V1 loss inside train p5 tail | rejected as gate; 2 forward-watch variables | no |
| E006 | 2026-09-12 00:30 | (infrastructure) Forward-observation ledger: narrow_stop flag + rolling-20 shadow state per L2/T2 trade, informational | – | L2, T2 accumulate | 0 | `live/bos_forward_observer.py` running | active | no |
| E007 | 2026-09-12 05:10 | WHY does the AWAKE gate work: is the 2h flip-recency effect real, broad and structural, or a fitted threshold? Tests: time-since-flip buckets, predeclared windows {30,60,120,240,none}, placebo flip timelines (fixed shifts ±6/±12/+24h + 1000 circular shifts), descriptive eligible-vs-not comparison, component dependence (combined / flip-only / cont-only) | R0-TRAIN | R0-TEST (blind); V1 reported as historical only | windows 5, fixed shifts 5, 3 nulls × 1000 draws, 0 thresholds selected | B: gate only affects continuations; young-trend conts positive both halves, ≥4h stale conts negative both halves, 2–4h flips sign; 2h adds +90 in TRAIN and −0.6 in TEST (4h +57/+46); real gate 97–99th pct of nulls in TRAIN, 84–94th in TEST; gate = trend age → dot distance (stops 1.7× wider when stale) | B fragile/threshold-sensitive; keep gate, 2h not special (`study/e007/E007.md`) | no |
| E008 | pending | next hypothesis from ChatGPT | to be declared | to be declared | | | | |

Rules of the registry:
1. Row first, run second. Declare discovery and validation data in the row.
2. A rejected idea is not re-run with new thresholds; a new row needs a new economic reason.
3. Forward eras (L2, T2, F) are validation only until ChatGPT opens them.
4. Every result, including failures, is committed with scripts and raw outputs.
