"""REGIME research pass (2026-09-11): per-trade features known BEFORE entry.

Baseline = the live rule set: flip-BOS + continuation on candle close,
awake gate 2h, SL at the pending dot, TP 0.8R, one position, flat 0.02,
tick execution (exec_audit.simulate mode "tick", min_dist 10).

Two runs: in-sample (pro_m1.npz, 2026-07-01 -> 09-08 07:11) and the
untouched tail (m1_trial9_all.npz, trades after 2026-09-08 07:12).
Writes trades_insample.csv and trades_oos.csv with one row per trade
and every feature listed in the request (sections 1-4).
"""
import csv
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "audit"))
import exec_audit as A  # noqa: E402
from bt_bos import Struct  # noqa: E402

DATA = os.path.join(HERE, "..", "data")
ENT = ("flip", "cont")


class Pre2(A.Pre):
    """Pre + structure events, reference levels, signal ordinals."""

    def __init__(self, O, H, L, C, T):
        super().__init__(O, H, L, C, T)
        N = len(T)
        self.ref_hi = np.full(N, np.nan)   # running high before the bar
        self.ref_lo = np.full(N, np.nan)
        self.ev_choch = np.zeros(N, bool)
        self.ev_repair = np.zeros(N, bool)
        self.ev_flip = np.zeros(N, bool)
        self.last_flip = np.full(N, -1, np.int64)   # bar index of the last flip (<= j)
        self.sig_ord = np.zeros(N, np.int32)        # 1 = flip signal, 2 = first cont, ...
        st = Struct()
        lf = -1
        order = 0
        for j in range(N):
            if st.hi_v is not None:
                self.ref_hi[j] = st.hi_v
            if st.lo_v is not None:
                self.ref_lo[j] = st.lo_v
            pt, pc = st.trend, st.choch
            sig = st.step(int(T[j]), O[j], H[j], L[j], C[j])
            if st.choch != pc and st.choch != 0:
                self.ev_choch[j] = True
            if pc != 0 and st.choch == 0 and st.trend == pt and st.trend != 0:
                self.ev_repair[j] = True
            if st.trend != pt and st.trend != 0 and pt != 0:
                self.ev_flip[j] = True
                lf = j
            if sig is not None:
                if st.trend != pt:
                    order = 1
                else:
                    order += 1
                self.sig_ord[j] = order
            self.last_flip[j] = lf


def features(P, x, tk):
    """All features for trade x (entry bar j = the BOS candle)."""
    j, d = x["j"], x["d"]
    O, H, L, C, T = P.O, P.H, P.L, P.C, P.T
    f = {}
    ref = P.ref_hi[j] if d == 1 else P.ref_lo[j]
    f["ref_level"] = ref
    f["overshoot"] = (C[j] - ref) * d
    f["stop_dist"] = x["dist"]
    f["overshoot_ratio"] = f["overshoot"] / x["dist"]
    body = abs(C[j] - O[j])
    rng = H[j] - L[j]
    f["body"] = body
    f["range"] = rng
    f["body_range"] = body / rng if rng > 0 else np.nan
    f["close_loc"] = ((C[j] - L[j]) / rng if d == 1 else (H[j] - C[j]) / rng) if rng > 0 else np.nan
    # ordinal
    f["ordinal"] = int(P.sig_ord[j])
    f["kind"] = x["kind"]
    lf = int(P.last_flip[j])
    f["bars_since_flip"] = j - lf if lf >= 0 else -1
    # structure efficiency since the last flip (continuation only meaningful)
    if lf >= 0 and j > lf:
        prog = (C[j] - C[lf]) * d
        trav = float(np.abs(np.diff(C[lf:j + 1])).sum())
        f["se_flip"] = prog / trav if trav > 0 else np.nan
        f["prog_flip"] = prog
        f["travel_flip"] = trav
        dist_ev = int(P.ev_choch[lf + 1:j + 1].sum() + P.ev_repair[lf + 1:j + 1].sum())
        f["disturb_flip"] = dist_ev
        f["prog_per_disturb"] = prog / (1 + dist_ev)
    else:
        f["se_flip"] = np.nan
        f["prog_flip"] = np.nan
        f["travel_flip"] = np.nan
        f["disturb_flip"] = np.nan
        f["prog_per_disturb"] = np.nan
    # windowed efficiency (all entries): last 60 bars, trend direction
    a = max(0, j - 60)
    prog60 = (C[j] - C[a]) * d
    trav60 = float(np.abs(np.diff(C[a:j + 1])).sum())
    f["se_60"] = prog60 / trav60 if trav60 > 0 else np.nan
    a2 = max(0, j - 120)
    f["chochs_2h"] = int(P.ev_choch[a2:j + 1].sum())
    f["repairs_2h"] = int(P.ev_repair[a2:j + 1].sum())
    f["flips_2h"] = int(P.ev_flip[a2:j + 1].sum())
    f["disturb_2h"] = f["chochs_2h"] + f["repairs_2h"]
    # risk geometry
    atr14 = float(np.mean(H[max(0, j - 13):j + 1] - L[max(0, j - 13):j + 1]))
    med60 = float(np.median(H[max(0, j - 59):j + 1] - L[max(0, j - 59):j + 1]))
    f["atr14"] = atr14
    f["med_range60"] = med60
    f["stop_atr"] = x["dist"] / atr14 if atr14 > 0 else np.nan
    f["stop_med60"] = x["dist"] / med60 if med60 > 0 else np.nan
    for w in (15, 30, 60):
        r = float(H[max(0, j - w + 1):j + 1].max() - L[max(0, j - w + 1):j + 1].min())
        f[f"range{w}"] = r
    f["stop_range60"] = x["dist"] / f["range60"] if f["range60"] > 0 else np.nan
    f["tp_dist"] = A.RR * x["dist"]
    return f


def build(m1_file, out_csv, t_lo=None, tk=None):
    O, H, L, C, T = A.load_m1(os.path.join(DATA, m1_file))
    P = Pre2(O, H, L, C, T)
    tr = A.simulate(P, "tick", ENT, True, ticks=tk, min_dist=10)
    if t_lo is not None:
        tr = [x for x in tr if x["t"] >= t_lo]
    rows = []
    for x in tr:
        f = features(P, x, tk)
        f.update(t=x["t"], time=dt.datetime.utcfromtimestamp(x["t"]).isoformat(),
                 d=x["d"], e=round(x["e"], 2), sl=round(x["sl"], 2), tp=round(x["tp"], 2),
                 exit=round(x["x"], 2), why=x["why"], pnl=round(x["pnl"], 4))
        rows.append(f)
    cols = ["time", "t", "kind", "d", "e", "sl", "tp", "exit", "why", "pnl", "ordinal", "bars_since_flip",
            "ref_level", "overshoot", "stop_dist", "overshoot_ratio", "body", "range", "body_range", "close_loc",
            "se_flip", "prog_flip", "travel_flip", "disturb_flip", "prog_per_disturb", "se_60",
            "chochs_2h", "repairs_2h", "flips_2h", "disturb_2h",
            "atr14", "med_range60", "stop_atr", "stop_med60", "range15", "range30", "range60", "stop_range60", "tp_dist"]
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    print(f"{out_csv}: {len(rows)} trades, net {sum(r['pnl'] for r in rows):+.2f}")
    return rows, T


if __name__ == "__main__":
    tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
    rows, T = build("pro_m1.npz", os.path.join(HERE, "trades_insample.csv"), tk=tk)
    mid = int(T[0] + (T[-1] - T[0]) // 2)
    print("in-sample midpoint:", dt.datetime.utcfromtimestamp(mid), "| research end:", dt.datetime.utcfromtimestamp(T[-1]))
    build("m1_trial9_all.npz", os.path.join(HERE, "trades_oos.csv"), t_lo=int(T[-1]) + 60, tk=tk)
    with open(os.path.join(HERE, "split.txt"), "w") as fh:
        fh.write(f"mid={mid}\nresearch_end={int(T[-1])}\n")
