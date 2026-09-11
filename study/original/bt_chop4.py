"""Day/week/month expectation table for the deployed config
(exact rules + awake gate, 0.02): trades, P&L, drawdowns."""
from collections import deque
from datetime import datetime, timezone

import numpy as np

from bt_bos import Struct, O, H, L, C, T, S

LOT = 0.02
RR = 0.8
WIN = 7200

st = Struct()
pos = None
ev = deque()
res = []          # (epoch, pnl)
for j in range(len(T)):
    t, o, h, l, c = int(T[j]), O[j], H[j], L[j], C[j]
    if pos is not None:
        d, e, sl, tp = pos
        sl_hit = (l <= sl) if d == 1 else (h >= sl - S)
        tp_hit = (h >= tp) if d == 1 else (l <= tp - S)
        if sl_hit:
            res.append((t, (sl - e) * d * LOT))
            pos = None
        elif tp_hit:
            res.append((t, (tp - e) * d * LOT))
            pos = None
    pt = st.trend
    sig = st.step(t, o, h, l, c)
    if st.trend != pt and st.trend != 0 and pt != 0:
        ev.append(t)
    while ev and ev[0] < t - WIN:
        ev.popleft()
    if sig is None or pos is not None or not ev:
        continue
    d, slp = sig
    if d == 1:
        e = c + S
        if e - slp <= S:
            continue
        tp = e + RR * (e - slp)
    else:
        e = c
        if slp - e <= S:
            continue
        tp = e - RR * (slp - e)
    pos = (d, e, slp, tp)

days = {}
weeks = {}
for t, p in res:
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    days.setdefault(dt.strftime("%Y-%m-%d"), []).append(p)
    weeks.setdefault(dt.strftime("%Y-W%W"), []).append(p)

dnet = [sum(v) for v in days.values()]
dcnt = [len(v) for v in days.values()]
wnet = [sum(v) for v in weeks.values()]
wcnt = [len(v) for v in weeks.values()]
cum = peak = mdd = 0.0
for _, p in res:
    cum += p
    peak = max(peak, cum)
    mdd = max(mdd, peak - cum)
# max intraday dd
didd = []
for v in days.values():
    c2 = p2 = m2 = 0.0
    for p in v:
        c2 += p
        p2 = max(p2, c2)
        m2 = max(m2, p2 - c2)
    didd.append(m2)
n = len(res)
tot = sum(p for _, p in res)
D = (T[-1] - T[0]) / 86400
print(f"total: {n} trades, net {tot:+.2f} over {D:.0f} days, "
      f"maxDD (whole run) {mdd:.2f}")
print(f"\nPER DAY  ({len(days)} days): trades avg "
      f"{np.mean(dcnt):.1f} (min {min(dcnt)} max {max(dcnt)})")
print(f"  net avg {np.mean(dnet):+.2f} | median "
      f"{np.median(dnet):+.2f} | best {max(dnet):+.2f} | worst "
      f"{min(dnet):+.2f}")
print(f"  green days {sum(1 for x in dnet if x>0)}/{len(dnet)} | "
      f"avg intraday DD {np.mean(didd):.2f} | worst intraday DD "
      f"{max(didd):.2f}")
print(f"\nPER WEEK ({len(weeks)} weeks): trades avg "
      f"{np.mean(wcnt):.0f}")
print(f"  net avg {np.mean(wnet):+.2f} | best {max(wnet):+.2f} | "
      f"worst {min(wnet):+.2f} | green "
      f"{sum(1 for x in wnet if x>0)}/{len(wnet)}")
print(f"\nPER MONTH (scaled from the 69d): trades ~"
      f"{n/D*30.44:.0f}, net ~{tot/D*30.44:+.2f}")
