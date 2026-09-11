"""User 2026-09-09: per-loss debt with a multiplier - every loss
adds FULL (1.0x) or HALF (0.5x) of itself to the debt bank; wins
pay it down; fighters active while debt > 0. Chest mechanics
unchanged (fills from win overflow after debt, cap 10, pays bullet
losses). Versus the deployed HWM peak-debt."""
from collections import deque

import numpy as np

from bt_bos import Struct, O, H, L, C, T, S

BASE = 0.02
RR = 0.8
WIN = 7200
CAP = 10.0
mid = np.searchsorted(T, T[0] + (T[-1] - T[0]) // 2)


def run(a, b, mode, alpha=1.0):
    st = Struct()
    pos = None
    ev = deque()
    out = []
    debt = chest = net = peak = 0.0
    nf = na2 = 0
    used_hi = used_lo = None

    def open_pos(d, e, slp):
        nonlocal nf
        dist = abs(e - slp)
        lot = BASE
        if debt > 0.5:
            extra = min(3, int(chest // max(dist * 0.01, 0.01)))
            if extra > 0:
                lot = round(BASE + extra * 0.01, 2)
                nf += 1
        tp = e + (1 if d == 1 else -1) * RR * dist
        return dict(d=d, e=e, sl=slp, tp=tp, lot=lot,
                    alvl=e - (1 if d == 1 else -1) * 0.5 * dist,
                    apx=None, alot=0.0)

    def book(pnl, lot, is_add):
        nonlocal debt, chest, net, peak
        net += pnl
        if mode == "hwm":
            if net > peak:
                chest = min(CAP, chest + (net - peak))
                peak = net
            elif pnl < 0 and (is_add or lot > BASE):
                bs = 0.0 if is_add else pnl * BASE / lot
                chest = max(0.0, chest + (pnl - bs))
            debt = max(0.0, peak - net)
            return
        # per-loss with multiplier
        if pnl < 0:
            debt += alpha * (-pnl)
            if is_add or lot > BASE:
                bs = 0.0 if is_add else pnl * BASE / lot
                chest = max(0.0, chest + (pnl - bs))
        else:
            pay = min(debt, pnl)
            debt -= pay
            chest = min(CAP, chest + pnl - pay)

    for j in range(a, b):
        t, o, h, l, c = int(T[j]), O[j], H[j], L[j], C[j]
        if pos is not None:
            p = pos
            d = p["d"]
            if p["apx"] is None:
                hit = (l <= p["alvl"]) if d == 1 \
                    else (h >= p["alvl"] - S)
                if hit:
                    cost = 0.5 * abs(p["e"] - p["sl"]) * 0.01
                    n2 = min(2, int(chest // max(cost, 0.01)))
                    p["apx"] = p["alvl"] if n2 > 0 else 0
                    if n2 > 0:
                        p["alot"] = round(n2 * 0.01, 2)
                        na2 += 1
            sl_hit = (l <= p["sl"]) if d == 1 else (h >= p["sl"] - S)
            tp_hit = (h >= p["tp"]) if d == 1 else (l <= p["tp"] - S)
            if sl_hit or tp_hit:
                px = p["sl"] if sl_hit else p["tp"]
                pnl = (px - p["e"]) * d * p["lot"]
                book(pnl, p["lot"], False)
                tot = pnl
                if p["alot"] > 0:
                    ap = (px - p["apx"]) * d * p["alot"]
                    book(ap, p["alot"], True)
                    tot += ap
                out.append(tot)
                pos = None
        if pos is None and ev:
            if (st.trend == 1 and st.hi_v is not None
                    and h > st.hi_v and used_hi != st.hi_v):
                span = st.kept[st.hi_i + 1:]
                if span and any(x[5] == -1 for x in span):
                    slp = min(span, key=lambda x: x[3])[3]
                    e = st.hi_v + S
                    if e - slp > S:
                        used_hi = st.hi_v
                        pos = open_pos(1, e, slp)
            elif (st.trend == -1 and st.lo_v is not None
                    and l < st.lo_v and used_lo != st.lo_v):
                span = st.kept[st.lo_i + 1:]
                if span and any(x[5] == 1 for x in span):
                    slp = max(span, key=lambda x: x[2])[2]
                    e = st.lo_v
                    if slp - e > S:
                        used_lo = st.lo_v
                        pos = open_pos(-1, e, slp)
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
        pos = open_pos(d, e2, slp)
    W = sum(1 for x in out if x > 0)
    cum = pk = mdd = 0.0
    for x in out:
        cum += x
        pk = max(pk, cum)
        mdd = max(mdd, pk - cum)
    return sum(out), len(out), W, mdd, nf, na2


for lbl, m, al in (("HWM peak-debt (live)", "hwm", 0),
                   ("per-loss FULL (1.0x)", "loss", 1.0),
                   ("per-loss HALF (0.5x)", "loss", 0.5)):
    n, cnt, w, dd, nf, na2 = run(0, len(T), m, al)
    na_, _, _, _, _, _ = run(0, mid, m, al)
    nb_, _, _, _, _, _ = run(mid, len(T), m, al)
    print(f"{lbl}: net {n:+8.2f} wr {w/max(1,cnt):.0%} "
          f"maxDD {dd:6.2f} fights {nf:3d} adds {na2:3d} | "
          f"h1 {na_:+7.2f} | h2 {nb_:+7.2f}")
