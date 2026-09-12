"""E018 - tradable forced-deleveraging shock, per PREREG_E018.md (frozen before
results). Consumed data only: Exness ticks (to 2026-09-11 13:39 UTC), OKX 5-min
OI / taker (recorder), OKX liquidation fills (descriptive). Nothing after END
is read; E017's forward stream is not opened."""
import csv
import datetime as dt
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
REC = r"C:\Projects\KinoliveLines\recorder\data"
out = open(os.path.join(HERE, "results_e018.txt"), "w", encoding="utf-8")
END = dt.datetime(2026, 9, 11, 13, 39, 53, tzinfo=dt.timezone.utc)
SPLIT = int(dt.datetime(2026, 8, 25, tzinfo=dt.timezone.utc).timestamp() * 1000)
LAT = 30                     # seconds after the slot end before the entry tick
SLIP = 5.0
HORIZ = (1, 5, 15, 30, 60)   # minutes
PRIMARY_H = 15
NRAND = 1000
MIN_HIST = 1000
DAY7 = 7 * 86400 * 1000


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")


# ---------------------------------------------------------------- ticks
D = np.load(os.path.join(HERE, "..", "data", "ticks_btcusd.npz"))
tt, bid, ask = D["t"].astype(np.int64), D["bid"].astype(float), D["ask"].astype(float)
keep = tt <= int(END.timestamp() * 1000)
tt, bid, ask = tt[keep], bid[keep], ask[keep]
mid = (bid + ask) / 2
say(f"ticks {len(tt)}: {dt.datetime.utcfromtimestamp(tt[0]/1000)} -> {dt.datetime.utcfromtimestamp(tt[-1]/1000)}")


def mid_before(t_ms):
    k = int(np.searchsorted(tt, t_ms, side="left")) - 1
    return mid[k] if k >= 0 else np.nan


def px_at(t_ms, side):
    k = int(np.searchsorted(tt, t_ms, side="left"))
    if k >= len(tt):
        return None, None
    return k, (ask[k] if side == "ask" else bid[k])


# ---------------------------------------------------------------- 5-min derivatives slots
rows = []
for r in csv.DictReader(open(os.path.join(REC, "derivs_BTC.csv"), encoding="utf-8")):
    try:
        t = int(r["ts_ms"])
        if t + 300000 > int(END.timestamp() * 1000):
            continue
        oi = float(r["open_interest"])
        tb = float(r["taker_buy"]) if r["taker_buy"] else np.nan
        ts_ = float(r["taker_sell"]) if r["taker_sell"] else np.nan
        rows.append((t, oi if oi > 1e8 else np.nan, tb, ts_))
    except Exception:
        pass
rows.sort()
S_t = np.array([x[0] for x in rows], np.int64)
S_oi = np.array([x[1] for x in rows])
S_tb = np.array([x[2] for x in rows])
S_ts = np.array([x[3] for x in rows])
prev = np.searchsorted(S_t, S_t - 300000)            # index of slot exactly 5 min earlier, if present
has_prev = (prev < len(S_t)) & (S_t[np.minimum(prev, len(S_t) - 1)] == S_t - 300000)
dOI = np.full(len(S_t), np.nan)
ok = has_prev & ~np.isnan(S_oi)
ok[ok] &= ~np.isnan(S_oi[prev[ok]])
dOI[ok] = S_oi[ok] / S_oi[prev[ok]] - 1
m0 = np.array([mid_before(t) for t in S_t])
m1 = np.array([mid_before(t + 300000) for t in S_t])
r5 = m1 / m0 - 1
imb = (S_tb - S_ts) / (S_tb + S_ts)
scorable = ~np.isnan(dOI) & ~np.isnan(r5) & (S_t >= tt[0])
say(f"5-min slots {len(S_t)} ({dt.datetime.utcfromtimestamp(S_t[0]/1000)} -> {dt.datetime.utcfromtimestamp(S_t[-1]/1000)}), scorable (consecutive OI + price) {scorable.sum()}")

# liquidations per slot (descriptive)
L = []
for r in csv.DictReader(open(os.path.join(REC, "liquidations_BTC.csv"), encoding="utf-8")):
    try:
        t = int(r["ts_ms"])
        if t <= int(END.timestamp() * 1000):
            L.append((t, float(r["sz"]) * 0.01))
    except Exception:
        pass
L.sort()
Lt = np.array([x[0] for x in L], np.int64)
Lcs = np.concatenate([[0.0], np.cumsum([x[1] for x in L])])
liq_slot = Lcs[np.searchsorted(Lt, S_t + 300000, side="left")] - Lcs[np.searchsorted(Lt, S_t, side="left")]

# ATR: 14-slot true range of 5-min mid bars (past-only at slot end)
b5 = tt // 300000
starts = np.concatenate([[0], np.where(np.diff(b5) != 0)[0] + 1])
bar_t = b5[starts] * 300000
bar_hi = np.array([mid[s:e].max() for s, e in zip(starts, np.concatenate([starts[1:], [len(tt)]]))])
bar_lo = np.array([mid[s:e].min() for s, e in zip(starts, np.concatenate([starts[1:], [len(tt)]]))])
bar_cl = mid[np.concatenate([starts[1:], [len(tt)]]) - 1]
tr = np.maximum(bar_hi[1:] - bar_lo[1:], np.maximum(np.abs(bar_hi[1:] - bar_cl[:-1]), np.abs(bar_lo[1:] - bar_cl[:-1])))
atr = np.full(len(bar_t), np.nan)
for i in range(15, len(bar_t)):
    atr[i] = tr[i - 15:i - 1].mean()          # bars strictly before bar i


def atr_at(t_ms):
    k = int(np.searchsorted(bar_t, t_ms, side="right")) - 1
    return atr[k] if k >= 0 else np.nan


# ---------------------------------------------------------------- rolling thresholds and classification
cls = np.zeros(len(S_t), np.int8)   # 1 primary, 2 robust-only flag handled separately, 3 ctrl A, 4 ctrl B, 5 ctrl D
robust = np.zeros(len(S_t), bool)
thr_rec = {}
sc_idx = np.where(scorable)[0]
for i in sc_idx:
    t_end = S_t[i] + 300000
    lo = np.searchsorted(S_t, t_end - DAY7 - 300000)
    h = sc_idx[(sc_idx >= lo) & (sc_idx < i)]
    if len(h) < MIN_HIST:
        continue
    hr, ho = r5[h], dOI[h]
    p5, p25, p95 = np.percentile(hr, [5, 2.5, 95])
    o20 = np.percentile(ho, 20)
    thr_rec[i] = (p5, p25, p95, o20)
    down, oidown = r5[i] <= p5, dOI[i] <= o20
    if down and oidown:
        cls[i] = 1
        robust[i] = r5[i] <= p25
    elif down and not oidown:
        cls[i] = 3
    elif oidown and r5[i] > p5:
        if r5[i] >= p95:
            cls[i] = 5
        else:
            cls[i] = 4
first_scored = min(thr_rec) if thr_rec else None
say(f"scoring starts {dt.datetime.utcfromtimestamp(S_t[first_scored]/1000)} (>= {MIN_HIST} trailing slots); raw triggers: primary {int((cls==1).sum())} (robust {int(robust.sum())}), ctrl A {int((cls==3).sum())}, ctrl B {int((cls==4).sum())}, ctrl D {int((cls==5).sum())}")


def first_of_cluster(idx):
    keep, last = [], -10 ** 12
    for i in idx:
        if S_t[i] - last >= 3600000:
            keep.append(i)
            last = S_t[i]
    return keep


def outcomes(i):
    """BUY at first tick >= slot end + LAT (ask); exits at bid; net points after $5."""
    t_in = S_t[i] + 300000 + LAT * 1000
    k0, e = px_at(t_in, "ask")
    if k0 is None:
        return None
    res = dict(i=i, t=S_t[i], entry=e, entry_delay=(tt[k0] - (S_t[i] + 300000)) / 1000)
    for hm in HORIZ:
        k1, x = px_at(tt[k0] + hm * 60000, "bid")
        res[f"n{hm}"] = (x - e - SLIP) if k1 is not None and tt[k1] - tt[k0] <= (hm * 60 + 600) * 1000 else np.nan
    k60 = int(np.searchsorted(tt, tt[k0] + 3600000, side="left"))
    seg = bid[k0:k60]
    res["mfe"] = seg.max() - e if len(seg) else np.nan
    res["mae"] = e - seg.min() if len(seg) else np.nan
    a = atr_at(S_t[i] + 300000)
    res["atr"] = a
    for mult in (0.5, 1.0):
        up = np.where(seg >= e + mult * a)[0]
        dn = np.where(seg <= e - mult * a)[0]
        fu = up[0] if len(up) else None
        fd = dn[0] if len(dn) else None
        res[f"fp{mult}"] = "neither" if fu is None and fd is None else ("fav" if fd is None or (fu is not None and fu < fd) else "adv")
    res["imb"] = imb[i]
    res["liq"] = liq_slot[i]
    res["r5"] = r5[i]
    res["dOI"] = dOI[i]
    return res


def table(evs, label, halves=True, extra=True):
    evs = [e for e in evs if e is not None]
    say(f"\n  {label}: n {len(evs)}")
    if not evs:
        return
    line = "    horizon  " + "".join(f"{h:>9d}m" for h in HORIZ)
    say(line)
    for nm, sel in (("ALL", evs), ("discovery <08-25", [e for e in evs if e['t'] < SPLIT]), ("internal check", [e for e in evs if e['t'] >= SPLIT])) if halves else (("ALL", evs),):
        cells = []
        for h in HORIZ:
            v = np.array([e[f"n{h}"] for e in sel if not np.isnan(e[f"n{h}"])])
            cells.append(f"{v.mean():+6.1f}({(v>0).mean():3.0%})" if len(v) else "        -")
        say(f"    {nm:<18s}" + "".join(f"{c:>11s}" for c in cells) + f"   n {len(sel)}")
    if extra:
        v = np.array([e[f"n{PRIMARY_H}"] for e in evs if not np.isnan(e[f"n{PRIMARY_H}"])])
        srt = np.sort(v)[::-1]
        k10 = int(np.ceil(len(v) * 0.1))
        say(f"    {PRIMARY_H} m: without top-1 {srt[1:].mean() if len(v)>1 else np.nan:+.1f}, top-2 {srt[2:].mean() if len(v)>2 else np.nan:+.1f}, top-10% ({k10}) {srt[k10:].mean() if len(v)>k10 else np.nan:+.1f}; median {np.median(v):+.1f}; best {srt[0]:+.1f} worst {srt[-1]:+.1f}")
        mfe = np.array([e["mfe"] for e in evs]); mae = np.array([e["mae"] for e in evs])
        say(f"    60-min MFE median {np.nanmedian(mfe):.0f} / MAE median {np.nanmedian(mae):.0f} pts; ATR median {np.nanmedian([e['atr'] for e in evs]):.0f}; entry delay median {np.median([e['entry_delay'] for e in evs]):.1f} s")
        for m in (0.5, 1.0):
            c = {k: sum(1 for e in evs if e[f"fp{m}"] == k) for k in ("fav", "adv", "neither")}
            say(f"    first passage ±{m} ATR within 60 min: favourable-first {c['fav']} ({c['fav']/len(evs):.0%}), adverse-first {c['adv']} ({c['adv']/len(evs):.0%}), neither {c['neither']}")


def seq_stats(evs, h):
    v = np.array([e[f"n{h}"] for e in sorted(evs, key=lambda e: e["t"]) if not np.isnan(e[f"n{h}"])])
    cum = np.cumsum(v)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    streak = mx = 0
    for x in v:
        streak = streak + 1 if x <= 0 else 0
        mx = max(mx, streak)
    return v, np.max(peak - cum), mx


# ---------------------------------------------------------------- events
P = [outcomes(i) for i in first_of_cluster(np.where(cls == 1)[0])]
PR = [e for e in P if robust[e["i"]]]
A = [outcomes(i) for i in first_of_cluster(np.where(cls == 3)[0])]
B = [outcomes(i) for i in first_of_cluster(np.where(cls == 4)[0])]
Dn = [outcomes(i) for i in first_of_cluster(np.where(cls == 5)[0])]
say("\n=== PRIMARY: price DOWN (<= p5) + OI DOWN (<= p20) -> BUY at first ask >= slot end + 30 s; net points after spread + $5 ===")
table(P, "PRIMARY downside deleveraging")
table(PR, "ROBUSTNESS (r5 <= p2.5, OI <= p20)")
say("\n=== CONTROL A: price DOWN (<= p5), OI NOT down (> p20) -> BUY ===")
table(A, "control A price-only shock")
say("\n=== CONTROL B: OI DOWN (<= p20), price NOT down (> p5) -> BUY ===")
table(B, "control B OI-only contraction", extra=False)
say("\n=== CONTROL D (descriptive): price UP (>= p95) + OI DOWN (<= p20); BUY-side net shown (continuation); SELL = negative ===")
table(Dn, "control D upside deleveraging", extra=False)

# ---------------------------------------------------------------- control C: matched random slot ends
say("\n=== CONTROL C: matched random slot ends (same n, same hour-of-day, not within 60 min after any trigger), BUY, 1000 draws ===")
P_ok = [e for e in P if e is not None]
trig = S_t[np.where(cls > 0)[0]]
cand = [i for i in sc_idx if i >= first_scored and not np.any((trig <= S_t[i]) & (trig > S_t[i] - 3600000))]
cand_hr = np.array([dt.datetime.utcfromtimestamp(S_t[i] / 1000).hour for i in cand])
cand = np.array(cand)
rng = np.random.default_rng(18)
hours = [dt.datetime.utcfromtimestamp(e["t"] / 1000).hour for e in P_ok]
sims = {h: [] for h in HORIZ}
for _ in range(NRAND):
    picks = [rng.choice(cand[cand_hr == hr]) for hr in hours if (cand_hr == hr).any()]
    o = [outcomes(i) for i in picks]
    for h in HORIZ:
        v = np.array([x[f"n{h}"] for x in o if x is not None and not np.isnan(x[f"n{h}"])])
        sims[h].append(v.mean() if len(v) else np.nan)
say("    horizon   real   random mean   sd    95th   99th   pctile     z")
for h in HORIZ:
    s = np.array(sims[h]); s = s[~np.isnan(s)]
    v = np.array([e[f"n{h}"] for e in P_ok if not np.isnan(e[f"n{h}"])])
    pct = (s < v.mean()).mean() * 100
    say(f"    {h:>4d} m  {v.mean():+6.1f}   {s.mean():+7.1f}   {s.std():5.1f}  {np.percentile(s,95):+6.1f} {np.percentile(s,99):+6.1f}   {pct:5.1f}%  {(v.mean()-s.mean())/s.std():+5.2f}")

# ---------------------------------------------------------------- descriptive context
say("\n=== DESCRIPTIVE CONTEXT (primary events) ===")
if P_ok:
    imbs = np.array([e["imb"] for e in P_ok])
    say(f"  taker imbalance in the event slot: median {np.nanmedian(imbs):+.3f} (all scorable slots median {np.nanmedian(imb[scorable]):+.3f}, p10 {np.nanpercentile(imb[scorable],10):+.3f}); share of events below the all-slot p10 {np.mean(imbs < np.nanpercentile(imb[scorable],10)):.0%}")
    liqs = np.array([e["liq"] for e in P_ok])
    ne = liq_slot[scorable]; ne = ne[ne > 0]
    big = np.percentile(ne, 95)
    say(f"  liquidated BTC in the event slot: median {np.median(liqs):.1f} (non-empty scorable slots median {np.median(ne):.1f}, p95 {big:.1f}); events with large liquidation (>= p95) {int((liqs >= big).sum())} of {len(liqs)}")
    table([e for e in P_ok if e["liq"] >= big], "events WITH large liquidation", halves=False, extra=False)
    table([e for e in P_ok if e["liq"] < big], "events WITHOUT large liquidation", halves=False, extra=False)
    rs = np.array([e["r5"] for e in P_ok]); q1, q2 = np.percentile(rs, [33.3, 66.7])
    table([e for e in P_ok if e["r5"] <= q1], "return tertile MOST negative", halves=False, extra=False)
    table([e for e in P_ok if e["r5"] > q2], "return tertile LEAST negative", halves=False, extra=False)
    os_ = np.array([e["dOI"] for e in P_ok]); q1, q2 = np.percentile(os_, [33.3, 66.7])
    table([e for e in P_ok if e["dOI"] <= q1], "OI-change tertile MOST negative", halves=False, extra=False)
    table([e for e in P_ok if e["dOI"] > q2], "OI-change tertile LEAST negative", halves=False, extra=False)
    # frequency
    ts_ev = np.array(sorted(e["t"] for e in P_ok))
    days = (S_t[-1] - S_t[first_scored]) / 86400000
    dkeys = set(int(t // 86400000) for t in ts_ev)
    alld = range(int(S_t[first_scored] // 86400000), int(S_t[-1] // 86400000) + 1)
    gaps = np.diff(ts_ev) / 3600000 if len(ts_ev) > 1 else np.array([0.0])
    say(f"\n=== FREQUENCY (primary): {len(ts_ev)/days:.2f}/day, {len(ts_ev)/days*7:.1f}/week over {days:.0f} scored days; days with none {1-len(dkeys)/len(alld):.0%}; longest gap {gaps.max():.1f} h; median spacing {np.median(gaps):.1f} h ===")
    # economics for all cells (descriptive; pass status decided in E018.md)
    say("\n=== ECONOMIC READ (primary, per horizon; $1 per point per 1.00 lot) ===")
    for h in HORIZ:
        v, dd, streak = seq_stats(P_ok, h)
        per_month = len(v) / days * 30
        say(f"  {h:>3d} m: mean {v.mean():+.1f} pts, trades/month {per_month:.0f}, maxDD {dd:.0f} pts, longest losing streak {streak} | $ per trade / monthly / maxDD at 0.01: {v.mean()*0.01:+.2f} / {v.mean()*0.01*per_month:+.2f} / {dd*0.01:.2f}; 0.02: {v.mean()*0.02:+.2f} / {v.mean()*0.02*per_month:+.2f} / {dd*0.02:.2f}; 0.05: {v.mean()*0.05:+.2f} / {v.mean()*0.05*per_month:+.2f} / {dd*0.05:.2f}")
# events csv
with open(os.path.join(HERE, "events_e018.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["set", "slot_utc", "r5_pct", "dOI_pct", "entry", "entry_delay_s"] + [f"n{h}" for h in HORIZ] + ["mfe", "mae", "atr", "fp0.5", "fp1.0", "imb", "liq_btc"])
    for nm, evs in (("primary", P), ("ctrlA", A), ("ctrlB", B), ("ctrlD", Dn)):
        for e in evs:
            if e is None:
                continue
            w.writerow([nm, dt.datetime.utcfromtimestamp(e["t"] / 1000).isoformat(), round(e["r5"] * 100, 3), round(e["dOI"] * 100, 3), e["entry"], e["entry_delay"]] + [round(e[f"n{h}"], 2) if not np.isnan(e[f"n{h}"]) else "" for h in HORIZ] + [round(e["mfe"], 1), round(e["mae"], 1), round(e["atr"], 1) if not np.isnan(e["atr"]) else "", e["fp0.5"], e["fp1.0"], round(e["imb"], 3) if not np.isnan(e["imb"]) else "", round(e["liq"], 2)])
say("\ndone")
out.close()
