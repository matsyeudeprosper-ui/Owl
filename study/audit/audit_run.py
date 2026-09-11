"""Runs the audit matrix. Usage: python audit_run.py <section>
sections: main | rand_m1 | rand_tick | oos
Results are written to results/<section>.txt (and CSV/JSON where noted).
"""
import csv
import datetime as dt
import json
import os
import sys
import time

import numpy as np

import exec_audit as A

HERE = A.HERE
RES = os.path.join(HERE, "results")
os.makedirs(RES, exist_ok=True)
DATA = os.path.join(HERE, "..", "data")
utc = dt.timezone.utc

section = sys.argv[1] if len(sys.argv) > 1 else "main"
out = open(os.path.join(RES, f"{section}.txt"), "w", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    out.write(s + "\n")
    out.flush()


def report(tr, label, T):
    mid = int(T[0] + (T[-1] - T[0]) // 2)
    say(A.fmt(A.stats(tr, label + " FULL")))
    say(A.fmt(A.stats(tr, label + "   h1", t_hi=mid)))
    say(A.fmt(A.stats(tr, label + "   h2", t_lo=mid)))


CONFIGS = [("FLIP only, gated", ("flip",), True),
           ("TOUCH only, gated", ("touch",), True),
           ("FLIP+TOUCH, NO gate", ("flip", "touch"), False),
           ("FLIP+TOUCH + awake gate (LIVE)", ("flip", "touch"), True)]

O, H, L, C, T = A.load_m1(os.path.join(DATA, "pro_m1.npz"))
P = A.Pre(O, H, L, C, T)
say(f"data pro_m1.npz: {len(T)} bars {dt.datetime.utcfromtimestamp(T[0])} -> "
    f"{dt.datetime.utcfromtimestamp(T[-1])}  ({(T[-1]-T[0])/86400:.1f} days)")

if section == "main":
    tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
    say(f"ticks: {tk.n} from {dt.datetime.utcfromtimestamp(tk.t[0]/1000)} to "
        f"{dt.datetime.utcfromtimestamp(tk.t[-1]/1000)}; spread mean {np.mean(tk.ask-tk.bid):.3f}")
    say("\n=== 1. ENTRY TYPES x EXECUTION MODE (S=7, min_dist=7 as in research) ===")
    for lbl, ent, gate in CONFIGS:
        say(f"\n--- {lbl}")
        for mode in ("legacy", "pess", "opt"):
            report(A.simulate(P, mode, ent, gate), f"{mode:7s}", T)
        report(A.simulate(P, "tick", ent, gate, ticks=tk, poll_delay_ms=1000), "tick1s ", T)

    say("\n=== 2. SAME-BAR AMBIGUITY COUNT (bars where SL and TP are both inside the bar) ===")
    trL = A.simulate(P, "legacy")
    amb = 0
    for x in trL:
        k = x["k"]
        if x["d"] == 1:
            both = (L[k] <= x["sl"]) and (H[k] >= x["tp"])
        else:
            both = (H[k] >= x["sl"] - 7.0) and (L[k] <= x["tp"] - 7.0)
        amb += both
    say(f"legacy run: {amb} of {len(trL)} trades exit on a bar that also touches the other level")
    trP = A.simulate(P, "pess")
    same_bar = sum(1 for x in trP if x["k"] == x["j"] and x["kind"] == "touch")
    say(f"pess run: {same_bar} touch trades resolved inside their entry bar "
        f"({sum(1 for x in trP if x['k']==x['j'] and x['kind']=='touch' and x['pnl']<0)} losses, "
        f"{sum(1 for x in trP if x['k']==x['j'] and x['kind']=='touch' and x['pnl']>0)} wins)")

    say("\n=== 3. TICK POLL DELAY SENSITIVITY (live config) ===")
    for pd in (0, 500, 1000, 2000, 3000, 5000):
        say(A.fmt(A.stats(A.simulate(P, "tick", ticks=tk, poll_delay_ms=pd), f"tick poll {pd}ms")))

    say("\n=== 4. MIN-DISTANCE: research (7) vs production S_MIN_DIST (10) ===")
    for md in (7.0, 10.0, 15.0, 20.0):
        say(A.fmt(A.stats(A.simulate(P, "pess", min_dist=md), f"pess  min_dist {md:.0f}")))
        say(A.fmt(A.stats(A.simulate(P, "tick", ticks=tk, min_dist=md), f"tick1s min_dist {md:.0f}")))

    say("\n=== 5. SLIPPAGE STRESS on ticks (live config, min_dist 10, poll 1s) ===")
    say("(observed live: entry slip median 0 / mean +2.5 pts, SL slip mean -2.3 pts, one 155-pt entry outlier)")
    for se in (0, 2.5, 5, 10, 20):
        for ss in (0, 2.5, 5, 10):
            say(A.fmt(A.stats(A.simulate(P, "tick", ticks=tk, min_dist=10, slip_entry=se, slip_sl=ss),
                              f"slip entry {se:>4} sl {ss:>4}")))

    say("\n=== 6. SPREAD STRESS on M1 pess (spread S also = entry cost and sell-side exits) ===")
    for S in (7.0, 10.0, 14.0, 20.0):
        say(A.fmt(A.stats(A.simulate(P, "pess", S=S, min_dist=10), f"pess S={S:.0f} min_dist 10")))

    say("\n=== 7. PER-TRADE DUMP of the tick run (live config, min_dist 10, poll 1s) -> results/trades_tick_live_config.csv ===")
    tr = A.simulate(P, "tick", ticks=tk, min_dist=10)
    with open(os.path.join(RES, "trades_tick_live_config.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entry_time_utc", "kind", "dir", "entry", "sl", "tp", "risk_usd", "exit_time_utc", "exit", "why", "pnl"])
        for x in tr:
            w.writerow([dt.datetime.utcfromtimestamp(tk.t[x["ti"]] / 1000).isoformat(timespec="seconds"), x["kind"],
                        "BUY" if x["d"] == 1 else "SELL", round(x["e"], 2), round(x["sl"], 2), round(x["tp"], 2),
                        round(x["dist"] * 0.02, 2),
                        dt.datetime.utcfromtimestamp(tk.t[x["xi"]] / 1000).isoformat(timespec="seconds"),
                        round(x["x"], 2), x["why"], round(x["pnl"], 2)])
    say(A.fmt(A.stats(tr, "tick1s min_dist 10 (LIVE CONFIG)")))
    # entry slippage inside the tick model: fill vs level+spread
    sl_ = [((x["e"] - 7.0) - (x["e"] - x["dist"] - 7.0)) for x in tr]  # placeholder
    say("done main")

elif section == "rand_m1":
    NS = 1000
    say(f"=== RANDOM-DIRECTION CONTROL, M1 pess, {NS} seeds per config ===")
    for lbl, ent, gate in CONFIGS:
        real = A.stats(A.simulate(P, "pess", ent, gate))
        nets = []
        t0 = time.time()
        for s in range(NS):
            nets.append(A.stats(A.simulate(P, "pess", ent, gate, seed=1000 + s))["net"])
        nets = np.array(nets)
        pct = (nets < real["net"]).mean()
        say(f"{lbl:32s}: real {real['net']:+8.2f} (n {real['n']}, wr {real['wr']:.1%}) | random mean {nets.mean():+7.2f} "
            f"sd {nets.std():6.2f} p5 {np.percentile(nets,5):+7.2f} p50 {np.percentile(nets,50):+7.2f} "
            f"p95 {np.percentile(nets,95):+7.2f} max {nets.max():+7.2f} | real beats {pct:.1%} of controls "
            f"| z {(real['net']-nets.mean())/nets.std():+.2f}  [{time.time()-t0:.0f}s]")
        np.save(os.path.join(RES, f"rand_m1_{ent[0]}{'_'+ent[1] if len(ent)>1 else ''}{'_gate' if gate else ''}.npy"), nets)
    say("done rand_m1")

elif section == "rand_tick":
    NS = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
    say(f"=== RANDOM-DIRECTION CONTROL, TICK execution (poll 1s, min_dist 10), {NS} seeds ===")
    for lbl, ent, gate in [CONFIGS[3], CONFIGS[1], CONFIGS[0], CONFIGS[2]]:
        real = A.stats(A.simulate(P, "tick", ent, gate, ticks=tk, min_dist=10))
        nets = []
        t0 = time.time()
        for s in range(NS):
            nets.append(A.stats(A.simulate(P, "tick", ent, gate, ticks=tk, min_dist=10, seed=5000 + s))["net"])
            if (s + 1) % 100 == 0:
                say(f"   {lbl}: {s+1} seeds, mean so far {np.mean(nets):+.2f}  [{time.time()-t0:.0f}s]")
        nets = np.array(nets)
        pct = (nets < real["net"]).mean()
        say(f"{lbl:32s}: real {real['net']:+8.2f} (n {real['n']}, wr {real['wr']:.1%}) | random mean {nets.mean():+7.2f} "
            f"sd {nets.std():6.2f} p5 {np.percentile(nets,5):+7.2f} p50 {np.percentile(nets,50):+7.2f} "
            f"p95 {np.percentile(nets,95):+7.2f} max {nets.max():+7.2f} | real beats {pct:.1%} of controls "
            f"| z {(real['net']-nets.mean())/nets.std():+.2f}")
        np.save(os.path.join(RES, f"rand_tick_{ent[0]}{'_'+ent[1] if len(ent)>1 else ''}{'_gate' if gate else ''}.npy"), nets)
    say("done rand_tick")

elif section == "oos":
    tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
    O2, H2, L2, C2, T2 = A.load_m1(os.path.join(DATA, "m1_trial9_all.npz"))
    say(f"data m1_trial9_all.npz: {len(T2)} bars {dt.datetime.utcfromtimestamp(T2[0])} -> {dt.datetime.utcfromtimestamp(T2[-1])}")
    P2 = A.Pre(O2, H2, L2, C2, T2)
    oos_from = int(T[-1]) + 60          # first bar after the research dataset
    live_from = int(dt.datetime(2026, 9, 8, 19, 30, tzinfo=utc).timestamp())   # bot deployed
    say(f"OOS = bars after {dt.datetime.utcfromtimestamp(oos_from)} (never used in any research)")
    for mode, kw in (("pess", {}), ("tick", dict(ticks=tk))):
        for lbl, ent, gate in CONFIGS:
            tr = A.simulate(P2, mode, ent, gate, min_dist=10, **kw)
            say(A.fmt(A.stats(tr, f"{mode:5s} {lbl[:26]:26s} OOS ", t_lo=oos_from)))
        say("")
    say("--- in-sample overlap on the SECOND data source (anchor-noise check: same rules, series starts 2026-07-04 instead of 07-01) ---")
    for lbl, ent, gate in CONFIGS[-1:]:
        tr1 = A.simulate(P, "pess", ent, gate, min_dist=10)
        tr2 = A.simulate(P2, "pess", ent, gate, min_dist=10)
        lo = int(T2[0]); hi = int(T[-1])
        say(A.fmt(A.stats(tr1, "pro_m1 (Jul-01 start) overlap", t_lo=lo, t_hi=hi)))
        say(A.fmt(A.stats(tr2, "trial9 (Jul-04 start) overlap", t_lo=lo, t_hi=hi)))
    say("\n--- the LIVE window (2026-09-08 19:30 -> end): backtest of the deployed config on ticks vs the real account ---")
    tr = A.simulate(P2, "tick", ("flip", "touch"), True, ticks=tk, min_dist=10)
    live = [x for x in tr if x["t"] >= live_from]
    say(A.fmt(A.stats(live, "tick backtest, live window")))
    with open(os.path.join(RES, "trades_tick_live_window.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entry_time_utc", "kind", "dir", "entry", "sl", "tp", "risk_usd", "exit_time_utc", "exit", "why", "pnl"])
        for x in live:
            w.writerow([dt.datetime.utcfromtimestamp(tk.t[x["ti"]] / 1000).isoformat(timespec="seconds"), x["kind"],
                        "BUY" if x["d"] == 1 else "SELL", round(x["e"], 2), round(x["sl"], 2), round(x["tp"], 2),
                        round(x["dist"] * 0.02, 2),
                        dt.datetime.utcfromtimestamp(tk.t[x["xi"]] / 1000).isoformat(timespec="seconds"),
                        round(x["x"], 2), x["why"], round(x["pnl"], 2)])
    say("per-trade list -> results/trades_tick_live_window.csv (compare with results/bos/trades_live_canonical.csv)")
    say("done oos")
out.close()
