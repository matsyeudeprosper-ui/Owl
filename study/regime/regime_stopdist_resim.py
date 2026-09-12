"""The one survivor of regime_buckets.py: block entries whose stop
distance is in the narrowest train quartile (<= 97.94 pts). Re-simulated
INSIDE the engine (min_dist = the train q25) so the one-position
interaction is included, on ticks; plus a permutation control: how
often does removing a random 25% of trades (list-based) score as well
as removing the narrow-stop set, in train and in test separately."""
import csv, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "audit"))
import exec_audit as A
DATA = os.path.join(HERE, "..", "data")
sp = dict(l.strip().split("=") for l in open(os.path.join(HERE, "split.txt"))); MID = int(sp["mid"]); END = int(sp["research_end"])
CUT = 97.94
E = ("flip", "cont")
tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
O, H, L, C, T = A.load_m1(os.path.join(DATA, "pro_m1.npz")); P = A.Pre(O, H, L, C, T)
O2, H2, L2, C2, T2 = A.load_m1(os.path.join(DATA, "m1_trial9_all.npz")); P2 = A.Pre(O2, H2, L2, C2, T2)
out = open(os.path.join(HERE, "results_stopdist_resim.txt"), "w")
def say(s=""):
    print(s); out.write(s + "\n")
say(f"=== in-engine re-simulation: min_dist 10 (baseline) vs min_dist {CUT} (block narrow stops), tick, gated, flat 0.02")
for md, lbl in ((10.0, "baseline"), (CUT, "block narrow stops")):
    tr = A.simulate(P, "tick", E, True, ticks=tk, min_dist=md)
    tro = [x for x in A.simulate(P2, "tick", E, True, ticks=tk, min_dist=md) if x["t"] >= END + 60]
    say(A.fmt(A.stats(tr, f"{lbl:20s} TRAIN", t_hi=MID)))
    say(A.fmt(A.stats(tr, f"{lbl:20s} TEST ", t_lo=MID)))
    say(A.fmt(A.stats(tro, f"{lbl:20s} OOS  ")))
    say(A.fmt(A.stats(tr, f"{lbl:20s} FULL ")))
    say("")
say("=== permutation control (list-based): P&L of the blocked set vs 10000 random subsets of the same size")
rows = list(csv.DictReader(open(os.path.join(HERE, "trades_insample.csv"))))
for r in rows:
    r["t"] = float(r["t"]); r["pnl"] = float(r["pnl"]); r["stop_dist"] = float(r["stop_dist"])
rng = np.random.default_rng(1)
for name, sel in (("TRAIN", [r for r in rows if r["t"] < MID]), ("TEST ", [r for r in rows if r["t"] >= MID])):
    p = np.array([r["pnl"] for r in sel]); blk = np.array([r["stop_dist"] <= CUT for r in sel])
    real = p[blk].sum(); k = int(blk.sum())
    sims = np.array([p[rng.choice(len(p), k, replace=False)].sum() for _ in range(10000)])
    say(f"  {name}: blocked set n {k} P&L {real:+.2f} | random same-size subsets mean {sims.mean():+.2f} sd {sims.std():.2f} "
        f"| P(random <= real) = {(sims <= real).mean():.3f}")
say("\n=== the mechanism check: win rate by stop distance bucket (fixed $7 spread = larger share of a narrow stop)")
for name, sel in (("TRAIN", [r for r in rows if r["t"] < MID]), ("TEST ", [r for r in rows if r["t"] >= MID])):
    for lo, hi in ((0, 60), (60, 98), (98, 150), (150, 250), (250, 9999)):
        s = [r for r in sel if lo < r["stop_dist"] <= hi]
        if s:
            w = sum(1 for r in s if r["pnl"] > 0)
            say(f"  {name} stop {lo:4d}-{hi:4d}: n {len(s):3d} wr {w/len(s):5.1%} net {sum(r['pnl'] for r in s):+7.2f} spread/stop {7/max(lo,1)*100 if lo else 0:.0f}%-{7/hi*100:.0f}%")
out.close()
