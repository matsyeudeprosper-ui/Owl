#!/bin/bash
# E011 sequential pipeline (one heavy job at a time on the 12 GB live box):
#   wait for the 2025 import -> V3 era run (tick) -> V3 control (M1 mode)
#   -> for each of 2022, 2023, 2024: download month, import, delete zip
#      -> era run -> control -> delete that year's tick files (M1 kept)
# Logs: pipeline.log ; markers: "STAGE ... DONE"
set -u
E=/c/Users/ADMINI~1/AppData/Local/Temp/2/claude/C--Users-Administrator--local-bin/d0f3d5ec-64a9-4f73-81c4-6f2d05427fd0/scratchpad/Owl/study/e011
A=/c/Users/ADMINI~1/AppData/Local/Temp/2/claude/C--Users-Administrator--local-bin/d0f3d5ec-64a9-4f73-81c4-6f2d05427fd0/scratchpad/exness_archive
UA="Mozilla/5.0"
cd "$E"
log() { echo "$(date -u +%FT%TZ) $*" >> pipeline.log; }

log "pipeline start; waiting for V3 import"
until grep -q "^DONE" data/v3/import_report.txt 2>/dev/null; do sleep 60; done
log "STAGE v3-import DONE"
rm -f data/v2_mt5_ticks.npz

python e011_run_era.py V3 data/v3 > run_V3.log 2>&1
log "STAGE V3 era DONE: $(grep '2h gate (production) ALL' results_V3.txt | head -1)"
python e011_control.py V3 data/v3 1000 2 pess > control_V3_m1.log 2>&1
log "STAGE V3 control DONE: $(head -1 control_V3_m1.txt)"
rm -f data/v3/ticks_*.npz
log "V3 tick files removed (M1 + index + report kept)"

for Y in 2022 2023 2024; do
  mkdir -p "data/v4_$Y"
  for M in 01 02 03 04 05 06 07 08 09 10 11 12; do
    Z="$A/Exness_BTCUSD_${Y}_${M}.zip"
    for attempt in 1 2 3; do
      curl -s -A "$UA" --max-time 1800 -o "$Z" "https://ticks.ex2archive.com/ticks/BTCUSD/$Y/$M/Exness_BTCUSD_${Y}_${M}.zip" && [ -s "$Z" ] && break
      sleep 30
    done
    if [ ! -s "$Z" ]; then log "WARN $Y-$M download failed"; continue; fi
    python exness_import2.py "data/v4_$Y" "$Z" --delete-zips >> "import_v4_$Y.log" 2>&1
    log "$Y-$M imported ($(tail -1 data/v4_$Y/import_report.txt | cut -c1-60))"
  done
  # the per-month runs each rewrote index/m1 with one month; rebuild the year's index + M1 from the monthly tick files
  python - "$Y" <<'PY'
import sys, os, json, glob, numpy as np
sys.path.insert(0, os.getcwd())
from compact_ticks import load_dir
from exness_import2 import to_m1
Y = sys.argv[1]; d = f"data/v4_{Y}"
idx = []
for f in sorted(glob.glob(f"{d}/ticks_*.npz")):
    key = os.path.basename(f)[6:-4]
    D = np.load(f)
    rep = [l for l in open(f"{d}/import_report.txt") if f"_{key[:4]}_{key[5:]}.zip" in l]
    sha = rep[-1].split("sha256 ")[1].split(" ")[0] if rep else ""
    t0 = None
    # t0 = day start of first tick: recover from the month key (files were written with t0 = first tick's day start)
    import datetime as dt
    first_day = dt.datetime(int(key[:4]), int(key[5:]), 1, tzinfo=dt.timezone.utc)
    # search the report line for the first timestamp to recover t0 exactly
    ft = rep[-1].split("| ")[2].split(" -> ")[0].strip() if rep else None
    if ft:
        fdt = dt.datetime.fromisoformat(ft).replace(tzinfo=dt.timezone.utc)
        t0 = int(fdt.timestamp() // 86400 * 86400 * 1000)
    else:
        t0 = int(first_day.timestamp() * 1000)
    n = int(len(D["t_off"]))
    idx.append(dict(key=key, t0_ms=t0, n=n, first_ms=t0 + int(D["t_off"][0]), last_ms=t0 + int(D["t_off"][-1]), zip=f"Exness_BTCUSD_{key[:4]}_{key[5:]}.zip", sha256=sha))
json.dump(idx, open(f"{d}/index.json", "w"), indent=1)
t, b, a = load_dir(d)
T, O, H, L, C, V, SP = to_m1(t, b, a)
np.savez_compressed(f"{d}/m1.npz", t=T, o=O, h=H, l=L, c=C, v=V, sp=SP)
print("rebuilt", d, len(idx), "months", len(t), "ticks", len(T), "bars")
PY
  echo "DONE" >> "data/v4_$Y/import_report.txt"
  log "STAGE v4-$Y import DONE"
  python e011_run_era.py "V4_$Y" "data/v4_$Y" > "run_V4_$Y.log" 2>&1
  log "STAGE V4_$Y era DONE: $(grep '2h gate (production) ALL' results_V4_$Y.txt | head -1)"
  python e011_control.py "V4_$Y" "data/v4_$Y" 1000 2 pess > "control_V4_${Y}_m1.log" 2>&1
  log "STAGE V4_$Y control DONE: $(head -1 control_V4_${Y}_m1.txt)"
  rm -f "data/v4_$Y"/ticks_*.npz
done
log "STAGE ALL DONE"
