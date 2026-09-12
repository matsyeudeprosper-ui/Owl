# Owl — BTCUSD structure bots, code + full results

Snapshot exported 2026-09-11 from the private working tree of the
KinoliveLines project. Purpose: let a second analyst (ChatGPT) study the
strategy, the backtests and the live record. Everything here is the real
code that runs, the real logs, and the real backtest scripts. MT5 passwords
are redacted; nothing else was edited.

Broker: Exness Pro accounts, symbol BTCUSD, fixed spread about $7 per BTC
(so every trade pays ~$0.14 at 0.02 lot). One BTC point = $1 per 1.0 lot.

**2026-09-11 decision:** continuation entries moved from touch to candle
close, see `DECISION_2026-09-11.md`; full audit in `study/audit/AUDIT.md`; regime/"clean gate" research pass in `study/regime/REGIME.md` (no gate survives).

## Research workflow (from 2026-09-12)

ChatGPT leads the research (reviews evidence, proposes the next hypothesis
and its methodology, reviews results). Claude Code executes (implements,
runs with tick execution and controls, reports every result including
failures, commits scripts + raw outputs). Production is frozen; it changes
only on the owner's explicit approval. Registry: `EXPERIMENTS.md`. Data
eras and what is still untouched: `DATA_ERAS.md`. Forward evidence of the
frozen config and its paper twin: `results/bos/bos_forward_ledger.csv`
(refreshed on each snapshot push; the live file is `live/bos_forward_ledger.csv`).

## What is live right now

| Bot | Account | Type | Since | Status |
|---|---|---|---|---|
| `structure_bos_bot.py` (live variant) | 223995441 REAL | BOS structure bot | 2026-09-08 | 38 trades, bot net −$36.59, kill line −$60, review at 100 trades |
| `structure_bos_bot.py sniper` | 476989735 demo | only the 2nd trade of each trend, flat 0.06 | 2026-09-09 | parallel lab |
| `structure_bos_bot.py halfdebt` | 476989740 demo | full config, 0.5× debt per loss | 2026-09-09 | parallel lab |
| `harvest_fresh_h1_bot.py` (BTC + ETH) | 476954287 demo | Renko H1 fresh-reversal + early-cycle harvest | 2026-09-08 | no cycle yet |
| `owl_manual_bot.py` ("KINO") | 223985697 REAL | pullback/page bot | RETIRED 2026-09-08 | runs as scribe only, entries off |

## The BOS strategy (user's rules, as coded)

Chart engine (`bots/owl_chart_feed.py` = the same brain as the bot):
- Silence filter: an M1 candle counts only if it closes beyond the last
  shown candle's high or low. Silenced candles still move price (the bot
  trades on raw M1) but do not build structure.
- Swing dots are confirmed only by full closes beyond the running extreme,
  and only if the span in between contains at least one opposite-colour
  candle.
- Bootstrap: 2 consecutive higher lows (or lower highs) start a trend.
- CHoCH = close beyond the protected dot. The FIRST fresh BOS after a
  CHoCH flips the trend.

Entries (one trade at a time, base 0.02 lot):
- Flip-BOS: when a CHoCH is followed by a BOS in the new direction, enter
  on the close of that BOS candle.
- Continuation BOS: SINCE 2026-09-11 17:26 UTC entered on the candle CLOSE
  (the execution audit in `study/audit/` showed the touch variant had
  tick-level optimistic bias). Before that: "touch" = enter the moment price
  touches the reference high/low. The touch rule keeps running as a paper
  twin (`bots/bos_paper_touch.py`) for a side-by-side record.
- Awake gate: no entry unless there was at least one trend flip in the
  last 2 hours (backtest shows sleepy markets are the bleed).
- SL at the glowing dot (the last confirmed swing). TP = 0.8 × risk.
- 50% pullback add: if an open trade retraces 50% of its risk, up to 2
  extra 0.01 "bullets" join at the same SL/TP, paid for by the chest.

War-chest (money management):
- Losses go to a debt book. Wins pay debt first; overflow fills the
  chest (cap $5).
- "Fighters use available bullets": while debt exists, extra 0.01 lots
  ride only if the chest already covers their full risk at the current
  stop distance. Losing fighter share is paid by chest; base share → debt.
- Kill line: bot net (banked + floating) ≤ −$60 → bot stops itself.

## Evidence before deploy (69 days of M1, $7 spread, 0.02 lot, ties = SL)

Engine: `study/bt_bos.py` (base rules) and the per-idea scripts
`study/bt_*.py` that import it. Data: `study/data/pro_m1.npz`
(99 000 M1 bars, bid OHLC). Baseline of the live config
(`study/bt_invert.py` "normal" line) = **+$255, 622 trades, 58% win rate,
max drawdown $66, both halves positive (+86 / +167)**.

Stack built up in order, each step measured before deploy:

| Step | Net 69d | Note |
|---|---|---|
| Plain "every BOS, SL at dot, TP 0.8R" | +$56 | INSIDE the random-direction band (−92..+113), no edge alone |
| + awake gate (≥1 flip in 2h) | +$207 | five random controls all negative (−50..−177); walk-forward +116 blind |
| + touch entries for continuation | +$263 | both halves positive |
| + 50% pullback add | +$343 (+0.01) / +$422 (+0.02) | both halves green |

Rejected ideas (all measured, scripts in `study/`): SL at the visible dot,
trail to dots, breakeven at 50/70/85%, skip flip trades, flip entry on
pullback limit, whipsaw filter, rising-dots filter, Kaufman-ER/ADX regime
gates, pause-after-loss, 2–3 concurrent trades, full inversion, pullback
entries (30/50% retrace, dot SL or tight SL), CHoCH-as-entry
(`bt_choch.py`: +155 vs +255, CHoCH trades inside the random band).

Honest caveats:
- The M1 simulation cannot see fills, slippage or spread spikes. The live
  record (49% win rate after 38 trades vs 58% in backtest) is running
  below the backtest so far.
- ~44% of trades resolve inside a single M1 bar where SL and TP are both
  touched; the sim counts those as losses (pessimistic).
- Sample: 69 days, one instrument. Walk-forward halves were checked but
  there is no multi-year test.

## Live record

`results/bos/trades_live.csv` = every trade of the real bot, parsed from
`bos_bot.log` (open time, type, direction, entry/SL/TP, risk, result,
P&L, debt/chest/net after). Same for `trades_sniper.csv` and
`trades_halfdebt.csv`. The raw logs are next to them (CHoCH/flip events,
skipped signals, restarts). A few result lines are duplicated in the log
after restarts (the deal-history backfill re-logs them); the CSV keeps
them as-is. `bos_state*.json` = the bot's live state (debt, chest,
banked, seen deals). `nest_*.json` = the app's stats feed (balance,
equity, day/week/month P&L, equity curve).

Note: `owl_manual.log` and `owl_manual_journal.csv` (folder
`results/kino/`) are the RETIRED pullback bot's history, including its
failed 50-trade forward test (`owl_forward_test.json`). Useful as
a reference for what did not work on this symbol.

## Fresh-H1 harvest (demo)

`bots/harvest_fresh_h1_bot.py`, spec `specs/SPEC_FRESH_H1_LIVE.md`,
evidence `specs/SPEC_FRESH_EARLY_COMBO.md` + `study/results/fresh_early_combo*.txt`.
Renko-brick H1 reversal, entries only in a "fresh" big-brick reversal
window and the first 2 cycles of the day; 12.6 years of history, +1429 vs
random (2SE 162), zero wipeouts. Cap 3 adds. No live cycle has started yet.

## Layout

```
bots/       the five bot programs (passwords redacted)
infra/      nest manager/worker, master publisher + copier (family
            mirroring), push + telegram notifiers, web app server,
            boot/restart scripts
specs/      preregistered specs, findings, research map, handoff notes
study/      backtest engine (bt_bos.py), every bt_*.py idea test,
            owl_*.py studies of the retired bot, hedge_engine.py (Renko),
            data/pro_m1.npz, results/*.txt
results/    logs, parsed trade CSVs, state files, app stats feeds
```

Run a backtest: `cd study && python bt_choch.py` (needs numpy).

## Questions worth asking of this data

1. Is the live 49% win rate a normal draw from the 58% backtest, or is
   execution (spread at the dot, touch fills) worse than modelled?
2. Which entry type is losing live: flip-BOS or touch? (column
   `entry_type` in trades_live.csv)
3. Does the war-chest sizing help or hurt at this trade count?
4. Any structural leak in the engine (look-ahead, dot re-anchoring)?
