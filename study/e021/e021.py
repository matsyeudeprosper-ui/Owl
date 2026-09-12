"""E021 - large downside shock -> SHORT continuation, per PREREG_E021.md (frozen
before results). M1 bars (bid OHLC + mean spread). Usage:
python e021.py <label> <m1.npz> [<m1.npz> ...]"""
import csv
import datetime as dt
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
REC = r"C:\Projects\KinoliveLines\recorder\data"
LABEL = sys.argv[1]
FILES = sys.argv[2:]
out = open(os.path.join(HERE, f"results_{LABEL}.txt"), "w", encoding="utf-8")
SLIP = 5.0
HORIZ = (5, 15, 30, 60)
PH = 30
NRAND = 1000
MIN_HIST = 1000
RNG = np.random.default_rng(21)


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")


def load(files):
    parts = [np.load(f) for f in files]
    T = np.concatenate([p["t"] for p in parts])
    if T[0] > 1e11:
        T = T // 1000
    O = np.concatenate([p["o"] for p in parts]); H = np.concatenate([p["h"] for p in parts])
    L = np.concatenate([p["l"] for p in parts]); C = np.concatenate([p["c"] for p in parts])
    SP = np.concatenate([p["sp"] for p in parts]).astype(float)
    o = np.argsort(T, kind="stable")
    T, O, H, L, C, SP = T[o], O[o], H[o], L[o], C[o], SP[o]
    u = np.concatenate([[True], np.diff(T) > 0])
    return T[u], O[u], H[u], L[u], C[u], SP[u]


T, O, H, L, C, SP = load(FILES)
N = len(T)
say(f"{LABEL}: M1 bars {N} {dt.datetime.utcfromtimestamp(T[0])} -> {dt.datetime.utcfromtimestamp(T[-1])}; spread median {np.median(SP):.2f}")
ASK_C = C + SP                                    # ask at bar close
ASK_O = O + SP
ASK_H = H + SP

# ---------------------------------------------------------------- windows
w = T // 300
ws = np.concatenate([[0], np.where(np.diff(w) != 0)[0] + 1])
we = np.concatenate([ws[1:], [N]])
W_t = w[ws] * 300
W_lo = np.array([L[s:e].min() for s, e in zip(ws, we)])
W_hi = np.array([H[s:e].max() for s, e in zip(ws, we)])
W_cl = C[we - 1]
W_last = we - 1
W_full = (we - ws) >= 4
r5 = np.full(len(W_t), np.nan)
r5[1:] = W_cl[1:] / W_cl[:-1] - 1
r5[~np.concatenate([[False], np.diff(W_t) == 300])] = np.nan
tr = np.maximum(W_hi[1:] - W_lo[1:], np.maximum(np.abs(W_hi[1:] - W_cl[:-1]), np.abs(W_lo[1:] - W_cl[:-1])))
ATR = np.full(len(W_t), np.nan)
for i in range(15, len(W_t)):
    ATR[i] = tr[i - 15:i - 1].mean()
valid = ~np.isnan(r5) & W_full
vidx = np.where(valid)[0]
DAY7 = 7 * 86400
p5 = np.full(len(W_t), np.nan); p25 = np.full(len(W_t), np.nan); p95 = np.full(len(W_t), np.nan)
lo_ptr = 0
for k, i in enumerate(vidx):
    while vidx[lo_ptr] < i and W_t[vidx[lo_ptr]] < W_t[i] - DAY7:
        lo_ptr += 1
    if k - lo_ptr >= MIN_HIST:
        p25[i], p5[i], p95[i] = np.percentile(r5[vidx[lo_ptr:k]], [2.5, 5, 95])
scored = ~np.isnan(p5)
first = np.where(scored)[0][0]


def first_of_cluster(idx, gap=3600):
    keep, last = [], -10 ** 12
    for i in idx:
        if W_t[i] - last >= gap:
            keep.append(i); last = W_t[i]
    return np.array(keep, int)


shocks = first_of_cluster(np.where(valid & scored & (r5 <= p5))[0])
robust = np.array([r5[i] <= p25[i] for i in shocks], bool)
ups = first_of_cluster(np.where(valid & scored & (r5 >= p95))[0])
say(f"windows {len(W_t)}, scorable {valid.sum()}, scoring from {dt.datetime.utcfromtimestamp(W_t[first])}; shocks first-of-cluster {len(shocks)} (robust {robust.sum()}), upside {len(ups)}")

# derivatives context (2026-07-31 -> 09-11 only)
ctx_t, ctx_imb, ctx_doi = np.array([], np.int64), np.array([]), np.array([])
liq_t, liq_cs = np.array([], np.int64), np.array([0.0])
try:
    rows = []
    for r in csv.DictReader(open(os.path.join(REC, "derivs_BTC.csv"), encoding="utf-8")):
        try:
            t = int(r["ts_ms"]) // 1000
            if t + 300 > 1789220400 - 86400 * 1 + 300:      # <= 2026-09-11 13:39 UTC (E018/E019 END)
                pass
            oi = float(r["open_interest"]); tb = float(r["taker_buy"]); ts_ = float(r["taker_sell"])
            rows.append((t, oi if oi > 1e8 else np.nan, (tb - ts_) / (tb + ts_) if tb + ts_ > 0 else np.nan))
        except Exception:
            pass
    rows.sort()
    ctx_t = np.array([x[0] for x in rows], np.int64); oi = np.array([x[1] for x in rows]); ctx_imb = np.array([x[2] for x in rows])
    ctx_doi = np.full(len(oi), np.nan)
    ok = np.concatenate([[False], (np.diff(ctx_t) == 300) & ~np.isnan(oi[1:]) & ~np.isnan(oi[:-1])])
    ctx_doi[ok] = oi[ok] / oi[np.where(ok)[0] - 1] - 1
    Lq = []
    for r in csv.DictReader(open(os.path.join(REC, "liquidations_BTC.csv"), encoding="utf-8")):
        try:
            Lq.append((int(r["ts_ms"]) // 1000, float(r["sz"]) * 0.01))
        except Exception:
            pass
    Lq.sort(); liq_t = np.array([x[0] for x in Lq], np.int64); liq_cs = np.concatenate([[0.0], np.cumsum([x[1] for x in Lq])])
except Exception as e:
    say(f"  derivatives context unavailable: {e}")
END_CTX = 1789220400 - 30 * 60 + 39 * 60 - 86400 * 0     # unused guard


def dctx(t_win):
    if len(ctx_t) == 0:
        return np.nan, np.nan, np.nan
    j = int(np.searchsorted(ctx_t, t_win))
    if j >= len(ctx_t) or ctx_t[j] != t_win or t_win > 1789133993:   # after 2026-09-11 13:39 UTC = E017 territory, never read
        return np.nan, np.nan, np.nan
    liq = liq_cs[np.searchsorted(liq_t, t_win + 300)] - liq_cs[np.searchsorted(liq_t, t_win)] if len(liq_t) else np.nan
    return ctx_imb[j], ctx_doi[j], liq


def trade(i, d):
    """d=-1 SELL (entry bid open, exits ask), d=+1 BUY (entry ask open, exits bid)."""
    ke = W_last[i] + 1
    if ke >= N or T[ke] - (W_t[i] + 300) > 600:
        return None
    e = O[ke] if d == -1 else ASK_O[ke]
    res = dict(i=i, t=W_t[i], t_entry=T[ke], entry=e, spread=SP[ke], hour=dt.datetime.utcfromtimestamp(T[ke]).hour, r5=r5[i], atr=ATR[i])
    for hm in HORIZ:
        kx = ke + hm - 1
        if kx < N and T[kx] - T[ke] <= (hm + 10) * 60:
            x = ASK_C[kx] if d == -1 else C[kx]
            res[f"n{hm}"] = (x - e) * d - SLIP
        else:
            res[f"n{hm}"] = np.nan
    k60 = min(N, ke + 60)
    if d == -1:
        fav = e - (L[ke:k60] + SP[ke:k60])          # buy-back at ask
        adv = ASK_H[ke:k60] - e
    else:
        fav = H[ke:k60] - e
        adv = e - L[ke:k60]
    if len(fav):
        res["mfe"], res["mae"] = fav.max(), adv.max()
        res["t_mfe"], res["t_mae"] = int(np.argmax(fav)), int(np.argmax(adv))
        a = ATR[i]
        for m in (0.5, 1.0):
            fu = np.where(fav >= m * a)[0]; fd = np.where(adv >= m * a)[0]
            fu = fu[0] if len(fu) else None; fd = fd[0] if len(fd) else None
            res[f"fp{m}"] = "neither" if fu is None and fd is None else ("adv" if fd is not None and (fu is None or fd <= fu) else "fav")
    else:
        res["mfe"] = res["mae"] = res["t_mfe"] = res["t_mae"] = np.nan; res["fp0.5"] = res["fp1.0"] = "neither"
    j24 = int(np.searchsorted(T, T[ke] - 86400)); k1h = int(np.searchsorted(T, T[ke] - 3600))
    res["vol24"] = np.median(H[j24:ke] - L[j24:ke]) if ke > j24 else np.nan
    res["d_hi"] = (H[k1h:ke].max() - e) / ATR[i] if ke > k1h and ATR[i] else np.nan
    res["d_lo"] = (e - L[k1h:ke].min()) / ATR[i] if ke > k1h and ATR[i] else np.nan
    res["imb"], res["dOI"], res["liq"] = dctx(int(W_t[i]))
    return res


S = [x for x in (trade(i, -1) for i in shocks) if x is not None]
SR = [x for x, rb in zip((trade(i, -1) for i in shocks), robust) if x is not None and rb]
Cb = [x for x in (trade(i, 1) for i in shocks) if x is not None]
Ub = [x for x in (trade(i, 1) for i in ups) if x is not None]


def cell(evs, h):
    return np.array([e[f"n{h}"] for e in evs if not np.isnan(e[f"n{h}"])])


def line(evs, label):
    cells = []
    for h in HORIZ:
        v = cell(evs, h)
        cells.append(f"{v.mean():+7.1f}({(v>0).mean():3.0%})" if len(v) else "         -")
    say(f"  {label:<36s}" + "".join(f"{c:>12s}" for c in cells) + f"  n {len(evs)}")


def anti(evs, label):
    v = cell(evs, PH)
    if len(v) < 3:
        return
    srt = np.sort(v)[::-1]; k10 = int(np.ceil(len(v) * 0.1)); ktr = int(len(v) * 0.1)
    vs = np.array([e[f"n{PH}"] for e in sorted(evs, key=lambda e: e["t"]) if not np.isnan(e[f"n{PH}"])])
    cum = np.cumsum(vs); peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    s = mx = 0
    for x in vs:
        s = s + 1 if x <= 0 else 0; mx = max(mx, s)
    say(f"    {label} {PH} m: median {np.median(v):+.1f}, trimmed10% {np.sort(v)[ktr:len(v)-ktr].mean():+.1f}, without best-1 {srt[1:].mean():+.1f}, best-2 {srt[2:].mean():+.1f}, top-10% ({k10}) {srt[k10:].mean():+.1f}; best {srt[0]:+.0f} worst {srt[-1]:+.0f}; maxDD {np.max(peak-cum):.0f} pts; longest losing streak {mx}")


say(f"\n=== {LABEL}: net points after spread + $5 ===")
say("  set                                 " + "".join(f"{h:>11d}m" for h in HORIZ))
line(S, "PRIMARY: downside shock -> SELL")
line(SR, "robustness p2.5 -> SELL")
line(Cb, "control C: same events -> BUY")
line(Ub, "control B: upside shock -> BUY")
anti(S, "primary SELL")
anti(SR, "robust SELL")
anti(Ub, "upside BUY")
if S:
    say(f"    path (SELL, 60 min): MFE(down) median {np.nanmedian([e['mfe'] for e in S]):.0f} at {np.nanmedian([e['t_mfe'] for e in S]):.0f} min (p25 {np.nanpercentile([e['t_mfe'] for e in S],25):.0f}, p75 {np.nanpercentile([e['t_mfe'] for e in S],75):.0f}); MAE(up) median {np.nanmedian([e['mae'] for e in S]):.0f} at {np.nanmedian([e['t_mae'] for e in S]):.0f} min; ATR median {np.nanmedian([e['atr'] for e in S]):.0f}; MAE-before-MFE {np.mean([e['t_mae'] < e['t_mfe'] for e in S]):.0%}")
    for m in (0.5, 1.0):
        c = {k: sum(1 for e in S if e[f'fp{m}'] == k) for k in ("fav", "adv", "neither")}
        say(f"    first passage ±{m} ATR (fav = down): favourable-first {c['fav']/len(S):.0%}, adverse-first {c['adv']/len(S):.0%}, neither {c['neither']/len(S):.0%}")
    rs = np.array([e["r5"] for e in S]); q1, q2 = np.percentile(rs, [33.3, 66.7])
    for nm, sel in (("largest shocks", [e for e in S if e["r5"] <= q1]), ("medium", [e for e in S if q1 < e["r5"] <= q2]), ("mild", [e for e in S if e["r5"] > q2])):
        v = cell(sel, PH); srt = np.sort(v)[::-1]
        say(f"    severity {nm:<15s} r5 median {np.median([e['r5'] for e in sel])*100:+.2f}%: {PH} m {v.mean():+.1f} (wr {(v>0).mean():.0%}, median {np.median(v):+.1f}, without best-2 {srt[2:].mean():+.1f}); 5 m {cell(sel,5).mean():+.1f}; 60 m {cell(sel,60).mean():+.1f}; n {len(sel)}")
    def split(name, key, fmt="%.2f"):
        vals = np.array([e[key] for e in S], float); okm = ~np.isnan(vals)
        if okm.sum() < 20:
            return
        med = np.nanmedian(vals); lo_ = [e for e, v in zip(S, vals) if not np.isnan(v) and v <= med]; hi_ = [e for e, v in zip(S, vals) if not np.isnan(v) and v > med]
        say(f"    context {name}: median {med:{fmt[1:]}}; <=median {PH} m {cell(lo_,PH).mean():+.1f} (n {len(lo_)}) / >median {cell(hi_,PH).mean():+.1f} (n {len(hi_)})")
    split("24h vol (pts)", "vol24"); split("spread", "spread"); split("dist below 1h high (ATR)", "d_hi"); split("dist above 1h low (ATR)", "d_lo")
    split("taker imbalance (2026-07/09 only)", "imb", "%.3f"); split("OI change (2026-07/09 only)", "dOI", "%.4f"); split("liquidated BTC (2026-07/09 only)", "liq")
    say("    hour buckets " + ", ".join(f"{a:02d}-{b:02d}h {cell([e for e in S if a <= e['hour'] < b],PH).mean() if [e for e in S if a <= e['hour'] < b] else np.nan:+.0f}/{len([e for e in S if a <= e['hour'] < b])}" for a, b in ((0, 6), (6, 12), (12, 18), (18, 24))))

# control A: matched random SHORT entries
after = np.zeros(N, bool)
for i in shocks:
    k0 = W_last[i] + 1; after[k0:min(N, k0 + 120)] = True
ok_bars = np.arange(1, N - 70)[~after[1:N - 70]]
by_hour = {h: ok_bars[((T[ok_bars] // 3600) % 24) == h] for h in range(24)}
hours = [e["hour"] for e in S]
sims = {h: [] for h in HORIZ}
for _ in range(NRAND):
    picks = np.array([RNG.choice(by_hour[hr]) for hr in hours if len(by_hour[hr])])
    e = O[picks]
    for hm in HORIZ:
        kx = picks + hm - 1
        okx = (T[kx] - T[picks]) <= (hm + 10) * 60
        sims[hm].append(((ASK_C[kx] - e) * -1 - SLIP)[okx].mean())
say("  control A matched random SHORT (1000 draws): " + "; ".join(f"{h} m real {cell(S,h).mean():+.1f} vs {np.mean(sims[h]):+.1f} ± {np.std(sims[h]):.1f}, 95th {np.percentile(sims[h],95):+.1f}, pctile {(np.array(sims[h]) < cell(S,h).mean()).mean()*100:.1f}%" for h in HORIZ))
days = (T[-1] - W_t[first]) / 86400
ts_ev = np.array(sorted(e["t_entry"] for e in S)); gaps = np.diff(ts_ev) / 3600
say(f"  frequency: {len(S)/days:.2f}/day = {len(S)/days*7:.1f}/week; days with none {1 - len(set(int(t//86400) for t in ts_ev)) / (int(T[-1]//86400) - int(W_t[first]//86400) + 1):.0%}; median spacing {np.median(gaps):.1f} h; longest gap {gaps.max():.1f} h")
say("  by month (SELL 30 m mean / n): " + ", ".join(f"{m} {cell([e for e in S if dt.datetime.utcfromtimestamp(e['t']).strftime('%Y-%m')==m],PH).mean():+.0f}/{len([e for e in S if dt.datetime.utcfromtimestamp(e['t']).strftime('%Y-%m')==m])}" for m in sorted(set(dt.datetime.utcfromtimestamp(e['t']).strftime('%Y-%m') for e in S))))
with open(os.path.join(HERE, f"events_{LABEL}.csv"), "w", newline="", encoding="utf-8") as f:
    wtr = csv.writer(f)
    keys = ["t_entry", "entry", "spread", "hour", "r5", "atr", "mfe", "t_mfe", "mae", "t_mae", "fp0.5", "fp1.0", "vol24", "d_hi", "d_lo", "imb", "dOI", "liq"] + [f"n{h}" for h in HORIZ]
    wtr.writerow(["set", "shock_utc"] + keys)
    for nm, evs in (("sell", S), ("buy_same", Cb), ("upside_buy", Ub)):
        for e in evs:
            wtr.writerow([nm, dt.datetime.utcfromtimestamp(e["t"]).isoformat()] + [e.get(k, "") if not isinstance(e.get(k), float) or not np.isnan(e.get(k)) else "" for k in keys])
say("done")
out.close()
