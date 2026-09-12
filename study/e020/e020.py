"""E020 - downside shock -> flush -> reclaim, per PREREG_E020.md (frozen before
results). M1 bars (bid OHLC + mean spread) for every era so eras are
comparable. Usage: python e020.py <label> <m1.npz> [<m1.npz> ...]
Writes results_<label>.txt and events_<label>.csv next to this file."""
import csv
import datetime as dt
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
LABEL = sys.argv[1]
FILES = sys.argv[2:]
out = open(os.path.join(HERE, f"results_{LABEL}.txt"), "w", encoding="utf-8")
SLIP = 5.0
HORIZ = (5, 15, 30, 60)
PH = 30
NRAND = 1000
MIN_HIST = 1000
WAIT = 60                       # minutes after the shock close for flush + reclaim
RNG = np.random.default_rng(20)


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
ASK_O = O + SP                                   # ask at bar open (mean spread of the bar)

# ---------------------------------------------------------------- 5-min windows on the clock
w = T // 300
ws = np.concatenate([[0], np.where(np.diff(w) != 0)[0] + 1])
we = np.concatenate([ws[1:], [N]])
W_t = w[ws] * 300
W_lo = np.array([L[s:e].min() for s, e in zip(ws, we)])
W_hi = np.array([H[s:e].max() for s, e in zip(ws, we)])
W_cl = C[we - 1]
W_last = we - 1                                   # index of the window's last bar
W_full = (we - ws) >= 4                           # at least 4 of 5 bars present
r5 = np.full(len(W_t), np.nan)
r5[1:] = W_cl[1:] / W_cl[:-1] - 1
consecutive = np.concatenate([[False], np.diff(W_t) == 300])
r5[~consecutive] = np.nan
tr = np.maximum(W_hi[1:] - W_lo[1:], np.maximum(np.abs(W_hi[1:] - W_cl[:-1]), np.abs(W_lo[1:] - W_cl[:-1])))
ATR = np.full(len(W_t), np.nan)
for i in range(15, len(W_t)):
    ATR[i] = tr[i - 15:i - 1].mean()
valid = ~np.isnan(r5) & W_full
vidx = np.where(valid)[0]
DAY7 = 7 * 86400
p5 = np.full(len(W_t), np.nan)
lo_ptr = 0
for k, i in enumerate(vidx):
    while vidx[lo_ptr] < i and W_t[vidx[lo_ptr]] < W_t[i] - DAY7:
        lo_ptr += 1
    if k - lo_ptr >= MIN_HIST:
        p5[i] = np.percentile(r5[vidx[lo_ptr:k]], 5)
shock_raw = np.where(valid & ~np.isnan(p5) & (r5 <= p5))[0]
nonshock = np.where(valid & ~np.isnan(p5) & (r5 > p5))[0]


def first_of_cluster(idx, gap=3600):
    keep, last = [], -10 ** 12
    for i in idx:
        if W_t[i] - last >= gap:
            keep.append(i); last = W_t[i]
    return np.array(keep, int)


shocks = first_of_cluster(shock_raw)
first_scored = np.where(~np.isnan(p5))[0]
say(f"windows {len(W_t)}, scorable {valid.sum()}, scoring from {dt.datetime.utcfromtimestamp(W_t[first_scored[0]]/1000*1000) if len(first_scored) else None}; raw shocks {len(shock_raw)}, first-of-cluster {len(shocks)}")


# ---------------------------------------------------------------- the rule
def bar_idx_after(t_sec):
    return int(np.searchsorted(T, t_sec, side="left"))


def path(k_entry, e, horizon_min=60):
    """bid path after entry at bar k_entry (entry price e = ask open). Returns nets at HORIZ, mfe, mae, seg."""
    res = {}
    for hm in HORIZ:
        kx = k_entry + hm - 1
        res[f"n{hm}"] = (C[kx] - e - SLIP) if kx < N and T[kx] - T[k_entry] <= (hm + 10) * 60 else np.nan
    k60 = min(N, k_entry + horizon_min)
    res["mfe"] = H[k_entry:k60].max() - e if k60 > k_entry else np.nan
    res["mae"] = e - L[k_entry:k60].min() if k60 > k_entry else np.nan
    return res, k60


def reclaim_trade(i, lowref):
    """Apply flush/reclaim to window i with reference low lowref. Returns dict or a reason string."""
    t_close = W_t[i] + 300
    k0 = W_last[i] + 1                                   # first bar after the window
    deadline = t_close + WAIT * 60
    k = k0
    breach = None
    while k < N and T[k] < deadline:
        if L[k] < lowref:
            breach = k; break
        k += 1
    if breach is None:
        return "no_flush"
    k = breach
    flush_low = L[k]
    while k < N and T[k] + 60 <= deadline:               # reclaim bar must close by the deadline
        flush_low = min(flush_low, L[k])
        if C[k] > lowref:
            ke = k + 1
            if ke >= N:
                return "no_reclaim"
            e = ASK_O[ke]
            R = e - flush_low
            res, k60 = path(ke, e)
            seg_h, seg_l = H[ke:k60], L[ke:k60]
            fp = {}
            for m in (0.5, 1.0, 1.5):
                up = np.where(seg_h >= e + m * R)[0]
                dn = np.where(seg_l <= flush_low)[0]
                fu = up[0] if len(up) else None
                fd = dn[0] if len(dn) else None
                fp[m] = "neither" if fu is None and fd is None else ("adv" if fd is not None and (fu is None or fd <= fu) else "fav")
            body = abs(C[k] - O[k]); rng_ = H[k] - L[k]
            j24 = bar_idx_after(T[ke] - 86400)
            return dict(i=i, t=W_t[i], t_entry=T[ke], entry=e, R=R, flush_low=flush_low, same_bar=(k == breach),
                        min_to_flush=(T[breach] - t_close) / 60, min_flush_to_reclaim=(T[k] + 60 - T[breach]) / 60,
                        depth=lowref - flush_low, depth_atr=(lowref - flush_low) / ATR[i] if ATR[i] else np.nan,
                        body=body, rng=rng_, spread=SP[ke], vol24=np.median(H[j24:ke] - L[j24:ke]) if ke > j24 else np.nan,
                        hour=dt.datetime.utcfromtimestamp(T[ke]).hour, bos=bool(C[k] > H[max(0, k - 3):k].max()) if k > 0 else False,
                        fp05=fp[0.5], fp10=fp[1.0], fp15=fp[1.5], **res)
        k += 1
    return "no_reclaim"


def immediate_trade(i):
    ke = W_last[i] + 1
    if ke >= N or T[ke] - (W_t[i] + 300) > 600:
        return None
    e = ASK_O[ke]
    res, _ = path(ke, e)
    return dict(i=i, t=W_t[i], t_entry=T[ke], entry=e, spread=SP[ke], hour=dt.datetime.utcfromtimestamp(T[ke]).hour, **res)


def no_reclaim_path(i, lowref):
    t_close = W_t[i] + 300
    kd = bar_idx_after(t_close + WAIT * 60)
    if kd + 60 >= N:
        return None
    base = C[kd]
    return dict(m30=C[kd + 30] - base, m60=C[kd + 60] - base, mfe=H[kd:kd + 60].max() - base, mae=base - L[kd:kd + 60].min(), vs_low=base - lowref)


# ---------------------------------------------------------------- run
P, A, Bn = [], [], []
n_flush = 0
for i in shocks:
    r = reclaim_trade(i, W_lo[i])
    a = immediate_trade(i)
    if a is not None:
        A.append(a)
    if isinstance(r, dict):
        P.append(r); n_flush += 1
    elif r == "no_reclaim":
        n_flush += 1
        b = no_reclaim_path(i, W_lo[i])
        if b is not None:
            Bn.append(b)
# control C: generic sweep/reclaim on non-shock windows, not within 60 min after a shock
shock_t = W_t[shocks]
Cc = []
cand = [i for i in nonshock if not np.any((shock_t <= W_t[i]) & (shock_t > W_t[i] - 3600))]
last = -10 ** 12
for i in cand:
    if W_t[i] - last < 3600:
        continue
    r = reclaim_trade(i, W_lo[i])
    if isinstance(r, dict):
        Cc.append(r); last = W_t[i]
# control D: matched random
hours = [e["hour"] for e in P]
all_bars = np.arange(1, N - 70)
bar_hr = (T[all_bars] // 3600) % 24
after_shock = np.zeros(N, bool)
for i in shocks:
    k0 = W_last[i] + 1
    after_shock[k0:min(N, k0 + 120)] = True
ok_bars = all_bars[~after_shock[all_bars]]
ok_hr = bar_hr[~after_shock[all_bars]]
sims = {h: [] for h in HORIZ}
for _ in range(NRAND):
    picks = [RNG.choice(ok_bars[ok_hr == hr]) for hr in hours if (ok_hr == hr).any()]
    vals = {h: [] for h in HORIZ}
    for ke in picks:
        e = ASK_O[ke]
        res, _ = path(ke, e)
        for h in HORIZ:
            if not np.isnan(res[f"n{h}"]):
                vals[h].append(res[f"n{h}"])
    for h in HORIZ:
        sims[h].append(np.mean(vals[h]) if vals[h] else np.nan)


def cell(evs, h):
    return np.array([e[f"n{h}"] for e in evs if not np.isnan(e[f"n{h}"])])


def line(evs, label):
    cells = []
    for h in HORIZ:
        v = cell(evs, h)
        cells.append(f"{v.mean():+7.1f}({(v>0).mean():3.0%})" if len(v) else "         -")
    say(f"  {label:<34s}" + "".join(f"{c:>12s}" for c in cells) + f"  n {len(evs)}")


def anti(evs, label):
    v = cell(evs, PH)
    if len(v) < 3:
        return
    srt = np.sort(v)[::-1]; k10 = int(np.ceil(len(v) * 0.1))
    say(f"    {label} {PH} m: median {np.median(v):+.1f}, without best-1 {srt[1:].mean():+.1f}, best-2 {srt[2:].mean():+.1f}, top-10% ({k10}) {srt[k10:].mean():+.1f}; best {srt[0]:+.0f} worst {srt[-1]:+.0f}")


def seqdd(evs, h):
    v = np.array([e[f"n{h}"] for e in sorted(evs, key=lambda e: e["t"]) if not np.isnan(e[f"n{h}"])])
    cum = np.cumsum(v); peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    s = mx = 0
    for x in v:
        s = s + 1 if x <= 0 else 0; mx = max(mx, s)
    return np.max(peak - cum) if len(v) else np.nan, mx


say(f"\n=== {LABEL}: net points after spread + $5, BUY ===")
say("  set                               " + "".join(f"{h:>11d}m" for h in HORIZ))
line(P, "RECLAIM rule (shock->flush->reclaim)")
line(A, "control A immediate entry")
line(Cc, "control C generic sweep/reclaim")
anti(P, "reclaim")
anti(A, "immediate")
anti(Cc, "generic")
if P:
    say(f"    first passage vs -1R (stop at flush low), within 60 min: " + "; ".join(f"+{m}R fav-first {sum(1 for e in P if e[k]=='fav')/len(P):.0%} / adv-first {sum(1 for e in P if e[k]=='adv')/len(P):.0%} / neither {sum(1 for e in P if e[k]=='neither')/len(P):.0%}" for m, k in ((0.5, 'fp05'), (1.0, 'fp10'), (1.5, 'fp15'))))
    say(f"    R median {np.median([e['R'] for e in P]):.0f} pts; 60-min MFE median {np.nanmedian([e['mfe'] for e in P]):.0f} / MAE median {np.nanmedian([e['mae'] for e in P]):.0f}; maxDD {PH} m {seqdd(P, PH)[0]:.0f} pts, longest losing streak {seqdd(P, PH)[1]}")
    say(f"    quality (descriptive): shock->flush median {np.median([e['min_to_flush'] for e in P]):.0f} min; flush->reclaim median {np.median([e['min_flush_to_reclaim'] for e in P]):.0f} min; same-bar reclaim {np.mean([e['same_bar'] for e in P]):.0%}; depth median {np.median([e['depth'] for e in P]):.0f} pts = {np.nanmedian([e['depth_atr'] for e in P]):.2f} ATR; reclaim body/range median {np.median([e['body'] for e in P]):.0f}/{np.median([e['rng'] for e in P]):.0f}; spread median {np.median([e['spread'] for e in P]):.2f}; M1 break-of-3-bar-high at reclaim {np.mean([e['bos'] for e in P]):.0%}")
    for nm, key in (("same-bar reclaim", "same_bar"), ("M1 3-bar break", "bos")):
        yes = [e for e in P if e[key]]; no = [e for e in P if not e[key]]
        say(f"    {nm}: yes {PH} m {cell(yes,PH).mean() if yes else np.nan:+.1f} (n {len(yes)}) / no {cell(no,PH).mean() if no else np.nan:+.1f} (n {len(no)})")
    for nm, key in (("flush depth (ATR)", "depth_atr"), ("R (pts)", "R"), ("24h vol", "vol24"), ("flush->reclaim min", "min_flush_to_reclaim")):
        vals = np.array([e[key] for e in P], float); med = np.nanmedian(vals)
        lo_ = [e for e, v in zip(P, vals) if v <= med]; hi_ = [e for e, v in zip(P, vals) if v > med]
        say(f"    {nm} median {med:.2f}: <=median {PH} m {cell(lo_,PH).mean():+.1f} (n {len(lo_)}) / >median {cell(hi_,PH).mean():+.1f} (n {len(hi_)})")
    say("    hour buckets " + ", ".join(f"{a:02d}-{b:02d}h {cell([e for e in P if a <= e['hour'] < b],PH).mean() if [e for e in P if a <= e['hour'] < b] else np.nan:+.0f}/{len([e for e in P if a <= e['hour'] < b])}" for a, b in ((0, 6), (6, 12), (12, 18), (18, 24))))
if Bn:
    say(f"  control B flush WITHOUT reclaim (n {len(Bn)}): bid move after the 60-min deadline: +30 m {np.mean([b['m30'] for b in Bn]):+.1f} ({np.mean([b['m30']>0 for b in Bn]):.0%} up), +60 m {np.mean([b['m60'] for b in Bn]):+.1f} ({np.mean([b['m60']>0 for b in Bn]):.0%} up); MFE median {np.median([b['mfe'] for b in Bn]):.0f} MAE median {np.median([b['mae'] for b in Bn]):.0f}; deadline close vs shock low median {np.median([b['vs_low'] for b in Bn]):+.0f} pts")
say("  control D matched random (1000 draws): " + "; ".join(f"{h} m real {cell(P,h).mean() if len(cell(P,h)) else np.nan:+.1f} vs {np.nanmean(sims[h]):+.1f} ± {np.nanstd(sims[h]):.1f}, 95th {np.nanpercentile(sims[h],95):+.1f}, pctile {(np.array(sims[h])[~np.isnan(sims[h])] < cell(P,h).mean()).mean()*100 if len(cell(P,h)) else np.nan:.1f}%" for h in HORIZ))
days = (T[-1] - T[np.searchsorted(T, W_t[first_scored[0]])]) / 86400 if len(first_scored) else np.nan
n_rec = len(P)
ts_ev = np.array(sorted(e["t_entry"] for e in P))
gaps = np.diff(ts_ev) / 3600 if len(ts_ev) > 1 else np.array([np.nan])
say(f"  frequency: shocks {len(shocks)/days:.2f}/day; flushed {n_flush/len(shocks) if len(shocks) else 0:.0%}; of flushed, reclaimed {n_rec/n_flush if n_flush else 0:.0%}; reclaim trades {n_rec/days:.2f}/day = {n_rec/days*7:.1f}/week; longest no-trade {np.nanmax(gaps)/24:.1f} days; median shock->entry {np.median([(e['t_entry']-e['t'])/60 for e in P]) if P else np.nan:.0f} min; days scored {days:.0f}")
# month by month (primary horizon)
say("  by month (reclaim, 30 m mean / n | immediate 30 m mean): " + ", ".join(
    f"{m} {cell([e for e in P if dt.datetime.utcfromtimestamp(e['t']).strftime('%Y-%m')==m],PH).mean():+.0f}/{len([e for e in P if dt.datetime.utcfromtimestamp(e['t']).strftime('%Y-%m')==m])} | {cell([e for e in A if dt.datetime.utcfromtimestamp(e['t']).strftime('%Y-%m')==m],PH).mean():+.0f}"
    for m in sorted(set(dt.datetime.utcfromtimestamp(e['t']).strftime('%Y-%m') for e in P))))
with open(os.path.join(HERE, f"events_{LABEL}.csv"), "w", newline="", encoding="utf-8") as f:
    wtr = csv.writer(f)
    keys = ["t_entry", "entry", "R", "flush_low", "same_bar", "min_to_flush", "min_flush_to_reclaim", "depth", "depth_atr", "body", "rng", "spread", "vol24", "hour", "bos", "fp05", "fp10", "fp15", "mfe", "mae"] + [f"n{h}" for h in HORIZ]
    wtr.writerow(["set", "shock_utc"] + keys)
    for nm, evs in (("reclaim", P), ("immediate", A), ("generic", Cc)):
        for e in evs:
            wtr.writerow([nm, dt.datetime.utcfromtimestamp(e["t"]).isoformat()] + [e.get(k, "") if not isinstance(e.get(k), float) or not np.isnan(e.get(k)) else "" for k in keys])
say("done")
out.close()
