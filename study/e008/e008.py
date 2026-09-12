"""E008 - stop-distance / risk geometry (2026-09-12).

Population for Parts 1-4 and 7: the UNGATED tick run of the candle-close
config (every otherwise-valid entry, so stale continuations are present).
Eligibility under the production 2h gate is carried as a flag.
Discovery = R0-TRAIN only. Blind = R0-TEST. V1 historical only.

Per trade: kind, flip age (min), stop distance (pts, from the actual tick
fill), stop/ATR14, stop/median M1 range(60), stop/range15/30/60, distance
from flip price, ordinal since flip, P&L $, P&L in R (= pnl / (dist*0.02)),
constant-risk P&L (= R x $4, i.e. every trade risks $4 before costs),
outcome, spread fraction (7/dist), total-cost fraction (12/dist: spread +
2.5 pt entry slip + 2.5 pt stop slip, the observed live means).

Predeclared rule for Part 5 (written before TRAIN is looked at): if the
TRAIN quintile table shows BOTH the lowest-20% and the highest-20% stop
buckets with lower $ expectancy than the middle 60%, the ONE candidate is
band = [TRAIN q20, TRAIN q80] of continuation stop distance, applied to
continuation entries only. Otherwise no candidate. Frozen, then TEST.
"""
import csv
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "e007"))
from e007_lib import (A, ENT, END, MID, Pre2, elig_share, features, load_all, real_flips, run, set_gate,  # noqa: E402
                      stats)

RISK = 4.0
S = 7.0
COST = 12.0
out = open(os.path.join(HERE, "results_e008.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s)
    out.write(s + "\n")


def st(rows, label=""):
    if not rows:
        return f"{label:26s} n    0"
    p = np.array([r["pnl"] for r in rows])
    R = np.array([r["pnl_R"] for r in rows])
    W = p[p > 0]
    Lo = p[p <= 0]
    cum = np.cumsum(p)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    pf = W.sum() / -Lo.sum() if len(Lo) and Lo.sum() < 0 else float("inf")
    return (f"{label:26s} n {len(p):4d} wr {len(W)/len(p):5.1%} net {p.sum():+8.2f} PF {pf:4.2f} exp$ {p.mean():+.3f} "
            f"expR {R.mean():+.3f} avgW {W.mean() if len(W) else 0:+.2f} avgL {Lo.mean() if len(Lo) else 0:+.2f} "
            f"maxDD {np.max(peak-cum):6.2f} constRisk {R.sum()*RISK:+8.2f}")


P, tk = load_all()
FL = real_flips(P)
T = P.T
set_gate(P, FL, 7200)
base = run(P, tk)                      # production baseline (gated)
nog = run(P, tk, gate=False)           # population
say(f"baseline gated: {A.fmt(A.stats(base,'')).strip()}")


def enrich(x):
    j = x["j"]
    lf = int(P.last_flip[j])
    x["age"] = 0.0 if x["kind"] == "flip" else ((int(T[j]) - int(T[lf])) / 60.0 if lf >= 0 else 1e9)
    f = features(P, x, tk)
    x.update(stop_atr=f["stop_atr"], stop_med60=f["stop_med60"], r15=x["dist"] / f["range15"] if f["range15"] else np.nan,
             r30=x["dist"] / f["range30"] if f["range30"] else np.nan, r60=x["dist"] / f["range60"] if f["range60"] else np.nan,
             ordinal=f["ordinal"], dist_flip=abs(P.C[j] - P.C[lf]) if lf >= 0 else np.nan)
    x["pnl_R"] = x["pnl"] / (x["dist"] * 0.02)
    x["cr"] = x["pnl_R"] * RISK
    x["spread_frac"] = S / x["dist"]
    x["cost_frac"] = COST / x["dist"]
    x["elig"] = x["kind"] == "flip" or x["age"] < 120
    return x


for x in nog:
    enrich(x)
for x in base:
    enrich(x)
with open(os.path.join(HERE, "trades_e008_ungated.csv"), "w", newline="") as fh:
    cols = ["t", "time", "kind", "d", "age_min", "elig_2h", "dist", "stop_atr", "stop_med60", "stop_r15", "stop_r30", "stop_r60",
            "dist_from_flip", "ordinal", "pnl", "pnl_R", "const_risk_pnl", "why", "spread_frac", "cost_frac"]
    w = csv.writer(fh)
    w.writerow(cols)
    for x in nog:
        w.writerow([x["t"], dt.datetime.utcfromtimestamp(x["t"]).isoformat(), x["kind"], x["d"], round(x["age"], 1), int(x["elig"]),
                    round(x["dist"], 2), round(x["stop_atr"], 3), round(x["stop_med60"], 3), round(x["r15"], 3), round(x["r30"], 3),
                    round(x["r60"], 3), round(x["dist_flip"], 2) if not np.isnan(x["dist_flip"]) else "", x["ordinal"],
                    round(x["pnl"], 4), round(x["pnl_R"], 4), round(x["cr"], 4), x["why"], round(x["spread_frac"], 4), round(x["cost_frac"], 4)])

TR = lambda rows: [x for x in rows if x["t"] < MID]
TE = lambda rows: [x for x in rows if x["t"] >= MID]
conts = [x for x in nog if x["kind"] == "cont"]
flips = [x for x in nog if x["kind"] == "flip"]
say(f"population (no gate): {len(nog)} trades = {len(flips)} flips + {len(conts)} continuations; TRAIN {len(TR(nog))} / TEST {len(TE(nog))}")

# ============ PART 1 ============
say("\n=== PART 1. STOP-DISTANCE SHAPE, continuation entries (population: no gate) ===")
qs = np.percentile([x["dist"] for x in TR(conts)], [20, 40, 60, 80])
say(f"TRAIN quintile cuts (continuations): {', '.join(f'{q:.0f}' for q in qs)} pts")
for name, sel in (("TRAIN", TR(conts)), ("TEST ", TE(conts))):
    say(f"  {name} quintiles:")
    edges = [-1] + list(qs) + [1e9]
    for i in range(5):
        s = [x for x in sel if edges[i] < x["dist"] <= edges[i + 1]]
        say("    " + st(s, f"Q{i+1} ({edges[i]:.0f}-{edges[i+1]:.0f}]" if i < 4 else f"Q5 (>{edges[i]:.0f})"))
    say(f"  {name} raw bands:")
    for lo, hi in ((0, 75), (75, 100), (100, 150), (150, 250), (250, 400), (400, 1e9)):
        s = [x for x in sel if lo < x["dist"] <= hi]
        say("    " + st(s, f"{lo:.0f}-{hi if hi < 1e9 else 9999:.0f}") + ("   (n<10: read with the neighbour)" if len(s) < 10 else ""))
say("  other geometry ratios (TRAIN tertiles applied to both halves), continuations:")
for feat, lbl in (("stop_atr", "stop/ATR14"), ("stop_med60", "stop/medRange60"), ("r15", "stop/range15"), ("r30", "stop/range30"), ("r60", "stop/range60")):
    t1, t2 = np.percentile([x[feat] for x in TR(conts) if not np.isnan(x[feat])], [33.3, 66.7])
    for name, sel in (("TRAIN", TR(conts)), ("TEST ", TE(conts))):
        parts = []
        for lo, hi, nm in ((-1, t1, "low"), (t1, t2, "mid"), (t2, 1e9, "high")):
            s = [x for x in sel if not np.isnan(x[feat]) and lo < x[feat] <= hi]
            R = np.array([x["pnl_R"] for x in s]) if s else np.array([0.0])
            parts.append(f"{nm} n {len(s):3d} $ {sum(x['pnl'] for x in s):+7.2f} R {R.mean():+.3f}")
        say(f"    {lbl:16s} {name}: " + " | ".join(parts) + f"   (cuts {t1:.2f}/{t2:.2f})")

# ============ PART 2 ============
say("\n=== PART 2. DOES STOP WIDTH EXPLAIN TREND AGE? cross-tab, continuations, TRAIN width tertiles ===")
w1, w2 = np.percentile([x["dist"] for x in TR(conts)], [33.3, 66.7])
say(f"width tertiles (TRAIN): narrow <= {w1:.0f}, medium {w1:.0f}-{w2:.0f}, wide > {w2:.0f} pts")
AGE = (("age<=2h", 0, 120), ("age 2-4h", 120, 240), ("age>=4h", 240, 1e12))
WID = (("narrow", -1, w1), ("medium", w1, w2), ("wide", w2, 1e9))
for name, sel in (("TRAIN", TR(conts)), ("TEST ", TE(conts))):
    say(f"  {name}: cell = n / net$ / expR / wr")
    say(f"    {'':10s}" + "".join(f"{wn:>30s}" for wn, _, _ in WID) + f"{'ALL widths':>30s}")
    for an, a0, a1 in AGE:
        row = f"    {an:10s}"
        for wn, l0, l1 in WID + (("all", -1, 1e9),):
            s = [x for x in sel if a0 <= x["age"] < a1 and l0 < x["dist"] <= l1]
            if s:
                R = np.mean([x["pnl_R"] for x in s])
                row += f"{len(s):4d} / {sum(x['pnl'] for x in s):+7.2f} / {R:+.3f} / {np.mean([x['pnl']>0 for x in s]):.0%}".rjust(30)
            else:
                row += f"{'-':>30s}"
        say(row)
    row = f"    {'ALL ages':10s}"
    for wn, l0, l1 in WID + (("all", -1, 1e9),):
        s = [x for x in sel if l0 < x["dist"] <= l1]
        R = np.mean([x["pnl_R"] for x in s])
        row += f"{len(s):4d} / {sum(x['pnl'] for x in s):+7.2f} / {R:+.3f} / {np.mean([x['pnl']>0 for x in s]):.0%}".rjust(30)
    say(row)
say("  secondary: OLS  pnl_R ~ 1 + log(dist) + [age 2-4h] + [age >= 4h]   (continuations; t-stats from classical SE)")
for name, sel in (("TRAIN", TR(conts)), ("TEST ", TE(conts))):
    X = np.array([[1.0, np.log(x["dist"]), float(120 <= x["age"] < 240), float(x["age"] >= 240)] for x in sel])
    y = np.array([x["pnl_R"] for x in sel])
    beta, res, rk, sv = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    s2 = resid @ resid / (len(y) - X.shape[1])
    cov = s2 * np.linalg.inv(X.T @ X)
    tstat = beta / np.sqrt(np.diag(cov))
    say(f"    {name}: const {beta[0]:+.3f} (t {tstat[0]:+.2f}) | log(dist) {beta[1]:+.3f} (t {tstat[1]:+.2f}) | "
        f"age2-4h {beta[2]:+.3f} (t {tstat[2]:+.2f}) | age>=4h {beta[3]:+.3f} (t {tstat[3]:+.2f})  n {len(y)}")
    X2 = X[:, [0, 2, 3]]
    b2 = np.linalg.lstsq(X2, y, rcond=None)[0]
    r2 = y - X2 @ b2
    c2 = (r2 @ r2 / (len(y) - 3)) * np.linalg.inv(X2.T @ X2)
    t2 = b2 / np.sqrt(np.diag(c2))
    say(f"    {name} without dist: age2-4h {b2[1]:+.3f} (t {t2[1]:+.2f}) | age>=4h {b2[2]:+.3f} (t {t2[2]:+.2f})")

# ============ PART 3 ============
say("\n=== PART 3. RISK NORMALISATION: fixed 0.02 $ vs R vs constant-risk ($4/trade), continuations by age and by width ===")
for name, sel in (("TRAIN", TR(conts)), ("TEST ", TE(conts))):
    say(f"  {name}")
    for an, a0, a1 in AGE:
        s = [x for x in sel if a0 <= x["age"] < a1]
        if s:
            say(f"    {an:10s} n {len(s):3d} fixed-lot {sum(x['pnl'] for x in s):+8.2f} | sum R {sum(x['pnl_R'] for x in s):+7.2f} "
                f"(mean R {np.mean([x['pnl_R'] for x in s]):+.3f}) | constant-risk {sum(x['cr'] for x in s):+8.2f}")
    for wn, l0, l1 in WID:
        s = [x for x in sel if l0 < x["dist"] <= l1]
        say(f"    {wn:10s} n {len(s):3d} fixed-lot {sum(x['pnl'] for x in s):+8.2f} | sum R {sum(x['pnl_R'] for x in s):+7.2f} "
            f"(mean R {np.mean([x['pnl_R'] for x in s]):+.3f}) | constant-risk {sum(x['cr'] for x in s):+8.2f}")
say("  awake gate value under each normalisation (in-engine gated run vs ungated run, all entries):")
for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
    g = [x for x in base if (lo is None or x["t"] >= lo) and (hi is None or x["t"] < hi)]
    u = [x for x in nog if (lo is None or x["t"] >= lo) and (hi is None or x["t"] < hi)]
    say(f"    {name}: gated  fixed-lot {sum(x['pnl'] for x in g):+8.2f} | sum R {sum(x['pnl_R'] for x in g):+7.2f} | constant-risk {sum(x['cr'] for x in g):+8.2f}  (n {len(g)})")
    say(f"    {name}: ungated fixed-lot {sum(x['pnl'] for x in u):+8.2f} | sum R {sum(x['pnl_R'] for x in u):+7.2f} | constant-risk {sum(x['cr'] for x in u):+8.2f}  (n {len(u)})")

# ============ PART 4 ============
say("\n=== PART 4. COST FRACTION (spread 7 / stop; total 12 / stop), continuations, predeclared bands ===")
BANDS = ((0.10, 9, ">10% (stop<70)"), (0.07, 0.10, "7-10% (70-100)"), (0.04, 0.07, "4-7% (100-175)"), (0.02, 0.04, "2-4% (175-350)"), (0, 0.02, "<2% (>350)"))
for name, sel in (("TRAIN", TR(conts)), ("TEST ", TE(conts))):
    say(f"  {name} by spread fraction:")
    for lo, hi, lbl in BANDS:
        s = [x for x in sel if lo < x["spread_frac"] <= hi]
        if s:
            R = np.array([x["pnl_R"] for x in s])
            wins = np.mean([x["pnl"] > 0 for x in s])
            say(f"    {lbl:18s} n {len(s):3d} wr {wins:5.1%} net {sum(x['pnl'] for x in s):+7.2f} meanR {R.mean():+.3f} "
                f"| break-even wr for RR 0.8 with this cost: {(1+np.mean([x['cost_frac'] for x in s]))/(1.8):.0%} (mean total-cost frac {np.mean([x['cost_frac'] for x in s]):.1%})")
say("  (break-even win rate = (1 + c) / (1 + RR) where c = total cost as a fraction of the stop; RR 0.8 -> 56% at zero cost)")

# ============ PART 7 (flips) ============
say("\n=== PART 7. FLIP-BOS entries by stop distance (TRAIN flip quintiles) ===")
qf = np.percentile([x["dist"] for x in TR(flips)], [20, 40, 60, 80])
say(f"TRAIN flip quintile cuts: {', '.join(f'{q:.0f}' for q in qf)} pts")
for name, sel in (("TRAIN", TR(flips)), ("TEST ", TE(flips))):
    edges = [-1] + list(qf) + [1e9]
    for i in range(5):
        s = [x for x in sel if edges[i] < x["dist"] <= edges[i + 1]]
        say("  " + st(s, f"{name} flips Q{i+1}"))
    say("  " + name + " flips by cost band: " + " | ".join(
        f"{lbl.split()[0]} n {len([x for x in sel if lo < x['spread_frac'] <= hi])} ${sum(x['pnl'] for x in sel if lo < x['spread_frac'] <= hi):+.1f}"
        for lo, hi, lbl in BANDS))

# ============ PART 5 ============
say("\n=== PART 5. ONE TRAIN-DERIVED BAND (predeclared rule: both tails worse than the middle 60% in TRAIN $ expectancy) ===")
trc = TR(conts)
edges = [-1] + list(qs) + [1e9]
q_exp = [np.mean([x["pnl"] for x in trc if edges[i] < x["dist"] <= edges[i + 1]]) for i in range(5)]
mid_exp = np.mean([x["pnl"] for x in trc if qs[0] < x["dist"] <= qs[3]])
say(f"TRAIN $ expectancy by quintile: {', '.join(f'{v:+.3f}' for v in q_exp)} | middle 60%: {mid_exp:+.3f}")
band = None
if q_exp[0] < mid_exp and q_exp[4] < mid_exp:
    band = (float(qs[0]), float(qs[3]))
    say(f"-> candidate band FROZEN: {band[0]:.0f} < stop <= {band[1]:.0f} pts (continuations only)")
else:
    say("-> rule condition NOT met in TRAIN: no candidate band. (Reported anyway below as a descriptive test of [q20,q80], NOT a candidate.)")
    band = (float(qs[0]), float(qs[3]))
lo_b, hi_b = band


def band_ok(x):
    return x["kind"] == "flip" or (lo_b < x["dist"] <= hi_b)


rng = np.random.default_rng(88)
for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
    g = [x for x in base if (lo is None or x["t"] >= lo) and (hi is None or x["t"] < hi)]   # gated baseline
    kept = [x for x in g if band_ok(x)]
    bn = [x for x in g if x["kind"] == "cont" and x["dist"] <= lo_b]
    bw = [x for x in g if x["kind"] == "cont" and x["dist"] > hi_b]
    say(f"  {name} (on the gated baseline, list-based):")
    say("    " + st(g, "baseline"))
    say("    " + st(kept, "kept"))
    say("    " + st(bn, "blocked narrow"))
    say("    " + st(bw, "blocked wide"))
    p = np.array([x["pnl"] for x in g])
    for lbl, blk in (("narrow", bn), ("wide", bw), ("both", bn + bw)):
        k = len(blk)
        if k == 0:
            continue
        real = sum(x["pnl"] for x in blk)
        sims = np.array([p[rng.choice(len(p), k, replace=False)].sum() for _ in range(1000)])
        say(f"    control {lbl:6s}: blocked n {k:3d} P&L {real:+7.2f} | random same-size mean {sims.mean():+7.2f} sd {sims.std():6.2f} | P(random <= real) {(sims <= real).mean():.3f}")

# ============ PART 6 ============
say("\n=== PART 6. INTERACTION WITH THE AWAKE GATE (in-engine tick re-simulation; band applied to continuation signals) ===")


def band_mask():
    m = np.ones(P.N, bool)
    cont = (P.sig_d != 0) & (~P.sig_flip)
    for j in np.where(cont)[0]:
        e = P.C[j] + S if P.sig_d[j] == 1 else P.C[j]
        dist = abs(e - P.sig_sl[j])
        m[j] = lo_b < dist <= hi_b
    return m


BM = band_mask()
CONFIGS = [("1 no gate", None, False), ("2 awake 2h (live)", 7200, False), ("3 stale >=4h excluded", 14400, False),
           ("4 band only", None, True), ("5 awake 2h + band", 7200, True)]
O2, H2, L2, C2, T2 = A.load_m1(os.path.join(HERE, "..", "data", "m1_trial9_all.npz"))
P2 = Pre2(O2, H2, L2, C2, T2)
FL2 = real_flips(P2)
BM2 = None
for lbl, W, use_band in CONFIGS:
    if W is None:
        P.awake_sig = np.ones(P.N, bool)
    else:
        set_gate(P, FL, W)
    if use_band:
        P.awake_sig = (P.awake_sig & BM) | P.ev_flip
    tr = run(P, tk)
    for x in tr:
        enrich(x)
    # V1 historical
    if W is None:
        P2.awake_sig = np.ones(P2.N, bool)
    else:
        set_gate(P2, FL2, W)
    if use_band:
        if BM2 is None:
            m = np.ones(P2.N, bool)
            cont = (P2.sig_d != 0) & (~P2.sig_flip)
            for j in np.where(cont)[0]:
                e = P2.C[j] + S if P2.sig_d[j] == 1 else P2.C[j]
                m[j] = lo_b < abs(e - P2.sig_sl[j]) <= hi_b
            BM2 = m
        P2.awake_sig = (P2.awake_sig & BM2) | P2.ev_flip
    v1 = [x for x in run(P2, tk) if x["t"] >= END + 60]
    for x in v1:
        x["pnl_R"] = x["pnl"] / (x["dist"] * 0.02)
        x["cr"] = x["pnl_R"] * RISK
    for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
        s = [x for x in tr if (lo is None or x["t"] >= lo) and (hi is None or x["t"] < hi)]
        say(f"  {lbl:24s} {name}: " + st(s, "") + f" | cont n {sum(1 for x in s if x['kind']=='cont')} ${sum(x['pnl'] for x in s if x['kind']=='cont'):+.2f}")
    say(f"  {lbl:24s} V1   : " + st(v1, "") + "   (historical only)")
set_gate(P, FL, 7200)
say("\ndone")
out.close()
