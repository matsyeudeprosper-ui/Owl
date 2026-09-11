"""User 2026-09-09: when an open trade pulls back ~50% toward the
SL, ADD bullets at that better price (same SL, same TP). Test adds
of +0.01 / +0.02 at 50% and 70% pullback, pessimistic same-bar
fills (add fills before a same-bar stop-out counts full)."""
from collections import deque

import numpy as np

from bt_bos import Struct, O, H, L, C, T, S

LOT = 0.02
RR = 0.8
WIN = 7200
mid = np.searchsorted(T, T[0] + (T[-1] - T[0]) // 2)


def run(a, b, addlot, k):
    st = Struct()
    pos = None      # (d,e,sl,tp,added,addpx)
    ev = deque()
    out = []
    used_hi = used_lo = None
    for j in range(a, b):
        t, o, h, l, c = int(T[j]), O[j], H[j], L[j], C[j]
        if pos is not None:
            d, e, sl, tp, added, apx = pos
            if addlot and not added:
                lvl = e - d * k * abs(e - sl)
                hit = (l <= lvl) if d == 1 else (h >= lvl - S)
                if hit:
                    added = True
                    apx = lvl
                    pos = (d, e, sl, tp, added, apx)
            sl_hit = (l <= sl) if d == 1 else (h >= sl - S)
            tp_hit = (h >= tp) if d == 1 else (l <= tp - S)
            if sl_hit or tp_hit:
                px = sl if sl_hit else tp
                pnl = (px - e) * d * LOT
                if added:
                    pnl += (px - apx) * d * addlot
                out.append(pnl)
                pos = None
        if pos is None and ev:
            if (st.trend == 1 and st.hi_v is not None
                    and h > st.hi_v and used_hi != st.hi_v):
                span = st.kept[st.hi_i + 1:]
                if span and any(x[5] == -1 for x in span):
                    slp = min(span, key=lambda x: x[3])[3]
                    e = st.hi_v + S
                    if e - slp > S:
                        tp = e + RR * (e - slp)
                        used_hi = st.hi_v
                        if l <= slp:
                            out.append((slp - e) * LOT)
                        elif h >= tp:
                            out.append((tp - e) * LOT)
                        else:
                            pos = (1, e, slp, tp, False, 0)
            elif (st.trend == -1 and st.lo_v is not None
                    and l < st.lo_v and used_lo != st.lo_v):
                span = st.kept[st.lo_i + 1:]
                if span and any(x[5] == 1 for x in span):
                    slp = max(span, key=lambda x: x[2])[2]
                    e = st.lo_v
                    if slp - e > S:
                        tp = e - RR * (slp - e)
                        used_lo = st.lo_v
                        if h >= slp - S:
                            out.append((e - slp) * LOT)
                        elif l <= tp - S:
                            out.append((e - tp) * LOT)
                        else:
                            pos = (-1, e, slp, tp, False, 0)
        pt = st.trend
        sig = st.step(t, o, h, l, c)
        if st.trend != pt and st.trend != 0 and pt != 0:
            ev.append(t)
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
        tp = e2 + d * RR * abs(e2 - slp)
        pos = (d, e2, slp, tp, False, 0)
    W = sum(1 for x in out if x > 0)
    cum = peak = mdd = 0.0
    for x in out:
        cum += x
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return sum(out), len(out), W, mdd


for lbl, al, k in (("deployed (no add)", 0, 0),
                   ("add +0.01 @50%", 0.01, 0.5),
                   ("add +0.02 @50%", 0.02, 0.5),
                   ("add +0.01 @70%", 0.01, 0.7),
                   ("add +0.02 @70%", 0.02, 0.7)):
    n, cnt, w, dd = run(0, len(T), al, k)
    na, _, _, _ = run(0, mid, al, k)
    nb, _, _, _ = run(mid, len(T), al, k)
    print(f"{lbl:18s}: net {n:+8.2f} n {cnt:4d} "
          f"wr {w/max(1,cnt):.0%} maxDD {dd:6.2f} | "
          f"h1 {na:+8.2f} | h2 {nb:+8.2f}")
