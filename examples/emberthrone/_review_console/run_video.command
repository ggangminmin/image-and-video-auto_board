#!/bin/bash
# EMBERTHRONE 영상 리뷰 콘솔 — 더블클릭 실행
cd "$(dirname "$0")"
python3 app.py --mode video --media-dir "../_영상" --port 8766
