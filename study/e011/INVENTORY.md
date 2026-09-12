# E011 — Phase 1 inventory and Phase 4 overlap validation (2026-09-12)

No strategy P&L was computed on any period outside R0. Nothing frozen yet
beyond the strategy itself; the reserved eras are proposed at the end for
ChatGPT / the owner to confirm before download.

## Phase 1 — what exists

### A. Exness public tick archive (https://ticks.ex2archive.com/ticks/)

- Directory JSON index, 1 501 symbols. BTCUSD variants: `BTCUSD`
  (unsuffixed = the Pro symbol we trade), `BTCUSDm` (Standard),
  `BTCUSDc`, `BTCUSD_Raw_Spread`, `BTCUSD_Zero_Spread`,
  `BTCUSD_Standart_Plus`, plus BTCUSDT and cross pairs.
- `BTCUSD` years: **2017 → 2026**, monthly zips
  `ticks/BTCUSD/<YYYY>/<MM>/Exness_BTCUSD_<YYYY>_<MM>.zip` (~34–40 MB
  each in 2026) and yearly zips (2022: 455 MB, 2023: 414 MB, 2024: 374 MB,
  2025: 341 MB compressed). Current month is published daily.
- CSV inside: `"Exness","Symbol","Timestamp","Bid","Ask"`; timestamp
  ISO-8601 with millisecond precision and a `Z` suffix (UTC); bid and ask
  both present. Format unchanged across the three months read.
- Volume for 2026-07: 3.09 M rows, of which 3 914 exact duplicate rows
  (0.13%), 0 unparsable, 0 bad prices. 2026-08: 3.70 M / 11 107 dups.
  2026-09 (to the 11th): 1.29 M / 1 547 dups.

### B. Exness MT5 server (demo Pro terminal 476954287, same feed as live)

- Tick history (`copy_ticks_range`) starts **exactly 2026-01-01 00:00 UTC**
  and stops at nothing before that (Dec 2025 empty). Monthly volume
  1.75–3.93 M ticks, every calendar day present.
- Spread regimes visible in the MT5 ticks: Jan–Mar 2026 fixed $12.60
  (Feb max 18.90); Apr–May $9.80 (May p95 10.78); Jun $7.00 median (early
  June still 9.80/10.78); Jul–Sep $7.00 flat.
- M1 bars on this terminal: only ~2 months back (the July-4 start seen in
  E001). H1 and D1 bars back to 2018-12-29.

So the MT5 route alone gives 6 independent months (Jan–Jun 2026); the
public archive gives 9.5 years, all with bid/ask and the same symbol.

## Phase 3 — importer (`exness_import.py`)

Zip → sorted ticks (t ms UTC, bid, ask) with exact-duplicate rows and bad
prices dropped and counted → M1 from BID prices (open/high/low/close,
tick count, mean spread), no interpolation, missing minutes absent, gap
list (> 5 min) reported. SHA-256 of each source zip and download time go
into `<prefix>_import_report.txt`. Raw zips are kept separately
(`scratchpad/exness_archive/`, not in the repo).

## Phase 4 — overlap validation, 2026-07-01 → 2026-09-11 13:39 (results_overlap.txt)

Data:

| | MT5 ticks | archive |
|---|---|---|
| ticks in overlap | 7 996 961 | 7 988 774 (ratio 0.9990; per-day ratio median 0.9989, min 0.9958, max 1.0050, no day off by > 0.5%) |
| spread | 7.00 on 100.000% of ticks | 7.00 on 100.000% of ticks |
| M1 range median / mean, ATR14 mean | 30.59 / 40.07, 40.06 | 30.57 / 40.02, 40.01 |
| daily log-return sd | 0.0193 | 0.0193 |

Timestamps: only 0.35% of ticks share an exact millisecond stamp. For
the rest, the nearest MT5 tick is a median **70 ms** away (p95 81 ms,
99.9% within 1 s): the archive carries the same tick stream with a
constant ~70 ms clock offset (archive later). On the few exact-stamp
coincidences the prices differ because they are different ticks, so
tick-by-tick price equality cannot be measured directly; the tick counts,
spreads and volatility say it is the same stream.

M1 (bid OHLC) consequences of the 70 ms shift: against the MT5 M1 bars,
archive bars are identical in 33–39% of minutes, median absolute
difference $0.02, p99 $2.5 (high/low) to $6 (open), a handful of
boundary bars differ by $30–216. For reference, M1 built from the MT5
ticks themselves matches the MT5 M1 bars in ~90% of minutes (p99 $0.4–0.6):
the terminal's own bars are not tick-exact either. Minute coverage is
the same (28 vs 40 minutes present in only one of the two).

Frozen strategy on both feeds, identical bar window (R0):

| feed | trades | wr | net | PF | maxDD | sum R |
|---|---|---|---|---|---|---|
| MT5 M1 bars + MT5 ticks (audit reference) | 524 | 58.6% | +$236.83 | 1.28 | 83.3 | |
| MT5-tick-built M1 + MT5 ticks | 524 | 58.6% | +$238.14 | 1.28 | 83.1 | +25.3 |
| archive M1 + archive ticks | 538 | 57.8% | **+$206.75** | 1.23 | 86.7 | +18.6 |

Trade alignment (same direction, entry within 120 s): 474 of 524 MT5
trades have an archive twin (90%); 469 same kind, 470 same outcome; entry
price difference median $0.17, SL difference median $0.06, P&L difference
per matched pair median $0.006. The unmatched 50 MT5-only trades net
+$9.74 and the 64 archive-only trades −$5.09: boundary-minute
differences move a few structure decisions, and the strategy is sensitive
to that (E001's anchor test found ±$17 for a 3-day start shift; this
feed difference is worth about −$31, 13%).

**Mismatch rate, honestly stated:** same market, same spread, same
volatility, same tick count; 10% of trades differ and the 69-day P&L
differs by 13% because the structure engine reacts to sub-dollar
boundary differences. The archive is fit for validating sign, magnitude
and time-stability of the frozen strategy over long periods; it is not
fit for claiming dollar-exact equivalence to the live feed, and any
single-period result from it carries a feed-noise floor of roughly
±15% of R0's net. Phase 5 should be read with that floor in mind.

## Proposed reserved eras (NOT yet frozen — confirm before download)

| era | period | source | why |
|---|---|---|---|
| V2 | 2026-01-01 → 2026-06-30 | MT5 ticks (also available from the archive as a cross-check) | closest to live economics; two older spread regimes ($12.60, $9.80) that stress the cost model; 6 months |
| V3 | 2025-01-01 → 2025-12-31 | archive | full year, still recent market structure |
| V4 | 2022-01-01 → 2024-12-31 | archive | three years incl. bear/bull cycles; 2022 spread regime unknown until imported |

Suggested order: V2 first (it doubles as the MT5-vs-archive cross-check
under the $12.60 and $9.80 regimes), then V3, then V4 only if V2 and V3
are consistent. Each era is consumed once it is reported.
