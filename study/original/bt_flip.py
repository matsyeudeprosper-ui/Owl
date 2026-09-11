"""Flip-entry study (user 2026-09-09):
1) split results: FLIP entries vs TOUCH continuations
2) measure the pullback (max adverse excursion) on flip trades
3) variants: skip flips entirely / enter flips on a pullback limit
   (30% and 50% of risk; cancel if SL or original TP is crossed
   first)."""
from collections import deque

import numpy as np

from bt_bos import Struct, O, H, L, C, T, S

LOT = 0.02
RR = 0.8
WIN = 7200


def run(flip_mode="market", pull=0.3, collect_mae=False):
    """flip_mode: market | skip | limit"""
    st = Struct()
    pos = None
    pend = None            # (d, limit, slp, deadline_guardTP)
    ev = deque()
    out = []               # (pnl, kind)
    maes = []
    used_hi = used_lo = None
    for j in range(len(T)):
        t, o, h, l, c = int(T[j]), O[j], H[j], L[j], C[j]
        if pos is not None:
            d, e, sl, tp, kind, mae = pos
            adv = (e - l) if d == 1 else ((h + S) - e)
            mae = max(mae, adv)
            sl_hit = (l <= sl) if d == 1 else (h >= sl - S)
            tp_hit = (h >= tp) if d == 1 else (l <= tp - S)
            if sl_hit or tp_hit:
                px = sl if sl_hit else tp
                out.append(((px - e) * d * LOT, kind))
                if collect_mae and kind == "flip":
                    maes.append((mae, abs(e - sl)))
                pos = None
            else:
                pos = (d, e, sl, tp, kind, mae)
        if pend is not None and pos is None:
            d, lim, slp, gtp = pend
            if d == 1:
                if l <= slp:
                    pend = None            # structure dead, cancel
                elif l <= lim:
                    e = lim
                    tp = e + RR * (e - slp)
                    pos = (1, e, slp, tp, "flip", 0.0)
                    pend = None
                elif h >= gtp:
                    pend = None            # ran away, missed
            else:
                if h >= slp - S:
                    pend = None
                elif h >= lim:
                    e = lim
                    tp = e - RR * (slp - e)
                    pos = (-1, e, slp, tp, "flip", 0.0)
                    pend = None
                elif l <= gtp - S:
                    pend = None
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
                        pend = None
                        if l <= slp:
                            out.append(((slp - e) * LOT, "cont"))
                        elif h >= tp:
                            out.append(((tp - e) * LOT, "cont"))
                        else:
                            pos = (1, e, slp, tp, "cont", 0.0)
            elif (st.trend == -1 and st.lo_v is not None
                    and l < st.lo_v and used_lo != st.lo_v):
                span = st.kept[st.lo_i + 1:]
                if span and any(x[5] == 1 for x in span):
                    slp = max(span, key=lambda x: x[2])[2]
                    e = st.lo_v
                    if slp - e > S:
                        tp = e - RR * (slp - e)
                        used_lo = st.lo_v
                        pend = None
                        if h >= slp - S:
                            out.append(((e - slp) * LOT, "cont"))
                        elif l <= tp - S:
                            out.append(((e - tp) * LOT, "cont"))
                        else:
                            pos = (-1, e, slp, tp, "cont", 0.0)
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
        risk = abs(e2 - slp)
        if risk <= S:
            continue
        if flip_mode == "skip":
            continue
        if flip_mode == "limit":
            lim = e2 - d * pull * risk
            gtp = e2 + d * RR * risk
            pend = (d, lim, slp, gtp)
            continue
        tp = e2 + d * RR * risk
        pos = (d, e2, slp, tp, "flip", 0.0)
    return out, maes


out, maes = run("market", collect_mae=True)
for k in ("flip", "cont"):
    sel = [p for p, kk in out if kk == k]
    w = sum(1 for x in sel if x > 0)
    print(f"{k:4s}: n {len(sel):4d} wr {w/max(1,len(sel)):.0%} "
          f"net {sum(sel):+8.2f} avg {sum(sel)/max(1,len(sel)):+.3f}")
if maes:
    fr = [m / r for m, r in maes]
    print(f"\nflip pullback (MAE, % of risk): mean "
          f"{np.mean(fr):.0%} median {np.median(fr):.0%} "
          f"p75 {np.percentile(fr,75):.0%}")
    for th in (0.25, 0.4, 0.5, 0.7):
        print(f"  reaches {th:.0%} of risk: "
              f"{np.mean([f >= th for f in fr]):.0%} of flips")

print("\n-- variants (whole config net) --")
for lbl, mode, p in (("deployed (market flip)", "market", 0),
                     ("skip flips", "skip", 0),
                     ("flip limit @30% pullback", "limit", 0.3),
                     ("flip limit @50% pullback", "limit", 0.5)):
    o2, _ = run(mode, p)
    tot = sum(p2 for p2, _ in o2)
    print(f"  {lbl:26s}: net {tot:+8.2f} n {len(o2)}")
