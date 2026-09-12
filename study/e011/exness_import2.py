"""E011 importer v2 (memory-efficient, for dense years like 2025).

Same rules as exness_import.py (sorted, exact duplicates dropped, bad
prices dropped, no interpolation, bid-based M1, SHA-256 per zip) but:
  - pandas C parser, one monthly zip at a time, nothing held across months
  - per-month compact tick file: t_off uint32 (ms since month start),
    bid_c int32 (price in cents), spr_c uint16 (spread in cents)
    -> 10 bytes/tick instead of 24; exact to the cent
  - a small index.json with month starts and counts so a lazy loader can
    map global tick indices to months
  - a merged M1 npz for the whole era (bid OHLC, tick count, mean spread)
usage: python exness_import2.py <out_dir> <zip> [<zip> ...]
"""
import datetime as dt
import hashlib
import json
import os
import sys
import zipfile

import numpy as np
import pandas as pd

DELETE_ZIPS = False


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_month(path):
    z = zipfile.ZipFile(path)
    name = [i.filename for i in z.infolist() if i.filename.endswith(".csv")][0]
    with z.open(name) as f:
        df = pd.read_csv(f, usecols=["Timestamp", "Bid", "Ask"], dtype={"Bid": "float64", "Ask": "float64"})
    rows = len(df)
    ts = pd.to_datetime(df["Timestamp"], format="%Y-%m-%d %H:%M:%S.%fZ", errors="coerce", utc=True)
    bad_ts = int(ts.isna().sum())
    t = ts.to_numpy().astype("datetime64[ms]").astype(np.int64)   # -> ms since epoch, unit-safe
    b = df["Bid"].to_numpy()
    a = df["Ask"].to_numpy()
    del df
    ok = (~ts.isna().to_numpy()) & (b > 0) & (a > 0) & (a >= b)
    n_bad = int((~ok).sum()) - bad_ts
    t, b, a = t[ok], b[ok], a[ok]
    o = np.argsort(t, kind="stable")
    t, b, a = t[o], b[o], a[o]
    same = np.concatenate([[False], (t[1:] == t[:-1]) & (b[1:] == b[:-1]) & (a[1:] == a[:-1])])
    n_dup = int(same.sum())
    t, b, a = t[~same], b[~same], a[~same]
    return name, rows, bad_ts, n_bad, n_dup, t, b, a


def to_m1(t, b, a):
    m = (t // 60000) * 60
    starts = np.concatenate([[0], np.where(np.diff(m) != 0)[0] + 1])
    ends = np.concatenate([starts[1:], [len(m)]])
    T = m[starts]
    O = b[starts]
    C = b[ends - 1]
    H = np.maximum.reduceat(b, starts)
    L = np.minimum.reduceat(b, starts)
    V = ends - starts
    SP = np.add.reduceat(a - b, starts) / V
    return T, O, H, L, C, V, SP


def main(out_dir, zips):
    os.makedirs(out_dir, exist_ok=True)
    index = []
    M1 = []
    rep = open(os.path.join(out_dir, "import_report.txt"), "a", encoding="utf-8")
    for p in sorted(zips):
        name, rows, bad_ts, n_bad, n_dup, t, b, a = read_month(p)
        t0 = int(t[0] // 1000 // 86400 * 86400 * 1000)          # day start of first tick
        key = dt.datetime.utcfromtimestamp(t[0] / 1000).strftime("%Y_%m")
        np.savez_compressed(os.path.join(out_dir, f"ticks_{key}.npz"),
                            t_off=(t - t0).astype(np.uint32), bid_c=np.round(b * 100).astype(np.int32),
                            spr_c=np.round((a - b) * 100).astype(np.uint16))
        T, O, H, L, C, V, SP = to_m1(t, b, a)
        M1.append((T, O, H, L, C, V, SP))
        index.append(dict(key=key, t0_ms=t0, n=int(len(t)), first_ms=int(t[0]), last_ms=int(t[-1]), zip=os.path.basename(p), sha256=sha256(p)))
        line = (f"{os.path.basename(p)}: sha256 {index[-1]['sha256']} | rows {rows} -> kept {len(t)} (bad ts {bad_ts}, bad price {n_bad}, exact dups {n_dup}) | "
                f"{dt.datetime.utcfromtimestamp(t[0]/1000)} -> {dt.datetime.utcfromtimestamp(t[-1]/1000)} | spread median {np.median(a-b):.2f} p95 {np.percentile(a-b,95):.2f} max {(a-b).max():.2f} | "
                f"M1 bars {len(T)} | downloaded {dt.datetime.utcfromtimestamp(os.path.getmtime(p)).isoformat(timespec='seconds')}Z")
        print(line, flush=True)
        rep.write(line + "\n")
        rep.flush()
        del t, b, a
        if DELETE_ZIPS:
            os.remove(p)
            print(f"  removed {os.path.basename(p)} (re-downloadable; sha256 recorded)", flush=True)
    ip = os.path.join(out_dir, "index.json")
    if os.path.exists(ip):
        try:
            old = json.load(open(ip))
            keys = {i["key"] for i in index}
            index = [i for i in old if i["key"] not in keys] + index
            index.sort(key=lambda i: i["key"])
        except Exception:
            pass
    json.dump(index, open(ip, "w"), indent=1)
    T = np.concatenate([m[0] for m in M1])
    o = np.argsort(T, kind="stable")
    np.savez_compressed(os.path.join(out_dir, "m1.npz"), t=T[o],
                        o=np.concatenate([m[1] for m in M1])[o], h=np.concatenate([m[2] for m in M1])[o],
                        l=np.concatenate([m[3] for m in M1])[o], c=np.concatenate([m[4] for m in M1])[o],
                        v=np.concatenate([m[5] for m in M1])[o], sp=np.concatenate([m[6] for m in M1])[o])
    d = np.diff(T[o]) // 60
    g = np.where(d > 5)[0]
    line = f"ERA: {sum(i['n'] for i in index)} ticks, M1 bars {len(T)}, gaps > 5 min: {len(g)}" + ("" if not len(g) else "; largest: " + ", ".join(
        f"{dt.datetime.utcfromtimestamp(int(T[o][i])).strftime('%Y-%m-%d %H:%M')}->{int(d[i])}min" for i in g[np.argsort(-d[g])][:8]))
    print(line, flush=True)
    rep.write(line + "\nDONE\n")
    rep.close()


if __name__ == "__main__":
    DELETE_ZIPS = "--delete-zips" in sys.argv
    args = [x for x in sys.argv[1:] if x != "--delete-zips"]
    main(args[0], args[1:])
