"""E010 - normal variance vs strategy failure: a risk-stop study (2026-09-12).

Base sequence = live config (candle-close, 2h gate) on ticks, fixed 0.02.
TRAIN = discovery for every threshold; TEST blind; V1 historical.

Live kill semantics (structure_bos_bot.py): net = banked + floating
<= -60 from the START (not a trailing drawdown). Both semantics are
studied: ABS (cumulative P&L from start) and TRAIL (drawdown from the
equity high-water mark). Floating losses are modelled with each trade's
real maximum adverse excursion (MAE) from ticks.

Bootstrap: circular block bootstrap of TRAIN trades, block length 10
(keeps local clustering), 10 000 paths per horizon.
Thresholds (frozen from TRAIN): fixed-$ = bootstrap maxDD p90/p95/p99 at
the TRAIN horizon + observed TRAIN maxDD; rolling-N (10/20/30) = p95/p99
of the path minimum of the rolling-N sum ($ and R); composite = trailing
DD >= p95 AND rolling-20 <= p95 simultaneously (depth AND concentration).
Degradation scenarios (Part 8), applied to bootstrap paths of 265 trades:
S0 unchanged; S1 10% of winners -> stop loss; S2 20%; S3 winners x0.7;
S4 extra slippage -$0.20/trade; S5 30% of continuation winners -> loss;
S6 30% of flip winners -> loss.
"""
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "e007"))
sys.path.insert(0, os.path.join(HERE, "..", "audit"))
from e007_lib import A, END, MID, Pre2, load_all, real_flips, run, set_gate  # noqa: E402
import warchest_layer as WL  # noqa: E402

NB = 10000
BLK = 10
KILL_LIVE = -60.0
out = open(os.path.join(HERE, "results_e010.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s)
    out.write(s + "\n")


# ------------------------------------------------------------------ data
P, tk = load_all()
FL = real_flips(P)
set_gate(P, FL, 7200)
base = run(P, tk)
O2, H2, L2, C2, T2 = A.load_m1(os.path.join(HERE, "..", "data", "m1_trial9_all.npz"))
P2 = Pre2(O2, H2, L2, C2, T2)
set_gate(P2, real_flips(P2), 7200)
V1 = [x for x in run(P2, tk) if x["t"] >= END + 60]


def mae_usd(x):
    """Worst floating loss during the trade at 0.02 lot (ticks)."""
    if x["ti"] is None or x["xi"] is None or x["xi"] <= x["ti"]:
        return 0.0
    s = slice(x["ti"], x["xi"] + 1)
    if x["d"] == 1:
        worst = x["e"] - tk.bid[s].min()
    else:
        worst = tk.ask[s].max() - x["e"]
    return max(0.0, worst) * 0.02


for seq in (base, V1):
    for x in seq:
        x["R"] = x["pnl"] / (x["dist"] * 0.02)
        x["mae"] = mae_usd(x)

TR = [x for x in base if x["t"] < MID]
TE = [x for x in base if x["t"] >= MID]
p_tr = np.array([x["pnl"] for x in TR])
r_tr = np.array([x["R"] for x in TR])
p_te = np.array([x["pnl"] for x in TE])
r_te = np.array([x["R"] for x in TE])
p_v1 = np.array([x["pnl"] for x in V1])
r_v1 = np.array([x["R"] for x in V1])
say(f"base: TRAIN {len(TR)} trades {p_tr.sum():+.2f} | TEST {len(TE)} {p_te.sum():+.2f} | V1 {len(V1)} {p_v1.sum():+.2f}")


# ------------------------------------------------------------------ helpers
def dd_series(p):
    cum = np.cumsum(p)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    return cum, peak, peak - cum


def rolling_min(p, n):
    if len(p) < n:
        return float(p.sum())
    cs = np.concatenate([[0.0], np.cumsum(p)])
    return float((cs[n:] - cs[:-n]).min())


def episodes(p, ts=None):
    """Completed peak-to-trough-to-recovery episodes."""
    cum, peak, dd = dd_series(p)
    eps = []
    i = 0
    n = len(p)
    while i < n:
        if dd[i] > 1e-9:
            start = i
            trough = i
            while i < n and dd[i] > 1e-9:
                if dd[i] > dd[trough]:
                    trough = i
                i += 1
            end = i  # first index back at high (or n if unrecovered)
            eps.append(dict(start=start, trough=trough, end=end, depth=float(dd[trough]),
                            to_trough=trough - start + 1, to_recover=(end - trough) if end < n else None,
                            days=((ts[min(end, n - 1)] - ts[start]) / 86400) if ts is not None else None,
                            recovered=end < n))
        else:
            i += 1
    return eps


def characterize(p, R, ts, label):
    cum, peak, dd = dd_series(p)
    eps = episodes(p, ts)
    streak = best = 0
    for v in p:
        streak = streak + 1 if v <= 0 else 0
        best = max(best, streak)
    # longest run of negative rolling-20 expectancy
    cs = np.concatenate([[0.0], np.cumsum(p)])
    r20 = (cs[20:] - cs[:-20]) if len(p) >= 20 else np.array([p.sum()])
    neg = 0
    run_ = 0
    for v in r20:
        run_ = run_ + 1 if v < 0 else 0
        neg = max(neg, run_)
    say(f"--- {label}: n {len(p)}, net {p.sum():+.2f}, maxDD {dd.max():.2f}, avgDD {dd.mean():.2f}, final DD {dd[-1]:.2f}")
    say(f"    worst rolling $  5/10/20/30/40: " + " / ".join(f"{rolling_min(p, n):+.2f}" for n in (5, 10, 20, 30, 40)))
    say(f"    worst rolling R  5/10/20/30/40: " + " / ".join(f"{rolling_min(R, n):+.2f}" for n in (5, 10, 20, 30, 40)))
    say(f"    longest losing streak {best} trades | longest run of negative rolling-20 expectancy {neg} trades | largest loss {p.min():+.2f} | largest win {p.max():+.2f}")
    if eps:
        deep = sorted(eps, key=lambda e: -e["depth"])
        say(f"    drawdown episodes: {len(eps)} (recovered {sum(e['recovered'] for e in eps)}); depth quantiles p50 {np.percentile([e['depth'] for e in eps],50):.2f} "
            f"p90 {np.percentile([e['depth'] for e in eps],90):.2f} max {deep[0]['depth']:.2f}")
        for e in deep[:5]:
            say(f"      depth {e['depth']:6.2f}: peak->trough {e['to_trough']:3d} trades, trough->recovery "
                f"{e['to_recover'] if e['to_recover'] is not None else 'not recovered':>13}, duration {e['days'] if e['days'] is not None else 0:.1f} d, "
                f"starts {dt.datetime.utcfromtimestamp(ts[e['start']]).strftime('%m-%d %H:%M')}")
    return dict(maxDD=float(dd.max()))


# ------------------------------------------------------------------ PART 1
say("\n=== PART 1. NORMAL DRAWDOWNS (fixed 0.02, chronological) ===")
characterize(p_tr, r_tr, np.array([x["t"] for x in TR]), "TRAIN")
characterize(p_te, r_te, np.array([x["t"] for x in TE]), "TEST")
characterize(p_v1, r_v1, np.array([x["t"] for x in V1]), "V1 (historical)")
say("  R-normalised: TRAIN maxDD %.2f R, TEST maxDD %.2f R" % (dd_series(r_tr)[2].max(), dd_series(r_te)[2].max()))


# ------------------------------------------------------------------ PART 2
def boot_paths(vals, n, nb, rng, blk=BLK):
    """Circular block bootstrap: nb paths of length n, blocks of blk."""
    m = len(vals)
    nblk = int(np.ceil(n / blk))
    starts = rng.integers(0, m, (nb, nblk))
    idx = (starts[:, :, None] + np.arange(blk)[None, None, :]) % m
    return vals[idx.reshape(nb, -1)[:, :n]]


def path_stats(paths):
    cs = np.cumsum(paths, axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.zeros((paths.shape[0], 1)), cs], axis=1), axis=1)[:, 1:]
    dd = peak - cs
    maxdd = dd.max(axis=1)
    minabs = cs.min(axis=1)
    under = dd > 1e-9
    # longest underwater run per row
    longest = np.zeros(paths.shape[0], int)
    runl = np.zeros(paths.shape[0], int)
    for k in range(paths.shape[1]):
        runl = np.where(under[:, k], runl + 1, 0)
        longest = np.maximum(longest, runl)
    cs0 = np.concatenate([np.zeros((paths.shape[0], 1)), cs], axis=1)
    roll = {}
    for n in (10, 20, 30):
        if paths.shape[1] >= n:
            roll[n] = (cs0[:, n:] - cs0[:, :-n]).min(axis=1)
    return dict(maxdd=maxdd, minabs=minabs, longest=longest, roll=roll, final=cs[:, -1])


rng = np.random.default_rng(2026)
say(f"\n=== PART 2. BOOTSTRAP NORMAL VARIANCE (TRAIN trades, block {BLK}, {NB} paths) ===")
BOOT = {}
for horizon in (100, len(TR), len(TE)):
    pp = boot_paths(p_tr, horizon, NB, rng)
    st = path_stats(pp)
    BOOT[horizon] = st
    say(f"  horizon {horizon} trades (~{horizon/len(TR)*34.3:.0f} days): maxDD p50 {np.percentile(st['maxdd'],50):.2f} p90 {np.percentile(st['maxdd'],90):.2f} "
        f"p95 {np.percentile(st['maxdd'],95):.2f} p97.5 {np.percentile(st['maxdd'],97.5):.2f} p99 {np.percentile(st['maxdd'],99):.2f} | "
        f"underwater max trades p50 {np.percentile(st['longest'],50):.0f} p95 {np.percentile(st['longest'],95):.0f} p99 {np.percentile(st['longest'],99):.0f} | "
        f"worst rolling 10/20/30 p50 " + "/".join(f"{np.percentile(st['roll'][n],50):+.1f}" for n in (10, 20, 30)) +
        " p95 " + "/".join(f"{np.percentile(st['roll'][n],5):+.1f}" for n in (10, 20, 30)) +
        " p99 " + "/".join(f"{np.percentile(st['roll'][n],1):+.1f}" for n in (10, 20, 30)))
    say(f"      P(trailing maxDD >= 60) = {(st['maxdd'] >= 60).mean():.1%} | P(cumulative net from start <= -60) = {(st['minabs'] <= -60).mean():.1%} | "
        f"P(net <= -60) with -80: {(st['minabs'] <= -80).mean():.1%}, -100: {(st['minabs'] <= -100).mean():.1%} | P(final < 0) {(st['final'] < 0).mean():.1%}")
say("  R-based, TRAIN horizon:")
rp = boot_paths(r_tr, len(TR), NB, rng)
rst = path_stats(rp)
say(f"    maxDD R p50 {np.percentile(rst['maxdd'],50):.2f} p95 {np.percentile(rst['maxdd'],95):.2f} p99 {np.percentile(rst['maxdd'],99):.2f} | "
    f"worst rolling-20 R p5 {np.percentile(rst['roll'][20],5):+.2f} p1 {np.percentile(rst['roll'][20],1):+.2f}")

H = len(TR)
ST = BOOT[H]
THR_DD = dict(p90=float(np.percentile(ST["maxdd"], 90)), p95=float(np.percentile(ST["maxdd"], 95)),
              p99=float(np.percentile(ST["maxdd"], 99)), obs=float(dd_series(p_tr)[2].max()))
THR_ABS = dict(p90=float(-np.percentile(ST["minabs"], 10)), p95=float(-np.percentile(ST["minabs"], 5)),
               p99=float(-np.percentile(ST["minabs"], 1)), live=60.0)
THR_ROLL = {n: dict(p95=float(np.percentile(ST["roll"][n], 5)), p99=float(np.percentile(ST["roll"][n], 1))) for n in (10, 20, 30)}
THR_ROLL_R = {n: dict(p95=float(np.percentile(rst["roll"][n], 5)), p99=float(np.percentile(rst["roll"][n], 1))) for n in (10, 20, 30)}
say(f"\nFROZEN THRESHOLDS (TRAIN): trailing DD {THR_DD} | absolute net {THR_ABS} | rolling $ {THR_ROLL} | rolling R {THR_ROLL_R}")


# ------------------------------------------------------------------ detectors
def det_abs(p, thr, mae=None):
    """Kill when cumulative net (incl. floating MAE) <= -thr. Returns trigger index or None."""
    cum = np.cumsum(p)
    prev = np.concatenate([[0.0], cum[:-1]])
    if mae is not None:
        hit = (prev - mae <= -thr) | (cum <= -thr)
    else:
        hit = cum <= -thr
    return int(np.argmax(hit)) if hit.any() else None


def det_trail(p, thr, mae=None):
    cum, peak, dd = dd_series(p)
    prev_dd = np.concatenate([[0.0], dd[:-1]])
    hit = (dd >= thr) | ((prev_dd + mae) >= thr if mae is not None else False)
    return int(np.argmax(hit)) if hit.any() else None


def det_roll(p, n, thr):
    if len(p) < n:
        return None
    cs = np.concatenate([[0.0], np.cumsum(p)])
    r = cs[n:] - cs[:-n]
    hit = r <= thr
    return int(np.argmax(hit)) + n - 1 if hit.any() else None


def det_composite(p, thr_dd, thr_r20):
    cum, peak, dd = dd_series(p)
    if len(p) < 20:
        return None
    cs = np.concatenate([[0.0], np.cumsum(p)])
    r = np.concatenate([np.full(19, np.inf), cs[20:] - cs[:-20]])
    hit = (dd >= thr_dd) & (r <= thr_r20)
    return int(np.argmax(hit)) if hit.any() else None


def det_e005(p, p10=-15.65, p5=-22.51, p50=8.14):
    """E005 rolling-20 state machine: index of first PAUSED, or None."""
    state = "NORMAL"
    for i in range(len(p)):
        if i >= 20:
            s = p[i - 20:i].sum()
            if state == "NORMAL" and s < p5:
                state = "PAUSED"
            elif state == "NORMAL" and s < p10:
                state = "REDUCED"
            elif state == "REDUCED" and s < p5:
                state = "PAUSED"
            elif state == "REDUCED" and s >= p50:
                state = "NORMAL"
            if state == "PAUSED":
                return i
    return None


def report_kill(name, idx, p, ts):
    if idx is None:
        say(f"    {name:34s}: never triggers | final {p.sum():+.2f}")
        return
    after = p[idx + 1:].sum()
    say(f"    {name:34s}: triggers at trade {idx+1}/{len(p)} ({dt.datetime.utcfromtimestamp(ts[idx]).strftime('%m-%d %H:%M')}), "
        f"net at trigger {p[:idx+1].sum():+.2f}, P&L after trigger that is forgone {after:+.2f}, final with stop {p[:idx+1].sum():+.2f} vs {p.sum():+.2f}")


SETS = (("TRAIN", TR, p_tr, r_tr), ("TEST ", TE, p_te, r_te), ("V1   ", V1, p_v1, r_v1))

# ------------------------------------------------------------------ PART 3
say("\n=== PART 3. FIXED-DOLLAR KILL LINES (frozen from TRAIN) ===")
for name, seq, p, R in SETS:
    ts = np.array([x["t"] for x in seq])
    mae = np.array([x["mae"] for x in seq])
    say(f"  {name}")
    for k, thr in THR_ABS.items():
        report_kill(f"ABS net <= -{thr:.0f} ({k}, floating incl.)", det_abs(p, thr, mae), p, ts)
    for k, thr in THR_DD.items():
        report_kill(f"TRAIL DD >= {thr:.0f} ({k}, floating incl.)", det_trail(p, thr, mae), p, ts)
say("  false-stop probability under unchanged TRAIN bootstrap (horizon = TRAIN length; closed P&L only, floating adds a little):")
for k, thr in THR_ABS.items():
    say(f"    ABS -{thr:.0f} ({k}): {(ST['minabs'] <= -thr).mean():.1%}")
for k, thr in THR_DD.items():
    say(f"    TRAIL {thr:.0f} ({k}): {(ST['maxdd'] >= thr).mean():.1%}")

# ------------------------------------------------------------------ PART 4/5
say("\n=== PART 4/5. ROLLING-N LOSS STOPS ($ and R; frozen p95/p99 of the TRAIN bootstrap path-minimum) ===")
for name, seq, p, R in SETS:
    ts = np.array([x["t"] for x in seq])
    say(f"  {name}")
    for n in (10, 20, 30):
        for q in ("p95", "p99"):
            report_kill(f"roll-{n} $ <= {THR_ROLL[n][q]:+.1f} ({q})", det_roll(p, n, THR_ROLL[n][q]), p, ts)
            report_kill(f"roll-{n} R <= {THR_ROLL_R[n][q]:+.2f} ({q})", det_roll(R, n, THR_ROLL_R[n][q]), p, ts)
say("  false-stop probability under unchanged bootstrap (TRAIN horizon): by construction p95 -> 5%, p99 -> 1% for each rule separately")
say("  stability TRAIN vs TEST of the underlying statistics:")
for lbl, a, b in (("maxDD $", dd_series(p_tr)[2].max(), dd_series(p_te)[2].max()), ("maxDD R", dd_series(r_tr)[2].max(), dd_series(r_te)[2].max()),
                  ("worst roll-20 $", rolling_min(p_tr, 20), rolling_min(p_te, 20)), ("worst roll-20 R", rolling_min(r_tr, 20), rolling_min(r_te, 20)),
                  ("largest loss $", p_tr.min(), p_te.min()), ("largest loss R", r_tr.min(), r_te.min())):
    say(f"    {lbl:16s} TRAIN {a:+8.2f} TEST {b:+8.2f} ratio {b/a if a else 0:.2f}")
for name, p in (("TRAIN", p_tr), ("TEST ", p_te)):
    cum, peak, dd = dd_series(p)
    i = int(np.argmax(dd))
    j = int(np.argmax(cum[:i + 1]))
    seg = p[j + 1:i + 1]
    say(f"    {name} maxDD {dd[i]:.2f} built over {len(seg)} trades; largest single loss inside it {seg.min():+.2f} = {abs(seg.min())/dd[i]:.0%} of the DD; "
        f"top-3 losses = {abs(np.sort(seg)[:3].sum())/dd[i]:.0%}")

# ------------------------------------------------------------------ PART 6
say("\n=== PART 6. WHAT HAPPENS AFTER A DRAWDOWN CROSSES A LEVEL (historical + bootstrap) ===")
LEVELS = (20, 40, 60, 80)


def after_cross(p, level, horizons=(10, 20, 40)):
    cum, peak, dd = dd_series(p)
    res = []
    i = 0
    n = len(p)
    while i < n:
        if dd[i] >= level and (i == 0 or dd[i - 1] < level):
            r = dict(i=i)
            for h in horizons:
                seg = p[i + 1:i + 1 + h]
                r[f"pnl{h}"] = float(seg.sum()) if len(seg) == h else np.nan
                r[f"rec{h}"] = bool((dd[i + 1:i + 1 + h] <= 1e-9).any()) if len(seg) == h else np.nan
                r[f"deep{h}"] = bool((dd[i + 1:i + 1 + h] >= level + 20).any()) if len(seg) == h else np.nan
            res.append(r)
            # skip until recovered or next crossing of a deeper level
            k = i + 1
            while k < n and dd[k] >= level:
                k += 1
            i = k
        else:
            i += 1
    return res


for name, seq, p, R in SETS[:2]:
    say(f"  {name} historical crossings:")
    for L in LEVELS:
        ev = after_cross(p, L)
        if not ev:
            say(f"    DD >= {L}: no crossing")
            continue
        for h in (10, 20, 40):
            v = [e for e in ev if not np.isnan(e[f"pnl{h}"])]
            if v:
                say(f"    DD >= {L}: {len(ev)} crossing(s); next {h:2d} trades: median P&L {np.median([e[f'pnl{h}'] for e in v]):+.2f}, "
                    f"recovered high {np.mean([e[f'rec{h}'] for e in v]):.0%}, deepened by 20+ {np.mean([e[f'deep{h}'] for e in v]):.0%}  (n {len(v)})")
say("  bootstrap (unchanged TRAIN strategy, 10000 paths of 265): conditional on the FIRST crossing of each level")
pp = boot_paths(p_tr, 265, NB, rng)
for L in LEVELS:
    rows = []
    for k in range(NB):
        ev = after_cross(pp[k], L)
        if ev:
            rows.append(ev[0])
    if not rows:
        say(f"    DD >= {L}: never in bootstrap")
        continue
    for h in (10, 20, 40):
        v = [e for e in rows if not np.isnan(e[f"pnl{h}"])]
        say(f"    DD >= {L} (reached in {len(rows)/NB:.0%} of paths): next {h:2d} trades median P&L {np.median([e[f'pnl{h}'] for e in v]):+.2f}, "
            f"P(recover high) {np.mean([e[f'rec{h}'] for e in v]):.0%}, P(deepen 20+) {np.mean([e[f'deep{h}'] for e in v]):.0%}")

# ------------------------------------------------------------------ PART 7 composite
COMP = (THR_DD["p95"], THR_ROLL[20]["p95"])
say(f"\n=== PART 7. COMPOSITE (frozen): trailing DD >= {COMP[0]:.1f} AND rolling-20 <= {COMP[1]:+.1f} at the same time ===")
for name, seq, p, R in SETS:
    ts = np.array([x["t"] for x in seq])
    say(f"  {name}")
    report_kill("composite", det_composite(p, *COMP), p, ts)
    report_kill("E005 rolling-20 state -> PAUSED", det_e005(p), p, ts)
cp = np.array([det_composite(pp[k], *COMP) is not None for k in range(2000)])
e5 = np.array([det_e005(pp[k]) is not None for k in range(2000)])
say(f"  false-positive rate under unchanged bootstrap (265 trades, 2000 paths): composite {cp.mean():.1%} | E005 PAUSED {e5.mean():.1%}")

# ------------------------------------------------------------------ PART 8 degradation
say("\n=== PART 8. EDGE-DEGRADATION SCENARIOS (bootstrap of TRAIN trades, 265 trades, 3000 paths each) ===")
kinds_tr = np.array([x["kind"] for x in TR])
dist_tr = np.array([x["dist"] for x in TR])
NP = 3000


def degrade(rng, scen):
    m = len(TR)
    nblk = int(np.ceil(265 / BLK))
    starts = rng.integers(0, m, (NP, nblk))
    idx = ((starts[:, :, None] + np.arange(BLK)[None, None, :]) % m).reshape(NP, -1)[:, :265]
    p = p_tr[idx].copy()
    k = kinds_tr[idx]
    d = dist_tr[idx]
    win = p > 0
    if scen == "S0":
        pass
    elif scen in ("S1", "S2"):
        frac = 0.10 if scen == "S1" else 0.20
        flip = win & (rng.random(p.shape) < frac)
        p[flip] = -d[flip] * 0.02 - 0.14
    elif scen == "S3":
        p[win] *= 0.7
    elif scen == "S4":
        p -= 0.20
    elif scen == "S5":
        flip = win & (k == "cont") & (rng.random(p.shape) < 0.30)
        p[flip] = -d[flip] * 0.02 - 0.14
    elif scen == "S6":
        flip = win & (k == "flip") & (rng.random(p.shape) < 0.30)
        p[flip] = -d[flip] * 0.02 - 0.14
    return p


DETS = [("ABS -60 (live)", lambda q: det_abs(q, 60)), (f"ABS -{THR_ABS['p95']:.0f} (p95)", lambda q: det_abs(q, THR_ABS["p95"])),
        (f"TRAIL {THR_DD['p95']:.0f} (p95)", lambda q: det_trail(q, THR_DD["p95"])), (f"TRAIL {THR_DD['p99']:.0f} (p99)", lambda q: det_trail(q, THR_DD["p99"])),
        (f"roll-10 $ {THR_ROLL[10]['p99']:+.0f} (p99)", lambda q: det_roll(q, 10, THR_ROLL[10]["p99"])),
        (f"roll-20 $ {THR_ROLL[20]['p95']:+.0f} (p95)", lambda q: det_roll(q, 20, THR_ROLL[20]["p95"])),
        (f"roll-20 $ {THR_ROLL[20]['p99']:+.0f} (p99)", lambda q: det_roll(q, 20, THR_ROLL[20]["p99"])),
        (f"roll-30 $ {THR_ROLL[30]['p95']:+.0f} (p95)", lambda q: det_roll(q, 30, THR_ROLL[30]["p95"])),
        ("composite DD p95 & roll-20 p95", lambda q: det_composite(q, *COMP)),
        ("E005 state -> PAUSED", lambda q: det_e005(q))]
SCEN = (("S0 unchanged", "S0"), ("S1 10% winners->SL", "S1"), ("S2 20% winners->SL", "S2"), ("S3 winners x0.7", "S3"),
        ("S4 slippage -$0.20/trade", "S4"), ("S5 30% cont winners->SL", "S5"), ("S6 30% flip winners->SL", "S6"))
rng2 = np.random.default_rng(77)
for slbl, s in SCEN:
    paths = degrade(rng2, s)
    exp_ = paths.mean()
    say(f"  {slbl}: expectancy {exp_:+.3f}/trade (unchanged {p_tr.mean():+.3f}); median path final {np.median(paths.sum(axis=1)):+.1f}")
    for dl, fn in DETS:
        idxs = [fn(paths[k]) for k in range(NP)]
        hit = [i for i in idxs if i is not None]
        rate = len(hit) / NP
        if hit:
            delay = np.median(hit) + 1
            lost = np.median([paths[k][:i + 1].sum() for k, i in enumerate(idxs) if i is not None])
            say(f"      {dl:34s}: fires {rate:5.1%} | median trade of trigger {delay:5.0f} | median net at trigger {lost:+7.2f}")
        else:
            say(f"      {dl:34s}: fires  0.0%")

# ------------------------------------------------------------------ PART 9 production bookkeeping
say("\n=== PART 9. EXACT PRODUCTION BOOKKEEPING (hwm debt, chest cap 10, fighters <=3 bullets, adds <=2 at 50%, kill on net incl. floating) ===")


def production(seq, kill=-60.0, fighters=True, adds=True):
    banked = 0.0
    peak = 0.0
    chest = 0.0
    debt = 0.0
    rows = []
    killed_at = None
    nf = na = 0
    peak_lot = 0.0
    for i, x in enumerate(seq):
        dist = x["dist"]
        lot = 0.02
        if fighters and debt > 0.5:
            extra = min(3, int(chest // max(dist * 0.01, 0.01)))
            if extra > 0:
                lot = round(0.02 + extra * 0.01, 2)
                nf += 1
        peak_lot = max(peak_lot, lot)
        pts = (x["x"] - x["e"]) * x["d"]
        pnl = pts * lot
        # floating kill: worst excursion during the trade
        mae_lot = x["mae"] / 0.02 * lot
        if kill is not None and banked - mae_lot <= kill:
            pnl = kill - banked
            banked += pnl
            rows.append(pnl)
            killed_at = i
            break
        # add
        add_pnl = 0.0
        if adds and WL.add_hit(tk, x):
            cost = 0.5 * dist * 0.01
            n = min(2, int(chest // max(cost, 0.01)))
            if n > 0:
                na += 1
                alot = n * 0.01
                apx = x["e"] - x["d"] * 0.5 * dist
                add_pnl = (x["x"] - apx) * x["d"] * alot
        # book main deal (production order: each deal separately)
        for dpnl, is_add, dlot in ((pnl, False, lot), (add_pnl, True, 0.01)):
            if is_add and add_pnl == 0.0:
                continue
            banked += dpnl
            if dpnl < 0:
                if is_add:
                    chest = max(0.0, chest + dpnl)
                elif dlot > 0.02 + 0.001:
                    chest = max(0.0, chest + dpnl * (1.0 - 0.02 / dlot))
            if banked > peak:
                chest = min(10.0, chest + banked - peak)
                peak = banked
            debt = max(0.0, peak - banked)
        rows.append(pnl + add_pnl)
    p = np.array(rows)
    cum, pk, dd = dd_series(p)
    return dict(net=float(p.sum()), maxdd=float(dd.max()), killed_at=killed_at, nf=nf, na=na, peak_lot=peak_lot,
                under=float((dd > 1e-9).mean()), p=p)


for name, seq, p, R in SETS:
    flat = production(seq, kill=None, fighters=False, adds=False)
    full = production(seq, kill=None)
    fullk = production(seq, kill=-60.0)
    say(f"  {name}: flat 0.02 no kill: net {flat['net']:+8.2f} maxDD {flat['maxdd']:6.2f} underwater {flat['under']:.0%} | "
        f"FULL no kill: net {full['net']:+8.2f} maxDD {full['maxdd']:6.2f} fights {full['nf']} adds {full['na']} peak lot {full['peak_lot']:.2f} underwater {full['under']:.0%} | "
        f"FULL with live -60 kill: {'killed at trade %d, net %+.2f' % (fullk['killed_at']+1, fullk['net']) if fullk['killed_at'] is not None else 'not killed, net %+.2f' % fullk['net']}")
say("  bootstrap of the FULL production layer (block resample of TRAIN trade objects, 2000 paths x 265): P(live -60 kill fires) and maxDD")
objs = np.array(TR, dtype=object)
kills = []
mdds = []
for k in range(2000):
    idx = ((rng.integers(0, len(TR), (int(np.ceil(265 / BLK)),))[:, None] + np.arange(BLK)[None, :]) % len(TR)).reshape(-1)[:265]
    r = production([TR[i] for i in idx], kill=-60.0)
    kills.append(r["killed_at"] is not None)
    r2 = production([TR[i] for i in idx], kill=None)
    mdds.append(r2["maxdd"])
say(f"    P(-60 kill fires within 265 trades, unchanged strategy, full layer) = {np.mean(kills):.1%} | full-layer maxDD p50 {np.percentile(mdds,50):.1f} p95 {np.percentile(mdds,95):.1f} p99 {np.percentile(mdds,99):.1f}")

# ------------------------------------------------------------------ PART 10
say("\n=== PART 10. ACCOUNT SCALE (fixed 0.02, unchanged strategy, TRAIN bootstrap) ===")
for horizon in (100, len(TR), 265):
    st = BOOT[horizon]
    say(f"  over {horizon} trades (~{horizon/len(TR)*34.3:.0f} days): typical maxDD {np.percentile(st['maxdd'],50):.0f}; 1-in-10 {np.percentile(st['maxdd'],90):.0f}; "
        f"1-in-20 {np.percentile(st['maxdd'],95):.0f}; 1-in-100 {np.percentile(st['maxdd'],99):.0f}; underwater typical {np.percentile(st['longest'],50):.0f} trades, 1-in-20 {np.percentile(st['longest'],95):.0f} trades; "
        f"P(net from start <= -60) {(st['minabs'] <= -60).mean():.0%}")
say("\ndone")
out.close()
