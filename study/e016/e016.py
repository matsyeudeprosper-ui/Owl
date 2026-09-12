"""E016 - real-time burst detection from raw liquidation fills, tick execution
on Exness BTCUSD, per PREREG_E016.md (frozen before results). Discovery data
only (2026-07-31 -> 2026-09-11). Light: 8 M ticks + 75 k fills."""
import csv
import datetime as dt
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
LIQ = r"C:\Projects\KinoliveLines\recorder\data\liquidations_BTC.csv"
out = open(os.path.join(HERE, "results_e016.txt"), "w", encoding="utf-8")
WINDOWS = (15, 30, 60)
DELAYS = (0, 5, 10, 20, 30, 60)
HORIZ = (30, 60, 120, 300)
COOL = 300
SLIP = 5.0
NS = 1000
HALF = int(dt.datetime(2026, 8, 21, tzinfo=dt.timezone.utc).timestamp() * 1000)


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")


# ---------------------------------------------------------------- ticks
D = np.load(os.path.join(HERE, "..", "data", "ticks_btcusd.npz"))
tt, bid, ask = D["t"].astype(np.int64), D["bid"].astype(float), D["ask"].astype(float)
mid = (bid + ask) / 2
T_LO, T_HI = int(tt[0]), int(tt[-1])
say(f"ticks: {len(tt)} {dt.datetime.utcfromtimestamp(T_LO/1000)} -> {dt.datetime.utcfromtimestamp(T_HI/1000)}")

# ---------------------------------------------------------------- fills
F = []
for r in csv.DictReader(open(LIQ, encoding="utf-8")):
    try:
        F.append((int(r["ts_ms"]), float(r["sz"]) * 0.01, -1 if r["posSide"] == "long" else 1))   # long liq = forced selling -> -1
    except Exception:
        pass
F.sort()
ft = np.array([f[0] for f in F], np.int64)
fs = np.array([f[1] for f in F])
fd = np.array([f[2] for f in F], np.int8)
sel = (ft >= T_LO) & (ft <= T_HI)
ft, fs, fd = ft[sel], fs[sel], fd[sel]
say(f"fills in tick window: {len(ft)}")
cs = np.concatenate([[0.0], np.cumsum(fs)])
cs_sell = np.concatenate([[0.0], np.cumsum(fs * (fd == -1))])
cs_buy = np.concatenate([[0.0], np.cumsum(fs * (fd == 1))])


def burst_at_fills(W):
    """rolling-W (seconds) total at each fill time, plus the forced-side split."""
    lo = np.searchsorted(ft, ft - W * 1000, side="right")   # fills with time > t - W
    hi = np.arange(1, len(ft) + 1)
    return cs[hi] - cs[lo], cs_sell[hi] - cs_sell[lo], cs_buy[hi] - cs_buy[lo]


def detections(W, pct):
    b, bs, bb = burst_at_fills(W)
    ev = []
    last_det = -1e18
    day7 = 7 * 86400 * 1000
    for i in range(len(ft)):
        t = ft[i]
        if t - day7 < T_LO:
            continue
        if t - last_det < COOL * 1000:
            continue
        lo = np.searchsorted(ft, t - day7, side="left")
        hist = b[lo:i]
        if len(hist) < 500:
            continue
        thr = np.percentile(hist, pct)
        if b[i] >= thr:
            d = -1 if bs[i] >= bb[i] else 1
            ev.append(dict(t=int(t), burst=float(b[i]), thr=float(thr), d=d, i=i))
            last_det = t
    return ev


def px_at(t_ms, side):
    """first tick at or after t_ms; returns (index, price) with side 'ask' or 'bid'."""
    k = int(np.searchsorted(tt, t_ms, side="left"))
    if k >= len(tt):
        return None, None
    return k, (ask[k] if side == "ask" else bid[k])


def trade(t_det, d, delay, horizon):
    """d = trade direction (+1 buy). Returns net points or None."""
    k0, e = px_at(t_det + delay * 1000, "ask" if d == 1 else "bid")
    if k0 is None:
        return None
    k1, x = px_at(tt[k0] + horizon * 1000, "bid" if d == 1 else "ask")
    if k1 is None:
        return None
    return (x - e) * d - SLIP


def excursions(t_det, d, delay):
    k0, e = px_at(t_det + delay * 1000, "ask" if d == 1 else "bid")
    if k0 is None:
        return np.nan, np.nan, np.nan
    k1 = int(np.searchsorted(tt, tt[k0] + 300 * 1000, side="left"))
    seg_b, seg_a = bid[k0:k1], ask[k0:k1]
    if len(seg_b) == 0:
        return np.nan, np.nan, np.nan
    if d == 1:
        mfe = seg_b.max() - e
        mae = e - seg_b.min()
        t_mfe = (tt[k0 + int(np.argmax(seg_b))] - tt[k0]) / 1000
    else:
        mfe = e - seg_a.min()
        mae = seg_a.max() - e
        t_mfe = (tt[k0 + int(np.argmin(seg_a))] - tt[k0]) / 1000
    return mfe, mae, t_mfe


def table(ev, label):
    say(f"  {label}: n {len(ev)}")
    if not ev:
        return
    say("    delay \\ horizon " + " ".join(f"{h:>13d}s" for h in HORIZ))
    for dl in DELAYS:
        cells = []
        for h in HORIZ:
            v = np.array([x for x in (trade(e["t"], -e["d"], dl, h) for e in ev) if x is not None])
            cells.append(f"{v.mean():+7.1f} ({(v>0).mean():.0%})" if len(v) else "      -")
        say(f"    +{dl:2d}s            " + " ".join(f"{c:>14s}" for c in cells))


# ---------------------------------------------------------------- main
RES = {}
for W in WINDOWS:
    for pct in (95, 97.5):
        ev = detections(W, pct)
        RES[(W, pct)] = ev
        say(f"\n=== W = {W}s, threshold p{pct} (trailing 7 days), cooldown {COOL}s: {len(ev)} detections "
            f"({sum(1 for e in ev if e['d']==-1)} forced-selling, {sum(1 for e in ev if e['d']==1)} forced-buying); "
            f"burst median {np.median([e['burst'] for e in ev]) if ev else 0:.1f} BTC, threshold median {np.median([e['thr'] for e in ev]) if ev else 0:.1f} BTC ===")
        if pct == 97.5 and W != 30:
            table(ev, "ALL (reversal), net points after $5 slip + spread")
            continue
        table(ev, "ALL (reversal), net points after $5 slip + spread")
        table([e for e in ev if e["d"] == -1], "after FORCED SELLING (buy)")
        table([e for e in ev if e["d"] == 1], "after FORCED BUYING (sell)")
        if pct == 95:
            table([e for e in ev if e["t"] < HALF], "first half (< 08-21)")
            table([e for e in ev if e["t"] >= HALF], "second half")
            sz = np.array([e["burst"] for e in ev])
            q1, q2 = np.percentile(sz, [33.3, 66.7])
            for nm, lo, hi in (("size SMALL", -1, q1), ("size MID", q1, q2), ("size LARGE", q2, 1e9)):
                table([e for e in ev if lo < e["burst"] <= hi], nm)
            exc = [excursions(e["t"], -e["d"], 20) for e in ev]
            exc = [x for x in exc if not np.isnan(x[0])]
            say(f"    excursions from a +20 s entry over 300 s: MFE median {np.median([x[0] for x in exc]):.0f} pts, MAE median {np.median([x[1] for x in exc]):.0f} pts, "
                f"time-to-MFE median {np.median([x[2] for x in exc]):.0f}s (p25 {np.percentile([x[2] for x in exc],25):.0f}s, p75 {np.percentile([x[2] for x in exc],75):.0f}s)")
            days = (T_HI - ev[0]["t"]) / 86400000 if ev else 1
            per_day = {}
            for e in ev:
                dkey = e["t"] // 86400000
                per_day[dkey] = per_day.get(dkey, 0) + 1
            alld = range(ev[0]["t"] // 86400000, T_HI // 86400000 + 1)
            counts = np.array([per_day.get(dk, 0) for dk in alld])
            gaps = np.diff(np.array([e["t"] for e in ev])) / 3600000
            say(f"    frequency: {len(ev)/days:.2f}/day over {days:.0f} scorable days; days with none {(counts==0).mean():.0%}; p90 per day {np.percentile(counts,90):.0f}; longest gap {gaps.max():.1f} h")

# ---------------------------------------------------------------- controls on the primary configuration (W chosen per prereg rule)
say("\n=== WINDOW CHOICE (frozen rule: highest mean net at +20 s delay, 60 s horizon, p95) ===")
best_W, best_v = None, -1e9
for W in WINDOWS:
    ev = RES[(W, 95)]
    v = np.array([x for x in (trade(e["t"], -e["d"], 20, 60) for e in ev) if x is not None])
    say(f"  W={W}s: +20s/60s mean {v.mean():+.2f} (n {len(v)})")
    if v.mean() > best_v:
        best_W, best_v = W, v.mean()
say(f"  -> W = {best_W}s")
EV = RES[(best_W, 95)]

say(f"\n=== MATCHED RANDOM CONTROL ({NS} draws), W={best_W}s events, direction inherited, same hour-of-day ===")
excl = np.zeros(int((T_HI - T_LO) // 1000) + 1, bool)
for e in EV:
    a = int((e["t"] - T_LO) // 1000)
    excl[max(0, a - 60):a + 600] = True
sec_all = np.arange(len(excl))
cand = sec_all[~excl]
cand_hour = ((cand + T_LO // 1000) // 3600) % 24
by_hour = {h: cand[cand_hour == h] for h in range(24)}
rng = np.random.default_rng(16)
ev_hours = [((e["t"] // 1000) // 3600) % 24 for e in EV]
cells = [(dl, h) for dl in (0, 10, 20, 30) for h in (60, 120, 300)]
real = {c: np.mean([x for x in (trade(e["t"], -e["d"], c[0], c[1]) for e in EV) if x is not None]) for c in cells}
sims = {c: [] for c in cells}
for s in range(NS):
    acc = {c: [] for c in cells}
    for e, hr in zip(EV, ev_hours):
        pool = by_hour[hr]
        t_r = int(T_LO + int(pool[rng.integers(len(pool))]) * 1000)
        for c in cells:
            v = trade(t_r, -e["d"], c[0], c[1])
            if v is not None:
                acc[c].append(v)
    for c in cells:
        sims[c].append(np.mean(acc[c]) if acc[c] else np.nan)
say(f"  {'delay/horizon':14s} {'real':>8s} {'rnd mean':>9s} {'sd':>6s} {'p99.5':>8s} {'pctile':>7s} {'z':>6s}")
for c in cells:
    v = np.array(sims[c])
    v = v[~np.isnan(v)]
    say(f"  +{c[0]:2d}s / {c[1]:3d}s     {real[c]:+8.2f} {v.mean():+9.2f} {v.std():6.2f} {np.percentile(v,99.5):+8.2f} {(v < real[c]).mean():7.1%} {(real[c]-v.mean())/v.std():+6.2f}")

say(f"\n=== PRICE-ONLY CONTROL: |mid move over previous {best_W}s| >= trailing-7-day p95 (1-second grid), reversal against the move, same cooldown ===")
sec_t = np.arange(T_LO, T_HI, 1000)
idx = np.searchsorted(tt, sec_t, side="right") - 1
idx = np.clip(idx, 0, len(tt) - 1)
m_sec = mid[idx]
Wn = best_W
mv = np.abs(m_sec[Wn:] - m_sec[:-Wn])
mv_t = sec_t[Wn:]
liq_flag = np.zeros(len(mv_t), bool)
for i, t in enumerate(ft):
    k = int((t - mv_t[0]) // 1000)
    if 0 <= k < len(liq_flag):
        liq_flag[max(0, k):min(len(liq_flag), k + Wn)] = True      # a burst-window fill within the previous W s
b, bs, bb = burst_at_fills(best_W)
pe = []
last = -1e18
day7 = 7 * 86400
thr = None
thr_at = -1
for i in range(len(mv)):
    t = int(mv_t[i])
    if t - day7 * 1000 < T_LO or t - last < COOL * 1000:
        continue
    lo = max(0, i - day7)
    if i - lo < 5000:
        continue
    if i - thr_at >= 300:                      # threshold refreshed every 5 min (trailing 7 days, past only)
        thr = np.percentile(mv[lo:i], 95)
        thr_at = i
    if mv[i] >= thr:
        d = int(np.sign(m_sec[Wn + i] - m_sec[i])) or 1
        # was there a liquidation burst detection (W, p95) within the previous W s?
        has_liq = any(abs(e["t"] - t) <= Wn * 1000 for e in EV)
        pe.append(dict(t=t, d=d, liq=has_liq))
        last = t
say(f"  price-only large-move events: {len(pe)} ({sum(1 for e in pe if e['liq'])} coincide with a liquidation detection within {best_W}s, {sum(1 for e in pe if not e['liq'])} do not)")
table(pe, "ALL price-only (reversal against the move)")
table([e for e in pe if not e["liq"]], "price-only WITHOUT liquidation detection")
table([e for e in pe if e["liq"]], "price-only WITH liquidation detection")

# ---------------------------------------------------------------- graduation rule
say("\n=== GRADUATION (frozen): at W, +20 s delay, horizons 60 s and 120 s: net > 0, above random 99.5th pct, both halves > 0, > 0 without the top-2 events, price-only control not positive ===")
ok = True
for h in (60, 120):
    vals = [(e, trade(e["t"], -e["d"], 20, h)) for e in EV]
    vals = [(e, v) for e, v in vals if v is not None]
    v = np.array([x for _, x in vals])
    r = np.array(sims[(20, h)])
    r = r[~np.isnan(r)]
    h1 = np.mean([x for e, x in vals if e["t"] < HALF])
    h2 = np.mean([x for e, x in vals if e["t"] >= HALF])
    top2 = np.sort(v)[-2:].sum()
    wo = (v.sum() - top2) / max(len(v) - 2, 1)
    po = np.array([x for x in (trade(e["t"], -e["d"], 20, h) for e in pe if not e["liq"]) if x is not None])
    cond = v.mean() > 0 and (r < v.mean()).mean() >= 0.995 and h1 > 0 and h2 > 0 and wo > 0 and po.mean() <= 0
    ok = ok and cond
    say(f"  {h}s: net {v.mean():+.2f} (n {len(v)}), random pct {(r < v.mean()).mean():.1%}, halves {h1:+.2f}/{h2:+.2f}, without top-2 {wo:+.2f}, price-only-no-liq {po.mean():+.2f} -> {'pass' if cond else 'FAIL'}")
say(f"  -> {'A: candidate graduates' if ok else 'not graduated'}")
with open(os.path.join(HERE, "events_e016.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["det_utc", "dir_trade", "burst_btc", "thr_btc"] + [f"d{dl}_h{h}" for dl in DELAYS for h in HORIZ])
    for e in EV:
        w.writerow([dt.datetime.utcfromtimestamp(e["t"] / 1000).isoformat(timespec="milliseconds"), -e["d"], round(e["burst"], 3), round(e["thr"], 3)]
                   + [round(trade(e["t"], -e["d"], dl, h) or 0, 2) for dl in DELAYS for h in HORIZ])
say("\ndone")
out.close()
