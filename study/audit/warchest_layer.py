"""War-chest layer on top of the tick execution audit (2026-09-11).

Takes the fixed trade sequence of a configuration (entries/exits do not
depend on lot size) and applies the live bot's money management:
  - base 0.02; while debt > 0.5, fighter bullets ride along: extra =
    min(MAX_EXTRA, chest // (dist*0.01)), lot = 0.02 + extra*0.01
  - 50% pullback add: if price retraces 50% of the risk before the exit
    (checked on ticks, bid like the bot), n = min(2, chest // (0.5*dist*0.01))
    bullets join at that level with the same SL/TP
  - booking (bt_full.py model): base share of a loss -> debt, extra share
    -> chest; wins pay debt first, overflow -> chest (cap CHEST_CAP);
    add losses -> chest, add wins pay debt then chest.
Same model for every variant, so the comparison is fair even if the live
'hwm' debt bookkeeping differs in detail."""
import os
import sys
import numpy as np
import exec_audit as A

BASE = 0.02
MAX_EXTRA = 3
CHEST_CAP = 10.0


def add_hit(tk, x):
    """Did the bid reach the 50% pullback level between entry and exit?"""
    lvl = x["e"] - x["d"] * 0.5 * x["dist"]
    s = slice(x["ti"] + 1, x["xi"])
    if x["ti"] is None or x["xi"] is None or x["xi"] <= x["ti"] + 1:
        return False
    b = tk.bid[s]
    return bool((b <= lvl).any()) if x["d"] == 1 else bool((b >= lvl).any())


def run(trades, tk, fighters=True, adds=True):
    debt = chest = 0.0
    out = []
    nf = na = 0
    for x in trades:
        dist = x["dist"]
        lot = BASE
        if fighters and debt > 0.5:
            extra = min(MAX_EXTRA, int(chest // max(dist * 0.01, 0.01)))
            if extra > 0:
                lot = round(BASE + extra * 0.01, 2)
                nf += 1
        pnl_pts = (x["x"] - x["e"]) * x["d"]
        pnl = pnl_pts * lot
        # booking of the main position
        if pnl < 0:
            base_sh = pnl * min(1.0, BASE / lot)
            debt += -base_sh
            chest = max(0.0, chest + (pnl - base_sh))
        else:
            pay = min(debt, pnl)
            debt -= pay
            chest = min(CHEST_CAP, chest + pnl - pay)
        tot = pnl
        if adds and add_hit(tk, x):
            cost = 0.5 * dist * 0.01
            n = min(2, int(chest // max(cost, 0.01)))
            if n > 0:
                na += 1
                alot = n * 0.01
                apx = x["e"] - x["d"] * 0.5 * dist
                ap = (x["x"] - apx) * x["d"] * alot
                if ap < 0:
                    chest = max(0.0, chest + ap)
                else:
                    pay = min(debt, ap)
                    debt -= pay
                    chest = min(CHEST_CAP, chest + ap - pay)
                tot += ap
        out.append(tot)
    p = np.array(out)
    cum = np.cumsum(p)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    return dict(net=float(p.sum()), n=len(p), wr=float((p > 0).mean()),
                mdd=float(np.max(peak - cum)), nf=nf, na=na,
                debt_end=debt, chest_end=chest)


if __name__ == "__main__":
    O, H, L, C, T = A.load_m1(os.path.join(A.HERE, "..", "data", "pro_m1.npz"))
    P = A.Pre(O, H, L, C, T)
    tk = A.Ticks(*A.load_ticks(os.path.join(A.HERE, "..", "data", "ticks_btcusd.npz")))
    O2, H2, L2, C2, T2 = A.load_m1(os.path.join(A.HERE, "..", "data", "m1_trial9_all.npz"))
    P2 = A.Pre(O2, H2, L2, C2, T2)
    oos = int(T[-1]) + 60
    mid = int(T[0] + (T[-1] - T[0]) // 2)
    E = ("flip", "cont")
    print("=== FULL SYSTEM (fighters + adds + debt/chest) on tick execution, 69d in-sample | halves | OOS 3.3d")
    for lbl, ent, ctp in (("close entry, OWN TP (live)", E, "own"),
                          ("close entry, TOUCH-geometry TP", E, "touch"),
                          ("flip+TOUCH (previous live rule)", ("flip", "touch"), "own")):
        tr = A.simulate(P, "tick", ent, True, ticks=tk, min_dist=10, cont_tp=ctp)
        flat = A.stats(tr)
        for fl, ad, tag in ((False, False, "flat 0.02"), (True, False, "fighters"), (True, True, "FULL")):
            r = run(tr, tk, fl, ad)
            h1 = run([x for x in tr if x["t"] < mid], tk, fl, ad)["net"]
            h2 = run([x for x in tr if x["t"] >= mid], tk, fl, ad)["net"]
            tro = [x for x in A.simulate(P2, "tick", ent, True, ticks=tk, min_dist=10, cont_tp=ctp) if x["t"] >= oos]
            ro = run(tro, tk, fl, ad)
            print(f"{lbl:32s} {tag:9s}: net {r['net']:+8.2f} n {r['n']} wr {r['wr']:.1%} maxDD {r['mdd']:6.2f} "
                  f"fights {r['nf']:3d} adds {r['na']:3d} | h1 {h1:+7.2f} h2 {h2:+7.2f} | OOS {ro['net']:+7.2f} (n {ro['n']}, debt end {ro['debt_end']:.2f})")
        print()
