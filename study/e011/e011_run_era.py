"""E011 era runner: the FROZEN strategy on a reserved validation era.

usage: python e011_run_era.py <ERA> <ticks.npz> [--archive <ticks.npz>] [--regimes "Jan-Mar:1,2,3;Apr-May:4,5;Jun:6"]

Frozen: candle-close flip-BOS + candle-close continuation, 2h awake gate,
pending-dot SL, TP 0.8R, one position, fixed 0.02, min_dist 10, tick
execution (1 s poll) with the ACTUAL historical bid/ask. Structure on M1
built from the bid ticks. Nothing is selected on the era.
Outputs: results_<ERA>.txt, trades_<ERA>.csv (gated run), and the
data documentation. Random controls: e011_control.py (parallel).
"""
import csv
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "e007"))
sys.path.insert(0, os.path.join(HERE, "..", "audit"))
from e007_lib import A, Pre2, real_flips, set_gate  # noqa: E402
from exness_import import to_m1, gaps  # noqa: E402

ERA = sys.argv[1]
TICKS = sys.argv[2]
ARCH = sys.argv[sys.argv.index("--archive") + 1] if "--archive" in sys.argv else None
REG = sys.argv[sys.argv.index("--regimes") + 1] if "--regimes" in sys.argv else None
out = open(os.path.join(HERE, f"results_{ERA}.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")
    out.flush()


def ym(t):
    d = dt.datetime.utcfromtimestamp(t)
    return f"{d.year}-{d.month:02d}"


def load(path):
    D = np.load(path)
    return D["t"].astype(np.int64), D["bid"].astype(float), D["ask"].astype(float)


def document(t, b, a, label):
    say(f"--- DATA {label}: {len(t)} ticks {dt.datetime.utcfromtimestamp(t[0]/1000)} -> {dt.datetime.utcfromtimestamp(t[-1]/1000)}")
    T, O, H, L, C, V, SP = to_m1(t, b, a)
    mT = np.array([ym(x) for x in T])
    sp = a - b
    dayidx = t // 86400000
    ud = np.unique(dayidx)
    ucode = np.array([ym(int(d) * 86400) for d in ud])
    tcode = np.searchsorted(ud, dayidx)          # int index per tick -> month via ucode
    for m in sorted(set(mT)):
        sel = np.isin(tcode, np.where(ucode == m)[0])
        s = sp[sel]
        bars = int((mT == m).sum())
        d0 = dt.datetime.strptime(m, "%Y-%m")
        d1 = (d0.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        exp_min = int((d1 - d0).total_seconds() // 60)
        say(f"  {m}: ticks {sel.sum():9d} | spread median {np.median(s):.2f} p95 {np.percentile(s,95):.2f} max {s.max():.2f} | "
            f"M1 bars {bars} = {bars/exp_min:.1%} of minutes | median M1 range {np.median((H-L)[mT==m]):.1f}")
    g = gaps(T, 5)
    say(f"  gaps > 5 min: {len(g)}" + ("" if not g else "; largest: " + ", ".join(
        f"{dt.datetime.utcfromtimestamp(x[0]).strftime('%m-%d %H:%M')}->{x[2]}min" for x in sorted(g, key=lambda x: -x[2])[:6])))
    bad = int(((a < b) | (b <= 0)).sum())
    say(f"  ask<bid or non-positive: {bad}; ticks with spread > 3x median: {int((sp > 3*np.median(sp)).sum())}")
    return T, O, H, L, C


def run_all(T, O, H, L, C, t, b, a):
    P = Pre2(O, H, L, C, T)
    FL = real_flips(P)
    tk = A.Ticks(t, b, a)
    set_gate(P, FL, 7200)
    g = A.simulate(P, "tick", ("flip", "cont"), True, ticks=tk, min_dist=10)
    P.awake_sig = np.ones(P.N, bool)
    u = A.simulate(P, "tick", ("flip", "cont"), True, ticks=tk, min_dist=10)
    set_gate(P, FL, 7200)
    for tr in (g, u):
        for x in tr:
            x["R"] = x["pnl"] / (x["dist"] * 0.02)
            j = x["j"]
            lf = int(P.last_flip[j])
            x["age"] = 0.0 if x["kind"] == "flip" else ((int(T[j]) - int(T[lf])) / 60.0 if lf >= 0 else 1e9)
            x["time"] = tk.t[x["ti"]] / 1000
            x["month"] = ym(x["t"])
    return P, tk, g, u, len(FL)


def dd(p):
    cum = np.cumsum(p)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    d = peak - cum
    under = d > 1e-9
    longest = cur = 0
    for v in under:
        cur = cur + 1 if v else 0
        longest = max(longest, cur)
    return float(d.max()), longest


def rmin(p, n):
    if len(p) < n:
        return float(p.sum())
    cs = np.concatenate([[0.0], np.cumsum(p)])
    return float((cs[n:] - cs[:-n]).min())


def full_stats(tr, label, months=None):
    if not tr:
        say(f"  {label:34s} n 0")
        return
    p = np.array([x["pnl"] for x in tr])
    R = np.array([x["R"] for x in tr])
    ts = np.array([x["t"] for x in tr])
    W = p[p > 0]
    Lo = p[p <= 0]
    pf = W.sum() / -Lo.sum() if len(Lo) and Lo.sum() < 0 else float("inf")
    mdd, under = dd(p)
    mddR, _ = dd(R)
    days = (ts[-1] - ts[0]) / 86400 if len(ts) > 1 else 1
    say(f"  {label:34s} n {len(p):4d} ({len(p)/max(days,1)*30.44:5.1f}/mo) wr {len(W)/len(p):5.1%} net {p.sum():+9.2f} PF {pf:4.2f} exp$ {p.mean():+.3f} "
        f"expR {R.mean():+.3f} sumR {R.sum():+6.1f} maxDD$ {mdd:6.2f} maxDD_R {mddR:5.1f} underwater max {under:3d} tr | "
        f"largest {p.max():+.2f}/{p.min():+.2f} | worst r20 {rmin(p,20):+.2f} r40 {rmin(p,40):+.2f}")


def by_month(tr, label):
    say(f"  monthly ({label}):")
    for m in sorted(set(x["month"] for x in tr)):
        s = [x for x in tr if x["month"] == m]
        p = np.array([x["pnl"] for x in s])
        R = np.array([x["R"] for x in s])
        W = p[p > 0]
        Lo = p[p <= 0]
        pf = W.sum() / -Lo.sum() if len(Lo) and Lo.sum() < 0 else float("inf")
        say(f"    {m}: n {len(p):3d} wr {len(W)/len(p):5.1%} net {p.sum():+8.2f} PF {pf:4.2f} exp$ {p.mean():+.3f} sumR {R.sum():+5.1f} maxDD {dd(p)[0]:6.2f} "
            f"| flip n {sum(1 for x in s if x['kind']=='flip')} ${sum(x['pnl'] for x in s if x['kind']=='flip'):+.1f} cont n {sum(1 for x in s if x['kind']=='cont')} ${sum(x['pnl'] for x in s if x['kind']=='cont'):+.1f}")


# ================= main =================
t, b, a = load(TICKS)
T, O, H, L, C = document(t, b, a, f"{ERA} primary ({os.path.basename(TICKS)})")
P, tk, G, U, nflips = run_all(T, O, H, L, C, t, b, a)
say(f"\n=== {ERA}: FROZEN STRATEGY, actual historical spread ===  ({nflips} confirmed flips, {nflips/((T[-1]-T[0])/86400):.1f}/day)")
full_stats(G, "2h gate (production) ALL")
full_stats([x for x in G if x["kind"] == "flip"], "2h gate FLIP")
full_stats([x for x in G if x["kind"] == "cont"], "2h gate CONT")
full_stats(U, "no gate ALL")
full_stats([x for x in U if x["kind"] == "flip"], "no gate FLIP")
full_stats([x for x in U if x["kind"] == "cont"], "no gate CONT")
say(f"  gate contribution (gated minus ungated net): {sum(x['pnl'] for x in G) - sum(x['pnl'] for x in U):+.2f}")
by_month(G, "2h gate")
months = sorted(set(x["month"] for x in G))
h = len(months) // 2
say("  halves (2h gate):")
full_stats([x for x in G if x["month"] in months[:h]], f"first {h} months {months[0]}..{months[h-1]}")
full_stats([x for x in G if x["month"] in months[h:]], f"last {len(months)-h} months {months[h]}..{months[-1]}")
if REG:
    say("  spread regimes (2h gate, actual spread):")
    for grp in REG.split(";"):
        nm, ms = grp.split(":")
        keys = [m for m in months if int(m[-2:]) in [int(v) for v in ms.split(",")]]
        s = [x for x in G if x["month"] in keys]
        sp = [(x["e"] - (P.C[x["j"]])) for x in s if x["d"] == 1]
        full_stats(s, f"{nm} ({','.join(keys)})")

# ---- constant $7 diagnostic
say("\n--- DIAGNOSTIC ONLY: same ticks with a constant $7 spread (ask = bid + 7) ---")
tk7 = A.Ticks(t, b, b + 7.0)
set_gate(P, real_flips(P), 7200)
G7 = A.simulate(P, "tick", ("flip", "cont"), True, ticks=tk7, min_dist=10)
for x in G7:
    x["R"] = x["pnl"] / (x["dist"] * 0.02)
    x["month"] = ym(x["t"])
full_stats(G7, "2h gate, constant $7 (diagnostic)")
say(f"  spread cost attribution: actual-spread net {sum(x['pnl'] for x in G):+.2f} vs $7 net {sum(x['pnl'] for x in G7):+.2f} -> {sum(x['pnl'] for x in G7) - sum(x['pnl'] for x in G):+.2f} attributable to the higher historical spread")
by_month(G7, "$7 diagnostic")

# ---- structural findings (E007/E008 definitions, no new buckets)
say("\n--- STRUCTURAL FINDINGS (frozen E007/E008 definitions) ---")
conts = [x for x in U if x["kind"] == "cont"]
say("  1/2. continuation by flip age (no-gate population): n / wr / net$ / expR")
for lbl, lo, hi in (("0-15", 0, 15), ("15-30", 15, 30), ("30-60", 30, 60), ("60-120", 60, 120), ("120-240", 120, 240), ("240+", 240, 1e12)):
    s = [x for x in conts if lo <= x["age"] < hi]
    if s:
        say(f"     age {lbl:8s}: n {len(s):3d} wr {np.mean([x['pnl']>0 for x in s]):5.1%} net {sum(x['pnl'] for x in s):+8.2f} expR {np.mean([x['R'] for x in s]):+.3f}")
flips = [x for x in U if x["kind"] == "flip"]
nar = [x for x in flips if x["dist"] <= 83]
rest = [x for x in flips if x["dist"] > 83]
say(f"  3. FLIPS with stop <= 83 pt (E008 Q1 cut): n {len(nar)} wr {np.mean([x['pnl']>0 for x in nar]) if nar else 0:.1%} net {sum(x['pnl'] for x in nar):+.2f} expR {np.mean([x['R'] for x in nar]) if nar else 0:+.3f} "
    f"| other flips: n {len(rest)} wr {np.mean([x['pnl']>0 for x in rest]) if rest else 0:.1%} net {sum(x['pnl'] for x in rest):+.2f} expR {np.mean([x['R'] for x in rest]) if rest else 0:+.3f}")
say("  4. continuation width tertiles (E008 cuts 146/272): fixed-lot $ / sum R / constant-risk $2.99 (cap 0.05):")
for lbl, lo, hi in (("narrow<=146", -1, 146), ("medium", 146, 272), ("wide>272", 272, 1e9)):
    s = [x for x in conts if lo < x["dist"] <= hi]
    if s:
        cr = sum(x["R"] * min(0.05, max(0.01, np.floor(2.99 / x["dist"] / 0.01) * 0.01)) * x["dist"] for x in s)
        say(f"     {lbl:12s}: n {len(s):3d} fixed {sum(x['pnl'] for x in s):+8.2f} | sumR {sum(x['R'] for x in s):+6.1f} | constant-risk {cr:+8.2f}")
stale = [x for x in conts if x["age"] >= 240]
say(f"     stale >=4h conts: n {len(stale)} fixed {sum(x['pnl'] for x in stale):+.2f} sumR {sum(x['R'] for x in stale):+.1f} avg $risk {np.mean([x['dist']*0.02 for x in stale]) if stale else 0:.2f} vs all conts avg $risk {np.mean([x['dist']*0.02 for x in conts]):.2f}")
say(f"  5. awake-gate contribution: ${sum(x['pnl'] for x in G) - sum(x['pnl'] for x in U):+.2f} (R: {sum(x['R'] for x in G) - sum(x['R'] for x in U):+.1f})")
say("  6. $ vs R stability across the two halves (gated run): maxDD, worst roll-20, largest loss")
for lbl, key in (("$", "pnl"), ("R", "R")):
    h1 = np.array([x[key] for x in G if x["month"] in months[:h]])
    h2 = np.array([x[key] for x in G if x["month"] in months[h:]])
    if len(h1) > 20 and len(h2) > 20:
        say(f"     {lbl}: maxDD {dd(h1)[0]:.2f} / {dd(h2)[0]:.2f} (ratio {dd(h2)[0]/max(dd(h1)[0],1e-9):.2f}) | roll-20 {rmin(h1,20):+.2f} / {rmin(h2,20):+.2f} | largest loss {h1.min():+.2f} / {h2.min():+.2f} (ratio {h2.min()/h1.min():.2f})")

# ---- trades CSV
with open(os.path.join(HERE, f"trades_{ERA}.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["entry_time_utc", "kind", "dir", "entry", "sl", "tp", "stop_dist", "age_min", "exit_time_utc", "exit", "why", "pnl_002", "R", "month"])
    for x in G:
        w.writerow([dt.datetime.utcfromtimestamp(x["time"]).isoformat(timespec="seconds"), x["kind"], "BUY" if x["d"] == 1 else "SELL", round(x["e"], 2), round(x["sl"], 2),
                    round(x["tp"], 2), round(x["dist"], 2), round(x["age"], 1), dt.datetime.utcfromtimestamp(tk.t[x["xi"]] / 1000).isoformat(timespec="seconds"),
                    round(x["x"], 2), x["why"], round(x["pnl"], 4), round(x["R"], 4), x["month"]])
np.save(os.path.join(HERE, f"trades_{ERA}_pnl.npy"), np.array([[x["t"], x["pnl"], x["R"]] for x in G]))

# ---- archive cross-check
if ARCH:
    say(f"\n--- ARCHIVE CROSS-CHECK ({os.path.basename(ARCH)}) ---")
    t2, b2, a2 = load(ARCH)
    lo_, hi_ = max(t[0], t2[0]), min(t[-1], t2[-1])
    m2 = (t2 >= lo_) & (t2 <= hi_)
    t2, b2, a2 = t2[m2], b2[m2], a2[m2]
    T2, O2, H2, L2, C2 = document(t2, b2, a2, f"{ERA} archive")
    P2, tk2, G2, U2, nf2 = run_all(T2, O2, H2, L2, C2, t2, b2, a2)
    full_stats(G2, "archive 2h gate ALL")
    full_stats([x for x in G2 if x["kind"] == "flip"], "archive FLIP")
    full_stats([x for x in G2 if x["kind"] == "cont"], "archive CONT")
    full_stats(U2, "archive no gate ALL")
    used = set()
    pairs = []
    for x in G:
        best = None
        for k, y in enumerate(G2):
            if k in used or y["d"] != x["d"] or abs(y["time"] - x["time"]) > 120:
                continue
            if best is None or abs(y["time"] - x["time"]) < abs(G2[best]["time"] - x["time"]):
                best = k
        if best is not None:
            used.add(best)
            pairs.append((x, G2[best]))
    say(f"  alignment: matched {len(pairs)} of MT5 {len(G)} / archive {len(G2)} ({len(pairs)/max(len(G),1):.0%}); same kind {sum(1 for x,y in pairs if x['kind']==y['kind'])}; "
        f"same outcome {sum(1 for x,y in pairs if (x['pnl']>0)==(y['pnl']>0))}; net MT5 {sum(x['pnl'] for x in G):+.2f} vs archive {sum(x['pnl'] for x in G2):+.2f}; "
        f"sumR {sum(x['R'] for x in G):+.1f} vs {sum(x['R'] for x in G2):+.1f}; maxDD {dd(np.array([x['pnl'] for x in G]))[0]:.2f} vs {dd(np.array([x['pnl'] for x in G2]))[0]:.2f}")
    by_month(G2, "archive 2h gate")
say("\ndone")
out.close()
