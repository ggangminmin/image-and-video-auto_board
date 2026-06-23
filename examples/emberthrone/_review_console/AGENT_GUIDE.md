# 🤖 에이전트 큐 처리 가이드 (Claude 세션이 읽음)

콘솔(app.py)은 **UI·서버·큐**만 담당한다. **실제 이미지·영상 생성은 Higgsfield MCP 전용**이라
브라우저/파이썬이 직접 못 부른다 → **Claude 에이전트(이 세션)가 큐를 읽어 MCP로 처리**한다.

## 트리거
사용자가 콘솔에서 Enter로 보낸 요청은 `runtime/revision_queue.jsonl` 에 한 줄씩 쌓인다.
사용자가 **"리뷰 큐 처리해줘"** 라고 하면 아래 루프를 수행한다.

## 처리 루프
1. `runtime/.agent_offset`(이미 처리한 줄 수)부터 `runtime/revision_queue.jsonl` 의 **새 줄만** 읽는다.
2. 각 항목 처리:
   - **`type:"image"`** `{cut, request, model, quality}` :
     - 원본 `MEDIA_DIR/cut{cut}_*.png` 를 `media_upload`→`media_confirm`
     - 캐릭터 일관성용 캐릭터시트 ref(`../01_캐릭터시트/view_front.png` 등)도 함께 업로드(인물 컷이면)
     - `generate_image({ model, prompt: 원장면 + "수정: "+request + 규칙0[A] + GAME_IMG_ENHANCE,
                         medias:[{role:"image",value:원본_media_id},{role:"image",value:ref_media_id}],
                         resolution: quality(1k/2k/4k), aspect_ratio:"16:9" })`
     - 결과를 `MEDIA_DIR/_revisions/cut{cut}_rev{k}.png` 로 다운로드
   - **`type:"video"`** `{cut, request, duration, quality}` — **모델 = Kling 3.0(`kling3_0`)**:
     - 원본 컷 이미지를 `media_upload`→`media_confirm`
     - `generate_video({ model:"kling3_0", prompt: 규칙0[B] No-BGM·SFX only + request, duration,
                         medias:[{role:"start_image",value:media_id}], aspect_ratio:"16:9",
                         params: { mode: quality(std/pro/4k), sound:"off" } })`   # sound:off = 무음(No-BGM, SFX/BGM은 후반 합성)
     - mp4를 `../_영상/cut{NN}.mp4`(단일 전환) 로 다운로드 → `result --status video_done --idx`(이미지 카드엔 "🎬 영상 생성됨" 칩만, 이미지 유지)
   - **`type:"batch_video"`** `{duration, quality}` : [전체 영상으로 돌리기].
     `_신규생성/`의 모든 cut 이미지를 위 Kling 절차로 일괄 생성(동시 8 한도 큐) → `../_영상/cut{NN}.mp4`
3. 항목 완료 시 `runtime/results.json` 갱신:
   ```json
   { "01": { "status":"done", "src":"/media/_revisions/cut01_rev1.png", "ts":1782177000 } }
   ```
   (영상 batch는 `src":"/media/cut01.mp4"`). 콘솔이 4초마다 폴링해 썸네일 자동 교체.
   처리 중에는 `{"status":"running","msg":"..."}`, 실패는 `{"status":"error","msg":"..."}`.
4. 처리한 줄 수를 `runtime/.agent_offset` 에 저장.

## 규칙
- **동시 8개 한도**(Higgsfield) 준수. 초과분은 큐로.
- **재생성은 새 파일**(`_revisions/`) — 원본 보존(절대 규칙).
- 폴링·다운로드가 길면 **백그라운드 에이전트**에 위임.
- 규칙0(이미지 화각/역광/네거티브필, 영상 No-BGM·SFX only) + GAME_IMG/VID_ENHANCE 항상 주입.
- 인물 일관성: 영웅 컷은 `../01_캐릭터시트/view_front.png`+`view_34.png` ref 유지.

## batch_video 완료 후
모든 컷 mp4가 `../_영상/`에 차면 **영상 리뷰 콘솔을 자동 팝업**:
`python3 app.py --mode video --media-dir "../_영상" --port 8766`
(또는 `run_video.command` 더블클릭) → 같은 디자인으로 영상 미리보기 + 컷별 Seedance 재수정.
