"""Random-direction control for the awake gate (flips>=1): same
gated moments and stop distances, coin-flip direction. If the edge
is the direction choice, signal beats the coins."""
from collections import deque

from bt_bos import Struct, O, H, L, C, T, S

LOT = 0.02
RR = 0.8
WIN = 7200


def run(mode="signal", seed=1):
    st = Struct()
    pos = None
    ev = deque()
    out = []
    rs = [seed]

    def rnd():
        rs[0] = (rs[0] * 1103515245 + 12345) % (2 ** 31)
        return rs[0] / (2 ** 31)

    for j in range(len(T)):
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
        if st.trend != pt and st.trend != 0 and pt != 0:
            ev.append((t, "flip"))
        while ev and ev[0][0] < t - WIN:
            ev.popleft()
        if sig is None or pos is not None:
            continue
        if not ev:                      # awake gate: >=1 flip in 2h
            continue
        d, slp = sig
        if mode == "random":
            dist = abs(c - slp)
            d = 1 if rnd() < 0.5 else -1
            slp = c - d * dist
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
    w = sum(1 for x in out if x > 0)
    print(f"{mode:7s} seed {seed:2d}: n {len(out):4d} "
          f"wr {w/max(1,len(out)):.0%} net {sum(out):+8.2f}")
    return sum(out)


run("signal")
for s in (11, 22, 33, 44, 55):
    run("random", seed=s)
