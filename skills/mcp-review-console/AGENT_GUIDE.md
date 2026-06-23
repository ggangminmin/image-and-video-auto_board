# 🤖 큐 처리 가이드 (Claude 세션이 읽음)

콘솔(`app.py`)은 **UI·서버·큐**만 담당한다. **실제 이미지·영상 생성은 Higgsfield MCP 전용**이라
브라우저/파이썬이 직접 못 부른다 → **Claude 에이전트(이 세션)가 큐를 읽어 MCP로 처리**한다.

## 큐 항목 형태
콘솔에서 Enter로 보낸 요청은 `runtime/<mode>/revision_queue.jsonl` 에 한 줄씩 쌓인다.
- `{"type":"image","cut":"<id>","file":"<원본파일명>","request":"...","model":"nano_banana_pro|nano_banana_2|gpt_image_2","quality":"1k|2k|4k"}`
- `{"type":"video","cut":"<id>","file":"<원본파일명>","request":"...","duration":5,"quality":"std|pro|4k"}`
- `{"type":"batch_video","duration":5,"quality":"std"}`  ← [전체 영상으로 돌리기]
- `cut` = 파일 stem(확장자 제외), `file` = 미디어폴더 안 원본 파일명. `_idx` 는 qtool 이 붙여줌.

## 처리 루프
1. **워처 대기:** `python3 <skill>/qtool.py --mode <image|video> wait --timeout 3000`
   → 새 큐 줄을 JSON 배열로 출력(각 항목에 `_idx`). 없으면 `[]`. (백그라운드 Bash 로 띄우고, 완료 알림에 깨어나 처리)
2. 각 항목 처리 (`media_dir` = `runtime/<mode>/media_dir.txt`):
   - **공통:** 원본 `media_dir/<file>` 을 `media_upload`→PUT→`media_confirm`. 인물·일관성 ref 가 있으면 함께 업로드.
   - **`type:"image"`** — `generate_image({ model, prompt: 원장면설명 + " 수정: " + request (+ 프로젝트 강화상수),
       medias:[{role:"image",value:원본_id}(,refs)], resolution: quality, aspect_ratio: 원본비율 })`
     → 결과를 `media_dir/_revisions/<cut>_rev<k>.png` 로 저장(원본 보존).
     → `qtool result --mode image --cut <cut> --status done --src /media/_revisions/<cut>_rev<k>.png --idx <_idx>`
   - **`type:"video"`** — 모델 = **Kling 3.0(`kling3_0`)**.
     `generate_video({ model:"kling3_0", prompt: "No background music. SFX only. " + request, duration,
       medias:[{role:"start_image",value:원본_id}], aspect_ratio: 원본비율, params:{ mode: quality, sound:"off" } })`
     → mp4 를 영상폴더(예: `../_영상/<cut>.mp4`)로 저장.
     → **영상 메타 기록(영상 보기 페이지용):** `<영상폴더>/_video_meta.json` 에 해당 컷 항목 머지
       `{"<cut>": {"file":"<cut>.mp4","src":"<시작이미지 상대경로>","prompt":"<쓴 프롬프트>","duration":N,"quality":"std","ts":<unix초>}}`
       (페이지가 `ts` 증가를 감지해 dim 이미지를 영상으로 자동 교체. `src`는 다음 재생성의 시작이미지로도 쓰임.)
     → 이미지 콘솔에서 전환한 거면 `qtool result --mode image --cut <cut> --status video_done --idx <_idx>`
       (이미지 카드엔 "🎬 영상 생성됨" 칩만, 이미지 유지). 영상 콘솔 재수정이면 `--status done --src /media/<cut>_rev<k>.mp4`.
   - **`type:"batch_video"`** — 미디어폴더의 모든 카드(또는 확정본)를 위 Kling 절차로 일괄 생성(동시 8 한도 큐) → 영상폴더에 채움.
     완료 후 **영상 리뷰 콘솔 자동 기동**: `python3 app.py --mode video --media-dir <영상폴더> --port 8766`.
3. 진행 중에는 `qtool result --mode <m> --cut <cut> --status running --msg "..."`, 실패는 `--status error --msg "..."`.
   콘솔이 4초마다 `results.json` 을 폴링해 썸네일을 자동 교체한다.

## 규칙
- **동시 8개 한도**(Higgsfield) 준수. 초과분은 큐로.
- **재생성은 새 파일**(`_revisions/<cut>_rev<k>.*`) — 원본 절대 덮어쓰기 금지.
- 폴링·다운로드는 `job_status(sync:true)` → `curl -o` 한 단계.
- 프로젝트 고유 강화상수(있으면)는 매 프롬프트에 합쳐서 호출(예: 시네마틱 화각·역광·No-BGM 등).

## ★ 권한 함정 (중요)
백그라운드 워처/처리가 도구를 부르려면 `settings.local.json` allow 에
`Bash(python3 *)`·`Bash(curl *)`·`mcp__higgsfield__{generate_image,generate_video,media_upload,media_confirm,job_status}` 가 있어야 한다.
`cd ... && python3` 복합명령은 매칭이 깨지니 **qtool/app.py 는 절대경로 단독 호출**.
무활동이 길면 워처가 타임아웃 종료될 수 있음 → "워처 다시 켜줘" 로 재기동.
