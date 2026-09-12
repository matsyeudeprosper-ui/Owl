"""E009 - fixed lot vs constant-dollar-risk sizing (2026-09-12).

Entries/exits never depend on lot size, so sizing is a layer over the
same tick trade sequences (candle-close config; gated / ungated / 4h).
Per trade: stop distance d (pts), P&L per 0.02 lot p02 (includes the $7
spread at entry and any stop gap), R = p02 / (0.02 d).

Sizing models (frozen before TEST; targets from TRAIN only):
  FIX   : lot 0.02
  CR(t) : lot = t / d, rounded DOWN to 0.01, min 0.01, cap LOT_CAP
  CA(t) : cost-aware, lot = t / (d + 12), same rounding/cap
Targets t = TRAIN q25 / q50 / q75 of the current dollar risk (0.02 d) on
the gated baseline. LOT_CAP = 0.05: the bot allows 200 pt of deviation
on a market fill and the worst observed entry slip was 155 pt; at 0.05
lots a 200-pt adverse fill costs $10, about the same as the largest
current trade risks, so the cap keeps the worst execution case inside
the range the account already lives with. It is a practical constraint,
not a fitted number. Broker: min 0.01, step 0.01 (Exness Pro BTCUSD).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "e007"))
from e007_lib import A, END, MID, Pre2, load_all, real_flips, run, set_gate  # noqa: E402

LOT_CAP = 0.05
COST_PTS = 12.0
out = open(os.path.join(HERE, "results_e009.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s)
    out.write(s + "\n")


def lot_for(model, t, d):
    if model == "FIX":
        return 0.02
    den = d if model == "CR" else d + COST_PTS
    lot = np.floor(t / den / 0.01 + 1e-9) * 0.01
    return float(min(LOT_CAP, max(0.01, lot)))


def size(tr, model, t=None):
    """Attach lot, pnl, risk to each trade of a sequence (new dicts)."""
    o = []
    for x in tr:
        d = x["dist"]
        lot = lot_for(model, t, d)
        o.append(dict(x, lot=lot, pnl=x["p02"] / 0.02 * lot, risk=d * lot, R=x["R"]))
    return o


def dd_stats(p):
    cum = np.cumsum(p)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    dd = peak - cum
    return float(dd.max()), float(dd.mean())


def worst_run(p, n):
    if len(p) < n:
        return float(p.sum())
    c = np.convolve(p, np.ones(n), "valid")
    return float(c.min())


def summary(tr, label=""):
    if not tr:
        return f"{label:30s} n 0"
    p = np.array([x["pnl"] for x in tr])
    R = np.array([x["R"] for x in tr])
    W = p[p > 0]
    Lo = p[p <= 0]
    pf = W.sum() / -Lo.sum() if len(Lo) and Lo.sum() < 0 else float("inf")
    mdd, add = dd_stats(p)
    return (f"{label:30s} n {len(p):4d} wr {len(W)/len(p):5.1%} net {p.sum():+8.2f} PF {pf:4.2f} exp$ {p.mean():+.3f} "
            f"expR {R.mean():+.3f} maxDD {mdd:6.2f} avgDD {add:5.2f} avg$risk {np.mean([x['risk'] for x in tr]):5.2f} "
            f"w10 {worst_run(p,10):+7.2f} w20 {worst_run(p,20):+7.2f}")


def sel(tr, lo=None, hi=None, kind=None):
    return [x for x in tr if (lo is None or x["t"] >= lo) and (hi is None or x["t"] < hi) and (kind is None or x["kind"] == kind)]


# ---------------- sequences ----------------
P, tk = load_all()
FL = real_flips(P)


def seq(W):
    if W is None:
        P.awake_sig = np.ones(P.N, bool)
    else:
        set_gate(P, FL, W)
    tr = run(P, tk)
    for x in tr:
        x["p02"] = x["pnl"]
        x["R"] = x["pnl"] / (x["dist"] * 0.02)
    return tr


SEQ = {"gate2h": seq(7200), "nogate": seq(None), "stale4h": seq(14400)}
set_gate(P, FL, 7200)
O2, H2, L2, C2, T2 = A.load_m1(os.path.join(HERE, "..", "data", "m1_trial9_all.npz"))
P2 = Pre2(O2, H2, L2, C2, T2)
FL2 = real_flips(P2)
set_gate(P2, FL2, 7200)
V1 = [x for x in run(P2, tk) if x["t"] >= END + 60]
for x in V1:
    x["p02"] = x["pnl"]
    x["R"] = x["pnl"] / (x["dist"] * 0.02)

base = SEQ["gate2h"]
risk_train = np.array([x["dist"] * 0.02 for x in sel(base, None, MID)])
T25, T50, T75 = [float(v) for v in np.percentile(risk_train, [25, 50, 75])]
say(f"TRAIN current $ risk per trade (0.02 x stop): q25 {T25:.2f}, median {T50:.2f}, q75 {T75:.2f}, mean {risk_train.mean():.2f}, max {risk_train.max():.2f}")
say(f"FROZEN targets: low {T25:.2f} / medium {T50:.2f} / high {T75:.2f}; lot cap {LOT_CAP}; cost-aware adds {COST_PTS:.0f} pt to the stop")
MODELS = [("FIX 0.02", "FIX", None), (f"CR low {T25:.2f}", "CR", T25), (f"CR med {T50:.2f}", "CR", T50), (f"CR high {T75:.2f}", "CR", T75),
          (f"CA med {T50:.2f}", "CA", T50)]

# ---------------- PART 1 + 2 ----------------
say("\n=== PART 1/2. FIXED LOT vs CONSTANT RISK on the live config (2h gate), TRAIN / TEST / V1, all + by entry type ===")
for lbl, m, t in MODELS:
    say(f"--- {lbl}")
    for name, lo, hi, src in (("TRAIN", None, MID, base), ("TEST ", MID, None, base), ("V1   ", None, None, V1)):
        s = size(sel(src, lo, hi), m, t)
        say("  " + summary(s, f"{name} all"))
        say("  " + summary([x for x in s if x["kind"] == "flip"], f"{name} flip"))
        say("  " + summary([x for x in s if x["kind"] == "cont"], f"{name} cont"))
    s_tr = size(sel(base, None, MID), m, t)
    s_te = size(sel(base, MID, None), m, t)
    say(f"  consistency: TRAIN/TEST net {sum(x['pnl'] for x in s_tr):+.2f} / {sum(x['pnl'] for x in s_te):+.2f}; "
        f"exp$ {np.mean([x['pnl'] for x in s_tr]):+.3f} / {np.mean([x['pnl'] for x in s_te]):+.3f}; "
        f"stale(>=4h) conts fixed-vs-this: see Part 3")

# ---------------- PART 3 ----------------
say("\n=== PART 3. AWAKE GATE x SIZING (TRAIN / TEST), plus stale-4h exclusion (descriptive) ===")
for lbl, m, t in MODELS:
    for gname in ("nogate", "gate2h", "stale4h"):
        for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
            s = size(sel(SEQ[gname], lo, hi), m, t)
            say(f"  {lbl:14s} {gname:8s} " + summary(s, name))
    g_tr = sum(x["pnl"] for x in size(sel(SEQ["gate2h"], None, MID), m, t)) - sum(x["pnl"] for x in size(sel(SEQ["nogate"], None, MID), m, t))
    g_te = sum(x["pnl"] for x in size(sel(SEQ["gate2h"], MID, None), m, t)) - sum(x["pnl"] for x in size(sel(SEQ["nogate"], MID, None), m, t))
    say(f"  {lbl:14s} gate value (2h minus no gate): TRAIN {g_tr:+.2f} TEST {g_te:+.2f}")
say("  stale (age>=4h) continuation damage in the UNGATED sequence by sizing:")
nog = SEQ["nogate"]
for x in nog:
    lf = int(P.last_flip[x["j"]])
    x["age"] = 0.0 if x["kind"] == "flip" else ((int(P.T[x["j"]]) - int(P.T[lf])) / 60 if lf >= 0 else 1e9)
for lbl, m, t in MODELS:
    row = f"    {lbl:14s}"
    for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
        s = size([x for x in sel(nog, lo, hi) if x["kind"] == "cont" and x["age"] >= 240], m, t)
        row += f" {name} n {len(s):2d} net {sum(x['pnl'] for x in s):+7.2f} avg$risk {np.mean([x['risk'] for x in s]):5.2f} |"
    say(row)

# ---------------- PART 4 ----------------
say("\n=== PART 4. DRAWDOWN DISTRIBUTION (live config, chronological; block bootstrap of 10-trade blocks, 2000 resamples) ===")
rng = np.random.default_rng(9)
for lbl, m, t in MODELS:
    for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None), ("FULL ", None, None)):
        s = size(sel(base, lo, hi), m, t)
        p = np.array([x["pnl"] for x in s])
        ts = np.array([x["t"] for x in s])
        cum = np.cumsum(p)
        peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
        under = peak - cum > 1e-9
        # longest time under water (by trade time)
        longest = 0.0
        start = None
        for i in range(len(p)):
            if under[i] and start is None:
                start = ts[i]
            if not under[i] and start is not None:
                longest = max(longest, (ts[i] - start) / 86400)
                start = None
        if start is not None:
            longest = max(longest, (ts[-1] - start) / 86400)
        r10 = np.convolve(p, np.ones(10), "valid") if len(p) >= 10 else p
        # block bootstrap of max DD
        nb = len(p) // 10
        blocks = [p[i * 10:(i + 1) * 10] for i in range(nb)]
        mdds = []
        for _ in range(2000):
            q = np.concatenate([blocks[k] for k in rng.integers(0, nb, nb)])
            mdds.append(dd_stats(q)[0])
        say(f"  {lbl:14s} {name}: maxDD {dd_stats(p)[0]:6.2f} avgDD {dd_stats(p)[1]:5.2f} underwater max {longest:5.1f} d | "
            f"worst5 {worst_run(p,5):+7.2f} worst10 {worst_run(p,10):+7.2f} worst20 {worst_run(p,20):+7.2f} | "
            f"rolling-10 p5 {np.percentile(r10,5):+7.2f} p1 {np.percentile(r10,1):+7.2f} | largest loss {p.min():+6.2f} win {p.max():+6.2f} | "
            f"bootstrap maxDD p50 {np.percentile(mdds,50):6.2f} p95 {np.percentile(mdds,95):6.2f}")

# ---------------- PART 5 ----------------
say("\n=== PART 5. LOT CONCENTRATION (live config, FULL R0) ===")
for lbl, m, t in MODELS[1:]:
    s = size(base, m, t)
    lots = np.array([x["lot"] for x in s])
    p = np.array([x["pnl"] for x in s])
    q90 = np.percentile(lots, 90)
    tail = lots >= q90
    raw = np.array([t / x["dist"] if m == "CR" else t / (x["dist"] + COST_PTS) for x in s])
    say(f"  {lbl:14s} lots min {lots.min():.2f} med {np.median(lots):.2f} p75 {np.percentile(lots,75):.2f} p90 {q90:.2f} "
        f"p95 {np.percentile(lots,95):.2f} max {lots.max():.2f} | uncapped would reach {raw.max():.2f} ({(raw > LOT_CAP).sum()} trades above cap, "
        f"{(raw < 0.01).sum()} below 0.01) | top-10% lots: n {tail.sum()} P&L {p[tail].sum():+.2f} of {p.sum():+.2f} | "
        f"$risk min {min(x['risk'] for x in s):.2f} max {max(x['risk'] for x in s):.2f}")
    narrow = [x for x in s if x["dist"] <= 83]
    say(f"      narrowest stops (<=83 pt, n {len(narrow)}): lots {np.mean([x['lot'] for x in narrow]) if narrow else 0:.3f} avg, "
        f"P&L {sum(x['pnl'] for x in narrow):+.2f}, worst single {min((x['pnl'] for x in narrow), default=0):+.2f}")

# ---------------- PART 7 ----------------
say("\n=== PART 7. WAR-CHEST LAYER (COMPARISON MODEL from audit/warchest_layer.py, NOT the live 'hwm' bookkeeping) on fixed vs CR med ===")
sys.path.insert(0, os.path.join(HERE, "..", "audit"))
import warchest_layer as WL  # noqa: E402


def wc(trades, base_lots):
    """Same rules as warchest_layer.run but the base lot varies per trade."""
    debt = chest = 0.0
    outp = []
    nf = na = 0
    peak_lot = 0.0
    for x, bl in zip(trades, base_lots):
        dist = x["dist"]
        lot = bl
        if debt > 0.5:
            extra = min(WL.MAX_EXTRA, int(chest // max(dist * 0.01, 0.01)))
            if extra > 0:
                lot = round(bl + extra * 0.01, 2)
                nf += 1
        peak_lot = max(peak_lot, lot)
        pnl = (x["x"] - x["e"]) * x["d"] * lot
        if pnl < 0:
            base_sh = pnl * min(1.0, bl / lot)
            debt += -base_sh
            chest = max(0.0, chest + (pnl - base_sh))
        else:
            pay = min(debt, pnl)
            debt -= pay
            chest = min(WL.CHEST_CAP, chest + pnl - pay)
        tot = pnl
        if WL.add_hit(tk, x):
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
                    chest = min(WL.CHEST_CAP, chest + ap - pay)
                tot += ap
        outp.append((tot, debt))
    p = np.array([o[0] for o in outp])
    dbt = np.array([o[1] for o in outp])
    return dict(net=float(p.sum()), mdd=dd_stats(p)[0], nf=nf, na=na, peak_lot=peak_lot,
                debt_days=float((dbt > 0.5).mean()), debt_max=float(dbt.max()))


for lbl, m, t in (MODELS[0], MODELS[2], MODELS[4]):
    for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
        s = sel(base, lo, hi)
        r = wc(s, [lot_for(m, t, x["dist"]) for x in s])
        say(f"  {lbl:14s} {name}: net {r['net']:+8.2f} maxDD {r['mdd']:6.2f} fights {r['nf']:3d} adds {r['na']:3d} peak lot {r['peak_lot']:.2f} "
            f"share of trades in debt {r['debt_days']:.0%} max debt {r['debt_max']:6.2f}")

# ---------------- PART 8 ----------------
say("\n=== PART 8. CONTROL: same lot multiset assigned at RANDOM across trades (1000 permutations), live config ===")
for lbl, m, t in MODELS[1:]:
    for name, lo, hi in (("TRAIN", None, MID), ("TEST ", MID, None)):
        s = size(sel(base, lo, hi), m, t)
        lots = np.array([x["lot"] for x in s])
        p02 = np.array([x["p02"] for x in s])
        real_net = float((p02 / 0.02 * lots).sum())
        real_mdd = dd_stats(p02 / 0.02 * lots)[0]
        nets, mdds = [], []
        for _ in range(1000):
            L = rng.permutation(lots)
            q = p02 / 0.02 * L
            nets.append(q.sum())
            mdds.append(dd_stats(q)[0])
        nets, mdds = np.array(nets), np.array(mdds)
        say(f"  {lbl:14s} {name}: structural net {real_net:+8.2f} maxDD {real_mdd:6.2f} | random-lot net mean {nets.mean():+7.2f} sd {nets.std():5.2f} "
            f"(beats {(nets < real_net).mean():.1%}) | random maxDD mean {mdds.mean():6.2f} (structural lower than {(mdds > real_mdd).mean():.1%})")

# ---------------- PART 9 ----------------
say("\n=== PART 9. ACCOUNT IMPACT (R0 only; 69 days; monthly = x 30.44/68.8) ===")
days = (P.T[-1] - P.T[0]) / 86400
for lbl, m, t in MODELS:
    s = size(base, m, t)
    p = np.array([x["pnl"] for x in s])
    say(f"  {lbl:14s} avg lot {np.mean([x['lot'] for x in s]):.3f} | typical $risk {np.median([x['risk'] for x in s]):.2f} (max {max(x['risk'] for x in s):.2f}) "
        f"| trades/month {len(s)/days*30.44:.0f} | monthly net {p.sum()/days*30.44:+.2f} | maxDD {dd_stats(p)[0]:.2f} | worst20 {worst_run(p,20):+.2f} "
        f"| -60 kill = {60/np.median([x['risk'] for x in s]):.0f} typical risks; maxDD/60 = {dd_stats(p)[0]/60:.2f}")
say("\ndone")
out.close()
