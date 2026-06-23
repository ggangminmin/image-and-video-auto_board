#!/bin/bash
# 클론 후 1회 실행 → 리뷰 콘솔 스킬을 ~/.claude/skills 에 설치
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.claude/skills/mcp-review-console"
mkdir -p "$HOME/.claude/skills"
rm -rf "$DEST"
cp -R "$DIR/skills/mcp-review-console" "$DEST"
echo "✅ 설치 완료: $DEST"
echo "사용: Claude Code 에서  /mcp-review-console   또는  \"이 폴더 리뷰 콘솔 띄워줘 <폴더경로>\""
