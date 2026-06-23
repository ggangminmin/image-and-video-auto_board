---
name: mcp-review-console
description: Spin up a local interactive web console to review a folder of AI-generated images (or videos) as a gallery, then click any card to revise its prompt and regenerate, or convert an image into a video — wired so Higgsfield MCP runs the actual generation as if connected live. Use when the user wants an interactive review/revision UI over generated media, wants to "click an image and fix it", iterate on a storyboard/batch, convert images to video (Kling), or asks to bring up "the console" / "리뷰 콘솔" / "수정 콘솔" for a set of generated cuts. Works with any folder of images — not tied to any one project.
---

# MCP Review Console

Open **any image/video folder** as a local web gallery, then click a card to
**revise its prompt and regenerate**, or **convert an image into a video** — as if a
Higgsfield MCP were attached directly to the browser.

Because a browser `file://` page cannot call MCP or write files, this uses a
**3-tier bridge**: **local server (`app.py`) + queue file + a Claude agent watcher.**
Card → Enter → POST `/revise` → appended to `revision_queue.jsonl` → **Claude reads the
queue and regenerates via MCP** → updates `results.json` → the console polls every 4s and
swaps the thumbnail.

## What it does
- **Auto-scans** the folder and shows every image (or video) as a 16:9 card gallery (no hardcoded story).
- Per card: **[Edit image]** (model nano_banana_pro / nano_banana_2 / gpt_image_2 + quality 1k/2k/4k) or
  **[Convert to video]** (auto-fills a recommended motion prompt + duration 4–10s + mode std/pro/4k, **Kling 3.0**).
- Auto-growing prompt box. Thumbnail click = lightbox (close with **ESC**).
- Header: **[Batch edit selected]** · **[🎞️ Videos]** · **[Make all into videos]** (batch_video).
- **Bottom selection bar** (when ≥1 card selected): count + file list +
  **[Select all] · [Clear] · [Copy selected paths] (absolute paths to clipboard) ·
  [Edit selected images] (one shared instruction) · [Make videos from selected] (batch Kling)**.
- **Videos page (`/videos`)**: shows every card — generated cuts **play + show/edit the prompt → [Regenerate]**,
  not-yet-generated cuts show the image **dimmed + recommended prompt + [Make video]**. When a clip finishes
  the dim image is auto-replaced by the video (4s polling). Routes: `/videos` · `/vmedia/<f>` · `/vmeta`.
- **Video metadata** (`<video-folder>/_video_meta.json`): per cut `{file, src (start image), prompt, duration, quality, ts}`.
  The agent writes it on each video render so the page can show the prompt and auto-refresh.
- Image/video **runtimes are isolated** (`runtime/image` · `runtime/video`) so the two consoles never share a queue.

## Files (this skill folder)
- `app.py` — console server (standard library only). `--mode image|video --media-dir <folder> --port <p> [--brand T] [--video-dir D]`.
- `qtool.py` — queue helper: `--mode <m> wait|result|offset|status`.
- `AGENT_GUIDE.md` — exact recipe for processing the queue with MCP (follow it).

## Run procedure (what the agent does)
1. **Check connection:** Higgsfield MCP `balance` OK? If not, `authenticate` → log in → `complete_authentication`.
2. **Permissions:** project `.claude/settings.local.json` allow-list must contain `Bash(python3 *)`, `Bash(curl *)`,
   and `mcp__higgsfield__{generate_image,generate_video,media_upload,media_confirm,job_status}` (add if missing).
3. **Launch the console (background):**
   ```bash
   python3 "<skill>/app.py" --mode image --media-dir "<absolute image folder>" --port 8765 > "<skill>/runtime/console.log" 2>&1 &
   ```
   Confirm 200 via `curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/`, then `open http://localhost:8765/`.
4. **Start the watcher (background):** `python3 "<skill>/qtool.py" --mode image wait --timeout 3000` as a background Bash.
   On the completion notification, process the queue per **AGENT_GUIDE.md** (upload → generate → download → `qtool result`),
   then relaunch `wait`.
5. **[Make all into videos]** → process batch_video, then open the **video console** with `--mode video --media-dir <video folder> --port 8766`.

## Optional: enrich card labels / recommended prompts
Drop a `_console_meta.json` in the media folder to set labels / sections / recommended motion prompts
(otherwise labels come from filenames and a generic prompt is used):
```json
{
  "title": "My Project",
  "subtitle": "Interactive MCP Review",
  "cards": {
    "cut01_intro": {"label": "Opening — ruins wide", "section": "Act 1", "rec_vid": "No BGM, SFX only. Slow crane-up, drifting embers."}
  }
}
```

## Rules
- **Preserve originals** — regenerations always go to `_revisions/<cut>_rev<k>.*` as new files. Never overwrite.
- **8-concurrent cap** (Higgsfield); queue the overflow.
- **Video = Kling 3.0 (`kling3_0`)**, `params:{mode: quality, sound:"off"}` (silent = No-BGM; BGM/VO added in post).
- No `cd ... && python3` compound commands (breaks permission matching) — call scripts by **absolute path**.
- Always follow **AGENT_GUIDE.md** for the processing recipe.

> Reference implementation: the EMBERTHRONE game cinematic console first used this to review and animate 35 cuts.
