"""E022 - previous-H1 direction gate on the live BOS configuration (PREREG_E022.md).
Usage:
  python e022.py r0                       # R0 ticks (TRAIN/TEST/V1) + random-mask control (pess)
  python e022.py era <label> <m1.npz> <S> # consumed era, M1 pess mode with spread S
"""
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "audit"))
sys.path.insert(0, os.path.join(HERE, "..", "regime"))
sys.path.insert(0, os.path.join(HERE, "..", "e007"))
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


def h1_prev(P):
    """Previous completed clock-hour candle for each bar: (dir, close). Past-only."""
    T, O, C = P.T, P.O, P.C
    hs = (T // 3600) * 3600
    N = len(T)
    starts = np.concatenate([[0], np.where(np.diff(hs) != 0)[0] + 1])
    h_t = hs[starts]
    h_o = O[starts]
    h_c = C[np.concatenate([starts[1:], [N]]) - 1]
    d = np.zeros(N, np.int8)
    cl = np.full(N, np.nan)
    for j in range(N):
        k = int(np.searchsorted(h_t, hs[j] - 3600))          # hour before the current one
        if k < len(h_t) and h_t[k] == hs[j] - 3600:
            cl[j] = h_c[k]
            d[j] = 1 if h_c[k] > h_o[k] else (-1 if h_c[k] < h_o[k] else 0)
    return d, cl


def masks(P):
    d, cl = h1_prev(P)
    sd = P.sig_d
    r1 = (sd != 0) & (d == sd)
    r2 = r1 & np.where(sd == 1, P.C > cl, P.C < cl)
    p1 = (sd != 0) & (d == -sd)
    return r1, r2, p1


def run(P, tk, mask=None, mode="tick", S=7.0):
    base = P.awake_sig.copy()
    if mask is not None:
        P.awake_sig = base & mask
    tr = A.simulate(P, mode, ENT, True, S=S, ticks=tk, min_dist=10)
    P.awake_sig = base
    return tr


def st(tr, lo=None, hi=None):
    s = A.stats(tr, "", lo, hi)
    return s


def line(tr, label, lo=None, hi=None):
    x = [t for t in tr if (lo is None or t["t"] >= lo) and (hi is None or t["t"] < hi)]
    if not x:
        say(f"  {label:<40s} n 0")
        return
    p = np.array([t["pnl"] for t in x])
    g = p[p > 0].sum(); l_ = -p[p <= 0].sum()
    cum = np.cumsum(p); dd = np.max(np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum)
    fl = [t for t in x if t["kind"] == "flip"]; co = [t for t in x if t["kind"] != "flip"]
    say(f"  {label:<40s} n {len(x):5d} net {p.sum():+8.2f} PF {g/l_ if l_ else float('inf'):5.2f} wr {(p>0).mean():4.0%} exp {p.mean():+6.3f} maxDD {dd:6.2f} | flips {len(fl)} {sum(t['pnl'] for t in fl):+7.2f} conts {len(co)} {sum(t['pnl'] for t in co):+7.2f}")


def removed(base_tr, gated_tr, label, lo=None, hi=None):
    keys = {(t["j"], t["kind"]) for t in gated_tr}
    rem = [t for t in base_tr if (t["j"], t["kind"]) not in keys and (lo is None or t["t"] >= lo) and (hi is None or t["t"] < hi)]
    say(f"    {label}: trades removed by the gate {len(rem)}, their P&L {sum(t['pnl'] for t in rem):+.2f}")


if sys.argv[1] == "r0":
    OUT = open(os.path.join(HERE, "results_r0.txt"), "w", encoding="utf-8")
    O, H, L, C, T = A.load_m1(os.path.join(DATA, "pro_m1.npz"))
    P = Pre2(O, H, L, C, T)
    tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
    r1, r2, p1 = masks(P)
    sig = P.sig_d != 0
    say(f"R0 M1 bars {P.N}; signal bars {sig.sum()}; pass share: R1 {r1[sig].mean():.0%}, R2 {r2[sig].mean():.0%}, P1 {p1[sig].mean():.0%}")
    runs = {"BASELINE (frozen live config)": run(P, tk), "R1 H1 direction only": run(P, tk, r1),
            "R2 direction + beyond H1 close (OWNER)": run(P, tk, r2), "P1 opposite direction (placebo)": run(P, tk, p1)}
    for nm, lo, hi in (("ALL R0 (07-01 -> 09-07)", None, END), ("TRAIN (< 08-04)", None, MID), ("TEST (08-04 -> 09-07)", MID, END), ("V1 tail (09-07 -> 09-11)", END, None)):
        say(f"\n=== {nm}, tick execution, net $ at 0.02 ===")
        for k, tr in runs.items():
            line(tr, k, lo, hi)
        removed(runs["BASELINE (frozen live config)"], runs["R2 direction + beyond H1 close (OWNER)"], "R2", lo, hi)
        removed(runs["BASELINE (frozen live config)"], runs["R1 H1 direction only"], "R1", lo, hi)
    # random-mask control in pess mode
    say("\n=== P2 random masks (same pass rate as R2 on signal bars), M1 pess mode, ALL R0 ===")
    base_p = run(P, None, None, "pess"); r2_p = run(P, None, r2, "pess"); r1_p = run(P, None, r1, "pess"); p1_p = run(P, None, p1, "pess")
    line(base_p, "baseline pess", None, END); line(r1_p, "R1 pess", None, END); line(r2_p, "R2 pess", None, END); line(p1_p, "P1 pess", None, END)
    rate = r2[sig].mean()
    rng = np.random.default_rng(22)
    nets = []
    sig_idx = np.where(sig)[0]
    for _ in range(NRAND):
        m = np.zeros(P.N, bool)
        m[sig_idx[rng.random(len(sig_idx)) < rate]] = True
        tr = run(P, None, m, "pess")
        nets.append(sum(t["pnl"] for t in tr if t["t"] < END))
    nets = np.array(nets)
    real = sum(t["pnl"] for t in r2_p if t["t"] < END)
    say(f"  random masks: mean {nets.mean():+.2f} sd {nets.std():.2f} 95th {np.percentile(nets,95):+.2f}; R2 pess {real:+.2f} at {(nets < real).mean()*100:.1f}th pct; R1 pess {sum(t['pnl'] for t in r1_p if t['t'] < END):+.2f} at {(nets < sum(t['pnl'] for t in r1_p if t['t'] < END)).mean()*100:.1f}th pct")
    np.save(os.path.join(HERE, "randmask_nets.npy"), nets)
    say("done"); OUT.close()
else:
    label, path, S = sys.argv[2], sys.argv[3], float(sys.argv[4])
    OUT = open(os.path.join(HERE, f"results_{label}.txt"), "w", encoding="utf-8")
    D = np.load(path)
    T = D["t"].astype(np.int64)
    if T[0] > 1e11:
        T = T // 1000
    P = Pre2(D["o"].astype(float), D["h"].astype(float), D["l"].astype(float), D["c"].astype(float), T)
    r1, r2, p1 = masks(P)
    sig = P.sig_d != 0
    say(f"{label} M1 bars {P.N}, S {S}; signal bars {sig.sum()}; pass share: R1 {r1[sig].mean():.0%}, R2 {r2[sig].mean():.0%}, P1 {p1[sig].mean():.0%}")
    say(f"\n=== {label}, M1 pess mode, net $ at 0.02 ===")
    base = run(P, None, None, "pess", S)
    line(base, "BASELINE")
    g1 = run(P, None, r1, "pess", S); line(g1, "R1 direction only")
    g2 = run(P, None, r2, "pess", S); line(g2, "R2 direction + beyond close (OWNER)")
    g3 = run(P, None, p1, "pess", S); line(g3, "P1 opposite (placebo)")
    removed(base, g2, "R2")
    half = int((T[0] + T[-1]) // 2)
    say(f"  halves (R2 / baseline / P1): H1 {sum(t['pnl'] for t in g2 if t['t'] < half):+.2f} / {sum(t['pnl'] for t in base if t['t'] < half):+.2f} / {sum(t['pnl'] for t in g3 if t['t'] < half):+.2f} | H2 {sum(t['pnl'] for t in g2 if t['t'] >= half):+.2f} / {sum(t['pnl'] for t in base if t['t'] >= half):+.2f} / {sum(t['pnl'] for t in g3 if t['t'] >= half):+.2f}")
    say("done"); OUT.close()
