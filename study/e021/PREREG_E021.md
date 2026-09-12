# E021 preregistration — large downside shock → SHORT continuation (frozen 2026-09-12 before any result)

Hypothesis: after an unusually large 5-minute BTC drop, price continues
lower long enough to trade a SHORT after realistic Exness costs. The
opposite polarity of E019/E020.

## Honesty note (before computing anything)
E020's control A (immediate BUY, same events, same M1 timing) was
−32 / −11 / −29 / −25 / −11 points net at 30 min in 2022–2026. Subtracting
the round-trip cost twice (the short pays the same spread + $5) implies the
short is roughly −6 to −23 net in every year. E021 is run as the formal,
registered test of that inference with its own controls and path
analysis; nothing is tuned.

## Data
Consumed only: Exness archive M1 bars with mean spread, 2022, 2023, 2024,
2025, 2026-01 → 09-11 (same files as E020). M1 convention everywhere:
entry = open of the bar after the shock window (0–60 s after the close;
the M1 stand-in for "first bid ≥ 30 s after the close"), at the BID; exits
at the ASK (bid close + that bar's mean spread) N minutes later; $5 per
round trip on top. Derivatives context (taker, OI, liquidations) exists
only for 2026-07-31 → 09-11 and is reported for that slice only.
2021 (B1) sealed, 2017–2020 (U0) untouched, E017 forward stream not
opened. DATA_ERAS.md updated before this file.

## Events (past-only)
5-min windows on the clock; r5 = window close / previous window close − 1;
trailing 7-day 5th percentile over ≥ 1 000 windows; **shock = r5 ≤ p5**,
first of cluster (no shock in the previous 60 min). Robustness variant
(only): r5 ≤ p2.5. ATR = mean true range of the previous 14 windows.

## Primary
SELL at the next bar's open bid; net at 5 / 15 / 30 / 60 min; **primary
= 30 min**. Path over 60 min: MFE (downward), MAE (upward), time to each,
first passage −0.5 ATR vs +0.5 ATR and −1 ATR vs +1 ATR (favourable =
down; same-bar touches count as adverse first).

## Controls
- A — matched random SHORT entries: 1 000 draws, same n, same hour-of-day,
  bars not within 120 min after any shock, same costs.
- B — upside symmetry: r5 ≥ trailing p95 → BUY continuation, same timing
  and costs.
- C — opposite trade: BUY on the identical downside events (polarity check;
  should reproduce E020's control A).

## Anti-outlier (primary horizon)
without best 1, best 2, top 10% winners; median; 10% trimmed mean; worst
trade; max drawdown; longest losing streak.

## Descriptive only (no filters)
shock-return tertiles (mild / medium / largest); 24 h median M1 range;
spread; hour of day; distance from the trailing 1 h high and low (ATR);
for 2026-07-31 → 09-11: taker imbalance, OI change, liquidated BTC.

## Consumed-data gate (frozen) — required before 2021 is opened
pooled 30-min SHORT net > 0; positive in ≥ 4 of 5 yearly blocks; > 0
without the best 2; > 0 without the top 10% winners; ≥ 95th percentile of
control A; median not strongly negative; practical frequency; drawdown
acceptable vs the average gain. If it fails: STOP, 2021 stays sealed,
verdict C.

## Blind 2021 (only if the gate passes; rule, code hash and criteria
committed first): mean net > 0; ≥ 95th percentile of matched random; > 0
without best 2 and top 10%; no single month carries it; practical DD and
frequency; sign consistent with the consumed years. Month by month.

## Not allowed
other thresholds / horizons / delays after results; filters from the
descriptive variables; money-management layers; production changes;
opening 2021 without the gate; any use of 2017–2020 or E017 forward data.

## Verdict
A — robust downside-shock continuation that survives blind 2021.
B — continuation exists but weak / unstable / blind evidence insufficient.
C — short continuation is not a durable edge.
