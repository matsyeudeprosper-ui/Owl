# 2026-09-18 — the nervosity gate does not survive its controls, and money management moves to packages

## 1. The nervosity gate: no measured benefit

`study/review/nerv_gate_test.py`. Paired test — same bars, same engine,
nervosity gate on vs off, the movement rule left ON in **both** arms so only
one thing changes. Costs included. 60000 M1 bars = 41.7 days.

| control | result |
|---|---|
| helps on how many anchors | **5 of 12** |
| mean difference | **−0.001 R/trade** |
| range across anchors | −0.013 … +0.010 (straddles zero) |
| both halves | **−0.095 then +0.038** — sign flips |
| spread 0 / 7 / 15 pts | **+0.012 / −0.001 / −0.016** — sign flips |

It also costs **half the trades**: 344 → 185, $117 → $53 over the window at
0.02 lot, because per-trade quality is unchanged while volume halves.

**This withdraws the 2026-09-17 claim** that nervosity was one of two rules
surviving both window anchors. That was measured on a different pipeline
(aligned internal trades). On the live path with the full engine it does not
hold.

**Do not flip to "remove it" either.** Both arms are indistinguishable from
zero: +0.016 R/trade, 95% CI [−0.078, +0.110] on 344 trades. Resolving an
effect of 0.05 R/trade needs ~1200 trades. 41.7 days cannot settle it.

**Method note.** Anchor variation is the control that matters here. The
silence filter chains from its first bar, so starting one bar earlier
rebuilds every candle, dot and signal. Permutation and random-direction
controls hold the window fixed and are blind to this — which is how three
findings were retracted on 09-17.

### Owner's decision
Win rate with the gate is 60.8% (113/186) against a 55.6% break-even at
RR 0.8 — positive, so the gate **stays**. Every signal it refuses is now
recorded and followed virtually (`bots/owl_shadow.py`) so the counterfactual
can be measured forward. ~1200 trades needed; expect months.

## 2. Real trades per day

`study/review/trades_per_day.py` — full live-path replay, one position at a
time, awake gate, used_hi/lo dedupe, S_MIN_DIST, risk cap, daily cap with its
debt waiver.

| | trades | /day | gross wins |
|---|---|---|---|
| no brake, no cap | 343 | 8.2 | 59.5% |
| brakes only (441) | 185 | 4.4 | 60.5% |
| brakes + $3 cap (Valère) | 154 | 3.7 | 59.7% |

Median trade lasts 12 min (max 11 h). Corrects two earlier numbers: the cut
is 46%, not 90%, and 6.2/day was a *signal* count, not a trade count.

Win rates are **gross** — no spread, no slippage. Not a profitability claim.

## 3. Strategy is now shared; money management is per-account data

Two live accounts were obeying different rules. On 2026-09-18 Valère entered
at 05:01 in a 1.30× market that the 441 desk refused at 05:31 — same flip,
same price. The brakes existed only in the desk.

- `weather_gate()` now lives in `bots/structure_bos_bot.py`; the desk calls
  it. One implementation. A missing or stale feed **allows** — a brake that
  fires on its own silence would stop everything on a feed hiccup.
- `bots/owl_packages.json` + `bots/owl_package.py` hold what may differ per
  account: lot, bullets, kill line, risk cap, debt mode, daily profit cap and
  a new `max_trades_day`. `extends` makes a new offer a few lines; the file is
  re-read every 60 s, so retuning needs no restart.
- Valère's package is now exactly base + `day_cap 3.0` + `week_target 20`.
- `study/review/package_parity.py` guards it against `FROZEN`, the values
  hardcoded before the refactor. It passed **before** the wiring — that run is
  the proof the file was faithful.

## 4. Safety

- **Kill line on 441** (`bots/owl_manual_trader.py`, `kill_check`). The desk
  was written when a human watched every trade; AUTO mode ended that. net =
  realised + floating. Crossing −$60 closes everything, cancels orders, and
  returns the account to MANUAL. One-way door.
- **Admin emergency stop** (`bots/owl_panic.py`): pauses the account first,
  then cancels orders and closes every position, whatever opened it.
  Wrong-account refusal before any order; never switches the terminal's
  logged-in account; dry run without `--armed`.

## 5. Still open

- MT5 password sits in **5 commits** of the Kinolivelines history (HEAD is
  clean, 0 forks). Rotation pending; the interim step is making that repo
  private. **This repo (Owl) is clean** — 0 commits contain it.
- Sniper and half-debt demo variants both hit their kill lines on 2026-09-18
  on the **same** trade: a sell at 75822 with a 1478-point stop held 57 h.
  Both take TOUCH entries; both real accounts use candle-close and did not
  take it. n=1 — not a finding, a reason to keep the close rule.
