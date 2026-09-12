"""E007 part 4b (descriptive): is 'stale trend' just 'wide stop'? Within
the ungated population, continuation entries split by age (<120 / 120-240
/ 240+) x stop width (train median split of stop_dist). No rule is
selected; this is to interpret what the gate proxies for."""
import os, numpy as np
from e007_lib import MID, load_all, real_flips, run, set_gate, stats, line
HERE = os.path.dirname(os.path.abspath(__file__))
out = open(os.path.join(HERE, "results_stale_stop.txt"), "w")
def say(s=""): print(s); out.write(s + "\n")
P, tk = load_all(); FL = real_flips(P); set_gate(P, FL, 7200)
nog = run(P, tk, gate=False)
conts = []
for x in nog:
    if x["kind"] != "cont": continue
    lf = int(P.last_flip[x["j"]]); x["age"] = (int(P.T[x["j"]]) - int(P.T[lf])) / 60 if lf >= 0 else 1e9
    conts.append(x)
med = float(np.median([x["dist"] for x in conts if x["t"] < MID]))
say(f"train median stop_dist of continuation entries: {med:.1f} pts")
for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
    sel = [x for x in conts if (lo is None or x["t"] >= lo) and (hi is None or x["t"] < hi)]
    say(f"\n{name}")
    for al, ah, albl in ((0, 120, "age <120"), (120, 240, "age 120-240"), (240, 1e12, "age 240+")):
        for wide, wl in ((False, "narrow stop"), (True, "wide stop  ")):
            s = [x for x in sel if al <= x["age"] < ah and ((x["dist"] > med) == wide)]
            st_ = stats(s)
            avgl = st_.get("avgL", 0); avgw = st_.get("avgW", 0)
            say(f"  {albl:12s} {wl}: {line(st_, '')}  avgW {avgw:+.2f} avgL {avgl:+.2f} mean stop {np.mean([x['dist'] for x in s]) if s else 0:.0f}")
say("\nrisk-normalised view (P&L in R = pnl / (stop_dist*0.02)) by age bucket:")
for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
    sel = [x for x in conts if (lo is None or x["t"] >= lo) and (hi is None or x["t"] < hi)]
    for al, ah, albl in ((0, 60, "0-60"), (60, 120, "60-120"), (120, 240, "120-240"), (240, 1e12, "240+")):
        s = [x for x in sel if al <= x["age"] < ah]
        if s:
            R = np.array([x["pnl"] / (x["dist"] * 0.02) for x in s])
            say(f"  {name} age {albl:8s}: n {len(s):3d} mean R {R.mean():+.3f} wr {(R>0).mean():.0%} sum R {R.sum():+.1f}")
out.close()
