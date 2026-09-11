"""Blind test of the 'market awake' gate: trade only when >=1 trend
flip happened in the last 2h. Grid of awake-definitions fitted on
days 1-35, the winner judged blind on days 36-69."""
from collections import deque

import numpy as np

from bt_bos import Struct, O, H, L, C, T, S

LOT = 0.02
RR = 0.8
WIN = 7200
mid = np.searchsorted(T, T[0] + (T[-1] - T[0]) // 2)


def run(a, b, gate):
    st = Struct()
    pos = None
    ev = deque()
    out = []
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
        pt, pc = st.trend, st.choch
        sig = st.step(t, o, h, l, c)
        if st.choch != pc and st.choch != 0:
            ev.append((t, "choch"))
        if st.trend != pt and st.trend != 0 and pt != 0:
            ev.append((t, "flip"))
        if pc != 0 and st.choch == 0 and st.trend == pt \
                and st.trend != 0:
            ev.append((t, "repair"))
        while ev and ev[0][0] < t - WIN:
            ev.popleft()
        if sig is None or pos is not None:
            continue
        ch = sum(1 for x in ev if x[1] == "choch")
        fl = sum(1 for x in ev if x[1] == "flip")
        if not gate(ch, fl):
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
    return out


GATES = [
    ("no gate", lambda ch, fl: True),
    ("flips>=1", lambda ch, fl: fl >= 1),
    ("flips>=2", lambda ch, fl: fl >= 2),
    ("chocs>=2", lambda ch, fl: ch >= 2),
    ("flips>=1 or chocs>=2", lambda ch, fl: fl >= 1 or ch >= 2),
]

print("gate                  | days 1-35        | days 36-69")
best = (None, -1e9)
for name, g in GATES:
    ra = run(0, mid, g)
    rb = run(mid, len(T), g)
    print(f"{name:21s} | {sum(ra):+8.2f} ({len(ra):3d}) | "
          f"{sum(rb):+8.2f} ({len(rb):3d})")
    if name != "no gate" and sum(ra) > best[1]:
        best = (name, sum(ra))
print(f"\nin-sample winner: {best[0]}")
g = dict((n, f) for n, f in GATES)[best[0]]
rb = run(mid, len(T), g)
w = sum(1 for x in rb if x > 0)
print(f"BLIND verdict: net {sum(rb):+.2f} over {len(rb)} trades "
      f"(wr {w/max(1,len(rb)):.0%})")
