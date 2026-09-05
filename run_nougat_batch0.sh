#!/bin/sh
# Full Nougat OCR of batch 0 on the laptop GPU. Resumable: re-running skips pages already written.
# usage: sh run_nougat_batch0.sh   (logs to data/extracted/batch0/_nougat.log)
cd "$(dirname "$0")"
PY=./.venv-ocr/Scripts/python
LOG=data/extracted/batch0/_nougat.log
export PYTHONIOENCODING=utf-8
for pair in \
  "brownian-motion-and-stochastic-calculus-karatzas-shreve-2ed.pdf:karatzas-shreve" \
  "groups-and-symmetry-armstrong.pdf:armstrong" \
  "permutation-groups-dixon-mortimer.pdf:dixon-mortimer" \
  "rational-points-on-elliptic-curves-silverman-tate.pdf:silverman-tate" \
  "elementary-probability-theory-chung-aitsahlia-4ed.pdf:chung-aitsahlia" \
  "the-arithmetic-of-elliptic-curves-silverman-2ed.pdf:silverman-aec"; do
  f=${pair%%:*}; slug=${pair##*:}
  echo "=== $(date -u +%H:%M:%SZ) $slug ===" >> "$LOG"
  $PY nougat_ocr.py "corpus/batch0/$f" "data/extracted/batch0/$slug/nougat" --batch 8 2>&1 \
    | grep --line-buffered -v -i "warning\|Loading weights\|still open" >> "$LOG"
done
echo "=== $(date -u +%H:%M:%SZ) ALL DONE ===" >> "$LOG"
