"""E012 - higher-timeframe context before an M1 BOS entry vs TP-first / SL-first.

Light study: M1 arrays only, existing frozen trade lists (R0 from the tick
baseline: study/regime/trades_insample.csv; V2 from study/e011/trades_V2.csv,
consumed era, historical replication only). No ticks, no V3/V4.

HTF construction: M5/M15/H1 from bid M1 OHLC. At an M1 entry on signal bar
time tb (entry at its close tb+60), only HTF candles with end <= tb+60 are
used (COMPLETED candles only). The same structure engine (bt_bos.Struct)
is run on each HTF series; per completed bar we store trend, the last
confirmed BOS (dir, bar), last flip/CHoCH (dir, bar), and the list of
confirmed swing levels (the pending-dot levels the engine confirms on
each BOS: swing LOWS on up-BOS, swing HIGHS on down-BOS).

Predeclared buckets (before results): recent = <= 3 completed HTF bars;
room_ratio = distance to nearest confirmed opposing swing / planned TP
distance, buckets <0.5, 0.5-1, 1-2, >2, none (1.0 = obstacle before TP);
range position = thirds of the previous 20 completed bars' range, labelled
favourable (BUY in bottom third / SELL in top third), middle,
unfavourable. Logistic regression on the predeclared variables only.
"""
import csv
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bt_bos import Struct  # noqa: E402

D = os.path.join(HERE, "..", "data")
sp = dict(l.strip().split("=") for l in open(os.path.join(HERE, "..", "regime", "split.txt")))
MID = int(sp["mid"])
out = open(os.path.join(HERE, "results_e012.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")


# ------------------------------------------------------------- HTF engine
def resample(T, O, H, L, C, tf):
    b = T // tf
    starts = np.concatenate([[0], np.where(np.diff(b) != 0)[0] + 1])
    ends = np.concatenate([starts[1:], [len(b)]])
    return (b[starts] * tf, O[starts], np.maximum.reduceat(H, starts), np.minimum.reduceat(L, starts), C[ends - 1])


class HTF:
    def __init__(self, T, O, H, L, C, tf):
        self.tf = tf
        self.T, self.O, self.H, self.L, self.C = resample(T, O, H, L, C, tf)
        n = len(self.T)
        self.end = self.T + tf                      # completion time of each bar
        self.trend = np.zeros(n, np.int8)
        self.last_bos_d = np.zeros(n, np.int8)
        self.last_bos_i = np.full(n, -1)
        self.last_flip_d = np.zeros(n, np.int8)
        self.last_flip_i = np.full(n, -1)
        self.last_choch_d = np.zeros(n, np.int8)
        self.last_choch_i = np.full(n, -1)
        self.swing_hi = []                          # (bar i, level) confirmed swing highs
        self.swing_lo = []
        self.n_hi = np.zeros(n, int)                # how many confirmed highs exist up to bar i
        self.n_lo = np.zeros(n, int)
        st = Struct()
        bos_d = bos_i = flip_d = flip_i = ch_d = ch_i = None
        bos_d, flip_d, ch_d = 0, 0, 0
        bos_i = flip_i = ch_i = -1
        for i in range(n):
            pt, pc = st.trend, st.choch
            sig = st.step(int(self.T[i]), self.O[i], self.H[i], self.L[i], self.C[i])
            if st.choch != pc and st.choch != 0:
                ch_d, ch_i = st.choch, i
            if st.trend != pt and st.trend != 0 and pt != 0:
                flip_d, flip_i = st.trend, i
            if sig is not None:
                bos_d, bos_i = sig[0], i
                if sig[0] == 1:
                    self.swing_lo.append((i, sig[1]))
                else:
                    self.swing_hi.append((i, sig[1]))
            self.trend[i] = st.trend
            self.last_bos_d[i], self.last_bos_i[i] = bos_d, bos_i
            self.last_flip_d[i], self.last_flip_i[i] = flip_d, flip_i
            self.last_choch_d[i], self.last_choch_i[i] = ch_d, ch_i
            self.n_hi[i], self.n_lo[i] = len(self.swing_hi), len(self.swing_lo)
        self.swing_hi_lv = np.array([x[1] for x in self.swing_hi]) if self.swing_hi else np.array([])
        self.swing_lo_lv = np.array([x[1] for x in self.swing_lo]) if self.swing_lo else np.array([])
        self.atr = np.concatenate([[np.nan] * 13, np.convolve(self.H - self.L, np.ones(14) / 14, "valid")]) if n >= 14 else np.full(n, np.nan)

    def idx_completed(self, t_entry):
        """index of the last bar completed at or before t_entry (None if none)."""
        k = int(np.searchsorted(self.end, t_entry, side="right")) - 1
        return k if k >= 0 else None

    def features(self, t_entry, d, price, tp_dist, prefix):
        f = {}
        k = self.idx_completed(t_entry)
        if k is None or k < 20:
            return {f"{prefix}_ok": 0}
        f[f"{prefix}_ok"] = 1
        tr = int(self.trend[k])
        f[f"{prefix}_trend"] = tr
        f[f"{prefix}_aligned"] = 1 if tr == d else (0 if tr == 0 else -1)
        # recent BOS / CHoCH-flip categories
        for nm, dd, ii in (("bos", self.last_bos_d, self.last_bos_i), ("flip", self.last_flip_d, self.last_flip_i), ("choch", self.last_choch_d, self.last_choch_i)):
            if ii[k] < 0:
                f[f"{prefix}_{nm}"] = "none"
            else:
                age = k - ii[k]
                al = "aligned" if dd[k] == d else "opposing"
                f[f"{prefix}_{nm}"] = f"recent_{al}" if age <= 3 else "stale"
                f[f"{prefix}_{nm}_age"] = age
        # room to nearest confirmed opposing swing (confirmed by bar k)
        if d == 1:
            lv = self.swing_hi_lv[:self.n_hi[k]]
            above = lv[lv > price]
            obst = above.min() if len(above) else None
        else:
            lv = self.swing_lo_lv[:self.n_lo[k]]
            below = lv[lv < price]
            obst = below.max() if len(below) else None
        if obst is None:
            f[f"{prefix}_room"] = np.nan
            f[f"{prefix}_room_b"] = "none"
        else:
            r = abs(obst - price) / tp_dist
            f[f"{prefix}_room"] = r
            f[f"{prefix}_room_b"] = "<0.5" if r < 0.5 else "0.5-1" if r < 1 else "1-2" if r < 2 else ">2"
        # position in the previous 20 completed bars' range
        hi = self.H[k - 19:k + 1].max()
        lo = self.L[k - 19:k + 1].min()
        pos = (price - lo) / (hi - lo) if hi > lo else 0.5
        pos_dir = pos if d == 1 else 1 - pos          # 0 = plenty of room in trade direction
        f[f"{prefix}_rangepos"] = "favourable" if pos_dir < 1 / 3 else "middle" if pos_dir < 2 / 3 else "unfavourable"
        f[f"{prefix}_rangepos_v"] = pos_dir
        # last completed candle shape
        o, h, l, c = self.O[k], self.H[k], self.L[k], self.C[k]
        rng = h - l
        body = abs(c - o)
        f[f"{prefix}_cdl_dir"] = "bull" if c > o else "bear" if c < o else "doji"
        f[f"{prefix}_cdl_body_range"] = body / rng if rng > 0 else np.nan
        f[f"{prefix}_cdl_body_atr"] = body / self.atr[k] if self.atr[k] and not np.isnan(self.atr[k]) else np.nan
        f[f"{prefix}_cdl_upper"] = (h - max(o, c)) / rng if rng > 0 else np.nan
        f[f"{prefix}_cdl_lower"] = (min(o, c) - l) / rng if rng > 0 else np.nan
        f[f"{prefix}_cdl_with"] = 1 if (c > o) == (d == 1) and c != o else 0
        return f


# ------------------------------------------------------------- trades
def load_r0():
    M = np.load(os.path.join(D, "pro_m1.npz"))
    T, O, H, L, C = M["t"].astype(np.int64), M["o"].astype(float), M["h"].astype(float), M["l"].astype(float), M["c"].astype(float)
    rows = list(csv.DictReader(open(os.path.join(HERE, "..", "regime", "trades_insample.csv"))))
    tr = []
    for r in rows:
        tr.append(dict(tb=int(float(r["t"])), kind=r["kind"], d=int(float(r["d"])), e=float(r["e"]), sl=float(r["sl"]), tp=float(r["tp"]),
                       why=r["why"], pnl=float(r["pnl"]), R=float(r["pnl"]) / (abs(float(r["e"]) - float(r["sl"])) * 0.02), ordinal=int(float(r["ordinal"])),
                       era="TRAIN" if float(r["t"]) < MID else "TEST"))
    return (T, O, H, L, C), tr


def load_v2():
    M = np.load(os.path.join(HERE, "..", "e011", "data", "archive_v2_m1.npz"))
    T, O, H, L, C = M["t"].astype(np.int64), M["o"].astype(float), M["h"].astype(float), M["l"].astype(float), M["c"].astype(float)
    rows = list(csv.DictReader(open(os.path.join(HERE, "..", "e011", "trades_V2.csv"))))
    tr = []
    for r in rows:
        fill = dt.datetime.fromisoformat(r["entry_time_utc"]).replace(tzinfo=dt.timezone.utc).timestamp()
        tb = int(fill // 60) * 60 - 60
        d = 1 if r["dir"] == "BUY" else -1
        tr.append(dict(tb=tb, kind=r["kind"], d=d, e=float(r["entry"]), sl=float(r["sl"]), tp=float(r["tp"]), why=r["why"],
                       pnl=float(r["pnl_002"]), R=float(r["R"]), ordinal=-1, era="V2"))
    return (T, O, H, L, C), tr


def build(m1, trades, label):
    T, O, H, L, C = m1
    htf = {nm: HTF(T, O, H, L, C, tf) for nm, tf in (("M5", 300), ("M15", 900), ("H1", 3600))}
    for x in trades:
        t_entry = x["tb"] + 60
        tp_dist = abs(x["tp"] - x["e"])
        for nm, h in htf.items():
            x.update(h.features(t_entry, x["d"], x["e"], tp_dist, nm))
        al = [x.get(f"{nm}_aligned", 0) for nm in ("M5", "M15", "H1")]
        x["n_aligned"] = sum(1 for a in al if a == 1)
        x["n_opposed"] = sum(1 for a in al if a == -1)
        rooms = [x.get(f"{nm}_room", np.nan) for nm in ("M5", "M15", "H1")]
        rooms = [r for r in rooms if not np.isnan(r)]
        x["min_room"] = min(rooms) if rooms else np.nan
        r = x["min_room"]
        x["min_room_b"] = "none" if np.isnan(r) else "<0.5" if r < 0.5 else "0.5-1" if r < 1 else "1-2" if r < 2 else ">2"
        x["tpfirst"] = 1 if x["why"] == "tp" else 0
    say(f"{label}: {len(trades)} trades; HTF bars M5 {len(htf['M5'].T)} M15 {len(htf['M15'].T)} H1 {len(htf['H1'].T)}; confirmed swings H1 hi/lo {len(htf['H1'].swing_hi)}/{len(htf['H1'].swing_lo)}")
    return trades


def stat(rows):
    if not rows:
        return "n    0"
    p = np.array([x["pnl"] for x in rows])
    R = np.array([x["R"] for x in rows])
    W = p[p > 0]
    Lo = p[p <= 0]
    pf = W.sum() / -Lo.sum() if len(Lo) and Lo.sum() < 0 else float("inf")
    return f"n {len(p):4d} TPfirst {np.mean([x['tpfirst'] for x in rows]):5.1%} wr {(p>0).mean():5.1%} expR {R.mean():+.3f} exp$ {p.mean():+.3f} PF {pf:4.2f} net {p.sum():+8.2f}"


def table(all_tr, key, label, kinds=("flip", "cont"), order=None):
    say(f"\n--- {label}")
    for kind in kinds:
        for era in ("TRAIN", "TEST", "V2"):
            rows = [x for x in all_tr if x["era"] == era and x["kind"] == kind]
            vals = order or sorted(set(str(x.get(key, "na")) for x in rows))
            parts = []
            for v in vals:
                s = [x for x in rows if str(x.get(key, "na")) == v]
                if s:
                    parts.append(f"{v}: {stat(s)}")
            say(f"  {kind:4s} {era:5s}")
            for pt in parts:
                say("      " + pt)


# ------------------------------------------------------------- run
m1_r0, tr_r0 = load_r0()
tr_r0 = build(m1_r0, tr_r0, "R0")
m1_v2, tr_v2 = load_v2()
tr_v2 = build(m1_v2, tr_v2, "V2 (consumed, historical replication only; archive M1)")
ALL = tr_r0 + tr_v2

say("\n=== PART 0. STOP DISTANCE BY ORDINAL (R0 gated trade list) ===")
for era in ("TRAIN", "TEST"):
    say(f"  {era}")
    for lbl, fn in (("FLIP-BOS", lambda x: x["kind"] == "flip"), ("cont ordinal 2 (1st cont)", lambda x: x["kind"] == "cont" and x["ordinal"] == 2),
                    ("cont ordinal 3", lambda x: x["kind"] == "cont" and x["ordinal"] == 3), ("cont ordinal 4+", lambda x: x["kind"] == "cont" and x["ordinal"] >= 4)):
        s = [x for x in tr_r0 if x["era"] == era and fn(x)]
        if s:
            dists = np.array([abs(x["e"] - x["sl"]) for x in s])
            say(f"    {lbl:26s} n {len(s):3d} stop median {np.median(dists):6.1f} q25 {np.percentile(dists,25):6.1f} q75 {np.percentile(dists,75):6.1f} | {stat(s)}")

say("\n=== FEATURE FAMILY 1. HTF STRUCTURE ALIGNMENT (completed candles; 1 aligned, 0 neutral, -1 opposing) ===")
for nm in ("M5", "M15", "H1"):
    table(ALL, f"{nm}_aligned", f"{nm} trend vs trade direction", order=["1", "0", "-1"])
table(ALL, "n_aligned", "number of aligned timeframes (M5+M15+H1)", order=["0", "1", "2", "3"])

say("\n=== FEATURE FAMILY 2. RECENT HTF BOS / CHoCH (recent = <= 3 completed bars) ===")
for nm in ("M15", "H1"):
    table(ALL, f"{nm}_bos", f"{nm} last confirmed BOS", order=["recent_aligned", "recent_opposing", "stale", "none"])
    table(ALL, f"{nm}_flip", f"{nm} last trend flip", order=["recent_aligned", "recent_opposing", "stale", "none"])

say("\n=== FEATURE FAMILY 3. ROOM TO TP vs nearest confirmed opposing HTF swing (ratio = obstacle distance / TP distance) ===")
for nm in ("M5", "M15", "H1"):
    table(ALL, f"{nm}_room_b", f"{nm} room ratio", order=["<0.5", "0.5-1", "1-2", ">2", "none"])
table(ALL, "min_room_b", "MINIMUM room ratio across M5/M15/H1", order=["<0.5", "0.5-1", "1-2", ">2", "none"])

say("\n=== FEATURE FAMILY 4. POSITION IN THE PREVIOUS 20 COMPLETED BARS' RANGE (directional thirds) ===")
for nm in ("M15", "H1"):
    table(ALL, f"{nm}_rangepos", f"{nm} range position", order=["favourable", "middle", "unfavourable"])

say("\n=== DESCRIPTIVE: last completed M15 / H1 candle, means by outcome (TRAIN / TEST / V2) ===")
for nm in ("M15", "H1"):
    for era in ("TRAIN", "TEST", "V2"):
        rows = [x for x in ALL if x["era"] == era and x.get(f"{nm}_ok")]
        for lab, sel in (("TP-first", [x for x in rows if x["tpfirst"]]), ("SL-first", [x for x in rows if not x["tpfirst"]])):
            if sel:
                say(f"  {nm} {era:5s} {lab:8s} n {len(sel):4d} | candle with trade {np.mean([x[f'{nm}_cdl_with'] for x in sel]):.0%} | body/range {np.nanmean([x[f'{nm}_cdl_body_range'] for x in sel]):.3f} "
                    f"| body/ATR {np.nanmean([x[f'{nm}_cdl_body_atr'] for x in sel]):.3f} | upper wick {np.nanmean([x[f'{nm}_cdl_upper'] for x in sel]):.3f} | lower wick {np.nanmean([x[f'{nm}_cdl_lower'] for x in sel]):.3f}")

# ------------------------------------------------------------- logistic regression (predeclared variables)
say("\n=== LOGISTIC REGRESSION on R0-TRAIN, predeclared variables only; frozen, scored on TEST and V2 ===")
VARS = ["n_aligned", "rec_al_m15h1", "rec_op_m15h1", "room_lt1", "room_none", "h1_fav", "h1_unfav", "is_flip"]


def design(x):
    rec_al = int(x.get("M15_bos") == "recent_aligned" or x.get("H1_bos") == "recent_aligned")
    rec_op = int(x.get("M15_bos") == "recent_opposing" or x.get("H1_bos") == "recent_opposing")
    room_lt1 = int(x["min_room_b"] in ("<0.5", "0.5-1"))
    room_none = int(x["min_room_b"] == "none")
    return [x["n_aligned"], rec_al, rec_op, room_lt1, room_none, int(x.get("H1_rangepos") == "favourable"), int(x.get("H1_rangepos") == "unfavourable"), int(x["kind"] == "flip")]


def fit_logit(X, y, iters=50, l2=1e-3):
    X1 = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(X1.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X1 @ w))
        Wd = p * (1 - p)
        g = X1.T @ (y - p) - l2 * w
        Hs = -(X1.T * Wd) @ X1 - l2 * np.eye(len(w))
        w = w - np.linalg.solve(Hs, g)
    return w


def predict(w, X):
    return 1 / (1 + np.exp(-(np.column_stack([np.ones(len(X)), X]) @ w)))


def auc(y, p):
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    return (ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else float("nan")


tr_ = [x for x in ALL if x["era"] == "TRAIN"]
Xtr = np.array([design(x) for x in tr_], float)
ytr = np.array([x["tpfirst"] for x in tr_], float)
w = fit_logit(Xtr, ytr)
say("  coefficients (log-odds): intercept %.3f | " % w[0] + " | ".join(f"{v} {c:+.3f}" for v, c in zip(VARS, w[1:])))
ptr = predict(w, Xtr)
cuts = np.percentile(ptr, [20, 40, 60, 80])
for era in ("TRAIN", "TEST", "V2"):
    rows = [x for x in ALL if x["era"] == era]
    X = np.array([design(x) for x in rows], float)
    y = np.array([x["tpfirst"] for x in rows], float)
    p = predict(w, X)
    say(f"  {era:5s}: n {len(y)} AUC {auc(y, p):.3f} Brier {np.mean((p - y) ** 2):.4f} (base rate {y.mean():.3f}, Brier of base rate {np.mean((y.mean() - y) ** 2):.4f})")
    q = np.digitize(p, cuts)
    for qi in range(5):
        sel = [rows[i] for i in range(len(rows)) if q[i] == qi]
        if sel:
            say(f"      quintile {qi+1} (pred {np.mean([p[i] for i in range(len(rows)) if q[i]==qi]):.3f}): {stat(sel)}")

# ------------------------------------------------------------- candidate rule (stated before results; reported regardless)
say("\n=== PREDECLARED CANDIDATE: skip CONTINUATION entries when a confirmed opposing M15 or H1 swing lies before the TP (room ratio < 1 on M15 or H1) ===")
for era in ("TRAIN", "TEST", "V2"):
    rows = [x for x in ALL if x["era"] == era]
    blk = [x for x in rows if x["kind"] == "cont" and (x.get("M15_room_b") in ("<0.5", "0.5-1") or x.get("H1_room_b") in ("<0.5", "0.5-1"))]
    kept = [x for x in rows if x not in blk]
    say(f"  {era:5s} baseline {stat(rows)}")
    say(f"  {era:5s} kept     {stat(kept)}")
    say(f"  {era:5s} blocked  {stat(blk)}")
say("\ndone")
out.close()
