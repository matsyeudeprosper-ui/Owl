# Data eras (keep them apart)

Rule: a period can be used for discovery only once it is listed here as
"open for discovery". Everything after the newest research hypothesis is
reserved until ChatGPT explicitly opens it. Never tune on a period that
was still forward data when the idea was proposed.

| Era | Period (UTC) | Source | Status as of 2026-09-11 |
|---|---|---|---|
| R0 original research sample | 2026-07-01 12:36 → 2026-09-08 07:11 | `study/data/pro_m1.npz` (M1) + `study/data/ticks_btcusd.npz` | Open for discovery. Split used since the regime pass: TRAIN = before 2026-08-04 21:53, TEST = after. |
| V1 first untouched OOS | 2026-09-08 07:12 → 2026-09-11 13:39 | `study/data/m1_trial9_all.npz` tail + ticks | **Consumed as validation** on 2026-09-11 by the execution audit (E001-E004) and the regime pass (E005). It is no longer untouched. Do not use it for discovery; it may be reported as a validation period for ideas proposed before 2026-09-11 only. |
| L1 live TOUCH era | 2026-09-08 19:30 → 2026-09-11 17:26 | `results/bos/trades_live_canonical.csv` (MT5 deals) | Real trades of the flip+touch config (41 positions, base −$43.08). Closed era. |
| L2 live CANDLE-CLOSE era | 2026-09-11 17:26 → now | `live/bos_forward_ledger.csv` (observer, MT5 deals) + `bos_bot.log` | Forward evidence of the frozen production config. Reserved: validation only, opened per experiment by ChatGPT. |
| T2 paper twin (flip+touch) | 2026-09-11 17:26 → now | `live/bos_forward_ledger.csv` source=twin, `bos_paper_touch_state.json` | Side-by-side record of the previous rule. Reserved like L2. |
| **V2** RESERVED VALIDATION (E011) | 2026-01-01 00:00 → 2026-06-30 23:59 UTC | PRIMARY: MT5 Exness Pro BTCUSD ticks (demo terminal 476954287, same feed as live); public archive Jan–Jun 2026 as feed cross-check only | Frozen 2026-09-12 (owner approval) BEFORE any P&L. Purpose: nearest independent pre-R0 period; spread regimes $12.60 (Jan–Mar), $9.80 (Apr–May), transition to $7 (Jun). Consumed once reported. |
| **V3** RESERVED VALIDATION (E011) | 2025-01-01 → 2025-12-31 UTC | Exness public archive `ticks/BTCUSD/2025/` (monthly zips; SHA-256 in the import report) | Frozen 2026-09-12 before download. One full recent independent year. Run only after V2 is reported; consumed once reported. |
| **V4** RESERVED VALIDATION (E011) | 2022-01-01 → 2024-12-31 UTC | Exness public archive `ticks/BTCUSD/2022..2024/` | Frozen 2026-09-12 before download. Multiple BTC regimes. Run only after V3 is reported; consumed once reported. |
| F(n) future | after each new hypothesis timestamp | ticks + M1 fetched on demand | Reserved for that hypothesis' validation. |

Forward-observation variables recorded per trade in L2/T2 (informational,
never acted on): `narrow_stop` (stop distance ≤ 98 pt) and
`shadow_state_before` / `rolling20_before` (rolling-20 state NORMAL /
REDUCED / PAUSED with the thresholds frozen from R0-TRAIN: −15.65 / −22.51
/ +8.14; seeded from the tick backtest of the same rule set up to the switch).
