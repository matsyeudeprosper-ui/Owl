"""E011 random-direction control for an era (frozen control of the audit):
same signal stream, direction coin-flipped per trade, SL/TP mirrored at the
same distances, full re-simulation (one-position coupling preserved), tick
execution with the actual spread. Parallel over processes.
usage: python e011_control.py <ERA> <ticks.npz> [NS=1000] [PROCS=5]
Output: control_<ERA>.txt + control_<ERA>.npy (net $, sum R per seed)."""
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "e007"))
sys.path.insert(0, os.path.join(HERE, "..", "audit"))

_G = {}


MODE = "tick"


def _init(ticks_path, mode="tick"):
    from e007_lib import A, Pre2, real_flips, set_gate
    from exness_import import to_m1
    if os.path.isdir(ticks_path):
        from compact_ticks import load_dir, load_m1
        if mode == "tick":
            t, b, a = load_dir(ticks_path)
            T, O, H, L, C, V, SP = to_m1(t, b, a)
        else:
            O, H, L, C, T = load_m1(ticks_path)
            M = np.load(os.path.join(ticks_path, "m1.npz"))
            _G["S"] = float(np.median(M["sp"]))
            t = b = a = None
    else:
        D = np.load(ticks_path)
        t, b, a = D["t"].astype(np.int64), D["bid"].astype(float), D["ask"].astype(float)
        T, O, H, L, C, V, SP = to_m1(t, b, a)
        _G["S"] = float(np.median(a - b))
    P = Pre2(O, H, L, C, T)
    set_gate(P, real_flips(P), 7200)
    _G["A"], _G["P"], _G["mode"] = A, P, mode
    _G["tk"] = A.Ticks(t, b, a) if mode == "tick" else None


def _one(seed):
    A, P, tk = _G["A"], _G["P"], _G["tk"]
    if _G["mode"] == "tick":
        tr = A.simulate(P, "tick", ("flip", "cont"), True, ticks=tk, min_dist=10, seed=seed)
    else:
        tr = A.simulate(P, "pess", ("flip", "cont"), True, S=_G["S"], min_dist=10, seed=seed)
    return (sum(x["pnl"] for x in tr), sum(x["pnl"] / (x["dist"] * 0.02) for x in tr), len(tr))


if __name__ == "__main__":
    era, ticks = sys.argv[1], sys.argv[2]
    NS = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    PROCS = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    MODE = sys.argv[5] if len(sys.argv) > 5 else "tick"
    _init(ticks, MODE)
    real = _one(None)
    t0 = time.time()
    with Pool(PROCS, initializer=_init, initargs=(ticks, MODE)) as pool:
        res = pool.map(_one, range(100000, 100000 + NS), chunksize=10)
    a = np.array(res)
    tag = era if MODE == "tick" else f"{era}_m1"
    np.save(os.path.join(HERE, f"control_{tag}.npy"), a)
    with open(os.path.join(HERE, f"control_{tag}.txt"), "w") as f:
        for k, lbl in ((0, "net $"), (1, "sum R")):
            v = a[:, k]
            line = (f"{era} [{MODE}] {lbl}: real {real[k]:+8.2f} | random mean {v.mean():+8.2f} sd {v.std():7.2f} p95 {np.percentile(v,95):+8.2f} max {v.max():+8.2f} "
                    f"| real beats {(v < real[k]).mean():.1%} | z {(real[k]-v.mean())/v.std():+.2f}  (n seeds {NS}, real trades {real[2]}, {time.time()-t0:.0f}s)")
            print(line)
            f.write(line + "\n")
