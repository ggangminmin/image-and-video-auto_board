#!/bin/bash
# EMBERTHRONE 이미지 스토리보드 리뷰 콘솔 — 더블클릭 실행
cd "$(dirname "$0")"
python3 app.py --mode image --media-dir "../_스토리보드_20컷" --port 8765
