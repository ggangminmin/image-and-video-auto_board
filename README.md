# image-and-video-auto_board

A local web "review board" for AI-generated images and videos. Click any card to
**revise its prompt and regenerate**, or **convert an image into a video** — wired so
Higgsfield MCP runs the actual generation as if connected live.

Browsers can't call MCP or write files from `file://`, so it uses a **3-tier bridge**:
**local server (`app.py`) + queue file + a Claude agent watcher.**

## Layout
- `skills/mcp-review-console/` — the **portable skill** (works on any image/video folder).
  `app.py` · `qtool.py` · `SKILL.md` · `AGENT_GUIDE.md`
- `examples/emberthrone/` — a real applied case (code + docs, media excluded)
  - `_review_console/` — a project-specific console instance
  - `docs/` — 35-cut edit sequence, 35-cut video prompts
  - `reference-analysis/` — reference-reel analysis (image / video prompts)

## Install (clone = ready to use)
```bash
git clone git@github.com:ggangminmin/image-and-video-auto_board.git
cd image-and-video-auto_board
./install.sh        # installs the skill into ~/.claude/skills
```
Then in Claude Code: `/mcp-review-console`, or just say "open a review console for this folder <path>".

## Keep the console always-on (so you can shut down and resume)
The console is a local process (not persisted across reboot), but **all state lives on disk**
(images, `_revisions/`, videos, `_video_meta.json`), so relaunching on the same folder shows the
identical gallery.

Start it now:
```bash
tools/start-console.sh <media-dir> [port] [video-dir]
# project-specific app instead of the generic skill:
AUTOBOARD_APP=/path/to/_review_console/app.py tools/start-console.sh <media-dir> 8765 <video-dir>
```

Auto-start at login (macOS launchd) — survives reboot, KeepAlive restarts it if it dies:
```bash
tools/autostart-macos.sh install <media-dir> [port] [video-dir]   # register
tools/autostart-macos.sh uninstall                                # remove
# project-specific app:
AUTOBOARD_APP=/path/to/_review_console/app.py tools/autostart-macos.sh install <media-dir> 8765 <video-dir>
```

> The auto-started console serves the **browser view** of your saved work. The **auto-processing**
> (actually generating images/videos) still needs a live Claude session running the watcher —
> a browser alone can't call MCP. So after a reboot: the page is back instantly; to generate again,
> ask Claude to relaunch the watcher.

## Features
- Auto-scans a folder into a card gallery. Per card: **[Edit image  /  Convert to video]**
  (recommended motion prompt auto-filled, Kling 3.0).
- Auto-growing prompt box; lightbox preview (close with **ESC**).
- Bottom selection bar: **[Copy selected paths] · [Edit selected images] · [Make videos from selected]**.
- **Videos page (`/videos`)**: shows every cut — generated ones play with editable prompt + **Regenerate**;
  not-yet-generated ones show the image **dimmed** + a **Make video** button.
- Video metadata (`_video_meta.json`) records each clip's prompt and auto-refreshes the page.
- Originals are preserved (revisions go to `_revisions/`). Image/video runtimes are isolated.

Routes: `/` (console) · `/results` · `/media/<f>` · `/videos` · `/vmedia/<f>` · `/vmeta`
POST `/revise`.

## Requirements
- macOS / Python 3.9+ (standard library only)
- Higgsfield MCP connection (image/video generation) · optional ElevenLabs (narration)

## How it works (queue bridge)
1. A card submit POSTs `/revise` → appended to `runtime/<mode>/revision_queue.jsonl`.
2. The Claude agent reads the queue (`qtool.py wait`) and runs the matching Higgsfield MCP
   tool (`generate_image` / `generate_video` = Kling 3.0, No-BGM / SFX-only).
3. The result is written back; the console polls every 4s and swaps the thumbnail.

See `skills/mcp-review-console/AGENT_GUIDE.md` for the exact processing recipe.
