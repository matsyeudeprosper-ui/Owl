"""E024 - (a) the live config WITHOUT the 2h awake rule, and (b) the owner's
"touch resets the structure" rule: at each touch of the previous H1 candle's
high or low, every pending pattern is cleared and only a pattern that forms
AFTER the touch may be traded.  PREREG_E024.md.
Usage:
  python e024.py r0                       # R0 ticks (TRAIN/TEST) + random control
  python e024.py era <label> <m1.npz> <S> # consumed era, M1 pess mode
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
ENT = ("flip", "cont")
MID = 1785880410
END = 1788851460
NRAND = 200
WIN = 7200


def say(s=""):
    print(s, flush=True)
    OUT.write(s + "\n")


def touch_events(P):
    """First bar of each clock hour that reaches the PREVIOUS hour's high,
    and the first that reaches its low (at most two events per hour).
    Past-only: the reference hour is complete before the current one."""
    T, H, L = P.T, P.H, P.L
    N = len(T)
    hs = (T // 3600) * 3600
    starts = np.concatenate([[0], np.where(np.diff(hs) != 0)[0] + 1])
    ends = np.concatenate([starts[1:], [N]])
    h_t = hs[starts]
    h_hi = np.array([H[s:e].max() for s, e in zip(starts, ends)])
    h_lo = np.array([L[s:e].min() for s, e in zip(starts, ends)])
    ev = np.zeros(N, bool)
    for i, (s, e) in enumerate(zip(starts, ends)):
        k = int(np.searchsorted(h_t, h_t[i] - 3600))
        if k >= len(h_t) or h_t[k] != h_t[i] - 3600:
            continue
        up = np.where(H[s:e] >= h_hi[k])[0]
        dn = np.where(L[s:e] <= h_lo[k])[0]
        if len(up):
            ev[s + int(up[0])] = True
        if len(dn):
            ev[s + int(dn[0])] = True
    return ev


def rebuild_with_resets(P, ev):
    """Re-run the structure engine, wiping it at every touch event: the
    touch bar becomes the first bar of a brand-new pattern."""
    O, H, L, C, T = P.O, P.H, P.L, P.C, P.T
    N = P.N
    sig_d = np.zeros(N, np.int8)
    sig_sl = np.full(N, np.nan)
    sig_flip = np.zeros(N, bool)
    first_after = np.zeros(N, bool)      # first signal produced after a reset
    flips = []
    st = Struct()
    fresh = True
    for j in range(N):
        if ev[j]:
            st = Struct()
            fresh = True
        pt = st.trend
        sig = st.step(int(T[j]), O[j], H[j], L[j], C[j])
        if st.trend != pt and st.trend != 0 and pt != 0:
            flips.append(int(T[j]))
        if sig is not None:
            sig_d[j] = sig[0]
            sig_sl[j] = sig[1]
            if st.trend != pt:
                sig_flip[j] = True
            if fresh:
                first_after[j] = True
                fresh = False
    return sig_d, sig_sl, sig_flip, np.array(flips, np.int64), first_after


def awake_from(P, flips):
    T = P.T
    aw = np.zeros(P.N, bool)
    if len(flips):
        lo = np.searchsorted(flips, T - WIN)
        hi = np.searchsorted(flips, T, side="right")
        aw = hi > lo
    return aw


def apply(P, sig_d, sig_sl, sig_flip, aw):
    P.sig_d, P.sig_sl, P.sig_flip = sig_d, sig_sl, sig_flip
    P.awake_sig = aw
    P.awake_touch = aw


def snapshot(P):
    return (P.sig_d.copy(), P.sig_sl.copy(), P.sig_flip.copy(),
            P.awake_sig.copy(), P.awake_touch.copy())


def restore(P, s):
    P.sig_d, P.sig_sl, P.sig_flip, P.awake_sig, P.awake_touch = s


def line(tr, label, lo=None, hi=None):
    x = [t for t in tr if (lo is None or t["t"] >= lo) and (hi is None or t["t"] < hi)]
    if not x:
        say(f"  {label:<44s} n 0")
        return
    p = np.array([t["pnl"] for t in x])
    g = p[p > 0].sum()
    l_ = -p[p <= 0].sum()
    cum = np.cumsum(p)
    dd = np.max(np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum)
    fl = [t for t in x if t["kind"] == "flip"]
    co = [t for t in x if t["kind"] != "flip"]
    say(f"  {label:<44s} n {len(x):5d} net {p.sum():+8.2f} PF {g/l_ if l_ else float('inf'):5.2f} "
        f"wr {(p>0).mean():4.0%} exp {p.mean():+6.3f} maxDD {dd:6.2f} | "
        f"flips {len(fl):4d} {sum(t['pnl'] for t in fl):+7.2f} conts {len(co):4d} {sum(t['pnl'] for t in co):+7.2f}")


def arms(P, tk, mode, S):
    """Build every arm; returns {label: trades}."""
    base = snapshot(P)
    out = {}
    kw = dict(ticks=tk, min_dist=10, S=S)
    out["BASELINE live (porte 2h)"] = A.simulate(P, mode, ENT, True, **kw)
    out["SANS la regle des 2h"] = A.simulate(P, mode, ENT, False, **kw)
    ev = touch_events(P)
    sd, ss, sf, fl, fa = rebuild_with_resets(P, ev)
    n_ev = int(ev.sum())
    n_sig = int((sd != 0).sum())
    apply(P, sd, ss, sf, np.ones(P.N, bool))
    out["RESET au toucher, tous les signaux"] = A.simulate(P, mode, ENT, False, **kw)
    m = fa.copy()
    apply(P, sd, ss, sf, m)
    out["RESET au toucher, 1er signal seulement"] = A.simulate(P, mode, ENT, True, **kw)
    apply(P, sd, ss, sf, awake_from(P, fl))
    out["RESET au toucher + porte 2h"] = A.simulate(P, mode, ENT, True, **kw)
    restore(P, base)
    return out, n_ev, n_sig, int(fa.sum()), int((base[0] != 0).sum())


if sys.argv[1] == "r0":
    OUT = open(os.path.join(HERE, "results_r0.txt"), "w", encoding="utf-8")
    O, H, L, C, T = A.load_m1(os.path.join(DATA, "pro_m1.npz"))
    P = Pre2(O, H, L, C, T)
    tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
    runs, n_ev, n_sig, n_first, n_sig0 = arms(P, tk, "tick", 7.0)
    days = (P.T[-1] - P.T[0]) / 86400
    say(f"R0 bars {P.N} ({days:.0f} jours); touchers H1 (evenements) {n_ev} = {n_ev/days:.1f}/jour")
    say(f"signaux du moteur: normal {n_sig0}, avec RESET {n_sig} ({n_sig/max(n_sig0,1)-1:+.0%}), "
        f"dont premiers-apres-reset {n_first}")
    for nm, lo, hi in (("TOUT R0 (07-01 -> 09-07)", None, END),
                       ("TRAIN (< 08-04)", None, MID),
                       ("TEST (08-04 -> 09-07)", MID, END)):
        say(f"\n=== {nm}, execution tick, net $ a 0.02 ===")
        for k, tr in runs.items():
            line(tr, k, lo, hi)
    say("\n=== PLACEBO: 200 masques aleatoires au taux de passage du 1er-signal, mode M1 pess ===")
    ev = touch_events(P)
    sd, ss, sf, fl, fa = rebuild_with_resets(P, ev)
    base = snapshot(P)
    apply(P, sd, ss, sf, fa)
    real = sum(t["pnl"] for t in A.simulate(P, "pess", ENT, True, S=7.0, min_dist=10) if t["t"] < END)
    sig_idx = np.where(sd != 0)[0]
    rate = fa[sd != 0].mean()
    rng = np.random.default_rng(24)
    nets = []
    for _ in range(NRAND):
        m = np.zeros(P.N, bool)
        m[sig_idx[rng.random(len(sig_idx)) < rate]] = True
        apply(P, sd, ss, sf, m)
        nets.append(sum(t["pnl"] for t in A.simulate(P, "pess", ENT, True, S=7.0, min_dist=10) if t["t"] < END))
    restore(P, base)
    nets = np.array(nets)
    say(f"  masques aleatoires (taux {rate:.0%}): moyenne {nets.mean():+.2f} ecart-type {nets.std():.2f} "
        f"95e {np.percentile(nets, 95):+.2f}; RESET-1er {real:+.2f} au {(nets < real).mean()*100:.1f}e centile")
    np.save(os.path.join(HERE, "randmask_nets.npy"), nets)
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
    runs, n_ev, n_sig, n_first, n_sig0 = arms(P, None, "pess", S)
    days = (P.T[-1] - P.T[0]) / 86400
    say(f"{label} bars {P.N}, S {S}; touchers {n_ev} = {n_ev/days:.1f}/jour; "
        f"signaux normal {n_sig0} -> reset {n_sig}, premiers {n_first}")
    say(f"\n=== {label}, mode M1 pess, net $ a 0.02 ===")
    for k, tr in runs.items():
        line(tr, k)
    say("done")
    OUT.close()
