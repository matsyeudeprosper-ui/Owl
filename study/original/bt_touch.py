"""User proposal 2026-09-09: in an ESTABLISHED trend, continuation
entries fire the moment price TOUCHES the reference level (entry at
level+spread, intrabar); the first BOS of a new trend still needs
the full close. Compare vs the deployed close-entry config, both
with the awake gate, ties = SL, same-bar fills allowed and judged
pessimistically. Full window + walk-forward halves."""
from collections import deque

import numpy as np

from bt_bos import Struct, O, H, L, C, T, S

LOT = 0.02
RR = 0.8
WIN = 7200
mid = np.searchsorted(T, T[0] + (T[-1] - T[0]) // 2)


def run(a, b, touch):
    st = Struct()
    pos = None
    ev = deque()
    out = []
    used_hi = used_lo = None      # consumed touch levels
    for j in range(a, b):
        t, o, h, l, c = int(T[j]), O[j], H[j], L[j], C[j]
        if pos is not None:
            d, e, sl, tp = pos
            sl_hit = (l <= sl) if d == 1 else (h >= sl - S)
            tp_hit = (h >= tp) if d == 1 else (l <= tp - S)
            if sl_hit:
                out.append((sl - e) * d * LOT)
                pos = None
            elif tp_hit:
                out.append((tp - e) * d * LOT)
                pos = None
        awake = bool(ev)
        # --- TOUCH entry (continuation only, trend from last close)
        if touch and pos is None and awake:
            if (st.trend == 1 and st.hi_v is not None
                    and h > st.hi_v and used_hi != st.hi_v):
                span = st.kept[st.hi_i + 1:]
                if span and any(x[5] == -1 for x in span):
                    m = min(span, key=lambda x: x[3])
                    slp = m[3]
                    e = st.hi_v + S
                    if e - slp > S:
                        tp = e + RR * (e - slp)
                        used_hi = st.hi_v
                        # same-bar outcome, pessimistic
                        if l <= slp:
                            out.append((slp - e) * LOT)
                        elif h >= tp:
                            out.append((tp - e) * LOT)
                        else:
                            pos = (1, e, slp, tp)
            elif (st.trend == -1 and st.lo_v is not None
                    and l < st.lo_v and used_lo != st.lo_v):
                span = st.kept[st.lo_i + 1:]
                if span and any(x[5] == 1 for x in span):
                    m = max(span, key=lambda x: x[2])
                    slp = m[2]
                    e = st.lo_v
                    if slp - e > S:
                        tp = e - RR * (slp - e)
                        used_lo = st.lo_v
                        if h >= slp - S:
                            out.append((e - slp) * LOT)
                        elif l <= tp - S:
                            out.append((e - tp) * LOT)
                        else:
                            pos = (-1, e, slp, tp)
        pt = st.trend
        sig = st.step(t, o, h, l, c)
        if st.trend != pt and st.trend != 0 and pt != 0:
            ev.append(t)
        while ev and ev[0] < t - WIN:
            ev.popleft()
        if sig is None or pos is not None or not ev:
            continue
        d, slp = sig
        flip = st.trend != pt
        if touch and not flip:
            continue              # continuation handled by touch
        e2 = c + S if d == 1 else c
        if abs(e2 - slp) <= S:
            continue
        tp = e2 + d * RR * abs(e2 - slp)
        pos = (d, e2, slp, tp)
    W = sum(1 for x in out if x > 0)
    cum = peak = mdd = 0.0
    for x in out:
        cum += x
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return sum(out), len(out), W, mdd


for lbl, tc in (("CLOSE (deployed)", False), ("TOUCH variant", True)):
    n, cnt, w, dd = run(0, len(T), tc)
    na, ca, wa, _ = run(0, mid, tc)
    nb, cb, wb, _ = run(mid, len(T), tc)
    print(f"{lbl:17s}: net {n:+8.2f} n {cnt:4d} "
          f"wr {w/max(1,cnt):.0%} maxDD {dd:6.2f} | "
          f"h1 {na:+8.2f} ({ca}) | h2 {nb:+8.2f} ({cb})")
