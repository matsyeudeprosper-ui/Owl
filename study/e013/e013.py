"""E013 - can the regime in which Owl's BOS logic has positive expectancy be
identified from PAST-ONLY information? (2026-09-12, light, consumed data)

Data: archive M1 Jan 1 -> Sep 11 2026 (V2 Jan-Jun + Jul-Sep files, one
continuous bid series) for regime features and the structure engine;
trade outcomes from the existing tick-execution lists: V2 (MT5 ticks),
R0 (regime/trades_insample.csv), V1 (regime/trades_oos.csv).
Discovery = trades before 2026-08-01; internal check = 2026-08-01 -> R0
end (2026-09-08 07:11); V1 descriptive. Tertile cuts from discovery only.
Every feature is computed from bars up to and including the signal bar
(which is complete at entry) and from trades whose entry is at least
120 min before the current entry (outcome known; the median holding time
is ~40 min). V3/V4 are NOT read. Fixed windows: 60/360/1440 bars.
"""
import csv
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bt_bos import Struct  # noqa: E402

utc = dt.timezone.utc
SPLIT = int(dt.datetime(2026, 8, 1, tzinfo=utc).timestamp())
R0_END = int(dt.datetime(2026, 9, 8, 7, 12, tzinfo=utc).timestamp())
out = open(os.path.join(HERE, "results_e013.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")


# ---------------------------------------------------------------- M1 series
A = np.load(os.path.join(HERE, "..", "e011", "data", "archive_v2_m1.npz"))
B = np.load(os.path.join(HERE, "..", "e011", "data", "archive_2026_07_09_m1.npz"))
T = np.concatenate([A["t"], B["t"]]).astype(np.int64)
O = np.concatenate([A["o"], B["o"]]).astype(float)
H = np.concatenate([A["h"], B["h"]]).astype(float)
L = np.concatenate([A["l"], B["l"]]).astype(float)
C = np.concatenate([A["c"], B["c"]]).astype(float)
SP = np.concatenate([A["sp"], B["sp"]]).astype(float)
o_ = np.argsort(T, kind="stable")
T, O, H, L, C, SP = T[o_], O[o_], H[o_], L[o_], C[o_], SP[o_]
keep = np.concatenate([[True], np.diff(T) > 0])
T, O, H, L, C, SP = T[keep], O[keep], H[keep], L[keep], C[keep], SP[keep]
N = len(T)
say(f"M1 series: {N} bars {dt.datetime.utcfromtimestamp(T[0])} -> {dt.datetime.utcfromtimestamp(T[-1])}")

# structure engine over the whole series (past-only by construction)
st = Struct()
flip_bars = []
sig = []           # (bar, dir, stopdist)
trend_age = np.zeros(N, np.int32)
lf = -1
for j in range(N):
    pt = st.trend
    s = st.step(int(T[j]), O[j], H[j], L[j], C[j])
    if st.trend != pt and st.trend != 0 and pt != 0:
        flip_bars.append(j)
        lf = j
    if s is not None:
        sig.append((j, s[0], abs(C[j] - s[1]), st.trend != pt))
    trend_age[j] = j - lf if lf >= 0 else -1
flip_bars = np.array(flip_bars)
sig_bar = np.array([x[0] for x in sig])
sig_dir = np.array([x[1] for x in sig])
sig_sd = np.array([x[2] for x in sig])
sig_flip = np.array([x[3] for x in sig])
say(f"engine: {len(flip_bars)} flips, {len(sig)} BOS signals")
# market follow-through per BOS signal (needs 30 later bars): forward move in signal direction / stop distance
fwd = {}
for n in (5, 15, 30):
    v = np.full(len(sig), np.nan)
    ok = sig_bar + n < N
    v[ok] = (C[sig_bar[ok] + n] - C[sig_bar[ok]]) * sig_dir[ok] / np.maximum(sig_sd[ok], 1e-9)
    fwd[n] = v
fwd_done_bar = sig_bar + 30          # the 30-bar follow-through of signal k is known from this bar on

# cumulative helpers
cs_absret = np.concatenate([[0.0], np.cumsum(np.abs(np.diff(C, prepend=C[0])))])
cs_rng = np.concatenate([[0.0], np.cumsum(H - L)])
cs_sp = np.concatenate([[0.0], np.cumsum(SP)])
lr = np.diff(np.log(C), prepend=np.log(C[0]))
cs_lr = np.concatenate([[0.0], np.cumsum(lr)])
cs_lr2 = np.concatenate([[0.0], np.cumsum(lr * lr)])
atr14 = np.concatenate([np.full(13, np.nan), np.convolve(H - L, np.ones(14) / 14, "valid")])


def win_sum(cs, j, n):
    a = max(0, j - n + 1)
    return cs[j + 1] - cs[a]


def er(j, n):
    a = max(0, j - n)
    trav = cs_absret[j + 1] - cs_absret[a + 1]
    return abs(C[j] - C[a]) / trav if trav > 0 else np.nan


def med_range(j, n):
    a = max(0, j - n + 1)
    return float(np.median(H[a:j + 1] - L[a:j + 1]))


def sign_ac(j, n=360):
    a = max(1, j - n + 1)
    s = np.sign(lr[a:j + 1])
    s = s[s != 0]
    return float(np.mean(s[1:] * s[:-1])) if len(s) > 10 else np.nan


# ---------------------------------------------------------------- trades
def load_trades():
    tr = []
    for r in csv.DictReader(open(os.path.join(HERE, "..", "e011", "trades_V2.csv"))):
        fill = dt.datetime.fromisoformat(r["entry_time_utc"]).replace(tzinfo=utc).timestamp()
        tr.append(dict(tb=int(fill // 60) * 60 - 60, kind=r["kind"], d=1 if r["dir"] == "BUY" else -1, e=float(r["entry"]), sl=float(r["sl"]), tp=float(r["tp"]),
                       why=r["why"], pnl=float(r["pnl_002"]), R=float(r["R"]), src="V2"))
    for fn, src in (("trades_insample.csv", "R0"), ("trades_oos.csv", "V1")):
        for r in csv.DictReader(open(os.path.join(HERE, "..", "regime", fn))):
            tr.append(dict(tb=int(float(r["t"])), kind=r["kind"], d=int(float(r["d"])), e=float(r["e"]), sl=float(r["sl"]), tp=float(r["tp"]), why=r["why"],
                           pnl=float(r["pnl"]), R=float(r["pnl"]) / (abs(float(r["e"]) - float(r["sl"])) * 0.02), src=src))
    tr.sort(key=lambda x: x["tb"])
    for x in tr:
        x["era"] = "DISC" if x["tb"] < SPLIT else ("CHECK" if x["tb"] < R0_END else "V1")
        x["month"] = dt.datetime.utcfromtimestamp(x["tb"]).strftime("%Y-%m")
        x["tpf"] = 1 if x["why"] == "tp" else 0
    return tr


TR = load_trades()
say(f"trades: {len(TR)} (DISC {sum(1 for x in TR if x['era']=='DISC')}, CHECK {sum(1 for x in TR if x['era']=='CHECK')}, V1 {sum(1 for x in TR if x['era']=='V1')})")

# ---------------------------------------------------------------- features
FEATS = ["spread_med24", "spread_over_range24", "spread_over_atr", "tp_over_spread", "stop_over_spread",
         "atr_over_price", "rng60", "rng360", "rng1440", "absret60", "absret360", "absret1440", "sd60", "sd360", "sd1440",
         "er60", "er360", "er1440", "signac360",
         "flips_per_day", "bos_per_day", "cont_per_flip", "med_flip_gap_min", "trend_age_min", "flip_share20",
         "own20_tpf", "own50_tpf", "own20_R", "own50_R", "own20_flip_R", "own20_cont_R",
         "mkt20_fwd5", "mkt20_fwd15", "mkt20_fwd30", "mkt20_ge05"]
for i, x in enumerate(TR):
    j = int(np.searchsorted(T, x["tb"]))
    if j >= N or T[j] != x["tb"]:
        j = min(j, N - 1)
    x["j"] = j
    f = {}
    f["spread_med24"] = float(np.median(SP[max(0, j - 1439):j + 1]))
    r24 = med_range(j, 1440)
    f["spread_over_range24"] = f["spread_med24"] / r24 if r24 > 0 else np.nan
    f["spread_over_atr"] = f["spread_med24"] / atr14[j] if atr14[j] and not np.isnan(atr14[j]) else np.nan
    f["tp_over_spread"] = abs(x["tp"] - x["e"]) / max(f["spread_med24"], 0.01)
    f["stop_over_spread"] = abs(x["sl"] - x["e"]) / max(f["spread_med24"], 0.01)
    f["atr_over_price"] = atr14[j] / C[j] * 1e4 if not np.isnan(atr14[j]) else np.nan
    for n in (60, 360, 1440):
        f[f"rng{n}"] = med_range(j, n)
        f[f"absret{n}"] = win_sum(cs_absret, j, n) / C[j] * 1e4
        m = win_sum(cs_lr, j, n) / n
        f[f"sd{n}"] = float(np.sqrt(max(win_sum(cs_lr2, j, n) / n - m * m, 0))) * 1e4
        f[f"er{n}"] = er(j, n)
    f["signac360"] = sign_ac(j)
    fb = flip_bars[(flip_bars <= j) & (flip_bars > j - 1440)]
    f["flips_per_day"] = len(fb)
    sb = (sig_bar <= j) & (sig_bar > j - 1440)
    f["bos_per_day"] = int(sb.sum())
    f["cont_per_flip"] = (sb & ~sig_flip).sum() / max(1, (sb & sig_flip).sum())
    last10 = flip_bars[flip_bars <= j][-10:]
    f["med_flip_gap_min"] = float(np.median(np.diff(last10))) if len(last10) > 2 else np.nan
    f["trend_age_min"] = float(trend_age[j]) if trend_age[j] >= 0 else np.nan
    prev = [y for y in TR[:i] if y["tb"] <= x["tb"] - 7200]
    f["flip_share20"] = np.mean([y["kind"] == "flip" for y in prev[-20:]]) if len(prev) >= 5 else np.nan
    p20, p50 = prev[-20:], prev[-50:]
    f["own20_tpf"] = np.mean([y["tpf"] for y in p20]) if len(p20) >= 10 else np.nan
    f["own50_tpf"] = np.mean([y["tpf"] for y in p50]) if len(p50) >= 25 else np.nan
    f["own20_R"] = np.mean([y["R"] for y in p20]) if len(p20) >= 10 else np.nan
    f["own50_R"] = np.mean([y["R"] for y in p50]) if len(p50) >= 25 else np.nan
    pf_ = [y for y in prev if y["kind"] == "flip"][-20:]
    pc_ = [y for y in prev if y["kind"] == "cont"][-20:]
    f["own20_flip_R"] = np.mean([y["R"] for y in pf_]) if len(pf_) >= 10 else np.nan
    f["own20_cont_R"] = np.mean([y["R"] for y in pc_]) if len(pc_) >= 10 else np.nan
    done = np.where(fwd_done_bar <= j)[0][-20:]
    if len(done) >= 10:
        f["mkt20_fwd5"] = float(np.nanmean(fwd[5][done]))
        f["mkt20_fwd15"] = float(np.nanmean(fwd[15][done]))
        f["mkt20_fwd30"] = float(np.nanmean(fwd[30][done]))
        f["mkt20_ge05"] = float(np.nanmean(fwd[30][done] >= 0.5))
    else:
        for k in ("mkt20_fwd5", "mkt20_fwd15", "mkt20_fwd30", "mkt20_ge05"):
            f[k] = np.nan
    x.update(f)

# ---------------------------------------------------------------- PART 1 monthly
say("\n=== PART 1. MONTHLY: Owl result + regime features (means at trade times) ===")
KEY = ["spread_med24", "spread_over_range24", "tp_over_spread", "atr_over_price", "rng1440", "sd1440", "er60", "er360", "er1440", "signac360",
       "flips_per_day", "bos_per_day", "cont_per_flip", "own20_tpf", "own20_R", "mkt20_fwd30", "mkt20_ge05"]
months = sorted(set(x["month"] for x in TR))
say("  month     n   net     expR  | " + " ".join(f"{k[:11]:>11s}" for k in KEY))
for m in months:
    s = [x for x in TR if x["month"] == m]
    say(f"  {m} {len(s):4d} {sum(x['pnl'] for x in s):+8.1f} {np.mean([x['R'] for x in s]):+.3f} | " + " ".join(f"{np.nanmean([x[k] for x in s]):11.3f}" for k in KEY))
bad = [x for x in TR if x["month"] <= "2026-05"]
good = [x for x in TR if "2026-06" <= x["month"] <= "2026-09" and x["era"] != "V1"]
say("  BAD (Jan-May) vs GOOD (Jun + R0), feature means and medians:")
for k in FEATS:
    a = np.array([x[k] for x in bad], float)
    b = np.array([x[k] for x in good], float)
    say(f"    {k:20s} bad mean {np.nanmean(a):9.3f} med {np.nanmedian(a):9.3f} | good mean {np.nanmean(b):9.3f} med {np.nanmedian(b):9.3f} | ratio good/bad {np.nanmean(b)/np.nanmean(a) if np.nanmean(a) else np.nan:6.2f}")

# ---------------------------------------------------------------- PART 2 3-day blocks
say("\n=== PART 2. 3-DAY BLOCKS (chronological): Owl n / net / expR / PF + key features ===")
t0 = int(T[0])
KEY2 = ["spread_over_range24", "er1440", "sd1440", "flips_per_day", "own20_R", "mkt20_fwd30"]
say("  block start   n   net    expR   PF  | " + " ".join(f"{k[:12]:>12s}" for k in KEY2))
for b0 in range(t0, int(T[-1]), 3 * 86400):
    s = [x for x in TR if b0 <= x["tb"] < b0 + 3 * 86400]
    if not s:
        continue
    p = np.array([x["pnl"] for x in s])
    W = p[p > 0]
    Lo = p[p <= 0]
    pf = W.sum() / -Lo.sum() if len(Lo) and Lo.sum() < 0 else float("inf")
    say(f"  {dt.datetime.utcfromtimestamp(b0).strftime('%m-%d')}      {len(s):4d} {p.sum():+7.1f} {np.mean([x['R'] for x in s]):+.3f} {min(pf,9.99):4.2f} | " + " ".join(f"{np.nanmean([x[k] for x in s]):12.3f}" for k in KEY2))

# ---------------------------------------------------------------- PART 3 tertiles
say("\n=== PART 3. DISCOVERY TERTILES -> expectancy R (and $), DISC / CHECK / V1 ===")
disc = [x for x in TR if x["era"] == "DISC"]
cuts = {}
mono = []
for k in FEATS:
    v = np.array([x[k] for x in disc], float)
    v = v[~np.isnan(v)]
    if len(v) < 100:
        continue
    q1, q2 = np.percentile(v, [33.3, 66.7])
    cuts[k] = (q1, q2)
    line = f"  {k:20s} cuts {q1:8.3f}/{q2:8.3f} |"
    res = {}
    for era in ("DISC", "CHECK", "V1"):
        rows = [x for x in TR if x["era"] == era and not np.isnan(x[k])]
        parts = []
        vals = []
        for lo, hi, nm in ((-np.inf, q1, "L"), (q1, q2, "M"), (q2, np.inf, "H")):
            s = [x for x in rows if lo <= x[k] < hi]
            if s:
                r = np.mean([x["R"] for x in s])
                vals.append(r)
                parts.append(f"{nm} n{len(s):4d} R{r:+.3f} ${np.mean([x['pnl'] for x in s]):+.2f}")
            else:
                vals.append(np.nan)
                parts.append(f"{nm} -")
        res[era] = vals
        line += f" {era}: " + ", ".join(parts) + " |"
    say(line)
    d_ = res["DISC"]
    if len(d_) == 3 and not any(np.isnan(d_)):
        inc = d_[0] < d_[1] < d_[2]
        dec = d_[0] > d_[1] > d_[2]
        if inc or dec:
            c_ = res["CHECK"]
            ok_check = (not any(np.isnan(c_))) and ((c_[2] > c_[0]) if inc else (c_[0] > c_[2]))
            mono.append((k, "inc" if inc else "dec", abs(d_[2] - d_[0]), ok_check, res))
say("\n  monotone in DISCOVERY (with gap H-L in R, and whether CHECK keeps the same H-vs-L ordering):")
for k, dirn, gap, okc, res in sorted(mono, key=lambda z: -z[2]):
    say(f"    {k:20s} {dirn} gap {gap:.3f} R | CHECK same direction: {okc} | CHECK L/M/H R = {', '.join(f'{v:+.3f}' for v in res['CHECK'])} | V1 {', '.join(f'{v:+.3f}' for v in res['V1'])}")

# ---------------------------------------------------------------- PART 4/5 gate
say("\n=== PART 4/5. ONE GATE (rule fixed before this section ran): the monotone discovery variable with the largest H-L gap whose")
say("    direction has an economic reading; ON = favourable tertile boundary from DISCOVERY; second variable only if also monotone and adds a mechanism ===")
ECON = {"er60": "inc", "er360": "inc", "er1440": "inc", "signac360": "inc", "spread_over_range24": "dec", "spread_over_atr": "dec", "tp_over_spread": "inc", "stop_over_spread": "inc",
        "own20_tpf": "inc", "own50_tpf": "inc", "own20_R": "inc", "own50_R": "inc", "own20_flip_R": "inc", "own20_cont_R": "inc",
        "mkt20_fwd5": "inc", "mkt20_fwd15": "inc", "mkt20_fwd30": "inc", "mkt20_ge05": "inc",
        "atr_over_price": "inc", "rng1440": "inc", "sd1440": "inc", "absret1440": "inc", "rng360": "inc", "sd360": "inc", "absret360": "inc", "rng60": "inc", "sd60": "inc", "absret60": "inc",
        "flips_per_day": "inc", "bos_per_day": "inc", "cont_per_flip": "inc"}
cands = [(k, dirn, gap, okc) for k, dirn, gap, okc, res in mono if ECON.get(k) == dirn]
cands.sort(key=lambda z: -z[2])
if not cands:
    say("  no discovery-monotone variable with an economically consistent direction -> NO GATE. (Reporting the best non-qualifying one descriptively.)")
    gate = None
else:
    k, dirn, gap, okc = cands[0]
    q1, q2 = cuts[k]
    thr = q2 if dirn == "inc" else q1
    gate = (k, dirn, thr)
    say(f"  GATE FROZEN: ON when {k} {'>=' if dirn=='inc' else '<='} {thr:.4f} (discovery {'upper' if dirn=='inc' else 'lower'} tertile boundary); discovery gap {gap:.3f} R; CHECK same direction: {okc}")
    say(f"  other qualifying candidates (not used): " + "; ".join(f"{c[0]} gap {c[2]:.3f} check {c[3]}" for c in cands[1:6]))


def gate_on(x):
    if gate is None:
        return True
    k, dirn, thr = gate
    v = x[k]
    if np.isnan(v):
        return True
    return v >= thr if dirn == "inc" else v <= thr


def perf(rows, label):
    if not rows:
        say(f"    {label:28s} n 0")
        return
    p = np.array([x["pnl"] for x in rows])
    R = np.array([x["R"] for x in rows])
    W = p[p > 0]
    Lo = p[p <= 0]
    pf = W.sum() / -Lo.sum() if len(Lo) and Lo.sum() < 0 else float("inf")
    cum = np.cumsum(p)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    say(f"    {label:28s} n {len(p):4d} net {p.sum():+8.2f} PF {min(pf,9.99):4.2f} expR {R.mean():+.3f} exp$ {p.mean():+.3f} maxDD {np.max(peak-cum):7.2f} wr {(p>0).mean():5.1%}")


if gate is not None:
    for era in ("DISC", "CHECK", "V1"):
        rows = [x for x in TR if x["era"] == era]
        on = [x for x in rows if gate_on(x)]
        off = [x for x in rows if not gate_on(x)]
        say(f"  {era}: trades allowed {len(on)}/{len(rows)} = {len(on)/max(1,len(rows)):.0%}")
        perf(rows, "always-on")
        perf(on, "gated (ON)")
        perf(off, "skipped (OFF)")
        say(f"    false-off cost (profitable skipped): {sum(x['pnl'] for x in off if x['pnl']>0):+.2f} on {sum(1 for x in off if x['pnl']>0)} | false-on cost (losers taken): {sum(x['pnl'] for x in on if x['pnl']<=0):+.2f} on {sum(1 for x in on if x['pnl']<=0)}")
    say("  monthly ON share and result (all eras):")
    for m in months:
        s = [x for x in TR if x["month"] == m]
        on = [x for x in s if gate_on(x)]
        say(f"    {m}: ON {len(on)}/{len(s)} ({len(on)/len(s):.0%}) | always-on {sum(x['pnl'] for x in s):+8.2f} | gated {sum(x['pnl'] for x in on):+8.2f}")
    say("  activation / deactivation (state changes across consecutive trades), longest runs:")
    state = None
    runs = []
    start = None
    for x in TR:
        g = gate_on(x)
        if g != state:
            if state is not None:
                runs.append((state, start, x["tb"]))
            state, start = g, x["tb"]
    runs.append((state, start, TR[-1]["tb"]))
    on_runs = sorted([r for r in runs if r[0]], key=lambda r: r[1] - r[2])[:3]
    off_runs = sorted([r for r in runs if not r[0]], key=lambda r: r[1] - r[2])[:3]
    say(f"    state changes: {len(runs)-1}; longest ON runs: " + "; ".join(f"{dt.datetime.utcfromtimestamp(r[1]).strftime('%m-%d %H:%M')}->{dt.datetime.utcfromtimestamp(r[2]).strftime('%m-%d %H:%M')} ({(r[2]-r[1])/86400:.1f} d)" for r in on_runs))
    say(f"    longest OFF runs: " + "; ".join(f"{dt.datetime.utcfromtimestamp(r[1]).strftime('%m-%d %H:%M')}->{dt.datetime.utcfromtimestamp(r[2]).strftime('%m-%d %H:%M')} ({(r[2]-r[1])/86400:.1f} d)" for r in off_runs))
    say("    first 25 state changes:")
    for r in runs[1:26]:
        say(f"      {dt.datetime.utcfromtimestamp(r[1]).strftime('%Y-%m-%d %H:%M')} -> {'ON' if r[0] else 'OFF'}")

# ---------------------------------------------------------------- PART 6 withdrawal simulation
say("\n=== PART 6. WITHDRAWAL SIMULATION: $500 start, fixed 0.02, withdraw $100 whenever equity >= baseline + 100 (reset baseline), dead when equity <= baseline - 60 ===")


def harvest(rows, label):
    eq = 500.0
    base = 500.0
    withdrawn = 0.0
    nw = 0
    first = None
    dead = None
    min_eq = eq
    for x in rows:
        eq += x["pnl"]
        min_eq = min(min_eq, eq)
        if eq >= base + 100:
            eq -= 100
            withdrawn += 100
            nw += 1
            base = eq
            first = first or x["tb"]
        if eq <= base - 60:
            dead = x["tb"]
            break
    say(f"  {label:22s} withdrawn {withdrawn:6.0f} ({nw} x $100) | ending equity {eq:7.2f} | min equity {min_eq:7.2f} | cash out minus capital lost = {withdrawn - max(0, 500 - eq):+7.2f} "
        f"| first withdrawal {dt.datetime.utcfromtimestamp(first).strftime('%Y-%m-%d') if first else '-'} | ruin {dt.datetime.utcfromtimestamp(dead).strftime('%Y-%m-%d') if dead else 'none'} | withdrawals > $500: {withdrawn > 500}")


seq_all = [x for x in TR if x["era"] != "V1"]
harvest(seq_all, "A always-on (Jan->R0)")
if gate is not None:
    harvest([x for x in seq_all if gate_on(x)], "B gated (Jan->R0)")
harvest([x for x in TR if x["month"] >= "2026-06" and x["era"] != "V1"], "A always-on from June")
if gate is not None:
    harvest([x for x in TR if x["month"] >= "2026-06" and x["era"] != "V1" and gate_on(x)], "B gated from June")

with open(os.path.join(HERE, "trades_features_e013.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    cols = ["tb", "time", "src", "era", "kind", "d", "pnl", "R", "tpf"] + FEATS
    w.writerow(cols)
    for x in TR:
        w.writerow([x["tb"], dt.datetime.utcfromtimestamp(x["tb"]).isoformat(), x["src"], x["era"], x["kind"], x["d"], round(x["pnl"], 4), round(x["R"], 4), x["tpf"]] + [round(x[k], 5) if not np.isnan(x[k]) else "" for k in FEATS])
say("\ndone")
out.close()
