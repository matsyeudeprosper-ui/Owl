"""E017 frozen forward scorer (PREREG_E017.md). Reads the shadow observer's
forward logs (>= 2026-09-12 13:07:04 UTC), scores the PRIMARY cell (forced
selling -> BUY, +20 s, 300 s exit, observer quotes), cross-checks with an
MT5 tick replay, runs controls A/B/C, the economic read and (n >= 30) the
harvest model. Nothing here chooses parameters. Run: python e017_forward.py"""
import csv
import datetime as dt
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = r"C:\Projects\KinoliveLines\live"
EVENTS = os.path.join(LIVE, "liq_shadow_events.csv")
FILLS = os.path.join(LIVE, "liq_shadow_fills.csv")
START = dt.datetime(2026, 9, 12, 13, 7, 4, tzinfo=dt.timezone.utc)
DELAY, EXIT, EXIT2, SLIP = 20, 300, 120, 5.0
NRAND = 1000
out = open(os.path.join(HERE, "results_e017_%s.txt" % dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M")), "w", encoding="utf-8")


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")


def parse(ts):
    return dt.datetime.fromisoformat(ts).replace(tzinfo=dt.timezone.utc)


# ---------------------------------------------------------------- forward events (observer)
ev = []
if os.path.exists(EVENTS):
    for r in csv.DictReader(open(EVENTS, encoding="utf-8")):
        t = parse(r["exch_utc"])
        if t < START:
            continue
        ev.append(r)
sell = [r for r in ev if r["forced_side"] == "-1"]     # forced selling -> BUY (primary)
buy = [r for r in ev if r["forced_side"] == "1"]       # forced buying -> SELL (control C)
now = dt.datetime.now(dt.timezone.utc)
days = (now - START).total_seconds() / 86400
say(f"E017 forward read at {now:%Y-%m-%d %H:%M} UTC: {days:.1f} days since freeze; detections {len(ev)} (forced selling {len(sell)}, forced buying {len(buy)})")
if os.path.exists(FILLS):
    lat = [float(r["latency_s"]) for r in csv.DictReader(open(FILLS, encoding="utf-8")) if parse(r["exch_utc"]) >= START]
    if lat:
        say(f"feed latency (exchange -> receive) over {len(lat)} fills: median {np.median(lat):.2f} s, p90 {np.percentile(lat, 90):.2f} s, max {max(lat):.2f} s")


def col(rows, name):
    v = []
    for r in rows:
        try:
            v.append(float(r[name]))
        except Exception:
            pass
    return np.array(v)


def describe(rows, label, name="net_300s"):
    v = col(rows, name)
    if len(v) == 0:
        say(f"  {label}: n 0")
        return v
    srt = np.sort(v)[::-1]
    say(f"  {label}: n {len(v)} mean {v.mean():+.1f} pts wr {(v > 0).mean():.0%} median {np.median(v):+.1f} | without top-1 {srt[1:].mean() if len(v) > 1 else float('nan'):+.1f}, top-2 {srt[2:].mean() if len(v) > 2 else float('nan'):+.1f}"
        f" | without top-10% |P&L| {np.sort(np.abs(v))[: max(1, int(len(v) * 0.9))].size and v[np.argsort(-np.abs(v))[int(np.ceil(len(v) * 0.1)):]].mean():+.1f}")
    if len(v) >= 30:
        h = len(v) // 2
        say(f"    halves: {v[:h].mean():+.1f} / {v[h:].mean():+.1f}")
    return v


say("\n=== PRIMARY (observer quotes): forced SELLING -> BUY, +20 s, exit 300 s, costs inside quotes + $5 ===")
v300 = describe(sell, "primary 300 s")
describe(sell, "descriptive 120 s", "net_120s")
if sell:
    mfe, mae = col(sell, "mfe"), col(sell, "mae")
    say(f"  MFE median {np.median(mfe):.0f} MAE median {np.median(mae):.0f}; spread at detection median {np.median(col(sell, 'spread_at_det')):.2f}; quote age at entry median {np.median(col(sell, 'quote_age_entry_s')):.2f} s; detection latency median {np.median(col(sell, 'det_latency_s')):.2f} s")
    b = col(sell, "burst_btc")
    if len(b) >= 9:
        q1, q2 = np.percentile(b, [33.3, 66.7])
        for nm, lo, hi in (("size SMALL", -1, q1), ("size MID", q1, q2), ("size LARGE", q2, 1e9)):
            describe([r for r in sell if lo < float(r["burst_btc"]) <= hi], nm)
say("\n=== CONTROL C (descriptive): forced BUYING -> SELL, same cell ===")
describe(buy, "forced buying 300 s")
describe(buy, "forced buying 120 s", "net_120s")

# ---------------------------------------------------------------- tick replay + controls A / B
say("\n=== TICK REPLAY (MT5 Trial9 ticks at exchange time + delay) and CONTROLS A / B ===")
try:
    import MetaTrader5 as mt5
    sec = json.load(open(os.path.join(LIVE, "owl_secrets.json"), encoding="utf-8"))
    assert mt5.initialize(path=r"C:\NestTerminals\u476954287\terminal64.exe", login=476954287, password=sec["mt5_password"], server="Exness-MT5Trial9", timeout=60000)
    t0 = START - dt.timedelta(days=7)
    tk = mt5.copy_ticks_range("BTCUSD", t0.replace(tzinfo=None), now.replace(tzinfo=None) + dt.timedelta(hours=3), mt5.COPY_TICKS_INFO)
    mt5.shutdown()
    tt = tk["time_msc"].astype(np.int64)
    bid, ask = tk["bid"].astype(float), tk["ask"].astype(float)
    mid = (bid + ask) / 2
    say(f"  ticks {len(tt)} {dt.datetime.utcfromtimestamp(tt[0]/1000)} -> {dt.datetime.utcfromtimestamp(tt[-1]/1000)}")

    def px(t_ms, side):
        k = int(np.searchsorted(tt, t_ms))
        if k >= len(tt):
            return None, None
        return k, (ask[k] if side == "ask" else bid[k])

    def trade(t_ms, d, delay, horizon):
        k0, e = px(t_ms + delay * 1000, "ask" if d == 1 else "bid")
        if k0 is None:
            return None
        k1, x = px(tt[k0] + horizon * 1000, "bid" if d == 1 else "ask")
        if k1 is None or tt[k1] - tt[k0] > (horizon + 120) * 1000:
            return None
        return (x - e) * d - SLIP

    det_ms = np.array([int(parse(r["exch_utc"]).timestamp() * 1000) for r in sell], np.int64)
    for dl in (10, 20, 30):
        for h in (120, 300):
            v = np.array([x for x in (trade(t, 1, dl, h) for t in det_ms) if x is not None])
            if len(v):
                say(f"  replay forced selling BUY +{dl}s/{h}s: n {len(v)} mean {v.mean():+.1f} wr {(v > 0).mean():.0%}" + ("   <- primary cell" if dl == 20 and h == 300 else ""))
    real = np.array([x for x in (trade(t, 1, DELAY, EXIT) for t in det_ms) if x is not None])
    if len(real) >= 5:
        rng = np.random.default_rng(17)
        hours = np.array([dt.datetime.utcfromtimestamp(t / 1000).hour for t in det_ms])
        lo_ms, hi_ms = int(START.timestamp() * 1000), int(tt[-1] - (DELAY + EXIT + 120) * 1000)
        excl = det_ms
        sims = []
        for _ in range(NRAND):
            vals = []
            for hr in hours:
                for _try in range(200):
                    t = int(rng.integers(lo_ms, hi_ms))
                    if dt.datetime.utcfromtimestamp(t / 1000).hour != hr or np.any((t > excl) & (t < excl + 600000)):
                        continue
                    x = trade(t, 1, DELAY, EXIT)
                    if x is not None:
                        vals.append(x)
                    break
            sims.append(np.mean(vals) if vals else np.nan)
        sims = np.array(sims)
        sims = sims[~np.isnan(sims)]
        pct = (sims < real.mean()).mean() * 100
        say(f"  CONTROL A matched random ({len(sims)} draws): real {real.mean():+.1f} vs random {sims.mean():+.1f} ± {sims.std():.1f}; 95th {np.percentile(sims, 95):+.1f}, 99th {np.percentile(sims, 99):+.1f}; real at {pct:.1f}th pct")
        # control B: large 60 s DOWN moves without a forced-selling detection in the previous 60 s
        g0 = int(START.timestamp())
        grid = np.arange(int(tt[0] / 1000) + 60, int(tt[-1] / 1000) - EXIT - DELAY - 120)
        gm = mid[np.searchsorted(tt, grid * 1000) - 1]
        mv = gm[60:] - gm[:-60]
        gt = grid[60:]
        thr = None
        thr_at = -10 ** 9
        last = -10 ** 9
        vals = []
        for i in range(len(mv)):
            if gt[i] < g0 or gt[i] - last < 300:
                continue
            lo = max(0, i - 7 * 86400)
            if i - lo < 5000:
                continue
            if i - thr_at >= 300:
                thr = np.percentile(np.abs(mv[lo:i]), 95)
                thr_at = i
            if -mv[i] >= thr and not np.any((det_ms > (gt[i] - 60) * 1000) & (det_ms <= gt[i] * 1000)):
                x = trade(gt[i] * 1000, 1, DELAY, EXIT)
                if x is not None:
                    vals.append(x)
                last = gt[i]
        if vals:
            vb = np.array(vals)
            say(f"  CONTROL B large 60 s DOWN moves without forced-selling burst, BUY +{DELAY}s/{EXIT}s: n {len(vb)} mean {vb.mean():+.1f} wr {(vb > 0).mean():.0%}")
    else:
        say("  controls A/B skipped: fewer than 5 forward events")
except Exception as e:
    say(f"  tick replay unavailable: {type(e).__name__}: {e}")

# ---------------------------------------------------------------- economics + harvest
say("\n=== ECONOMIC READ (primary cell, observer quotes) ===")
if len(v300):
    rate = len(v300) / max(days, 1e-9)
    say(f"  events/day {rate:.2f} -> ~{rate * 30:.0f} trades/month; mean {v300.mean():+.1f} pts")
    for lot in (0.01, 0.02, 0.05):
        p = v300 * lot
        cum = np.cumsum(p)
        peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
        streak = mx = 0
        for x in p:
            streak = streak + 1 if x <= 0 else 0
            mx = max(mx, streak)
        say(f"  lot {lot:.2f}: net ${p.sum():+.2f} maxDD ${np.max(peak - cum):.2f} longest losing streak {mx} illustrative monthly ${p.mean() * rate * 30:+.2f}")
    if len(v300) >= 30:
        say("\n=== HARVEST MODEL ($500, fixed 0.02, withdraw $100 at baseline+100, stop at net-from-start <= -60) ===")
        eq, base, wd, start = 500.0, 500.0, 0, 500.0
        maxrisk = 0.0
        stopped = False
        for x in v300 * 0.02:
            eq += x
            maxrisk = max(maxrisk, start - eq + 100 * wd)
            if eq - start + 100 * wd <= -60:
                stopped = True
                break
            if eq >= base + 100:
                eq -= 100
                wd += 1
                base = eq
        say(f"  withdrawals {wd} (${100 * wd}), ending equity ${eq:.2f}, withdrawn > start? {'yes' if 100 * wd > start else 'no'}, max capital at risk ${maxrisk:.2f}, stopped by kill rule: {stopped}")
    else:
        say(f"  harvest model: waits for 30 events (have {len(v300)})")
else:
    say("  no forward forced-selling events yet")
say("\nVERDICT: not due before 30 forward forced-selling events." if len(v300) < 30 else "\nVERDICT: apply PREREG_E017.md pass criteria to the numbers above.")
out.close()
