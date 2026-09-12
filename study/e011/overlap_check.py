"""E011 Phase 4: is the public Exness archive the same feed as our MT5 Pro
ticks? Data comparison first (July-Sept 2026 overlap), then the frozen
strategy on both feeds over the identical window. Output results_overlap.txt."""
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "e007"))
sys.path.insert(0, os.path.join(HERE, "..", "audit"))
from e007_lib import A, Pre2, real_flips, set_gate  # noqa: E402
from exness_import import to_m1  # noqa: E402

out = open(os.path.join(HERE, "results_overlap.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s)
    out.write(s + "\n")


D = os.path.join(HERE, "..", "data")
mt = np.load(os.path.join(D, "ticks_btcusd.npz"))
ar = np.load(os.path.join(HERE, "data", "archive_2026_07_09_ticks.npz"))
mt_t, mt_b, mt_a = mt["t"].astype(np.int64), mt["bid"], mt["ask"]
ar_t, ar_b, ar_a = ar["t"].astype(np.int64), ar["bid"], ar["ask"]
lo = max(mt_t[0], ar_t[0])
hi = min(mt_t[-1], ar_t[-1])
say(f"MT5 ticks: {len(mt_t)} {dt.datetime.utcfromtimestamp(mt_t[0]/1000)} -> {dt.datetime.utcfromtimestamp(mt_t[-1]/1000)}")
say(f"archive : {len(ar_t)} {dt.datetime.utcfromtimestamp(ar_t[0]/1000)} -> {dt.datetime.utcfromtimestamp(ar_t[-1]/1000)}")
say(f"overlap : {dt.datetime.utcfromtimestamp(lo/1000)} -> {dt.datetime.utcfromtimestamp(hi/1000)}")
m = (mt_t >= lo) & (mt_t <= hi)
n_ = (ar_t >= lo) & (ar_t <= hi)
mt_t, mt_b, mt_a = mt_t[m], mt_b[m], mt_a[m]
ar_t, ar_b, ar_a = ar_t[n_], ar_b[n_], ar_a[n_]
say(f"in overlap: MT5 {len(mt_t)} ticks, archive {len(ar_t)} ticks (ratio {len(ar_t)/len(mt_t):.4f})")

# ---- tick alignment: exact timestamp matches
common, i_mt, i_ar = np.intersect1d(mt_t, ar_t, return_indices=True)
say(f"exact timestamp (ms) matches: {len(common)} = {len(common)/len(mt_t):.2%} of MT5 ticks, {len(common)/len(ar_t):.2%} of archive ticks")
db = ar_b[i_ar] - mt_b[i_mt]
da = ar_a[i_ar] - mt_a[i_mt]
say(f"  on matched ticks: bid diff mean {db.mean():+.4f} | abs median {np.median(np.abs(db)):.4f} | abs p99 {np.percentile(np.abs(db),99):.4f} | max {np.abs(db).max():.2f} | "
    f"share identical {(np.abs(db) < 0.005).mean():.2%}")
say(f"  on matched ticks: ask diff mean {da.mean():+.4f} | abs median {np.median(np.abs(da)):.4f} | abs p99 {np.percentile(np.abs(da),99):.4f} | max {np.abs(da).max():.2f} | "
    f"share identical {(np.abs(da) < 0.005).mean():.2%}")
# unmatched ticks: how far is the nearest MT5 tick in time, and is the price the same?
un = np.setdiff1d(np.arange(len(ar_t)), i_ar)
if len(un):
    pos = np.searchsorted(mt_t, ar_t[un])
    pos = np.clip(pos, 1, len(mt_t) - 1)
    dprev = ar_t[un] - mt_t[pos - 1]
    dnext = mt_t[pos] - ar_t[un]
    near = np.minimum(dprev, dnext)
    say(f"  archive ticks without exact MT5 match: {len(un)} ({len(un)/len(ar_t):.2%}); nearest MT5 tick median {np.median(near):.0f} ms, p95 {np.percentile(near,95):.0f} ms, share within 1 s {(near <= 1000).mean():.1%}")
un2 = np.setdiff1d(np.arange(len(mt_t)), i_mt)
say(f"  MT5 ticks without exact archive match: {len(un2)} ({len(un2)/len(mt_t):.2%})")
# per-day counts
dmt = mt_t // 86400000
dar = ar_t // 86400000
days = np.unique(np.concatenate([dmt, dar]))
cm = np.array([(dmt == d).sum() for d in days])
ca = np.array([(dar == d).sum() for d in days])
r = ca / np.maximum(cm, 1)
say(f"  per-day tick-count ratio archive/MT5: median {np.median(r):.4f} min {r.min():.4f} max {r.max():.4f}; days with ratio < 0.95 or > 1.05: {int(((r < 0.95) | (r > 1.05)).sum())} of {len(days)}")
for d, a_, b_ in zip(days, cm, ca):
    if a_ == 0 or b_ == 0 or b_ / max(a_, 1) < 0.95 or b_ / max(a_, 1) > 1.05:
        say(f"     {dt.datetime.utcfromtimestamp(int(d)*86400).date()}: MT5 {a_} archive {b_}")
# spreads
for lbl, b_, a_ in (("MT5", mt_b, mt_a), ("archive", ar_b, ar_a)):
    sp = a_ - b_
    say(f"  {lbl:8s} spread: median {np.median(sp):.2f} mean {sp.mean():.3f} p95 {np.percentile(sp,95):.2f} max {sp.max():.2f} | share == 7.00: {(np.abs(sp-7) < 0.005).mean():.4%}")

# ---- M1 comparison
say("\n--- M1 (bid OHLC) built from each tick stream, vs the MT5 M1 bars (pro_m1.npz)")
T1, O1, H1, L1, C1, V1, S1 = to_m1(mt_t, mt_b, mt_a)
T2, O2, H2, L2, C2, V2, S2 = to_m1(ar_t, ar_b, ar_a)
pm = np.load(os.path.join(D, "pro_m1.npz"))
pt = pm["t"].astype(np.int64)
sel = (pt >= T1[0]) & (pt <= T1[-1])
pt, po, ph, pl, pc = pt[sel], pm["o"][sel], pm["h"][sel], pm["l"][sel], pm["c"][sel]


def cmp(TA, OA, HA, LA, CA, TB, OB, HB, LB, CB, la, lb):
    common, ia, ib = np.intersect1d(TA, TB, return_indices=True)
    say(f"  {la} vs {lb}: minutes {len(TA)} vs {len(TB)}; common {len(common)}; only-{la} {len(TA)-len(common)}; only-{lb} {len(TB)-len(common)}")
    for nm, xa, xb in (("open", OA, OB), ("high", HA, HB), ("low", LA, LB), ("close", CA, CB)):
        d = np.abs(xa[ia] - xb[ib])
        say(f"     {nm:5s}: identical {(d < 0.005).mean():.2%} | abs diff median {np.median(d):.3f} p99 {np.percentile(d,99):.3f} max {d.max():.2f} | bars with diff > 1.0: {(d > 1.0).sum()}")
    return common, ia, ib


cmp(pt, po, ph, pl, pc, T1, O1, H1, L1, C1, "MT5-M1", "MT5-ticks-M1")
cmp(pt, po, ph, pl, pc, T2, O2, H2, L2, C2, "MT5-M1", "archive-M1")
cmp(T1, O1, H1, L1, C1, T2, O2, H2, L2, C2, "MT5-ticks-M1", "archive-M1")
say("  market statistics (M1 from ticks):")
for lbl, T_, O_, H_, L_, C_ in (("MT5", T1, O1, H1, L1, C1), ("archive", T2, O2, H2, L2, C2)):
    rng = H_ - L_
    atr = np.convolve(rng, np.ones(14) / 14, "valid")
    day = T_ // 86400
    dcl = [C_[day == d][-1] for d in np.unique(day)]
    dret = np.diff(np.log(dcl))
    say(f"     {lbl:8s}: M1 range median {np.median(rng):.2f} mean {rng.mean():.2f} | ATR14 mean {atr.mean():.2f} | daily log-return sd {dret.std():.4f} | bars {len(T_)}")

# ---- frozen strategy on both feeds, identical window (the R0 bar range)
say("\n--- FROZEN STRATEGY on both feeds (candle-close config, 2h gate, tick execution, min_dist 10, flat 0.02), window = R0 bars")
r0 = np.load(os.path.join(D, "pro_m1.npz"))
t0, t1 = int(r0["t"][0]), int(r0["t"][-1])
res = {}
for lbl, (T_, O_, H_, L_, C_), (tt, bb, aa) in (("MT5", (T1, O1, H1, L1, C1), (mt_t, mt_b, mt_a)), ("archive", (T2, O2, H2, L2, C2), (ar_t, ar_b, ar_a))):
    s = (T_ >= t0) & (T_ <= t1)
    P = Pre2(O_[s].astype(float), H_[s].astype(float), L_[s].astype(float), C_[s].astype(float), T_[s].astype(np.int64))
    set_gate(P, real_flips(P), 7200)
    tk = A.Ticks(tt, bb, aa)
    tr = A.simulate(P, "tick", ("flip", "cont"), True, ticks=tk, min_dist=10)
    for x in tr:
        x["R"] = x["pnl"] / (x["dist"] * 0.02)
        x["time"] = tk.t[x["ti"]] / 1000
    res[lbl] = tr
    st = A.stats(tr, lbl)
    say("  " + A.fmt(st) + f" | sum R {sum(x['R'] for x in tr):+.1f}")
# reference: the R0 result on MT5 M1 bars + MT5 ticks (the audit's baseline)
P0 = Pre2(r0["o"].astype(float), r0["h"].astype(float), r0["l"].astype(float), r0["c"].astype(float), r0["t"].astype(np.int64))
set_gate(P0, real_flips(P0), 7200)
tr0 = A.simulate(P0, "tick", ("flip", "cont"), True, ticks=A.Ticks(mt["t"].astype(np.int64), mt["bid"], mt["ask"]), min_dist=10)
say("  " + A.fmt(A.stats(tr0, "reference (MT5 M1 bars + MT5 ticks)")))
# trade alignment MT5-ticks-M1 vs archive
a_, b_ = res["MT5"], res["archive"]
used = set()
pairs = []
for x in a_:
    best = None
    for k, y in enumerate(b_):
        if k in used or y["d"] != x["d"]:
            continue
        if abs(y["time"] - x["time"]) <= 120:
            if best is None or abs(y["time"] - x["time"]) < abs(b_[best]["time"] - x["time"]):
                best = k
    if best is not None:
        used.add(best)
        pairs.append((x, b_[best]))
same_kind = sum(1 for x, y in pairs if x["kind"] == y["kind"])
same_out = sum(1 for x, y in pairs if (x["pnl"] > 0) == (y["pnl"] > 0))
de = np.array([y["e"] - x["e"] for x, y in pairs])
ds = np.array([y["sl"] - x["sl"] for x, y in pairs])
dp = np.array([y["pnl"] - x["pnl"] for x, y in pairs])
say(f"  trade alignment (same direction, entry within 120 s): matched {len(pairs)} of MT5 {len(a_)} / archive {len(b_)}; same kind {same_kind}; same outcome {same_out}; "
    f"entry diff abs median {np.median(np.abs(de)):.2f} max {np.abs(de).max():.2f}; SL diff abs median {np.median(np.abs(ds)):.2f} max {np.abs(ds).max():.2f}; "
    f"P&L diff mean {dp.mean():+.3f} abs median {np.median(np.abs(dp)):.3f}")
say(f"  MT5-only trades: {len(a_)-len(pairs)} (P&L {sum(x['pnl'] for x in a_) - sum(x['pnl'] for x, y in pairs):+.2f}); archive-only: {len(b_)-len(pairs)} (P&L {sum(y['pnl'] for y in b_) - sum(y['pnl'] for x, y in pairs):+.2f})")
say("\ndone")
out.close()
