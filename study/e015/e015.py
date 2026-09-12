"""E015 - BTC response after forced-liquidation bursts (frozen in PREREG_E015.md).
Light: M1 + CSVs. No V4, no production change."""
import csv
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LIQ = r"C:\Projects\KinoliveLines\recorder\data\liquidations_BTC.csv"
DER = r"C:\Projects\KinoliveLines\recorder\data\derivs_BTC.csv"
utc = dt.timezone.utc
out = open(os.path.join(HERE, "results_e015.txt"), "w", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HORIZONS = (1, 5, 15, 30, 60)
COST = 12.0          # $7 spread + $5 round-trip slippage, in points
LOT = 0.02
NS = 1000


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")


# ---------------------------------------------------------------- price
M = np.load(os.path.join(HERE, "..", "e011", "data", "archive_2026_07_09_m1.npz"))
T, O, H, L, C, SP = (M["t"].astype(np.int64), M["o"].astype(float), M["h"].astype(float), M["l"].astype(float), M["c"].astype(float), M["sp"].astype(float))
atr14 = np.concatenate([np.full(13, np.nan), np.convolve(H - L, np.ones(14) / 14, "valid")])
N = len(T)

# ---------------------------------------------------------------- liquidations -> 5-min buckets
long_btc, short_btc = {}, {}
n_rows = 0
for r in csv.DictReader(open(LIQ, encoding="utf-8")):
    try:
        ms = int(r["ts_ms"])
        sz = float(r["sz"]) * 0.01
    except Exception:
        continue
    n_rows += 1
    b = ms // 300000
    if r["posSide"] == "long":
        long_btc[b] = long_btc.get(b, 0.0) + sz
    else:
        short_btc[b] = short_btc.get(b, 0.0) + sz
buckets = sorted(set(long_btc) | set(short_btc))
bt = np.array(buckets, np.int64)
tot = np.array([long_btc.get(b, 0.0) + short_btc.get(b, 0.0) for b in buckets])
lng = np.array([long_btc.get(b, 0.0) for b in buckets])
sht = np.array([short_btc.get(b, 0.0) for b in buckets])
feed_lo, feed_hi = bt[0] * 300, bt[-1] * 300
say(f"liquidation feed: {n_rows} fills, {len(bt)} non-empty 5-min buckets, {dt.datetime.utcfromtimestamp(feed_lo)} -> {dt.datetime.utcfromtimestamp(feed_hi)} "
    f"(price data to {dt.datetime.utcfromtimestamp(int(T[-1]))}); bucket total BTC median {np.median(tot):.2f} p95 {np.percentile(tot,95):.2f} max {tot.max():.1f}")

# derivs context
der = {}
for r in csv.DictReader(open(DER, encoding="utf-8")):
    try:
        der[int(r["ts_ms"]) // 300000] = (float(r["open_interest"]), float(r["taker_buy"]), float(r["taker_sell"]))
    except Exception:
        pass


def large_events(window_days):
    W = window_days * 86400
    ev = []
    for i, b in enumerate(bt):
        t = int(b) * 300
        if t - W < feed_lo:
            continue
        lo = np.searchsorted(bt, (t - W) // 300, side="left")
        hist = tot[lo:i]
        if len(hist) < 200:
            continue
        q = np.percentile(hist, 95)
        if tot[i] >= q:
            ev.append(dict(b=int(b), t_end=t + 300, total=float(tot[i]), long=float(lng[i]), short=float(sht[i]), q95=float(q),
                           d=(-1 if lng[i] >= sht[i] else 1)))     # forced selling -> continuation = SELL (-1)
    # merge consecutive large buckets into episodes; entry after the last bucket
    eps = []
    for e in ev:
        if eps and e["b"] == eps[-1]["b_last"] + 1:
            eps[-1]["b_last"] = e["b"]
            eps[-1]["t_end"] = e["t_end"]
            eps[-1]["total"] += e["total"]
            eps[-1]["long"] += e["long"]
            eps[-1]["short"] += e["short"]
            eps[-1]["n_b"] += 1
        else:
            eps.append(dict(e, b_last=e["b"], n_b=1))
    for e in eps:
        e["d"] = -1 if e["long"] >= e["short"] else 1
    return eps


def entry_index(t_end):
    j = int(np.searchsorted(T, t_end - 60))      # first bar whose close (T+60) >= t_end
    return j if j + 61 < N else None


def outcomes(j, d):
    """Net points for CONTINUATION (direction d) and REVERSAL (-d) at each horizon, MFE/MAE 60, first passage +/-1 ATR."""
    res = {}
    for dd, nm in ((d, "cont"), (-d, "rev")):
        e = C[j] + (SP[j] if dd == 1 else 0.0)
        for h in HORIZONS:
            x = C[j + h] + (SP[j + h] if dd == -1 else 0.0)
            res[f"{nm}{h}"] = (x - e) * dd - 5.0
    seg_h, seg_l = H[j + 1:j + 61], L[j + 1:j + 61]
    res["mfe"] = ((seg_h.max() - C[j]) if d == 1 else (C[j] - seg_l.min()))
    res["mae"] = ((C[j] - seg_l.min()) if d == 1 else (seg_h.max() - C[j]))
    a = atr14[j] if not np.isnan(atr14[j]) else np.nan
    res["atr"] = a
    fp = "none"
    if not np.isnan(a):
        for k in range(j + 1, j + 61):
            fav = (H[k] >= C[j] + a) if d == 1 else (L[k] <= C[j] - a)
            adv = (L[k] <= C[j] - a) if d == 1 else (H[k] >= C[j] + a)
            if adv:
                fp = "adverse"
                break
            if fav:
                fp = "favourable"
                break
    res["fp"] = fp
    return res


def summarize(rows, label):
    if not rows:
        say(f"  {label}: n 0")
        return
    say(f"  {label}: n {len(rows)}")
    for nm in ("cont", "rev"):
        parts = []
        for h in HORIZONS:
            v = np.array([r[f"{nm}{h}"] for r in rows])
            parts.append(f"{h:2d}m {v.mean():+7.2f} pts (wr {(v>0).mean():.0%})")
        say(f"    {nm.upper():4s} net after $12 costs: " + " | ".join(parts))
    say(f"    MFE60 {np.mean([r['mfe'] for r in rows]):.1f} MAE60 {np.mean([r['mae'] for r in rows]):.1f} pts (cascade direction); "
        f"first passage +/-1 ATR: fav {np.mean([r['fp']=='favourable' for r in rows]):.0%} adv {np.mean([r['fp']=='adverse' for r in rows]):.0%} none {np.mean([r['fp']=='none' for r in rows]):.0%}")


# ---------------------------------------------------------------- events + outcomes
for wd in (7, 30):
    eps = large_events(wd)
    rows = []
    for e in eps:
        j = entry_index(e["t_end"])
        if j is None or T[j] < feed_lo:
            continue
        r = dict(e, j=j, t=int(T[j]) + 60)
        r.update(outcomes(j, e["d"]))
        if e["b"] in der and (e["b"] - 1) in der:
            oi1, tb, ts = der[e["b"]]
            oi0 = der[e["b"] - 1][0]
            r["oi_chg"] = (oi1 - oi0) / oi0 * 100
            r["taker_imb"] = (tb - ts) / (tb + ts) if (tb + ts) > 0 else np.nan
        rows.append(r)
    say(f"\n=== TRAILING {wd}-DAY 95th-PERCENTILE CASCADES{' (FROZEN PRIMARY)' if wd == 7 else ' (original 30-day rule, fewer scorable days)'} ===")
    say(f"  large buckets -> {len(eps)} episodes ({sum(1 for e in eps if e['n_b']>1)} multi-bucket), {len(rows)} with price data; "
        f"forced-selling {sum(1 for r in rows if r['d']==-1)}, forced-buying {sum(1 for r in rows if r['d']==1)}; "
        f"episode size median {np.median([r['total'] for r in rows]):.1f} BTC, q95 threshold median {np.median([r['q95'] for r in rows]):.1f} BTC")
    if wd == 7:
        EV = rows
    summarize(rows, "ALL")
    summarize([r for r in rows if r["d"] == -1], "forced SELLING cascades")
    summarize([r for r in rows if r["d"] == 1], "forced BUYING cascades")
    if wd == 7:
        mid = (feed_lo + int(T[-1])) // 2
        summarize([r for r in rows if r["t"] < mid], "first half")
        summarize([r for r in rows if r["t"] >= mid], "second half")
        sz = np.array([r["total"] for r in rows])
        q1, q2 = np.percentile(sz, [33.3, 66.7])
        summarize([r for r in rows if r["total"] < q1], "size tertile SMALL")
        summarize([r for r in rows if q1 <= r["total"] < q2], "size tertile MID")
        summarize([r for r in rows if r["total"] >= q2], "size tertile LARGE")
        ctx = [r for r in rows if "oi_chg" in r]
        if ctx:
            say(f"  context at event buckets: OI change mean {np.mean([r['oi_chg'] for r in ctx]):+.3f}% (all buckets ~ 0), taker imbalance mean {np.nanmean([r['taker_imb'] for r in ctx]):+.3f}; "
                f"forced-selling events taker imb {np.nanmean([r['taker_imb'] for r in ctx if r['d']==-1]):+.3f}, forced-buying {np.nanmean([r['taker_imb'] for r in ctx if r['d']==1]):+.3f}")

# ---------------------------------------------------------------- matched random controls (7-day primary)
say(f"\n=== MATCHED RANDOM CONTROL ({NS} draws): same number of timestamps, same hour-of-day per event, non-event buckets, event direction inherited ===")
ev_b = set()
for r in EV:
    for k in range(r["b"] - 1, r["b_last"] + 13):     # exclude the episode and 60 min after
        ev_b.add(k)
all_b = np.arange(feed_lo // 300, int(T[-1]) // 300 - 13)
cand = np.array([b for b in all_b if b not in ev_b])
cand_hour = (cand * 300 // 3600) % 24
by_hour = {h: cand[cand_hour == h] for h in range(24)}
rng = np.random.default_rng(15)
real = {f"{nm}{h}": np.mean([r[f"{nm}{h}"] for r in EV]) for nm in ("cont", "rev") for h in HORIZONS}
sims = {k: [] for k in real}
ev_hours = [(r["b"] * 300 // 3600) % 24 for r in EV]
for s in range(NS):
    acc = {k: 0.0 for k in real}
    n = 0
    for r, hr in zip(EV, ev_hours):
        pool = by_hour[hr]
        b = int(pool[rng.integers(len(pool))])
        j = entry_index(b * 300 + 300)
        if j is None:
            continue
        o = outcomes(j, r["d"])
        for k in acc:
            acc[k] += o[k]
        n += 1
    for k in acc:
        sims[k].append(acc[k] / max(n, 1))
say(f"  {'cell':8s} {'real':>8s} {'rnd mean':>9s} {'sd':>7s} {'p95':>8s} {'p99.5':>8s} {'max':>8s} {'pctile':>7s} {'z':>6s}")
verdict_cells = []
for nm in ("cont", "rev"):
    for h in HORIZONS:
        k = f"{nm}{h}"
        v = np.array(sims[k])
        pct = (v < real[k]).mean()
        z = (real[k] - v.mean()) / v.std() if v.std() > 0 else 0
        say(f"  {k:8s} {real[k]:+8.2f} {v.mean():+9.2f} {v.std():7.2f} {np.percentile(v,95):+8.2f} {np.percentile(v,99.5):+8.2f} {v.max():+8.2f} {pct:7.1%} {z:+6.2f}")
        verdict_cells.append((k, real[k], pct, z))
np.save(os.path.join(HERE, "control_sims.npy"), np.array([[sims[k][i] for k in real] for i in range(NS)]))

# ---------------------------------------------------------------- pass rule + harvest of the best predeclared cell
say("\n=== PASS RULE (frozen): better direction net > 0 AND above the 99.5th random percentile AND same sign in both halves ===")
best = max(verdict_cells, key=lambda c: c[1])
k, rv, pct, z = best
nm, h = ("cont" if k.startswith("cont") else "rev"), int(k[4:] if k.startswith("cont") else k[3:])
mid = (feed_lo + int(T[-1])) // 2
h1 = np.mean([r[k] for r in EV if r["t"] < mid])
h2 = np.mean([r[k] for r in EV if r["t"] >= mid])
say(f"  best cell {k}: real {rv:+.2f} pts net, random percentile {pct:.1%}, z {z:+.2f}; halves {h1:+.2f} / {h2:+.2f}")
A = rv > 0 and pct >= 0.995 and h1 > 0 and h2 > 0
B = (not A) and pct >= 0.95
say(f"  -> {'A candidate' if A else ('B (beats random at 95% but fails costs/halves/99.5)' if B else 'C (does not beat matched random)')}")
seq = sorted([(r["t"], r[k] * LOT) for r in EV])
eq = base = 500.0
w = 0
dead = None
for t, usd in seq:
    eq += usd
    if eq >= base + 100:
        eq -= 100
        w += 100
        base = eq
    if eq <= base - 60:
        dead = t
        break
say(f"  fixed-lot harvest of that cell ($500, +$100, -60): withdrawn {w}, ending {eq:.2f}, ruin {dt.datetime.utcfromtimestamp(dead).strftime('%Y-%m-%d') if dead else 'none'} "
    f"(n {len(seq)}, net {sum(u for _, u in seq):+.2f})")

with open(os.path.join(HERE, "events_e015.csv"), "w", newline="") as fh:
    wcsv = csv.writer(fh)
    wcsv.writerow(["episode_end_utc", "entry_utc", "n_buckets", "total_btc", "long_btc", "short_btc", "q95", "dir(-1=forced selling)", "atr14"] + [f"cont{h}" for h in HORIZONS] + [f"rev{h}" for h in HORIZONS] + ["mfe60", "mae60", "fp1atr", "oi_chg_pct", "taker_imb"])
    for r in sorted(EV, key=lambda r: r["t"]):
        wcsv.writerow([dt.datetime.utcfromtimestamp(r["t_end"]).isoformat(), dt.datetime.utcfromtimestamp(r["t"]).isoformat(), r["n_b"], round(r["total"], 3), round(r["long"], 3), round(r["short"], 3),
                       round(r["q95"], 3), r["d"], round(r["atr"], 2) if not np.isnan(r["atr"]) else ""] + [round(r[f"cont{h}"], 2) for h in HORIZONS] + [round(r[f"rev{h}"], 2) for h in HORIZONS]
                      + [round(r["mfe"], 2), round(r["mae"], 2), r["fp"], round(r.get("oi_chg", np.nan), 3) if "oi_chg" in r else "", round(r.get("taker_imb", np.nan), 3) if "taker_imb" in r else ""])
say("\ndone")
out.close()
