# Queue processing guide (read by the Claude session)

The console (`app.py`) only owns the **UI, server and queue**. The actual image/video
generation is **MCP-only**, which a browser/Python can't call — so **the Claude agent
(this session) reads the queue and runs MCP.**

## Queue item shapes
Each card submit lands one JSON line in `runtime/<mode>/revision_queue.jsonl`:
- `{"type":"image","cut":"<id>","file":"<source filename>","src":"<rel path>","request":"...","model":"nano_banana_pro|nano_banana_2|gpt_image_2","quality":"1k|2k|4k"}`
- `{"type":"video","cut":"<id>","file":"<source>","src":"<start image rel path>","request":"...","duration":5,"quality":"std|pro|4k"}`
- `{"type":"batch_video","duration":5,"quality":"std"}`  ← [Make all into videos]
- `cut` = filename stem; `src`/`file` = the source media relative to the media dir; `_idx` is added by qtool.

## Processing loop
1. **Watch:** `python3 <skill>/qtool.py --mode <image|video> wait --timeout 3000`
   → prints new queue lines as a JSON array (each with `_idx`); `[]` on timeout. Run it as a background Bash
   and wake on its completion to process, then relaunch.
2. Process each item (`media_dir` = `runtime/<mode>/media_dir.txt`):
   - **Common:** `media_upload` → PUT bytes → `media_confirm` on `media_dir/<src or file>`. Add identity/reference
     images too if the project needs character consistency.
   - **`type:"image"`** — `generate_image({ model, prompt: original scene + " revise: " + request (+ project enhance constants),
       medias:[{role:"image",value:source_id}(,refs)], resolution: quality, aspect_ratio: source ratio })`
     → save to `media_dir/_revisions/<cut>_rev<k>.png` (keep the original).
     → `qtool result --mode image --cut <cut> --status done --src /media/_revisions/<cut>_rev<k>.png --idx <_idx>`
   - **`type:"video"`** — model = **Kling 3.0 (`kling3_0`)**.
     `generate_video({ model:"kling3_0", prompt: "No background music. SFX only. " + request, duration,
       medias:[{role:"start_image",value:source_id}], aspect_ratio: source ratio, params:{ mode: quality, sound:"off" } })`
     → save the mp4 to the video folder (e.g. `../_영상/<cut>.mp4`).
     → **Write video metadata (for the Videos page):** merge into `<video-folder>/_video_meta.json`
       `{"<cut>": {"file":"<cut>.mp4","src":"<start image rel path>","prompt":"<prompt used>","duration":N,"quality":"std","ts":<unix sec>}}`
       (the page watches `ts` increasing to swap the dim image for the video; `src` is reused as the next regenerate's start image).
     → If triggered from the image console: `qtool result --mode image --cut <cut> --status video_done --idx <_idx>`
       (image card keeps the image, just shows a "video generated" chip). If re-revising in the video console:
       `--status done --src /media/<cut>_rev<k>.mp4`.
   - **`type:"batch_video"`** — [Make all into videos]: run every cut image through the Kling step above
     (8-concurrent cap, queue overflow) → fill the video folder. Then auto-open the **video review console**:
     `python3 app.py --mode video --media-dir <video folder> --port 8766`.
3. While running: `qtool result --mode <m> --cut <cut> --status running --msg "..."`; on failure `--status error --msg "..."`.
   The console polls `results.json` every 4s and swaps thumbnails.

## Rules
- **8-concurrent cap** (Higgsfield); queue the overflow.
- **Regenerations are new files** (`_revisions/<cut>_rev<k>.*`) — never overwrite the original.
- Poll/download via `job_status(sync:true)` → `curl -o`.
- Inject project enhancement constants (cinematic framing, backlight, No-BGM, etc.) on every prompt if the project defines them.

## ★ Permission trap (important)
For the background watcher/processing to call tools, `settings.local.json` allow must include
`Bash(python3 *)`, `Bash(curl *)`, and `mcp__higgsfield__{generate_image,generate_video,media_upload,media_confirm,job_status}`.
`cd ... && python3` compound commands break matching — call `qtool`/`app.py` by **absolute path**.
A long idle may time out the watcher → just relaunch it.
