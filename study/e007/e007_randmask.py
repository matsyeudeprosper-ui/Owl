"""E007 part 3d: RANDOM-ELIGIBILITY control (third null).

Null: "admit a random 61% of continuation signals" - no flip timeline at
all, just the same coverage as the real 2h gate, drawn independently per
continuation signal bar. Flips always eligible, as in every arm. If the
real gate's value comes from WHICH continuations it admits (young trends)
rather than from admitting fewer of them, it must beat this null too.
Output: results_randmask.txt + randmask.npy."""
import os
import sys
import time

import numpy as np

from e007_lib import MID, elig_share, load_all, real_flips, run, set_gate, stats

HERE = os.path.dirname(os.path.abspath(__file__))
NS = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
out = open(os.path.join(HERE, "results_randmask.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")
    out.flush()


P, tk = load_all()
FL = real_flips(P)
set_gate(P, FL, 7200)
target = elig_share(P)
tr = run(P, tk)
real = (stats(tr, None, MID)["net"], stats(tr, MID, None)["net"], stats(tr)["net"])
say(f"REAL 2h gate: train {real[0]:+.2f} test {real[1]:+.2f} full {real[2]:+.2f} eligible share {target:.3f}")
cont_bars = np.where((P.sig_d != 0) & (~P.sig_flip))[0]
rng = np.random.default_rng(4242)
res = []
t0 = time.time()
for i in range(NS):
    aw = np.zeros(P.N, bool)
    aw[cont_bars[rng.random(len(cont_bars)) < target]] = True
    P.awake_sig = aw | P.ev_flip
    tr = run(P, tk)
    res.append((stats(tr, None, MID)["net"], stats(tr, MID, None)["net"], stats(tr)["net"]))
    if (i + 1) % 100 == 0:
        a = np.array(res)
        say(f"  {i+1}: train mean {a[:,0].mean():+.2f} test mean {a[:,1].mean():+.2f} full mean {a[:,2].mean():+.2f}  [{time.time()-t0:.0f}s]")
a = np.array(res)
np.save(os.path.join(HERE, "randmask.npy"), a)
for k, lbl in enumerate(("TRAIN", "TEST", "FULL")):
    v = a[:, k]
    say(f"{lbl}: real {real[k]:+8.2f} | random-mask mean {v.mean():+7.2f} sd {v.std():6.2f} p5 {np.percentile(v,5):+7.2f} "
        f"p50 {np.percentile(v,50):+7.2f} p95 {np.percentile(v,95):+7.2f} max {v.max():+7.2f} "
        f"| real beats {(v < real[k]).mean():.1%} | z {(real[k]-v.mean())/v.std():+.2f}")
say("done")
out.close()
