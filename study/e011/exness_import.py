"""E011 importer: Exness public tick archive -> research formats.

Source: https://ticks.ex2archive.com/ticks/BTCUSD/<YYYY>/<MM>/Exness_BTCUSD_<YYYY>_<MM>.zip
CSV columns: "Exness","Symbol","Timestamp","Bid","Ask"; Timestamp is
ISO-8601 with millisecond precision and a trailing Z (UTC).

Outputs (per call):
  ticks npz : t (int64, ms since epoch UTC), bid, ask (float64)
  M1 npz    : t (int64, bar open time, s), o/h/l/c from BID prices
              (the MT5 convention; verified in overlap_check.py),
              v = tick count, sp = mean spread in the bar
Rules: rows sorted by timestamp (stable); exact duplicate rows
(same timestamp, bid, ask) dropped and counted; rows with bid<=0,
ask<=0 or ask<bid dropped and counted; no interpolation; minutes with no
ticks are simply absent from the M1 file (gap list written to the
report). Every input zip's SHA-256 is recorded.
"""
import csv
import hashlib
import io
import os
import sys
import zipfile
import datetime as dt

import numpy as np


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_zip(path):
    z = zipfile.ZipFile(path)
    name = [i.filename for i in z.infolist() if i.filename.endswith(".csv")][0]
    ts, bid, ask = [], [], []
    bad = 0
    with z.open(name) as f:
        rd = csv.reader(io.TextIOWrapper(f, encoding="utf-8", newline=""))
        header = next(rd)
        assert header[2] == "Timestamp" and header[3] == "Bid" and header[4] == "Ask", header
        for row in rd:
            try:
                s = row[2]
                # "2026-07-01 00:00:00.677Z"
                d = dt.datetime(int(s[0:4]), int(s[5:7]), int(s[8:10]), int(s[11:13]), int(s[14:16]), int(s[17:19]),
                                int(s[20:23]) * 1000 if len(s) > 20 and s[19] == "." else 0, tzinfo=dt.timezone.utc)
                b = float(row[3])
                a = float(row[4])
            except Exception:
                bad += 1
                continue
            ts.append(int(d.timestamp() * 1000))
            bid.append(b)
            ask.append(a)
    return np.array(ts, np.int64), np.array(bid), np.array(ask), bad, name


def clean(t, b, a):
    o = np.argsort(t, kind="stable")
    t, b, a = t[o], b[o], a[o]
    ok = (b > 0) & (a > 0) & (a >= b)
    n_bad = int((~ok).sum())
    t, b, a = t[ok], b[ok], a[ok]
    # exact duplicates
    if len(t):
        same = np.concatenate([[False], (t[1:] == t[:-1]) & (b[1:] == b[:-1]) & (a[1:] == a[:-1])])
        n_dup = int(same.sum())
        t, b, a = t[~same], b[~same], a[~same]
    else:
        n_dup = 0
    return t, b, a, n_bad, n_dup


def to_m1(t, b, a):
    m = (t // 60000) * 60
    starts = np.concatenate([[0], np.where(np.diff(m) != 0)[0] + 1])
    ends = np.concatenate([starts[1:], [len(m)]])
    T = m[starts]
    O = b[starts]
    C = b[ends - 1]
    H = np.array([b[s:e].max() for s, e in zip(starts, ends)])
    L = np.array([b[s:e].min() for s, e in zip(starts, ends)])
    V = ends - starts
    SP = np.array([(a[s:e] - b[s:e]).mean() for s, e in zip(starts, ends)])
    return T, O, H, L, C, V, SP


def gaps(T, min_minutes=5):
    d = np.diff(T) // 60
    idx = np.where(d > min_minutes)[0]
    return [(int(T[i]), int(T[i + 1]), int(d[i])) for i in idx]


def import_files(zips, out_prefix, report):
    parts = []
    lines = []
    for p in zips:
        t, b, a, bad_rows, name = read_zip(p)
        t, b, a, n_bad, n_dup = clean(t, b, a)
        lines.append(f"{os.path.basename(p)}: sha256 {sha256(p)} | member {name} | rows {len(t)+n_bad+n_dup+bad_rows} -> kept {len(t)} "
                     f"(unparsable {bad_rows}, bad price {n_bad}, exact dups {n_dup}) | {dt.datetime.utcfromtimestamp(t[0]/1000)} -> {dt.datetime.utcfromtimestamp(t[-1]/1000)} "
                     f"| spread median {np.median(a-b):.2f} p95 {np.percentile(a-b,95):.2f} max {(a-b).max():.2f} | downloaded {dt.datetime.utcfromtimestamp(os.path.getmtime(p)).isoformat(timespec='seconds')}Z")
        parts.append((t, b, a))
    t = np.concatenate([x[0] for x in parts])
    b = np.concatenate([x[1] for x in parts])
    a = np.concatenate([x[2] for x in parts])
    t, b, a, n_bad, n_dup = clean(t, b, a)
    lines.append(f"combined: {len(t)} ticks (cross-file dups removed {n_dup}), {dt.datetime.utcfromtimestamp(t[0]/1000)} -> {dt.datetime.utcfromtimestamp(t[-1]/1000)}")
    np.savez_compressed(out_prefix + "_ticks.npz", t=t, bid=b, ask=a)
    T, O, H, L, C, V, SP = to_m1(t, b, a)
    np.savez_compressed(out_prefix + "_m1.npz", t=T, o=O, h=H, l=L, c=C, v=V, sp=SP)
    g = gaps(T)
    lines.append(f"M1: {len(T)} bars; gaps > 5 min: {len(g)}" + ("" if not g else "; largest: " + ", ".join(
        f"{dt.datetime.utcfromtimestamp(x[0]).strftime('%m-%d %H:%M')}->{x[2]}min" for x in sorted(g, key=lambda x: -x[2])[:8])))
    with open(report, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return t, b, a, T, O, H, L, C


if __name__ == "__main__":
    src = sys.argv[1]
    out = sys.argv[2]
    zips = sorted(sys.argv[3:])
    import_files(zips, out, out + "_import_report.txt")
