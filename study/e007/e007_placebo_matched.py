"""E007 part 3c: COVERAGE-MATCHED placebo.

Plain circular shifts of the flip timeline keep the number and clustering
of flip events but NOT the eligibility coverage: real flips are causally
aligned with continuation signals (a flip starts the trend whose
continuations follow), so a shifted timeline lets only ~40-44% of
continuation signals through against 61% for the real one. A gate that
simply admits fewer trades is not a fair null.

Here each shifted timeline gets its own window W(delta), found by
bisection on [10 min, 48 h], such that the eligible share of continuation
signal bars equals the real 2h gate's share (61%). The null is therefore:
"same events, same clustering, same coverage, wrong alignment".
Output: results_placebo_matched.txt + placebo_matched.npy."""
import os
import sys
import time

import numpy as np

from e007_lib import MID, circ_shift, elig_share, load_all, real_flips, run, set_gate, stats

HERE = os.path.dirname(os.path.abspath(__file__))
NS = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
out = open(os.path.join(HERE, "results_placebo_matched.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")
    out.flush()


P, tk = load_all()
FL = real_flips(P)
T0, T1 = int(P.T[0]), int(P.T[-1])
set_gate(P, FL, 7200)
target = elig_share(P)
tr = run(P, tk)
real = (stats(tr, None, MID)["net"], stats(tr, MID, None)["net"], stats(tr)["net"], target, 7200)
say(f"REAL 2h gate: train {real[0]:+.2f} test {real[1]:+.2f} full {real[2]:+.2f} eligible share {target:.3f}")


def matched_window(ev):
    lo, hi = 600, 48 * 3600
    for _ in range(18):
        mid = (lo + hi) // 2
        set_gate(P, ev, mid)
        if elig_share(P) < target:
            lo = mid
        else:
            hi = mid
    set_gate(P, ev, hi)
    return hi


rng = np.random.default_rng(777)
res = []
t0 = time.time()
for i in range(NS):
    d = int(rng.integers(3 * 3600, (T1 - T0) - 3 * 3600))
    ev = circ_shift(FL, T0, T1, d)
    W = matched_window(ev)
    tr = run(P, tk)
    res.append((stats(tr, None, MID)["net"], stats(tr, MID, None)["net"], stats(tr)["net"], elig_share(P), W))
    if (i + 1) % 100 == 0:
        a = np.array(res)
        say(f"  {i+1}: train mean {a[:,0].mean():+.2f} test mean {a[:,1].mean():+.2f} full mean {a[:,2].mean():+.2f} "
            f"share mean {a[:,3].mean():.3f} W median {np.median(a[:,4])/60:.0f} min  [{time.time()-t0:.0f}s]")
a = np.array(res)
np.save(os.path.join(HERE, "placebo_matched.npy"), a)
for k, lbl in enumerate(("TRAIN", "TEST", "FULL")):
    v = a[:, k]
    say(f"{lbl}: real {real[k]:+8.2f} | matched placebo mean {v.mean():+7.2f} sd {v.std():6.2f} p5 {np.percentile(v,5):+7.2f} "
        f"p50 {np.percentile(v,50):+7.2f} p95 {np.percentile(v,95):+7.2f} max {v.max():+7.2f} "
        f"| real beats {(v < real[k]).mean():.1%} | z {(real[k]-v.mean())/v.std():+.2f}")
say(f"eligible share: real {target:.3f} | placebo mean {a[:,3].mean():.3f} sd {a[:,3].std():.3f} | matched W: median "
    f"{np.median(a[:,4])/60:.0f} min, p5 {np.percentile(a[:,4],5)/60:.0f}, p95 {np.percentile(a[:,4],95)/60:.0f}")
say("done")
out.close()
