"""E019 - pure 5-minute downside-shock rebound, per PREREG_E019.md (frozen before
results). Consumed data only (ticks to 2026-09-11 13:39 UTC). OKX 5-min series
used for the slot grid and descriptive context only. E017 forward data not read."""
import csv
import datetime as dt
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
REC = r"C:\Projects\KinoliveLines\recorder\data"
out = open(os.path.join(HERE, "results_e019.txt"), "w", encoding="utf-8")
END = dt.datetime(2026, 9, 11, 13, 39, 53, tzinfo=dt.timezone.utc)
END_MS = int(END.timestamp() * 1000)
SPLIT = int(dt.datetime(2026, 8, 25, tzinfo=dt.timezone.utc).timestamp() * 1000)
LAT, SLIP = 30, 5.0
HORIZ = (1, 5, 15, 30, 60)
PH = 15
NRAND = 1000
MIN_HIST = 1000
DAY7 = 7 * 86400 * 1000


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")


# ---------------------------------------------------------------- ticks
D = np.load(os.path.join(HERE, "..", "data", "ticks_btcusd.npz"))
tt, bid, ask = D["t"].astype(np.int64), D["bid"].astype(float), D["ask"].astype(float)
keep = tt <= END_MS
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


# ---------------------------------------------------------------- slot grid + context
rows = []
for r in csv.DictReader(open(os.path.join(REC, "derivs_BTC.csv"), encoding="utf-8")):
    try:
        t = int(r["ts_ms"])
        if t + 300000 > END_MS:
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
imb = np.array([(x[2] - x[3]) / (x[2] + x[3]) if x[2] + x[3] > 0 else np.nan for x in rows])
prev = np.searchsorted(S_t, S_t - 300000)
has_prev = (prev < len(S_t)) & (S_t[np.minimum(prev, len(S_t) - 1)] == S_t - 300000)
dOI = np.full(len(S_t), np.nan)
ok = has_prev & ~np.isnan(S_oi)
ok[ok] &= ~np.isnan(S_oi[prev[ok]])
dOI[ok] = S_oi[ok] / S_oi[prev[ok]] - 1
m0 = np.array([mid_before(t) for t in S_t])
m1 = np.array([mid_before(t + 300000) for t in S_t])
r5 = m1 / m0 - 1
scorable = ~np.isnan(r5) & (S_t >= tt[0])
say(f"5-min slots {len(S_t)}, scorable (price) {scorable.sum()}")

L = []
for r in csv.DictReader(open(os.path.join(REC, "liquidations_BTC.csv"), encoding="utf-8")):
    try:
        t = int(r["ts_ms"])
        if t <= END_MS:
            L.append((t, float(r["sz"]) * 0.01))
    except Exception:
        pass
L.sort()
Lt = np.array([x[0] for x in L], np.int64)
Lcs = np.concatenate([[0.0], np.cumsum([x[1] for x in L])])
liq_slot = Lcs[np.searchsorted(Lt, S_t + 300000)] - Lcs[np.searchsorted(Lt, S_t)]

# 5-min bars (ATR), 1-min bars (24 h median range), 1 h high/low
b5 = tt // 300000
st5 = np.concatenate([[0], np.where(np.diff(b5) != 0)[0] + 1])
en5 = np.concatenate([st5[1:], [len(tt)]])
bar_t = b5[st5] * 300000
bar_hi = np.array([mid[s:e].max() for s, e in zip(st5, en5)])
bar_lo = np.array([mid[s:e].min() for s, e in zip(st5, en5)])
bar_cl = mid[en5 - 1]
tr = np.maximum(bar_hi[1:] - bar_lo[1:], np.maximum(np.abs(bar_hi[1:] - bar_cl[:-1]), np.abs(bar_lo[1:] - bar_cl[:-1])))
atr = np.full(len(bar_t), np.nan)
for i in range(15, len(bar_t)):
    atr[i] = tr[i - 15:i - 1].mean()
b1 = tt // 60000
st1 = np.concatenate([[0], np.where(np.diff(b1) != 0)[0] + 1])
en1 = np.concatenate([st1[1:], [len(tt)]])
m1_t = b1[st1] * 60000
m1_rng = np.array([mid[s:e].max() - mid[s:e].min() for s, e in zip(st1, en1)])


def atr_at(t_ms):
    k = int(np.searchsorted(bar_t, t_ms, side="right")) - 1
    return atr[k] if k >= 0 else np.nan


def ctx(t_end, k0):
    j = int(np.searchsorted(m1_t, t_end, side="left"))
    j0 = int(np.searchsorted(m1_t, t_end - 86400000, side="left"))
    rng24 = np.median(m1_rng[j0:j]) if j > j0 else np.nan
    k1h = int(np.searchsorted(tt, t_end - 3600000, side="left"))
    hi1, lo1 = mid[k1h:k0].max(), mid[k1h:k0].min()
    return rng24, hi1, lo1


# ---------------------------------------------------------------- rolling thresholds
cls = np.zeros(len(S_t), np.int8)   # 1 primary (<= p5), 2 upside (>= p95)
robust = np.zeros(len(S_t), bool)
sc = np.where(scorable)[0]
first = None
for i in sc:
    t_end = S_t[i] + 300000
    lo = np.searchsorted(S_t, t_end - DAY7 - 300000)
    h = sc[(sc >= lo) & (sc < i)]
    if len(h) < MIN_HIST:
        continue
    if first is None:
        first = i
    p25, p5, p95 = np.percentile(r5[h], [2.5, 5, 95])
    if r5[i] <= p5:
        cls[i] = 1
        robust[i] = r5[i] <= p25
    elif r5[i] >= p95:
        cls[i] = 2
say(f"scoring starts {dt.datetime.utcfromtimestamp(S_t[first]/1000)}; raw triggers: downside {int((cls==1).sum())} (robust {int(robust.sum())}), upside {int((cls==2).sum())}")


def first_of_cluster(idx):
    keep, last = [], -10 ** 12
    for i in idx:
        if S_t[i] - last >= 3600000:
            keep.append(i)
            last = S_t[i]
    return keep


def outcomes(i, d=1):
    """d=+1 BUY (entry ask, exit bid), d=-1 SELL (entry bid, exit ask)."""
    t_end = S_t[i] + 300000
    k0, e = px_at(t_end + LAT * 1000, "ask" if d == 1 else "bid")
    if k0 is None:
        return None
    res = dict(i=i, t=S_t[i], entry=e, entry_delay=(tt[k0] - t_end) / 1000, spread=ask[k0] - bid[k0], hour=dt.datetime.utcfromtimestamp(t_end / 1000).hour)
    for hm in HORIZ:
        k1, x = px_at(tt[k0] + hm * 60000, "bid" if d == 1 else "ask")
        res[f"n{hm}"] = ((x - e) * d - SLIP) if k1 is not None and tt[k1] - tt[k0] <= (hm * 60 + 600) * 1000 else np.nan
    k60 = int(np.searchsorted(tt, tt[k0] + 3600000, side="left"))
    seg = (bid[k0:k60] if d == 1 else ask[k0:k60])
    pnl = (seg - e) * d
    if len(pnl):
        res["mfe"], res["mae"] = pnl.max(), -pnl.min()
        res["t_mfe"], res["t_mae"] = (tt[k0 + int(np.argmax(pnl))] - tt[k0]) / 60000, (tt[k0 + int(np.argmin(pnl))] - tt[k0]) / 60000
    else:
        res["mfe"] = res["mae"] = res["t_mfe"] = res["t_mae"] = np.nan
    a = atr_at(t_end)
    res["atr"] = a
    for mult in (0.5, 1.0):
        up = np.where(pnl >= mult * a)[0]
        dn = np.where(pnl <= -mult * a)[0]
        fu = up[0] if len(up) else None
        fd = dn[0] if len(dn) else None
        res[f"fp{mult}"] = "neither" if fu is None and fd is None else ("fav" if fd is None or (fu is not None and fu < fd) else "adv")
    rng24, hi1, lo1 = ctx(t_end, k0)
    res.update(r5=r5[i], dOI=dOI[i], imb=imb[i], liq=liq_slot[i], rng24=rng24, d_hi=(hi1 - e) / a if a else np.nan, d_lo=(e - lo1) / a if a else np.nan)
    return res


def cell(evs, h):
    return np.array([e[f"n{h}"] for e in evs if not np.isnan(e[f"n{h}"])])


def table(evs, label, halves=True, extra=True):
    evs = [e for e in evs if e is not None]
    say(f"\n  {label}: n {len(evs)}")
    if not evs:
        return
    say("    horizon           " + "".join(f"{h:>9d}m" for h in HORIZ))
    sets = (("ALL", evs), ("discovery <08-25", [e for e in evs if e["t"] < SPLIT]), ("internal check", [e for e in evs if e["t"] >= SPLIT])) if halves else (("ALL", evs),)
    for nm, sel in sets:
        cells = []
        for h in HORIZ:
            v = cell(sel, h)
            cells.append(f"{v.mean():+6.1f}({(v>0).mean():3.0%})" if len(v) else "        -")
        say(f"    {nm:<18s}" + "".join(f"{c:>11s}" for c in cells) + f"   n {len(sel)}")
    if extra:
        v = cell(evs, PH)
        srt = np.sort(v)[::-1]
        k10 = int(np.ceil(len(v) * 0.1))
        ktr = int(len(v) * 0.1)
        say(f"    {PH} m anti-outlier: without best-1 {srt[1:].mean():+.1f}, best-2 {srt[2:].mean():+.1f}, top-10% ({k10}) {srt[k10:].mean():+.1f}; median {np.median(v):+.1f}; 10% trimmed mean {np.sort(v)[ktr:len(v)-ktr].mean():+.1f}; best {srt[0]:+.0f} worst {srt[-1]:+.0f}")
        say(f"    path (60 min): MFE median {np.nanmedian([e['mfe'] for e in evs]):.0f} at {np.nanmedian([e['t_mfe'] for e in evs]):.0f} min (p25 {np.nanpercentile([e['t_mfe'] for e in evs],25):.0f}, p75 {np.nanpercentile([e['t_mfe'] for e in evs],75):.0f}); MAE median {np.nanmedian([e['mae'] for e in evs]):.0f} at {np.nanmedian([e['t_mae'] for e in evs]):.0f} min (p25 {np.nanpercentile([e['t_mae'] for e in evs],25):.0f}, p75 {np.nanpercentile([e['t_mae'] for e in evs],75):.0f}); ATR median {np.nanmedian([e['atr'] for e in evs]):.0f}")
        for m in (0.5, 1.0):
            c = {k: sum(1 for e in evs if e[f"fp{m}"] == k) for k in ("fav", "adv", "neither")}
            say(f"    first passage ±{m} ATR: favourable-first {c['fav']} ({c['fav']/len(evs):.0%}), adverse-first {c['adv']} ({c['adv']/len(evs):.0%}), neither {c['neither']}")
        say(f"    MAE before MFE (went lower first): {np.mean([e['t_mae'] < e['t_mfe'] for e in evs if not np.isnan(e['t_mfe'])]):.0%}")


def seq(evs, h):
    v = np.array([e[f"n{h}"] for e in sorted(evs, key=lambda e: e["t"]) if not np.isnan(e[f"n{h}"])])
    cum = np.cumsum(v)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    s = mx = 0
    for x in v:
        s = s + 1 if x <= 0 else 0
        mx = max(mx, s)
    return v, np.max(peak - cum), mx


# ---------------------------------------------------------------- events
P = [outcomes(i) for i in first_of_cluster(np.where(cls == 1)[0])]
P = [e for e in P if e is not None]
PR = [e for e in P if robust[e["i"]]]
Uidx = first_of_cluster(np.where(cls == 2)[0])
UB = [x for x in (outcomes(i, 1) for i in Uidx) if x is not None]
US = [x for x in (outcomes(i, -1) for i in Uidx) if x is not None]
say("\n=== PRIMARY: 5-min return <= trailing-7-day p5 -> BUY at first ask >= slot end + 30 s; net points after spread + $5 ===")
table(P, "PRIMARY downside shock (p5)")
table(PR, "ROBUSTNESS (p2.5)")
say("\n=== UPSIDE SHOCK (>= p95), descriptive ===")
table(UB, "upside: continuation BUY", extra=False)
table(US, "upside: reversal SELL", extra=False)

say("\n=== SHOCK SEVERITY (primary, tertiles of r5) ===")
rs = np.array([e["r5"] for e in P])
q1, q2 = np.percentile(rs, [33.3, 66.7])
for nm, sel in (("MOST negative (largest crash)", [e for e in P if e["r5"] <= q1]), ("MID", [e for e in P if q1 < e["r5"] <= q2]), ("LEAST negative (mild)", [e for e in P if e["r5"] > q2])):
    table(sel, f"{nm}: r5 median {np.median([e['r5'] for e in sel])*100:+.2f}%", halves=False, extra=False)
    v = cell(sel, PH)
    srt = np.sort(v)[::-1]
    say(f"    {PH} m without best-2 {srt[2:].mean():+.1f}, median {np.median(v):+.1f}; 60 m without best-2 {np.sort(cell(sel,60))[::-1][2:].mean():+.1f}")

say("\n=== CONTROL: matched random slot ends (same n, same hour-of-day, not within 60 min after any trigger), BUY, 1000 draws ===")
trig = S_t[np.where(cls > 0)[0]]
cand = np.array([i for i in sc if i >= first and not np.any((trig <= S_t[i]) & (trig > S_t[i] - 3600000))])
cand_hr = np.array([dt.datetime.utcfromtimestamp(S_t[i] / 1000).hour for i in cand])
rng = np.random.default_rng(19)
hours = [e["hour"] for e in P]
sims = {h: [] for h in HORIZ}
for _ in range(NRAND):
    picks = [rng.choice(cand[cand_hr == hr]) for hr in hours if (cand_hr == hr).any()]
    o = [outcomes(i) for i in picks]
    o = [x for x in o if x is not None]
    for h in HORIZ:
        v = cell(o, h)
        sims[h].append(v.mean() if len(v) else np.nan)
say("    horizon   real   random mean   sd    95th   99th   pctile     z")
for h in HORIZ:
    s = np.array(sims[h]); s = s[~np.isnan(s)]
    v = cell(P, h)
    say(f"    {h:>4d} m  {v.mean():+6.1f}   {s.mean():+7.1f}   {s.std():5.1f}  {np.percentile(s,95):+6.1f} {np.percentile(s,99):+6.1f}   {(s < v.mean()).mean()*100:5.1f}%  {(v.mean()-s.mean())/s.std():+5.2f}")
# same for the internal-check half only
Pc = [e for e in P if e["t"] >= SPLIT]
hours_c = [e["hour"] for e in Pc]
cand_c = cand[S_t[cand] >= SPLIT]; cand_c_hr = np.array([dt.datetime.utcfromtimestamp(S_t[i] / 1000).hour for i in cand_c])
sims_c = []
for _ in range(NRAND):
    picks = [rng.choice(cand_c[cand_c_hr == hr]) for hr in hours_c if (cand_c_hr == hr).any()]
    o = [x for x in (outcomes(i) for i in picks) if x is not None]
    v = cell(o, PH); sims_c.append(v.mean() if len(v) else np.nan)
sims_c = np.array(sims_c); sims_c = sims_c[~np.isnan(sims_c)]
vc = cell(Pc, PH)
say(f"    internal-check half only, {PH} m: real {vc.mean():+.1f} (n {len(vc)}) vs random {sims_c.mean():+.1f} ± {sims_c.std():.1f}, 95th {np.percentile(sims_c,95):+.1f}, pctile {(sims_c < vc.mean()).mean()*100:.1f}%")

say("\n=== MARKET-STATE CONTEXT (primary events; descriptive, not gated) ===")
def by_ctx(name, label, fn=None):
    vals = np.array([e[name] for e in P], float)
    okm = ~np.isnan(vals)
    if okm.sum() < 20:
        say(f"  {label}: insufficient"); return
    med = np.median(vals[okm])
    lo = [e for e, v in zip(P, vals) if not np.isnan(v) and v <= med]
    hi = [e for e, v in zip(P, vals) if not np.isnan(v) and v > med]
    say(f"  {label}: median {med:+.3f}; below-median events {PH} m {cell(lo,PH).mean():+.1f} (n {len(lo)}), 60 m {cell(lo,60).mean():+.1f} | above-median {PH} m {cell(hi,PH).mean():+.1f} (n {len(hi)}), 60 m {cell(hi,60).mean():+.1f}")
by_ctx("spread", "spread at entry ($)")
by_ctx("rng24", "24 h median M1 range (pts)")
by_ctx("dOI", "OI change of the slot")
by_ctx("imb", "taker imbalance")
by_ctx("liq", "liquidated BTC in slot")
by_ctx("d_hi", "distance below 1 h high (ATR)")
by_ctx("d_lo", "distance above 1 h low (ATR)")
say("  hour-of-day buckets (UTC), " + f"{PH} m mean / n: " + ", ".join(f"{a:02d}-{b:02d}h {cell([e for e in P if a <= e['hour'] < b],PH).mean():+.0f}/{len([e for e in P if a <= e['hour'] < b])}" for a, b in ((0, 6), (6, 12), (12, 18), (18, 24))))

ts_ev = np.array(sorted(e["t"] for e in P))
days = (S_t[-1] - S_t[first]) / 86400000
dkeys = set(int(t // 86400000) for t in ts_ev)
alld = range(int(S_t[first] // 86400000), int(S_t[-1] // 86400000) + 1)
gaps = np.diff(ts_ev) / 3600000
say(f"\n=== FREQUENCY (primary): {len(ts_ev)/days:.2f}/day, {len(ts_ev)/days*7:.1f}/week over {days:.0f} scored days; days with none {1-len(dkeys)/len(alld):.0%}; median spacing {np.median(gaps):.1f} h; longest gap {gaps.max():.1f} h ===")
say("\n=== ECONOMICS (primary, all horizons, descriptive; $1 per point per 1.00 lot) ===")
for h in HORIZ:
    v, dd, streak = seq(P, h)
    pm = len(v) / days * 30
    say(f"  {h:>3d} m: mean {v.mean():+.1f} pts, trades/month {pm:.0f}, maxDD {dd:.0f} pts, longest losing streak {streak} | per trade / monthly / maxDD $ at 0.01: {v.mean()*0.01:+.2f} / {v.mean()*0.01*pm:+.2f} / {dd*0.01:.2f}; 0.02: {v.mean()*0.02:+.2f} / {v.mean()*0.02*pm:+.2f} / {dd*0.02:.2f}; 0.05: {v.mean()*0.05:+.2f} / {v.mean()*0.05*pm:+.2f} / {dd*0.05:.2f}")

with open(os.path.join(HERE, "events_e019.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    keys = ["entry", "entry_delay", "spread", "hour", "r5", "dOI", "imb", "liq", "rng24", "d_hi", "d_lo", "atr", "mfe", "t_mfe", "mae", "t_mae", "fp0.5", "fp1.0"] + [f"n{h}" for h in HORIZ]
    w.writerow(["set", "slot_utc", "robust"] + keys)
    for nm, evs in (("primary", P), ("upside_buy", UB), ("upside_sell", US)):
        for e in evs:
            w.writerow([nm, dt.datetime.utcfromtimestamp(e["t"] / 1000).isoformat(), int(robust[e["i"]])] + [e[k] if isinstance(e[k], str) else (round(float(e[k]), 4) if not (isinstance(e[k], float) and np.isnan(e[k])) else "") for k in keys])
say("\ndone")
out.close()
