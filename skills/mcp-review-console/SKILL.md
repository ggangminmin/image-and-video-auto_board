---
name: mcp-review-console
description: Spin up a local interactive web console to review a folder of AI-generated images (or videos) as a gallery, then click any card to revise its prompt and regenerate, or convert an image into a video — wired so Higgsfield MCP runs the actual generation as if connected live. Use when the user wants an interactive review/revision UI over generated media, wants to "click an image and fix it", iterate on a storyboard/batch, convert images to video (Kling), or asks to bring up "the console" / "리뷰 콘솔" / "수정 콘솔" for a set of generated cuts. Works with any folder of images — not tied to any one project.
---

# MCP Review Console (인터랙티브 리뷰·수정 콘솔)

**어떤 이미지/영상 폴더든** 로컬 웹 갤러리로 띄우고, 카드를 클릭하면 **프롬프트 수정 → 즉시 재생성**,
또는 **이미지 → 영상 전환**까지 — 마치 브라우저에 Higgsfield MCP가 바로 붙은 것처럼 동작하게 하는 스킬.

브라우저 `file://` 는 MCP·파일쓰기가 막혀 있으므로 **3단 브리지**로 잇는다:
**[로컬서버(app.py) + 큐파일 + 에이전트 워처(이 Claude 세션)]**.
카드 Enter → `/revise` POST → `revision_queue.jsonl` 적재 → **Claude가 큐를 읽어 MCP로 재생성** →
`results.json` 갱신 → 콘솔이 4초마다 폴링해 썸네일 자동 교체.

## 무엇이 되나 (핵심 기능)
- 폴더 **자동 스캔** → 그 안의 이미지(또는 영상)를 16:9 카드 갤러리로 전부 표시 (스토리 하드코딩 없음).
- 카드 선택 → **✎ 이미지 수정**(모델 nano_banana_pro/nano_banana_2/gpt_image_2 + 화질 1k/2k/4k) 또는
  **🎬 영상으로 전환**(누르면 **추천 모션 프롬프트 자동입력** + 초수 4–10s + 모드 std/pro/4k, **Kling 3.0**).
- 입력창은 내용따라 **자동 높이확장**. 썸네일 클릭=확대(라이트박스), **ESC로 닫기**.
- 상단 **[선택 카드 일괄 수정]** · **[🎞️ 영상 보기]** · **[전체 영상으로 돌리기]**(batch_video).
- **하단 선택 바**(카드 1개+ 선택 시): `N개 선택` + 파일목록 + **[전체선택]·[선택해제]·[선택 목록 복사](절대경로 클립보드)·[✎ 선택 이미지 수정](공통지시 일괄)·[🎬 선택 영상화](선택분 일괄 Kling)**.
- **영상 보기 페이지(`/videos`)**: 전체 카드 표시 — 영상 있는 컷은 **재생+프롬프트 표시·수정→[재생성]**, 아직 없는 컷은 **이미지 흐리게(dim)+추천프롬프트+[영상화]**. 생성 완료 시 dim→영상 자동교체(4초 폴링). 라우트: `/videos`·`/vmedia/<f>`·`/vmeta`.
- **영상 메타**(`<영상폴더>/_video_meta.json`): 컷별 `{file, src(시작이미지), prompt, duration, quality, ts}`. 에이전트가 영상 생성 시 기록 → 페이지가 프롬프트 표시·자동갱신.
- 이미지/영상 **모드별 런타임 분리**(`runtime/image`·`runtime/video`)로 큐 충돌 방지.

## 파일 (이 스킬 폴더)
- `app.py` — 콘솔 서버(표준 라이브러리만). `--mode image|video --media-dir <폴더> --port <p> [--brand 텍스트]`.
- `qtool.py` — 큐 헬퍼: `--mode <m> wait|result|offset|status`.
- `AGENT_GUIDE.md` — 큐를 MCP로 처리하는 상세 레시피(반드시 따른다).

## 실행 절차 (에이전트가 할 일)
1. **연결 확인:** Higgsfield MCP `balance` 정상인지. 안 되면 `authenticate`→로그인→`complete_authentication`.
2. **권한:** 프로젝트 `.claude/settings.local.json` allow 에 `Bash(python3 *)`·`Bash(curl *)`·
   `mcp__higgsfield__{generate_image,generate_video,media_upload,media_confirm,job_status}` 가 있는지 확인(없으면 추가 안내).
3. **콘솔 기동(백그라운드):**
   ```bash
   python3 "<이 스킬>/app.py" --mode image --media-dir "<이미지폴더 절대경로>" --port 8765 > "<스킬>/runtime/console.log" 2>&1 &
   ```
   `curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/` 로 200 확인 후 `open http://localhost:8765/`.
4. **워처 가동(백그라운드):** `python3 "<스킬>/qtool.py" --mode image wait --timeout 3000` 을 백그라운드 Bash 로.
   완료 알림에 깨어나면 큐를 **AGENT_GUIDE.md** 절차대로 처리(업로드→generate→다운로드→`qtool result`)하고, 다시 `wait` 재기동.
5. **[전체 영상으로 돌리기]** 가 오면 batch_video 처리 후 **영상 콘솔**을 `--mode video --media-dir <영상폴더> --port 8766` 으로 띄운다.

## 선택: 카드 라벨·추천 프롬프트 보강
미디어 폴더에 `_console_meta.json` 을 두면 라벨/섹션/추천 모션 프롬프트를 채울 수 있다(없으면 파일명 기반 + 기본 프롬프트):
```json
{
  "title": "내 프로젝트",
  "subtitle": "Interactive MCP Review",
  "cards": {
    "cut01_intro": {"label":"오프닝 — 폐허 와이드", "section":"1막", "rec_vid":"No BGM, SFX only. Slow crane-up, drifting embers."}
  }
}
```

## 규칙
- **원본 보존** — 재생성은 항상 `_revisions/<cut>_rev<k>.*` 새 파일. 절대 덮어쓰기 금지.
- **동시 8개 한도** 준수, 초과분 큐.
- **영상 = Kling 3.0(`kling3_0`)**, `params:{mode:화질, sound:"off"}`(무음=No-BGM, BGM/내레이션은 후반 합성).
- `cd ... && python3` 복합명령 금지(권한 매칭 깨짐) — **절대경로 단독 호출**.
- 자세한 처리 레시피는 항상 **AGENT_GUIDE.md** 를 따른다.

> 레퍼런스 구현: EMBERTHRONE 게임 시네마틱(`이용가이드_공유용/EMBERTHRONE_게임시네마틱/_review_console/`)이 이 콘솔로 20컷을 리뷰·영상화한 첫 사례다.
