"""E007 part 3b: 1000 random circular shifts of the real flip timeline.
Each placebo keeps the same number and clustering of flip events; the
2h continuation-eligibility rule is applied to the shifted events
(flips themselves stay eligible, as in every arm). Tick execution.
Output: results_placebo.txt + placebo_nets.npy (train, test, full, share)."""
import os
import sys
import time

import numpy as np

from e007_lib import MID, circ_shift, elig_share, load_all, real_flips, run, set_gate, stats

HERE = os.path.dirname(os.path.abspath(__file__))
NS = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
out = open(os.path.join(HERE, "results_placebo.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")
    out.flush()


P, tk = load_all()
FL = real_flips(P)
T0, T1 = int(P.T[0]), int(P.T[-1])
set_gate(P, FL, 7200)
tr = run(P, tk)
real = (stats(tr, None, MID)["net"], stats(tr, MID, None)["net"], stats(tr)["net"], elig_share(P))
say(f"REAL 2h gate: train {real[0]:+.2f} test {real[1]:+.2f} full {real[2]:+.2f} eligible share {real[3]:.3f}")
rng = np.random.default_rng(2026)
res = []
t0 = time.time()
for i in range(NS):
    d = int(rng.integers(3 * 3600, (T1 - T0) - 3 * 3600))
    set_gate(P, circ_shift(FL, T0, T1, d), 7200)
    tr = run(P, tk)
    res.append((stats(tr, None, MID)["net"], stats(tr, MID, None)["net"], stats(tr)["net"], elig_share(P)))
    if (i + 1) % 100 == 0:
        a = np.array(res)
        say(f"  {i+1} shifts: train mean {a[:,0].mean():+.2f} test mean {a[:,1].mean():+.2f} full mean {a[:,2].mean():+.2f} "
            f"share mean {a[:,3].mean():.3f}  [{time.time()-t0:.0f}s]")
a = np.array(res)
np.save(os.path.join(HERE, "placebo_nets.npy"), a)
for k, lbl in enumerate(("TRAIN", "TEST", "FULL")):
    v = a[:, k]
    say(f"{lbl}: real {real[k]:+8.2f} | placebo mean {v.mean():+7.2f} sd {v.std():6.2f} p5 {np.percentile(v,5):+7.2f} "
        f"p50 {np.percentile(v,50):+7.2f} p95 {np.percentile(v,95):+7.2f} max {v.max():+7.2f} "
        f"| real beats {(v < real[k]).mean():.1%} | z {(real[k]-v.mean())/v.std():+.2f}")
say(f"eligible share: real {real[3]:.3f} | placebo mean {a[:,3].mean():.3f} sd {a[:,3].std():.3f}")
say("done")
out.close()
