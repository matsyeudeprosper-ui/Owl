"""Two questions (user 2026-09-09 night):
1) Is the Nth trade of a trend better than the 1st? Bucket every
   trade by its position within its trend.
2) Do flip trades do better when the HIGHER timeframe agrees?
   Proxy: 4h momentum (close now vs close 240 bars ago)."""
from collections import deque

import numpy as np

from bt_bos import Struct, O, H, L, C, T, S

LOT = 0.02
RR = 0.8
WIN = 7200

st = Struct()
pos = None
ev = deque()
out = []          # (ordinal, htf_agree, pnl)
used_hi = used_lo = None
ordinal = 0
for j in range(len(T)):
    t, o, h, l, c = int(T[j]), O[j], H[j], L[j], C[j]
    if pos is not None:
        d, e, sl, tp, meta = pos
        sl_hit = (l <= sl) if d == 1 else (h >= sl - S)
        tp_hit = (h >= tp) if d == 1 else (l <= tp - S)
        if sl_hit or tp_hit:
            px = sl if sl_hit else tp
            out.append((meta[0], meta[1], (px - e) * d * LOT))
            pos = None
    if pos is None and ev:
        sigt = None
        if (st.trend == 1 and st.hi_v is not None
                and h > st.hi_v and used_hi != st.hi_v):
            span = st.kept[st.hi_i + 1:]
            if span and any(x[5] == -1 for x in span):
                slp = min(span, key=lambda x: x[3])[3]
                e = st.hi_v + S
                if e - slp > S:
                    used_hi = st.hi_v
                    sigt = (1, e, slp)
        elif (st.trend == -1 and st.lo_v is not None
                and l < st.lo_v and used_lo != st.lo_v):
            span = st.kept[st.lo_i + 1:]
            if span and any(x[5] == 1 for x in span):
                slp = max(span, key=lambda x: x[2])[2]
                e = st.lo_v
                if slp - e > S:
                    used_lo = st.lo_v
                    sigt = (-1, e, slp)
        if sigt:
            d, e, slp = sigt
            ordinal += 1
            htf = 1 if c >= C[max(0, j - 240)] else -1
            tp = e + d * RR * abs(e - slp)
            pos = (d, e, slp, tp, (min(ordinal, 4), htf == d))
    pt = st.trend
    sig = st.step(t, o, h, l, c)
    if st.trend != pt and st.trend != 0 and pt != 0:
        ev.append(t)
        ordinal = 0
    while ev and ev[0] < t - WIN:
        ev.popleft()
    if sig is None or pos is not None or not ev:
        continue
    if st.trend == pt:
        continue
    d, slp = sig
    e2 = c + S if d == 1 else c
    if abs(e2 - slp) <= S:
        continue
    ordinal = 1
    htf = 1 if c >= C[max(0, j - 240)] else -1
    tp = e2 + d * RR * abs(e2 - slp)
    pos = (d, e2, slp, tp, (1, htf == d))

print("-- by position within the trend --")
for k, lbl in ((1, "1st (flip)"), (2, "2nd"), (3, "3rd"),
               (4, "4th+")):
    sel = [p for o2, _, p in out if o2 == k]
    if sel:
        w = sum(1 for x in sel if x > 0)
        print(f"  {lbl:10s}: n {len(sel):4d} wr {w/len(sel):.0%} "
              f"net {sum(sel):+8.2f} avg {sum(sel)/len(sel):+.3f}")
print("-- flip trades by 4h-momentum agreement --")
for ag, lbl in ((True, "HTF agrees"), (False, "HTF against")):
    sel = [p for o2, a, p in out if o2 == 1 and a == ag]
    if sel:
        w = sum(1 for x in sel if x > 0)
        print(f"  {lbl:12s}: n {len(sel):4d} wr {w/len(sel):.0%} "
              f"net {sum(sel):+8.2f} avg {sum(sel)/len(sel):+.3f}")
