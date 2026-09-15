"""E023 - replace the 2h "awake" gate with a previous-H1 high/low touch gate
(PREREG_E023.md). Usage:
  python e023.py r0                       # R0 ticks + random-mask control
  python e023.py era <label> <m1.npz> <S> # consumed era, M1 pess mode
"""
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "audit"))
sys.path.insert(0, os.path.join(HERE, "..", "regime"))
import exec_audit as A  # noqa: E402
from regime_features import Pre2  # noqa: E402

DATA = os.path.join(HERE, "..", "data")
ENT = ("flip", "cont")
MID = 1785880410
END = 1788851460
NRAND = 200


def say(s=""):
    print(s, flush=True)
    OUT.write(s + "\n")


def h1_touch_masks(P):
    """armed_hour / armed_2h: has price touched the PREVIOUS clock hour's
    high or low? Past-only: the reference comes from the completed hour
    before the one containing T[j]; a touch inside bar j counts at its
    close, which is when the signal is taken."""
    T, H, L = P.T, P.H, P.L
    N = len(T)
    hs = (T // 3600) * 3600
    starts = np.concatenate([[0], np.where(np.diff(hs) != 0)[0] + 1])
    ends = np.concatenate([starts[1:], [N]])
    h_t = hs[starts]
    h_hi = np.array([H[s:e].max() for s, e in zip(starts, ends)])
    h_lo = np.array([L[s:e].min() for s, e in zip(starts, ends)])
    ref_hi = np.full(N, np.nan)
    ref_lo = np.full(N, np.nan)
    for i, (s, e) in enumerate(zip(starts, ends)):
        k = int(np.searchsorted(h_t, h_t[i] - 3600))       # the hour before
        if k < len(h_t) and h_t[k] == h_t[i] - 3600:
            ref_hi[s:e] = h_hi[k]
            ref_lo[s:e] = h_lo[k]
    touched = (~np.isnan(ref_hi)) & ((H >= ref_hi) | (L <= ref_lo))
    # A: armed from the first touch of the current hour to the end of it
    armed_hour = np.zeros(N, bool)
    for s, e in zip(starts, ends):
        t = touched[s:e]
        if t.any():
            armed_hour[s + int(np.argmax(t)):e] = True
    # B: armed if a touch happened within the last 120 minutes
    tt = np.where(touched)[0]
    armed_2h = np.zeros(N, bool)
    if len(tt):
        T_touch = T[tt]
        lo = np.searchsorted(T_touch, T - 7200, side="left")
        hi = np.searchsorted(T_touch, T, side="right")
        armed_2h = hi > lo
    return armed_hour, armed_2h, touched


def run(P, tk, mask=None, mode="tick", S=7.0, gate=True):
    base = P.awake_sig.copy()
    if mask is not None:
        P.awake_sig = mask
    tr = A.simulate(P, mode, ENT, gate, S=S, ticks=tk, min_dist=10)
    P.awake_sig = base
    return tr


def cellstats(tr, lo=None, hi=None):
    x = [t for t in tr if (lo is None or t["t"] >= lo) and (hi is None or t["t"] < hi)]
    if not x:
        return None
    p = np.array([t["pnl"] for t in x])
    g = p[p > 0].sum()
    l_ = -p[p <= 0].sum()
    cum = np.cumsum(p)
    dd = np.max(np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum)
    fl = [t for t in x if t["kind"] == "flip"]
    co = [t for t in x if t["kind"] != "flip"]
    return dict(n=len(x), net=p.sum(), pf=(g / l_ if l_ else float("inf")),
                wr=(p > 0).mean(), exp=p.mean(), dd=dd,
                nf=len(fl), pf_net=sum(t["pnl"] for t in fl),
                nc=len(co), pc_net=sum(t["pnl"] for t in co))


def line(tr, label, lo=None, hi=None):
    s = cellstats(tr, lo, hi)
    if s is None:
        say(f"  {label:<40s} n 0")
        return
    say(f"  {label:<40s} n {s['n']:5d} net {s['net']:+8.2f} PF {s['pf']:5.2f} "
        f"wr {s['wr']:4.0%} exp {s['exp']:+6.3f} maxDD {s['dd']:6.2f} | "
        f"flips {s['nf']:4d} {s['pf_net']:+7.2f} conts {s['nc']:4d} {s['pc_net']:+7.2f}")


def removed(ref_tr, gated_tr, label, lo=None, hi=None):
    keys = {(t["j"], t["kind"]) for t in gated_tr}
    rem = [t for t in ref_tr if (t["j"], t["kind"]) not in keys
           and (lo is None or t["t"] >= lo) and (hi is None or t["t"] < hi)]
    if rem:
        say(f"    {label}: {len(rem)} trades ecartes vs NOGATE, leur P&L {sum(t['pnl'] for t in rem):+.2f}")


def build(P):
    ah, a2, touched = h1_touch_masks(P)
    sig = P.sig_d != 0
    return {
        "A/all  touch -> fin d'heure (tous)": ah,
        "A/cont touch -> fin d'heure (PRIMAIRE)": ah | P.ev_flip,
        "B/all  touch -> 2 h (tous)": a2,
        "B/cont touch -> 2 h": a2 | P.ev_flip,
    }, ah, a2, touched, sig


if sys.argv[1] == "r0":
    OUT = open(os.path.join(HERE, "results_r0.txt"), "w", encoding="utf-8")
    O, H, L, C, T = A.load_m1(os.path.join(DATA, "pro_m1.npz"))
    P = Pre2(O, H, L, C, T)
    tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
    arms, ah, a2, touched, sig = build(P)
    say(f"R0 bars {P.N}; barres qui touchent le haut/bas H1 precedent: {touched.mean():.0%}; "
        f"armed fin-d'heure {ah.mean():.0%} des barres, armed 2h {a2.mean():.0%}")
    say("part des SIGNAUX laisses passer: " + ", ".join(
        f"{k.split()[0]} {m[sig].mean():.0%}" for k, m in arms.items())
        + f", porte actuelle 2h-flip {P.awake_sig[sig].mean():.0%}")
    runs = {"BASELINE porte 2h-flip (live)": run(P, tk),
            "NOGATE aucune porte": run(P, tk, None, "tick", 7.0, False)}
    for k, m in arms.items():
        runs[k] = run(P, tk, m)
    for nm, lo, hi in (("TOUT R0 (07-01 -> 09-07)", None, END),
                       ("TRAIN (< 08-04)", None, MID),
                       ("TEST (08-04 -> 09-07)", MID, END)):
        say(f"\n=== {nm}, execution tick, net $ a 0.02 ===")
        for k, tr in runs.items():
            line(tr, k, lo, hi)
        removed(runs["NOGATE aucune porte"], runs["A/cont touch -> fin d'heure (PRIMAIRE)"], "PRIMAIRE", lo, hi)
        removed(runs["NOGATE aucune porte"], runs["BASELINE porte 2h-flip (live)"], "baseline 2h", lo, hi)
    say("\n=== PLACEBO: 200 masques aleatoires au meme taux de passage que le primaire, mode M1 pess ===")
    prim = arms["A/cont touch -> fin d'heure (PRIMAIRE)"]
    base_p = run(P, None, None, "pess")
    prim_p = run(P, None, prim, "pess")
    line(base_p, "BASELINE pess", None, END)
    line(prim_p, "PRIMAIRE pess", None, END)
    rate = prim[sig].mean()
    rng = np.random.default_rng(23)
    sig_idx = np.where(sig)[0]
    nets = []
    for _ in range(NRAND):
        m = P.ev_flip.copy()
        m[sig_idx[rng.random(len(sig_idx)) < rate]] = True
        nets.append(sum(t["pnl"] for t in run(P, None, m, "pess") if t["t"] < END))
    nets = np.array(nets)
    real = sum(t["pnl"] for t in prim_p if t["t"] < END)
    say(f"  masques aleatoires: moyenne {nets.mean():+.2f} ecart-type {nets.std():.2f} "
        f"95e {np.percentile(nets, 95):+.2f}; PRIMAIRE {real:+.2f} au {(nets < real).mean()*100:.1f}e centile")
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
    arms, ah, a2, touched, sig = build(P)
    say(f"{label} bars {P.N}, S {S}; part des signaux passes: " + ", ".join(
        f"{k.split()[0]} {m[sig].mean():.0%}" for k, m in arms.items())
        + f", porte actuelle {P.awake_sig[sig].mean():.0%}")
    say(f"\n=== {label}, mode M1 pess, net $ a 0.02 ===")
    nog = run(P, None, None, "pess", S, False)
    line(nog, "NOGATE aucune porte")
    line(run(P, None, None, "pess", S), "BASELINE porte 2h-flip")
    for k, m in arms.items():
        line(run(P, None, m, "pess", S), k)
    say("done")
    OUT.close()
