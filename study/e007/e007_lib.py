"""E007 shared pieces: baseline engine + a parameterised awake gate.

Gate semantics (identical to production for the real flip list): a
continuation signal at bar j is eligible iff an event lies in
[T[j] - win, T[j]]; a FLIP-BOS signal is always eligible because its own
flip is an event at T[j]. For placebo event lists the own-flip allowance
is kept explicitly (P.ev_flip[j]) so flips are treated the same way in
every arm and only the CONTINUATION eligibility is being tested.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "audit"))
sys.path.insert(0, os.path.join(HERE, "..", "regime"))
import exec_audit as A  # noqa: E402
from regime_features import Pre2, features  # noqa: E402

DATA = os.path.join(HERE, "..", "data")
ENT = ("flip", "cont")
sp = dict(l.strip().split("=") for l in open(os.path.join(HERE, "..", "regime", "split.txt")))
MID = int(sp["mid"])
END = int(sp["research_end"])


def load_all():
    O, H, L, C, T = A.load_m1(os.path.join(DATA, "pro_m1.npz"))
    P = Pre2(O, H, L, C, T)
    tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
    return P, tk


def set_gate(P, events, win):
    """Recompute P.awake_sig from an arbitrary sorted event-time array."""
    F = np.asarray(sorted(events), np.int64)
    T = P.T
    aw = np.zeros(P.N, bool)
    if len(F):
        lo = np.searchsorted(F, T - win)                 # first event >= T-win
        hi = np.searchsorted(F, T, side="right")         # events <= T
        aw = hi > lo
    P.awake_sig = aw | P.ev_flip                          # own flip always eligible
    P.awake_touch = aw                                    # unused (no touch in this config)


def real_flips(P):
    return P.T[P.ev_flip].astype(np.int64)


def circ_shift(events, T0, T1, delta):
    span = T1 - T0
    return np.sort(T0 + ((events - T0 + delta) % span))


def run(P, tk, entries=ENT, gate=True):
    return A.simulate(P, "tick", entries, gate, ticks=tk, min_dist=10)


def stats(tr, t_lo=None, t_hi=None):
    return A.stats(tr, "", t_lo, t_hi)


def line(s, label=""):
    if s.get("n", 0) == 0:
        return f"{label:28s} n    0"
    return (f"{label:28s} n {s['n']:4d} wr {s['wr']:5.1%} net {s['net']:+8.2f} PF {s['pf']:4.2f} "
            f"exp {s['exp']:+.3f} maxDD {s['mdd']:6.2f} | flip {s['n_flip']:3d} {s['net_flip']:+7.2f} "
            f"cont {s['n']-s['n_flip']-s['n_touch']:3d} {s['net']-s['net_flip']-s['net_touch']:+7.2f}")


def elig_share(P):
    """Share of continuation signal bars that the current gate lets through."""
    cont = (P.sig_d != 0) & (~P.sig_flip)
    return float(P.awake_sig[cont].mean()) if cont.any() else float("nan")
