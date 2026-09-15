"""E026 - stop trading the Asian / Australian sessions (PREREG_E026.md).
Usage:
  python e026.py r0                       # R0 ticks + random-mask control
  python e026.py era <label> <m1.npz> <S> # consumed era, M1 pess mode
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
BLOCK_ASIA = set(list(range(21, 24)) + list(range(0, 9)))     # 21:00 -> 08:59
BLOCK_TOKYO = set(range(0, 9))                                # 00:00 -> 08:59


def say(s=""):
    print(s, flush=True)
    OUT.write(s + "\n")


def hour_of(P):
    return ((P.T // 3600) % 24).astype(int)


def run(P, tk, mask, mode, S):
    base = P.awake_sig.copy()
    if mask is not None:
        P.awake_sig = base & mask
    tr = A.simulate(P, mode, ENT, True, S=S, ticks=tk, min_dist=10)
    P.awake_sig = base
    return tr


def stats(tr, lo=None, hi=None):
    x = [t for t in tr if (lo is None or t["t"] >= lo) and (hi is None or t["t"] < hi)]
    if not x:
        return None
    p = np.array([t["pnl"] for t in x])
    g, l_ = p[p > 0].sum(), -p[p <= 0].sum()
    cum = np.cumsum(p)
    dd = np.max(np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum)
    return dict(n=len(x), net=p.sum(), pf=(g / l_ if l_ else float("inf")),
                wr=(p > 0).mean(), exp=p.mean(), dd=dd)


def line(tr, label, lo=None, hi=None):
    s = stats(tr, lo, hi)
    if s is None:
        say(f"  {label:<34s} n 0")
        return
    say(f"  {label:<34s} n {s['n']:5d} net {s['net']:+8.2f} PF {s['pf']:5.2f} "
        f"wr {s['wr']:4.0%} exp {s['exp']:+6.3f} maxDD {s['dd']:6.2f}")


def removed(ref, gated, label, lo=None, hi=None):
    keys = {(t["j"], t["kind"]) for t in gated}
    rem = [t for t in ref if (t["j"], t["kind"]) not in keys
           and (lo is None or t["t"] >= lo) and (hi is None or t["t"] < hi)]
    if rem:
        p = sum(t["pnl"] for t in rem)
        say(f"    {label}: {len(rem)} trades ecartes, leur P&L {p:+.2f} "
            f"(moyenne {p/len(rem):+.3f})")


def by_hour(tr, label):
    say(f"  {label} par heure UTC (net $ / n):")
    for blk in range(0, 24, 8):
        cells = []
        for h in range(blk, blk + 8):
            x = [t["pnl"] for t in tr if ((t["t"] // 3600) % 24) == h]
            tag = "*" if h in BLOCK_ASIA else " "
            cells.append(f"{h:02d}h{tag}{sum(x):+7.1f}/{len(x):<4d}")
        say("    " + " ".join(cells))
    say("    (* = heure bloquee par le filtre principal)")


def masks(P):
    hh = hour_of(P)
    return {
        "NO-ASIA (principal) 09-21h": ~np.isin(hh, list(BLOCK_ASIA)),
        "NO-TOKYO 09-24h": ~np.isin(hh, list(BLOCK_TOKYO)),
        "ASIA-ONLY (miroir)": np.isin(hh, list(BLOCK_ASIA)),
    }


if sys.argv[1] == "r0":
    OUT = open(os.path.join(HERE, "results_r0.txt"), "w", encoding="utf-8")
    O, H, L, C, T = A.load_m1(os.path.join(DATA, "pro_m1.npz"))
    P = Pre2(O, H, L, C, T)
    tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
    mk = masks(P)
    sig = P.sig_d != 0
    say("part des signaux laisses passer: " + ", ".join(
        f"{k.split()[0]} {m[sig].mean():.0%}" for k, m in mk.items()))
    base = run(P, tk, None, "tick", 7.0)
    runs = {"BASELINE (toutes heures)": base}
    for k, m in mk.items():
        runs[k] = run(P, tk, m, "tick", 7.0)
    for nm, lo, hi in (("TOUT R0", None, END), ("TRAIN (< 08-04)", None, MID),
                       ("TEST (08-04 -> 09-07)", MID, END)):
        say(f"\n=== {nm}, execution tick, net $ a 0.02 ===")
        for k, tr in runs.items():
            line(tr, k, lo, hi)
        removed(base, runs["NO-ASIA (principal) 09-21h"], "NO-ASIA", lo, hi)
    say("")
    by_hour(base, "BASELINE R0")
    say("\n=== PLACEBO: 200 masques aleatoires au meme taux de passage, M1 pess ===")
    prim = mk["NO-ASIA (principal) 09-21h"]
    rate = prim[sig].mean()
    real = sum(t["pnl"] for t in run(P, None, prim, "pess", 7.0) if t["t"] < END)
    rng = np.random.default_rng(26)
    sig_idx = np.where(sig)[0]
    nets = []
    for _ in range(NRAND):
        m = np.zeros(P.N, bool)
        m[sig_idx[rng.random(len(sig_idx)) < rate]] = True
        nets.append(sum(t["pnl"] for t in run(P, None, m, "pess", 7.0) if t["t"] < END))
    nets = np.array(nets)
    say(f"  taux {rate:.0%}: aleatoires moyenne {nets.mean():+.2f} ecart-type {nets.std():.2f} "
        f"95e {np.percentile(nets, 95):+.2f}; NO-ASIA {real:+.2f} au {(nets < real).mean()*100:.1f}e centile")
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
    mk = masks(P)
    sig = P.sig_d != 0
    say(f"{label}: part des signaux passes " + ", ".join(
        f"{k.split()[0]} {m[sig].mean():.0%}" for k, m in mk.items()))
    base = run(P, None, None, "pess", S)
    say(f"\n=== {label}, M1 pess, net $ a 0.02 ===")
    line(base, "BASELINE (toutes heures)")
    for k, m in mk.items():
        tr = run(P, None, m, "pess", S)
        line(tr, k)
        if k.startswith("NO-ASIA"):
            removed(base, tr, "NO-ASIA")
    say("")
    by_hour(base, f"BASELINE {label}")
    say("done")
    OUT.close()
