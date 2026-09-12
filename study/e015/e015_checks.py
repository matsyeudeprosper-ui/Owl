"""E015 robustness checks, predeclared in commit 'E015 raw results' before running:
 (a) LATENCY: enter 1 / 2 / 5 / 10 min after the episode's bucket end (live feeds
     arrive late); reversal measured 5 / 15 / 30 min after the delayed entry.
 (b) VOLATILITY-MATCHED PRICE-ONLY CONTROL: 5-min buckets whose absolute
     close-to-close move is in the top 5% of the trailing 7 days (same ranking
     rule, price only, no liquidation data); reversal against the move. Split:
     buckets that coincide with a liquidation cascade vs those that do not.
     If price-only large moves revert just as much, the liquidation feed adds
     nothing beyond price. Also: the reverse split - cascades WITHOUT a large
     price move.
 (c) 0.02-lot equity curve of the primary cell (rev, 5 min) and rev 15 min.
Same costs ($12 round trip), same price data, no new thresholds."""
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
exec(open(os.path.join(HERE, "e015.py"), encoding="utf-8").read().split("# ---------------------------------------------------------------- events + outcomes")[0]
     .replace('out = open(os.path.join(HERE, "results_e015.txt"), "w", encoding="utf-8")', 'out = open(os.path.join(HERE, "results_e015_checks.txt"), "w", encoding="utf-8")'))

EV = []
for e in large_events(7):
    j = entry_index(e["t_end"])
    if j is None or T[j] < feed_lo:
        continue
    EV.append(dict(e, j=j, t=int(T[j]) + 60))
say(f"\n=== (a) LATENCY: reversal entered k minutes AFTER the bucket end (n {len(EV)}) ===")
for delay in (0, 1, 2, 5, 10):
    parts = []
    for h in (5, 15, 30):
        vals = []
        for e in EV:
            j = e["j"] + delay
            if j + h >= N:
                continue
            dd = -e["d"]
            ent = C[j] + (SP[j] if dd == 1 else 0.0)
            x = C[j + h] + (SP[j + h] if dd == -1 else 0.0)
            vals.append((x - ent) * dd - 5.0)
        v = np.array(vals)
        parts.append(f"+{h:2d}m {v.mean():+7.2f} pts (wr {(v>0).mean():.0%}, n {len(v)})")
    say(f"  delay {delay:2d} min: " + " | ".join(parts))

say("\n=== (b) VOLATILITY-MATCHED PRICE-ONLY CONTROL: top-5% |5-min move| (trailing 7 days), reversal against the move ===")
b5 = T // 300
starts = np.concatenate([[0], np.where(np.diff(b5) != 0)[0] + 1])
ends = np.concatenate([starts[1:], [N]])
bk = b5[starts]
mv = C[ends - 1] - O[starts]                       # bucket close - open
absmv = np.abs(mv)
bk_t = bk * 300
liq_b = set()
for e in EV:
    for k in range(e["b"], e["b_last"] + 1):
        liq_b.add(k)
pe = []
for i in range(len(bk)):
    t = int(bk_t[i])
    if t - 7 * 86400 < feed_lo or t < feed_lo:
        continue
    lo = np.searchsorted(bk_t, t - 7 * 86400)
    hist = absmv[lo:i]
    if len(hist) < 200:
        continue
    if absmv[i] >= np.percentile(hist, 95):
        pe.append(dict(b=int(bk[i]), t_end=t + 300, d=int(np.sign(mv[i])) or 1, move=float(absmv[i]), liq=int(bk[i]) in liq_b))
# merge consecutive
eps = []
for e in pe:
    if eps and e["b"] == eps[-1]["b_last"] + 1:
        eps[-1]["b_last"] = e["b"]
        eps[-1]["t_end"] = e["t_end"]
        eps[-1]["liq"] = eps[-1]["liq"] or e["liq"]
    else:
        eps.append(dict(e, b_last=e["b"]))
rows = []
for e in eps:
    j = entry_index(e["t_end"])
    if j is None:
        continue
    r = dict(e, j=j, t=int(T[j]) + 60)
    r.update(outcomes(j, e["d"]))
    rows.append(r)
say(f"  price-only large-move episodes: {len(rows)} ({sum(1 for r in rows if r['liq'])} coincide with a liquidation cascade, {sum(1 for r in rows if not r['liq'])} do not)")
summarize(rows, "ALL price-only large moves")
summarize([r for r in rows if r["liq"]], "price-only large moves WITH a liquidation cascade")
summarize([r for r in rows if not r["liq"]], "price-only large moves WITHOUT a liquidation cascade")
# reverse split: liquidation cascades with / without a large price move in the same bucket
pm_b = set()
for e in eps:
    for k in range(e["b"], e["b_last"] + 1):
        pm_b.add(k)
rowsE = []
for e in EV:
    r = dict(e)
    r.update(outcomes(e["j"], e["d"]))
    r["bigmove"] = any(k in pm_b for k in range(e["b"], e["b_last"] + 1))
    rowsE.append(r)
summarize([r for r in rowsE if r["bigmove"]], "liquidation cascades WITH a top-5% price move")
summarize([r for r in rowsE if not r["bigmove"]], "liquidation cascades WITHOUT a top-5% price move")

say("\n=== (c) 0.02-lot equity of the primary cell (reversal, exit 5 min) and 15 min ===")
for h in (5, 15):
    seq = sorted([(r["t"], r[f"rev{h}"] * LOT) for r in rowsE])
    p = np.array([u for _, u in seq])
    cum = np.cumsum(p)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    say(f"  rev{h}: n {len(p)} net ${p.sum():+.2f} maxDD ${np.max(peak-cum):.2f} avg ${p.mean():+.3f} largest win/loss ${p.max():+.2f}/${p.min():+.2f} | per week: " +
        " ".join(f"{sum(u for t,u in seq if dt.datetime.utcfromtimestamp(t).strftime('%W')==w):+.1f}" for w in sorted(set(dt.datetime.utcfromtimestamp(t).strftime('%W') for t,_ in seq))))
say("\ndone")
out.close()
