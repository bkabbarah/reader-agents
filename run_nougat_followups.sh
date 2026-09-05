#!/bin/sh
# GPU follow-ups after run_nougat_batch0.sh reports ALL DONE:
#  1. fill any page a book is still missing (resumable pass over all six books)
#  2. redo the Karatzas-Shreve pages that hit the 3072-token cap, at 4096
#  3. OCR Trench (LaTeX truth available) so md_chunk recall can be scored against data/extracted/trench-ra/
cd "$(dirname "$0")"
PY=./.venv-ocr/Scripts/python
LOG=data/extracted/batch0/_nougat.log
export PYTHONIOENCODING=utf-8
echo "=== $(date -u +%H:%M:%SZ) followups: fill missing pages ===" >> "$LOG"
sh run_nougat_batch0.sh
echo "=== $(date -u +%H:%M:%SZ) followups: K&S truncated pages at 4096 tokens ===" >> "$LOG"
$PY nougat_ocr.py corpus/batch0/brownian-motion-and-stochastic-calculus-karatzas-shreve-2ed.pdf data/extracted/batch0/karatzas-shreve/nougat \
   --only 134,256,343,412,422,454,468,473,480,481,488,489 --max-tokens 4096 --batch 4 2>&1 \
   | grep --line-buffered -v -i "warning\|Loading weights\|still open" >> "$LOG"
echo "=== $(date -u +%H:%M:%SZ) followups: trench-ra (recall test vs LaTeX truth) ===" >> "$LOG"
mkdir -p data/extracted/trench-ra/nougat
$PY nougat_ocr.py corpus/pdf/trench-ra.pdf data/extracted/trench-ra/nougat --batch 8 2>&1 \
   | grep --line-buffered -v -i "warning\|Loading weights\|still open" >> "$LOG"
echo "=== $(date -u +%H:%M:%SZ) FOLLOWUPS DONE ===" >> "$LOG"
