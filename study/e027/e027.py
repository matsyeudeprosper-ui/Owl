"""E027 - first BOS of a flip only, stop at the true lowest low of the leg
(PREREG_E027.md).  Usage:
  python e027.py r0                       # R0 ticks (TRAIN/TEST)
  python e027.py era <label> <m1.npz> <S> # consumed era, M1 pess mode
"""
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "audit"))
sys.path.insert(0, os.path.join(HERE, "..", "regime"))
import exec_audit as A  # noqa: E402
from bt_bos import Struct  # noqa: E402
from regime_features import Pre2  # noqa: E402

DATA = os.path.join(HERE, "..", "data")
MID = 1785880410
END = 1788851460


def say(s=""):
    print(s, flush=True)
    OUT.write(s + "\n")


def deep_stops(P):
    """For every signal bar, the stop taken from ALL raw candles of the leg
    (the dot only sees candles the silence filter kept). Span = the bar
    after the swing high/low that opened the leg, through the signal bar."""
    O, H, L, C, T = P.O, P.H, P.L, P.C, P.T
    N = P.N
    idx_of = {int(t): j for j, t in enumerate(T)}
    deep = np.full(N, np.nan)
    st = Struct()
    for j in range(N):
        # the leg anchors BEFORE this bar is processed: a buy signal's leg
        # starts at the swing HIGH, a sell signal's at the swing LOW
        ref_t = st.kept[st.hi_i][0] if st.kept and st.hi_i < len(st.kept) else None
        ref_lo_t = st.kept[st.lo_i][0] if st.kept and st.lo_i < len(st.kept) else None
        sig = st.step(int(T[j]), O[j], H[j], L[j], C[j])
        if sig is None:
            continue
        d = sig[0]
        anchor = ref_t if d == 1 else ref_lo_t
        if anchor is None:
            continue
        a = idx_of.get(int(anchor))
        if a is None or a + 1 > j:
            continue
        seg_lo, seg_hi = L[a + 1:j + 1], H[a + 1:j + 1]
        if len(seg_lo) == 0:
            continue
        deep[j] = seg_lo.min() if d == 1 else seg_hi.max()
    return deep


def run(P, tk, entries, sl_arr, mode, S, seed=None):
    base = P.sig_sl.copy()
    if sl_arr is not None:
        P.sig_sl = sl_arr
    tr = A.simulate(P, mode, entries, True, S=S, ticks=tk, min_dist=10, seed=seed)
    P.sig_sl = base
    return tr


def line(tr, label, lo=None, hi=None):
    x = [t for t in tr if (lo is None or t["t"] >= lo) and (hi is None or t["t"] < hi)]
    if not x:
        say(f"  {label:<36s} n 0")
        return
    p = np.array([t["pnl"] for t in x])
    g, l_ = p[p > 0].sum(), -p[p <= 0].sum()
    cum = np.cumsum(p)
    dd = np.max(np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum)
    say(f"  {label:<36s} n {x and len(x):5d} net {p.sum():+8.2f} PF {g/l_ if l_ else float('inf'):5.2f} "
        f"wr {(p>0).mean():4.0%} exp {p.mean():+6.3f} maxDD {dd:6.2f} "
        f"dist med {np.median([t['dist'] for t in x]):5.0f}")


def arms(P, tk, mode, S):
    deep = deep_stops(P)
    sig = P.sig_d != 0
    both = sig & ~np.isnan(deep)
    diff = np.abs(deep[both] - P.sig_sl[both])
    say(f"  signaux {int(sig.sum())}, stop profond calculable {int(both.sum())}; "
        f"il differe du point sur {float((diff > 0.01).mean()):.0%} des cas, "
        f"median {np.median(diff):.0f} pts plus loin (p90 {np.percentile(diff, 90):.0f})")
    out = {}
    out["BASELINE live (flip+cont, stop point)"] = run(P, tk, ("flip", "cont"), None, mode, S)
    out["FLIP seul, stop point"] = run(P, tk, ("flip",), None, mode, S)
    out["FLIP seul, stop profond (PRINCIPAL)"] = run(P, tk, ("flip",), deep, mode, S)
    out["flip+cont, stop profond"] = run(P, tk, ("flip", "cont"), deep, mode, S)
    out["PRINCIPAL direction aleatoire"] = run(P, tk, ("flip",), deep, mode, S, seed=27)
    return out


if sys.argv[1] == "r0":
    OUT = open(os.path.join(HERE, "results_r0.txt"), "w", encoding="utf-8")
    O, H, L, C, T = A.load_m1(os.path.join(DATA, "pro_m1.npz"))
    P = Pre2(O, H, L, C, T)
    tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
    runs = arms(P, tk, "tick", 7.0)
    for nm, lo, hi in (("TOUT R0", None, END), ("TRAIN (< 08-04)", None, MID),
                       ("TEST (08-04 -> 09-07)", MID, END)):
        say(f"\n=== {nm}, execution tick, net $ a 0.02 ===")
        for k, tr in runs.items():
            line(tr, k, lo, hi)
    say("done")
    OUT.close()
else:
    label, path, S = sys.argv[2], sys.argv[3], float(sys.argv[4])
    OUT = open(os.path.join(HERE, f"results_{label}.txt"), "w", encoding="utf-8")
    D = np.load(path)
    T = D["t"].astype(np.int64)
    if T[0] > 1e11:
        T = T // 1000
    P = Pre2(D["o"].astype(float), D["h"].astype(float), D["l"].astype(float), D["c"].astype(float), T)
    say(f"{label} bars {P.N}, S {S}")
    runs = arms(P, None, "pess", S)
    say(f"\n=== {label}, M1 pess, net $ a 0.02 ===")
    for k, tr in runs.items():
        line(tr, k)
    say("done")
    OUT.close()
