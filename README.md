# image-and-video-auto_board

이미지/영상을 **로컬 웹 콘솔에서 클릭해 수정·재생성하고, 이미지→영상으로 전환**까지
Higgsfield MCP 가 바로 붙은 것처럼 처리하는 자동 리뷰 보드.

브라우저 `file://` 는 MCP·파일쓰기가 막혀 있으므로 **3단 브리지**로 잇는다:
**[로컬서버(app.py) + 큐파일 + Claude 에이전트 워처]**.

## 구성
- `skills/mcp-review-console/` — **범용 스킬** (어떤 이미지/영상 폴더든 동작). app.py·qtool.py·SKILL.md·AGENT_GUIDE.md
- `examples/emberthrone/` — 실제 적용 사례(코드+문서, 미디어 제외)
  - `_review_console/` — 프로젝트 전용 콘솔 인스턴스
  - `docs/` — 편집 시퀀스 35컷, 영상 프롬프트 35컷
  - `reference-analysis/` — 레퍼런스 릴스 분석(이미지/영상 프롬프트)

## 설치 (클론하면 바로 세팅)
```bash
git clone git@github.com:ggangminmin/image-and-video-auto_board.git
cd image-and-video-auto_board
./install.sh        # 스킬을 ~/.claude/skills 에 설치
```
이후 Claude Code 에서 `/mcp-review-console` 또는 "이 폴더 리뷰 콘솔 띄워줘 <폴더경로>".

## 주요 기능
- 폴더 자동 스캔 → 카드 갤러리. 카드별 **[✎ 이미지 수정 ↔ 🎬 영상으로 전환]**(추천 모션 프롬프트 자동입력, Kling 3.0)
- 입력창 자동확장 · 라이트박스(ESC 닫기)
- 하단 선택 바: **[선택 목록 복사 · ✎ 선택 이미지 수정 · 🎬 선택 영상화]**
- **[🎞️ 영상 보기] 페이지**(`/videos`): 전체 카드 — 영상 있으면 재생/프롬프트 수정·재생성, 없으면 이미지(dim)+[영상화]
- 영상 메타(`_video_meta.json`)로 프롬프트 기록·자동 갱신
- 원본 보존(재생성은 `_revisions/` 새 파일), 이미지/영상 런타임 분리

## 요구사항
- macOS / Python 3.9+ (표준 라이브러리만)
- Higgsfield MCP 연결(이미지/영상 생성) · (선택) ElevenLabs(내레이션)
