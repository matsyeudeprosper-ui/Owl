"""Section 5: SHADOW REGIME CIRCUIT BREAKER.

Idea: the strategy keeps trading virtually (shadow) all the time; the
REAL size follows a state machine NORMAL -> REDUCED (half) -> PAUSED (0)
driven by whether the recent shadow record is statistically consistent
with the strategy's own historical distribution.

Thresholds come ONLY from the TRAIN half (first half of the research
sample). Preregistered tiny grid: window N in {20, 30, 40}; REDUCED when
the rolling-N shadow net < p10 of the train distribution of N-trade
sums; PAUSED when < p5; back to NORMAL when the rolling-N net >= p50
(median). The train distribution is a bootstrap (100 000 draws of N
trades with replacement from the train trade list) - it answers "what
does a run of N trades of THIS strategy normally look like".
Plus one CUSUM variant: S = max(0, S + (mu_train - pnl) - k), k = mu/2,
alarm at h = the 99th percentile of the CUSUM peak over train bootstrap
sequences of 300 trades; reset to 0 on alarm; REDUCED while S > h/2.

Evaluation is blind on TEST (second half) and on the untouched OOS
(rolling window carries across the boundary, chronological sequence).
State for a trade = state computed from trades strictly before it.
Real P&L = shadow P&L x (1 / 0.5 / 0) by state.
"""
import csv
import datetime as dt
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sp = dict(l.strip().split("=") for l in open(os.path.join(HERE, "split.txt")))
MID = int(sp["mid"])
END = int(sp["research_end"])


def load(fn):
    rows = list(csv.DictReader(open(os.path.join(HERE, fn))))
    return [(float(r["t"]), float(r["pnl"])) for r in rows]


INS = load("trades_insample.csv")
OOS = load("trades_oos.csv")
ALL = sorted(INS + OOS)
TRAIN = [x for x in INS if x[0] < MID]
out = open(os.path.join(HERE, "results_breaker.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s)
    out.write(s + "\n")


tp = np.array([p for _, p in TRAIN])
mu = tp.mean()
rng = np.random.default_rng(7)
say(f"train: {len(tp)} trades, mean {mu:+.3f}/trade, sd {tp.std():.3f}")


def thresholds(N):
    sums = rng.choice(tp, (100000, N), replace=True).sum(axis=1)
    return np.percentile(sums, 5), np.percentile(sums, 10), np.percentile(sums, 50)


def run_rolling(seq, N, p5, p10, p50, label, t_lo, t_hi=None):
    """seq = chronological (t, pnl); evaluate trades with t_lo <= t < t_hi."""
    state = "NORMAL"
    hist = []
    rows = []
    events = []
    for t, p in seq:
        # state from history strictly before this trade
        if len(hist) >= N:
            s = sum(hist[-N:])
            prev = state
            if state == "NORMAL":
                if s < p5:
                    state = "PAUSED"
                elif s < p10:
                    state = "REDUCED"
            elif state == "REDUCED":
                if s < p5:
                    state = "PAUSED"
                elif s >= p50:
                    state = "NORMAL"
            elif state == "PAUSED":
                if s >= p50:
                    state = "NORMAL"
                elif s >= p10:
                    state = "REDUCED"
            if state != prev:
                events.append((t, prev, state, s))
        mult = {"NORMAL": 1.0, "REDUCED": 0.5, "PAUSED": 0.0}[state]
        if t >= t_lo and (t_hi is None or t < t_hi):
            rows.append((t, p, state, p * mult))
        hist.append(p)
    return rows, events


def summarize(rows, events, label, t_lo, t_hi):
    if not rows:
        say(f"  {label}: no trades")
        return
    shadow = sum(r[1] for r in rows)
    real = sum(r[3] for r in rows)
    npaused = sum(1 for r in rows if r[2] == "PAUSED")
    nred = sum(1 for r in rows if r[2] == "REDUCED")
    lost_p = sum(r[1] for r in rows if r[2] == "PAUSED")
    lost_r = sum(r[1] * 0.5 for r in rows if r[2] == "REDUCED")
    say(f"  {label}: shadow {shadow:+8.2f} -> real {real:+8.2f} | trades {len(rows)}: paused {npaused}, reduced {nred} "
        f"| P&L not taken: paused {lost_p:+.2f}, reduced-half {lost_r:+.2f}")
    ev = [e for e in events if t_lo <= e[0] < (t_hi or 1e12)]
    for t, a, b, s in ev[:12]:
        say(f"      {dt.datetime.utcfromtimestamp(t).isoformat()} {a} -> {b} (rolling {s:+.2f})")
    if len(ev) > 12:
        say(f"      ... {len(ev)-12} more transitions")


say("\n=== ROLLING-SUM BREAKER (thresholds = bootstrap of TRAIN trades) ===")
for N in (20, 30, 40):
    p5, p10, p50 = thresholds(N)
    say(f"\n--- N={N}: REDUCED below p10 {p10:+.2f}, PAUSED below p5 {p5:+.2f}, NORMAL again at/above p50 {p50:+.2f}")
    rows, ev = run_rolling(ALL, N, p5, p10, p50, "", 0)
    summarize([r for r in rows if r[0] < MID], ev, "TRAIN (in-sample, not blind)", 0, MID)
    summarize([r for r in rows if MID <= r[0] < END + 60], ev, "TEST  (blind)", MID, END + 60)
    summarize([r for r in rows if r[0] >= END + 60], ev, "OOS   (blind)", END + 60, None)

say("\n=== CUSUM BREAKER (k = mu/2, h = p99 of the CUSUM peak over train bootstrap runs of 300 trades) ===")
k = mu / 2
peaks = []
for _ in range(2000):
    s = 0.0
    pk = 0.0
    for p in rng.choice(tp, 300, replace=True):
        s = max(0.0, s + (mu - p) - k)
        pk = max(pk, s)
    peaks.append(pk)
h = float(np.percentile(peaks, 99))
say(f"mu {mu:+.3f} k {k:+.3f} h {h:.2f} (p99 of train CUSUM peaks; p95 {np.percentile(peaks,95):.2f})")


def run_cusum(seq, h, k, resume_n=20):
    state = "NORMAL"
    s = 0.0
    rows = []
    events = []
    since = 0
    for t, p in seq:
        prev = state
        if state == "NORMAL" and s > h / 2:
            state = "REDUCED"
        if s > h:
            state = "PAUSED"
            s = 0.0
            since = 0
        if state == "PAUSED":
            since += 1
            if since > resume_n and s == 0.0:
                state = "NORMAL"
        elif state == "REDUCED" and s <= h / 4:
            state = "NORMAL"
        if state != prev:
            events.append((t, prev, state, s))
        mult = {"NORMAL": 1.0, "REDUCED": 0.5, "PAUSED": 0.0}[state]
        rows.append((t, p, state, p * mult))
        s = max(0.0, s + (mu - p) - k)
    return rows, events


rows, ev = run_cusum(ALL, h, k)
summarize([r for r in rows if r[0] < MID], ev, "TRAIN (in-sample, not blind)", 0, MID)
summarize([r for r in rows if MID <= r[0] < END + 60], ev, "TEST  (blind)", MID, END + 60)
summarize([r for r in rows if r[0] >= END + 60], ev, "OOS   (blind)", END + 60, None)
say("\n(CUSUM resume rule: paused for 20 shadow trades then NORMAL; REDUCED while S > h/2, back when S <= h/4 - "
    "one preregistered variant, not tuned)")
say(f"\nchoices tried: 3 windows x 1 threshold set (p5/p10/p50) + 1 CUSUM = 4 candidates")
out.close()
