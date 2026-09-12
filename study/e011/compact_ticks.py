"""Loader for the compact monthly tick files written by exness_import2.py.
Returns full float64 arrays (t ms int64, bid, ask) for an era directory,
optionally restricted to a [t_lo_ms, t_hi_ms] window. One process should
hold at most one era at a time (2025 ≈ 150 M ticks ≈ 3.6 GB)."""
import json
import os

import numpy as np


def load_dir(d, t_lo=None, t_hi=None, months=None):
    idx = json.load(open(os.path.join(d, "index.json")))
    parts = []
    for m in idx:
        if months is not None and m["key"] not in months:
            continue
        if t_hi is not None and m["first_ms"] > t_hi:
            continue
        if t_lo is not None and m["last_ms"] < t_lo:
            continue
        D = np.load(os.path.join(d, f"ticks_{m['key']}.npz"))
        t = m["t0_ms"] + D["t_off"].astype(np.int64)
        b = D["bid_c"].astype(np.float64) / 100.0
        a = b + D["spr_c"].astype(np.float64) / 100.0
        if t_lo is not None or t_hi is not None:
            s = np.ones(len(t), bool)
            if t_lo is not None:
                s &= t >= t_lo
            if t_hi is not None:
                s &= t <= t_hi
            t, b, a = t[s], b[s], a[s]
        parts.append((t, b, a))
    t = np.concatenate([p[0] for p in parts])
    b = np.concatenate([p[1] for p in parts])
    a = np.concatenate([p[2] for p in parts])
    return t, b, a


def load_m1(d):
    M = np.load(os.path.join(d, "m1.npz"))
    return (M["o"].astype(float), M["h"].astype(float), M["l"].astype(float), M["c"].astype(float), M["t"].astype(np.int64))
