#!/usr/bin/env bash
# E020 blind era B1: download + import the 2021 Exness BTCUSD archive month by month,
# keep only M1 bars (bid OHLC + mean spread) and the import report; delete zips and
# compact ticks immediately (disk has ~2 GB free). Run ONLY after the E020 freeze commit.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/data_2021"
IMP="$HERE/../e011/exness_import2.py"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) research-import"
mkdir -p "$OUT"
for M in 01 02 03 04 05 06 07 08 09 10 11 12; do
  Z="$OUT/Exness_BTCUSD_2021_$M.zip"
  if [ -f "$OUT/m1_2021_$M.npz" ]; then echo "month $M already done"; continue; fi
  for try in 1 2 3; do
    curl -s -A "$UA" --max-time 1800 -o "$Z" "https://ticks.ex2archive.com/ticks/BTCUSD/2021/$M/Exness_BTCUSD_2021_$M.zip" && [ -s "$Z" ] && break
    sleep 20
  done
  [ -s "$Z" ] || { echo "DOWNLOAD FAILED 2021-$M"; continue; }
  python "$IMP" "$OUT" "$Z" --delete-zips || { echo "IMPORT FAILED 2021-$M"; continue; }
  mv "$OUT/m1.npz" "$OUT/m1_2021_$M.npz"
  rm -f "$OUT"/ticks_2021_*.npz
  echo "month $M done $(date -u +%H:%M)"
done
python - <<'EOF'
import numpy as np, glob, os
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
EOF
echo "IMPORT 2021 DONE"
