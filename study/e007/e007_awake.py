"""E007 parts 1, 2, 4 and the component dependence. Placebos are in
e007_placebo.py (long run). Output: results_awake.txt."""
import datetime as dt
import os

import numpy as np

from e007_lib import (A, ENT, END, MID, circ_shift, elig_share, features, line, load_all, real_flips, run, set_gate,
                      stats)

HERE = os.path.dirname(os.path.abspath(__file__))
out = open(os.path.join(HERE, "results_awake.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s)
    out.write(s + "\n")


P, tk = load_all()
FL = real_flips(P)
T = P.T
say(f"R0: {P.N} bars {dt.datetime.utcfromtimestamp(T[0])} -> {dt.datetime.utcfromtimestamp(T[-1])}; "
    f"{len(FL)} confirmed trend flips ({len(FL)/((T[-1]-T[0])/86400):.1f}/day); TRAIN < {dt.datetime.utcfromtimestamp(MID)}")

# ---- parity: production gate = real flips, 2h
set_gate(P, FL, 7200)
base = run(P, tk)
say(line(stats(base), "PARITY baseline 2h gate") + "   (expect +236.83 / 524)")

# ================= 1. TIME SINCE LAST REAL FLIP (population = ungated run) =================
say("\n=== 1. TIME SINCE LAST CONFIRMED FLIP at entry (population: NO gate, so every otherwise-valid entry) ===")
nog = run(P, tk, gate=False)
for x in nog:
    j = x["j"]
    lf = int(P.last_flip[j])
    x["age"] = (int(T[j]) - int(T[lf])) / 60.0 if lf >= 0 else 1e9
    if x["kind"] == "flip":
        x["age"] = 0.0
BUCKETS = [("FLIP entry (age 0)", lambda a, k: k == "flip"),
           ("cont 0-15 min", lambda a, k: k == "cont" and 0 <= a < 15),
           ("cont 15-30 min", lambda a, k: k == "cont" and 15 <= a < 30),
           ("cont 30-60 min", lambda a, k: k == "cont" and 30 <= a < 60),
           ("cont 60-120 min", lambda a, k: k == "cont" and 60 <= a < 120),
           ("cont 120-240 min", lambda a, k: k == "cont" and 120 <= a < 240),
           ("cont 240+ / none", lambda a, k: k == "cont" and a >= 240)]
for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
    say(f"  {name}: {line(stats(nog, lo, hi), 'all entries, no gate')}")
    for lbl, fn in BUCKETS:
        sel = [x for x in nog if fn(x["age"], x["kind"]) and (lo is None or x["t"] >= lo) and (hi is None or x["t"] < hi)]
        say("    " + line(stats(sel), lbl))
say("  (continuation entries with age >= 120 min are exactly the ones the production gate blocks)")

# ================= 2. PREDECLARED WINDOWS =================
say("\n=== 2. WINDOW ROBUSTNESS: continuation eligible iff a real flip within W (flips always eligible) ===")
nog_s = {k: stats(nog, lo, hi) for k, lo, hi in (("TRAIN", None, MID), ("TEST", MID, None))}
for W in (1800, 3600, 7200, 14400, None):
    if W is None:
        tr = nog
        lbl = "no gate"
    else:
        set_gate(P, FL, W)
        tr = run(P, tk)
        lbl = f"W = {W//60:3d} min"
    share = 1.0 if W is None else elig_share(P)
    for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
        s = stats(tr, lo, hi)
        blocked = [x for x in nog if x["kind"] == "cont" and W is not None and x["age"] * 60 > W
                   and (lo is None or x["t"] >= lo) and (hi is None or x["t"] < hi)]
        bs = stats(blocked)
        say(f"  {lbl} {name}: {line(s, '')} | vs no gate {s['net']-nog_s[name.strip()]['net']:+7.2f} "
            f"| eligible share {share:.0%} | blocked(list) n {bs.get('n',0)} net {bs.get('net',0):+7.2f}")
set_gate(P, FL, 7200)

# ================= components =================
say("\n=== COMPONENT DEPENDENCE: 2h gate vs no gate, combined / flip-only / cont-only (tick) ===")
for ent, lbl in ((ENT, "combined"), (("flip",), "flip-only"), (("cont",), "cont-only")):
    for g, gl in ((True, "2h gate"), (False, "no gate")):
        tr = run(P, tk, ent, g)
        for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
            say(f"  {lbl:9s} {gl:8s} {name}: {line(stats(tr, lo, hi), '')}")

# ================= 3a. FIXED PLACEBO SHIFTS (the 1000 random ones run in e007_placebo.py) =================
say("\n=== 3a. FIXED PLACEBO SHIFTS of the flip timeline (circular within R0), 2h continuation eligibility ===")
T0, T1 = int(T[0]), int(T[-1])
for d in (0, 6 * 3600, 12 * 3600, 24 * 3600, -6 * 3600, -12 * 3600):
    set_gate(P, circ_shift(FL, T0, T1, d), 7200)
    tr = run(P, tk)
    sh = elig_share(P)
    lbl = "REAL (shift 0)" if d == 0 else f"shift {d/3600:+.0f} h"
    for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
        say(f"  {lbl:15s} {name}: {line(stats(tr, lo, hi), '')} | eligible share {sh:.0%}")
set_gate(P, FL, 7200)

# ================= 4. WHAT DOES THE GATE PROXY FOR (descriptive, ungated population, continuation entries) =================
say("\n=== 4. DESCRIPTIVE: continuation entries, ELIGIBLE (flip within 2h) vs NOT, no gate population ===")
FEATS = ["range15", "range30", "range60", "atr14", "med_range60", "stop_dist", "stop_atr", "chochs_2h", "repairs_2h",
         "flips_2h", "disturb_2h", "se_60", "se_flip", "bars_since_flip", "ordinal"]
for x in nog:
    if x["kind"] != "cont":
        continue
    f = features(P, x, tk)
    j = x["j"]
    lf = int(P.last_flip[j])
    f["dist_from_flip_px"] = abs(P.C[j] - P.C[lf]) if lf >= 0 else np.nan
    for w in (30, 60, 120):
        a = max(0, j - w)
        f[f"netmove{w}"] = (P.C[j] - P.C[a]) * x["d"]
        f[f"travel{w}"] = float(np.abs(np.diff(P.C[a:j + 1])).sum())
    f["hour"] = dt.datetime.utcfromtimestamp(x["t"]).hour
    x["f"] = f
FEATS2 = FEATS + ["dist_from_flip_px", "netmove30", "netmove60", "netmove120", "travel30", "travel60", "travel120"]
for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
    conts = [x for x in nog if x["kind"] == "cont" and (lo is None or x["t"] >= lo) and (hi is None or x["t"] < hi)]
    el = [x for x in conts if x["age"] < 120]
    ne = [x for x in conts if x["age"] >= 120]
    say(f"  {name}: eligible {line(stats(el), '')}")
    say(f"  {name}: NOT elig {line(stats(ne), '')}")
    say(f"    {'feature':18s} {'elig median':>12s} {'not median':>12s} {'elig mean':>11s} {'not mean':>11s}")
    for k in FEATS2:
        a = np.array([x["f"][k] for x in el], float)
        b = np.array([x["f"][k] for x in ne], float)
        a, b = a[~np.isnan(a)], b[~np.isnan(b)]
        if len(a) and len(b):
            say(f"    {k:18s} {np.median(a):12.3f} {np.median(b):12.3f} {a.mean():11.3f} {b.mean():11.3f}")
    say("    hour-of-day (UTC) of continuation entries, eligible vs not, count | net:")
    for h0 in range(0, 24, 4):
        ea = [x for x in el if h0 <= x["f"]["hour"] < h0 + 4]
        na = [x for x in ne if h0 <= x["f"]["hour"] < h0 + 4]
        say(f"      {h0:02d}-{h0+4:02d}h  elig n {len(ea):3d} net {sum(x['pnl'] for x in ea):+7.2f} | not n {len(na):3d} net {sum(x['pnl'] for x in na):+7.2f}")

# ================= V1 historical (report only) =================
say("\n=== V1 (2026-09-08 07:12 -> 09-11, ALREADY CONSUMED, historical report only): 2h gate vs no gate ===")
O2, H2, L2, C2, T2 = A.load_m1(os.path.join(HERE, "..", "data", "m1_trial9_all.npz"))
from e007_lib import Pre2  # noqa: E402
P2 = Pre2(O2, H2, L2, C2, T2)
for g, gl in ((True, "2h gate"), (False, "no gate")):
    tr = [x for x in run(P2, tk, ENT, g) if x["t"] >= END + 60]
    say(f"  V1 {gl}: {line(stats(tr), '')}")
say("\ndone")
out.close()
