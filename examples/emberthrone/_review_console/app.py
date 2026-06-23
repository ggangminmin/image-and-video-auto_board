# -*- coding: utf-8 -*-
"""
EMBERTHRONE 리뷰 콘솔 (표준 라이브러리만, 파이썬 3.9+).

이미지/영상 스토리보드를 POC 갤러리 디자인으로 띄우고,
카드를 선택 → 모델/화질(이미지) · 초수/화질(영상)을 고르고 → 수정요청 입력 → Enter 하면
runtime/revision_queue.jsonl 에 한 줄 쌓인다.
실제 재생성은 Claude 에이전트가 큐를 읽어 Higgsfield MCP(nano_banana_2/gpt_image_2 · seedance_2_0)로 처리하고
runtime/results.json 을 갱신 → 콘솔이 4초마다 폴링해 썸네일을 자동 교체한다.

브라우저 file:// 는 MCP·파일쓰기가 막혀 있어 [로컬서버 + 큐파일 + 에이전트 워처] 3단 브리지를 쓴다.

실행:
  python3 app.py --mode image --media-dir ../_신규생성 --port 8765
  python3 app.py --mode video --media-dir ../_영상     --port 8766
"""
import argparse, http.server, json, os, re, mimetypes, urllib.parse, webbrowser, threading, time
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# 컷 정의 (POC 갤러리와 동일) — 번호·막·한글 라벨
CUTS = [
    # ── 1막 · 몰락 (레퍼런스 리듬: 빠른 도입 비트) ──
    {"n": "N1", "act": "1막 · 몰락",   "ko": "🎬 회랑 글라이딩 POV (CM01)"},
    {"n": "01", "act": "1막 · 몰락",   "ko": "불타는 왕국 스카이라인, 잿가루 상승"},
    {"n": "01b","act": "1막 · 몰락",   "ko": "🎞️ 인서트 — 잿불 위 피어오르는 연기"},
    {"n": "02", "act": "1막 · 몰락",   "ko": "폐허가 된 왕좌 홀, 찢긴 깃발"},
    {"n": "03b","act": "1막 · 몰락",   "ko": "🎞️ 인서트 — 빛줄기 속 흩날리는 재"},
    {"n": "03", "act": "1막 · 몰락",   "ko": "잿더미에 묻힌 기사 건틀릿"},
    {"n": "04", "act": "1막 · 몰락",   "ko": "부러진 장검을 쥐는 영웅의 손"},
    {"n": "08b","act": "1막 · 몰락",   "ko": "🎞️ 인서트 — 칼자루를 쥔 흉터 난 손"},
    {"n": "05", "act": "1막 · 몰락",   "ko": "폐허 속 무릎 꿇은 영웅 (실루엣)"},
    {"n": "05b","act": "1막 · 몰락",   "ko": "🎞️ 인서트 — 갈라진 땅의 용암 균열"},
    {"n": "N3", "act": "1막 · 몰락",   "ko": "🎬 광각더치 — 작은 영웅 vs 거대 군세 (CM07)"},
    {"n": "06", "act": "1막 · 몰락",   "ko": "능선 위 적군 · 어둠의 지휘관"},
    # ── 2막 · 각성 (무브 다양 빌드업) ──
    {"n": "07", "act": "2막 · 각성",   "ko": "그늘 속 영웅의 눈, 잿불 반사"},
    {"n": "07b","act": "2막 · 각성",   "ko": "🎞️ 인서트 — 영웅의 하관·다문 입 (결기)"},
    {"n": "08", "act": "2막 · 각성",   "ko": "🗣️ 불빛 속 일어서며 명대사 발화 (립싱크)"},
    {"n": "N2", "act": "2막 · 각성",   "ko": "🎬 잿불 스파크 매크로 (CM04 트랜지션)"},
    {"n": "09", "act": "2막 · 각성",   "ko": "재단조된 검을 들어올림"},
    {"n": "10", "act": "2막 · 각성",   "ko": "검에 잿불 마법 점화 (룬 발광)"},
    {"n": "11", "act": "2막 · 각성",   "ko": "망토 휘날리며 돌아섬"},
    {"n": "N5", "act": "2막 · 각성",   "ko": "🎬 로우 POV — 잿가루 들판 돌진 (CM09)"},
    {"n": "12", "act": "2막 · 각성",   "ko": "전장으로 질주 (모션블러)"},
    {"n": "N4", "act": "2막 · 각성",   "ko": "🎬 탑다운 드론 — 잿더미 원 속 영웅 (CM08)"},
    {"n": "13", "act": "2막 · 각성",   "ko": "마법 / 화력 폭발"},
    # ── 3막 · 결전 → 승리 (CM13 초고속 몽타주 → CM15 정지) ──
    {"n": "14", "act": "3막 · 결전",   "ko": "적진과 충돌 · 임팩트"},
    {"n": "N7", "act": "3막 · 결전",   "ko": "🎞️ 칼날 스파크 매크로 (CM13)"},
    {"n": "15", "act": "3막 · 결전",   "ko": "전투 중 결연한 표정 (재·상처)"},
    {"n": "N8", "act": "3막 · 결전",   "ko": "🎞️ 영웅 눈 섬광 (분노)"},
    {"n": "16", "act": "3막 · 결전",   "ko": "결정타 내려치기"},
    {"n": "N9", "act": "3막 · 결전",   "ko": "🎞️ 잿더미 내딛는 부츠 매크로"},
    {"n": "17", "act": "3막 · 결전",   "ko": "적 지휘관 쓰러짐 · 충격파"},
    {"n": "N10","act": "3막 · 결전",   "ko": "🎞️ 임팩트 충격파 매크로"},
    {"n": "18", "act": "3막 · 승리",   "ko": "폐허 정상에 선 영웅 (부상)"},
    {"n": "19", "act": "3막 · 승리",   "ko": "불타는 왕좌 앞 영웅 + 용 (안개)"},
    {"n": "N12","act": "3막 · 승리",   "ko": "🎬 용을 향해 글라이딩 업 (CM01)"},
    {"n": "20", "act": "3막 · 타이틀", "ko": "EMBERTHRONE 타이틀 카드"},
]

# 컷별 추천 영상(모션) 프롬프트 — 영상 페이지 '미생성 컷' 자동입력용 (콘솔 JS REC_VID와 동일)
REC_VID_PY = {
 "N1": "No background music. NO BGM. SFX only — fire crackle, ember whoosh. FAST dolly-in glide racing down the burning ruined corridor toward the fiery vanishing point, embers and ash streaking past, slight dutch roll, heavy motion blur.",
 "01": "No background music. NO BGM. SFX only — distant fire roar, wind. Slow DOLLY-OUT + crane-up revealing the burning kingdom skyline, ember motes rising, smoke columns drifting.",
 "01b": "No background music. NO BGM. SFX only — soft ember sizzle. Slow macro DOLLY-IN on smoke curling off glowing embers, sparks floating up, shallow rack focus.",
 "02": "No background music. NO BGM. SFX only — falling debris, faint wind. High crane-down ARC sweeping over the ruined throne hall, ash falling through light shafts, tattered banners swaying.",
 "03b": "No background music. NO BGM. SFX only — airy hush. Slow ARC through a hard god-ray as fine ash drifts and glints, dust motes passing the beam.",
 "03": "No background music. NO BGM. SFX only — metal tick, ember pop. FAST macro DOLLY-IN to the half-buried gauntlet in the ash, embers pulsing, sharp rack focus.",
 "04": "No background music. NO BGM. SFX only — leather creak, grip tighten. Quick DOLLY-IN as the steel-gauntleted hand closes on the broken hilt, embers swirling up.",
 "08b": "No background music. NO BGM. SFX only — knuckle creak. Tight ARC orbiting around the scarred hand gripping the hilt, knuckles tightening, ember rim flicker.",
 "05": "No background music. NO BGM. SFX only — low wind, embers. Slow ARC orbit around the kneeling rim-lit silhouette, cloak swaying, smoke drifting.",
 "05b": "No background music. NO BGM. SFX only — deep molten rumble, crackle. Slow macro DOLLY-IN along the glowing lava crack, heat shimmer, rising embers.",
 "N3": "No background music. NO BGM. SFX only — ominous wind, low stomps (no music). FAST ARC swing + slow DOLLY-OUT revealing the colossal dark army and warlord looming over the tiny hero, heavy wide-angle distortion.",
 "06": "No background music. NO BGM. SFX only — torch flutter, low murmur. Slow parallax ARC across the ridgeline horde, torches flickering, ragged banners waving.",
 "07": "No background music. NO BGM. SFX only — faint ember crackle. FAST DOLLY-IN to the hero's eye, ember fire flaring in the iris, ash passing.",
 "07b": "No background music. NO BGM. SFX only — slow breath. Subtle DOLLY-IN on the set jaw and mouth, visible breath, ember rim light flickering.",
 "08": "No background music. NO BGM. SFX only — breath, distant fire. Subtle handheld hold with a very slow DOLLY-IN on the three-quarter face as he speaks, lips moving, firelight flicker. (final lip-sync via Artlist AI Avatar over the Gideon VO)",
 "N2": "No background music. NO BGM. SFX only — spark hiss, whoosh. FAST macro ARC through a swirl of ember sparks and molten light, the sparks engulf the lens as a morph wipe into the next shot.",
 "09": "No background music. NO BGM. SFX only — steel ring, spark shower. Dramatic low DOLLY-IN + crane-up as the hero raises the reforged sword overhead, sparks showering, hard backlight burst.",
 "10": "No background music. NO BGM. SFX only — magical ignite crackle. Slow macro DOLLY along the blade as ember-fire runes ignite crawling down the steel, glow bloom.",
 "11": "No background music. NO BGM. SFX only — cloth whip, ember rush. FAST ARC orbit as the hero whips around, heavy cloak trailing, ash and sparks streaking, dutch tilt.",
 "N5": "No background music. NO BGM. SFX only — pounding footsteps, wind rush. FAST DOLLY-IN push-through low across the ember field as the hero charges, ash streaking past, motion blur.",
 "12": "No background music. NO BGM. SFX only — sprint footfalls, armor clank. FAST side-tracking ARC alongside the sprinting hero, ash kicking up, heavy motion blur, fire backlight.",
 "N4": "No background music. NO BGM. SFX only — low ember hum. ROBOT-ARM style top-down descend + slow rotate over the hero standing in the ring of embers, ash swirling outward.",
 "13": "No background music. NO BGM. SFX only — fiery boom, shockwave. FAST DOLLY-OUT recoiling from the arcane fire blast, shockwave expanding, silhouettes flaring.",
 "14": "No background music. NO BGM. SFX only — steel clash, spark burst. HARD FAST DOLLY-IN snap to the sword impact, sparks exploding, dutch camera shake, embers.",
 "N7": "No background music. NO BGM. SFX only — sharp metal shriek. EXTREME fast macro DOLLY-IN to the white-hot spark burst at the blade contact point.",
 "15": "No background music. NO BGM. SFX only — heavy breath. FAST DOLLY-IN to the gritted face, sweat and ember light flickering, shallow focus.",
 "N8": "No background music. NO BGM. SFX only — low whoosh. SNAP DOLLY-IN to the eye as ember fury flares, pupil sharp.",
 "16": "No background music. NO BGM. SFX only — blade swing, impact thud. FAST crane-down ARC following the decisive overhead strike, sparks raining, silhouette against fire.",
 "N9": "No background music. NO BGM. SFX only — heavy stomp, dust burst. FAST DOLLY-IN to the armored boot stomping into ash, cinders and sparks bursting up.",
 "17": "No background music. NO BGM. SFX only — falling body, ember blast. High-angle ARC as the warlord falls back, an ember shockwave bursting outward, debris flying, slight slow-mo.",
 "N10": "No background music. NO BGM. SFX only — concussive boom. Explosive DOLLY-OUT from the ember shockwave ring, debris and sparks flying toward the lens.",
 "18": "No background music. NO BGM. SFX only — wind, ember settle, breath. Slow heroic DOLLY-IN + crane-up to the hero standing atop the rubble, cloak and embers blowing, chest heaving.",
 "19": "No background music. NO BGM. SFX only — low dragon rumble, fire. Slow DOLLY-IN toward the lone hero as the colossal dragon looms out of the smoke above the burning throne.",
 "N12": "No background music. NO BGM. SFX only — wind rush, diegetic dragon roar. FAST DOLLY-IN glide upward toward the colossal dragon emerging from smoke, embers raining, awe of scale.",
 "20": "No background music. NO BGM. SFX only — soft ember drift, low sub-boom on logo. LOCKED-OFF static, drifting embers with a glow pulse blooming across the EMBERTHRONE forged-metal title.",
}

PKG = Path(__file__).resolve().parent

MODE = os.environ.get("MODE", "image")
MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", PKG / ".." / "_신규생성")).resolve()
PORT = int(os.environ.get("PORT", "8765"))
VIDEO_DIR = None  # main()에서 설정 (기본: 미디어폴더 상위의 _영상)

# 모드별 런타임(이미지/영상 콘솔이 큐·결과를 공유하지 않도록 분리). main()에서 MODE 확정 후 재설정.
RUNTIME = PKG / "runtime" / MODE
QUEUE = RUNTIME / "revision_queue.jsonl"
RESULTS = RUNTIME / "results.json"


def _set_runtime(mode):
    global RUNTIME, QUEUE, RESULTS
    RUNTIME = PKG / "runtime" / mode
    RUNTIME.mkdir(parents=True, exist_ok=True)
    QUEUE = RUNTIME / "revision_queue.jsonl"
    RESULTS = RUNTIME / "results.json"


def find_base_file(cut_n):
    """미디어 폴더에서 cut{NN}_*.png|mp4 베이스 파일을 찾는다."""
    ext = "mp4" if MODE == "video" else "png"
    for f in sorted(MEDIA_DIR.glob(f"cut{cut_n}_*.{ext}")):
        return f.name
    # cutNN.mp4 형태(영상 기본 저장명)도 허용
    for f in sorted(MEDIA_DIR.glob(f"cut{cut_n}.{ext}")):
        return f.name
    return None


def latest_revision(cut_n):
    rev_dir = MEDIA_DIR / "_revisions"
    if not rev_dir.is_dir():
        return None
    ext = "mp4" if MODE == "video" else "png"
    revs = sorted(rev_dir.glob(f"cut{cut_n}_rev*.{ext}"),
                  key=lambda p: int(re.search(r"rev(\d+)", p.name).group(1)))
    return f"_revisions/{revs[-1].name}" if revs else None


def current_src(cut_n):
    """results.json > 최신 revision > 베이스 순으로 현재 보여줄 미디어 상대경로."""
    try:
        res = json.loads(RESULTS.read_text("utf-8")) if RESULTS.exists() else {}
    except Exception:
        res = {}
    item = res.get(cut_n) or res.get(f"cut{cut_n}")
    if item and item.get("status") == "done" and item.get("src"):
        return item["src"].replace("/media/", "")
    rev = latest_revision(cut_n)
    if rev:
        return rev
    return find_base_file(cut_n)


# ─────────────────────────────────────────────────────────────────────────────
def build_html():
    cards = json.dumps([{**c, "src": current_src(c["n"])} for c in CUTS], ensure_ascii=False)
    is_video = "true" if MODE == "video" else "false"
    title = "EMBERTHRONE — 영상 리뷰 콘솔" if MODE == "video" else "EMBERTHRONE — 스토리보드 리뷰 콘솔"
    return (HTML_TEMPLATE.replace("__CARDS__", cards).replace("__ISVIDEO__", is_video)
            .replace("__TITLE__", title)
            .replace("__MEDIADIR__", json.dumps(str(MEDIA_DIR), ensure_ascii=False)))


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>__TITLE__</title>
<style>
 :root{ --gold:#c9a24b; --blue:#5b8cff; --ok:#46c98b; --run:#e0a13a; }
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:#0a0a0c;color:#e8e6e0;font-family:"Pretendard","맑은 고딕",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
 header{position:sticky;top:0;z-index:20;background:rgba(10,10,12,.92);backdrop-filter:blur(8px);border-bottom:1px solid #1c1c22;padding:18px 22px}
 .htop{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
 .logo{font-size:24px;font-weight:800;letter-spacing:.12em;background:linear-gradient(180deg,#cfe0ff,var(--blue) 60%,#22418f);-webkit-background-clip:text;background-clip:text;color:transparent}
 .sub{color:var(--gold);letter-spacing:.3em;font-size:11px;text-transform:uppercase}
 .bar{margin-left:auto;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
 .bar label{font-size:12px;color:#8a8a95}
 select,button{font-family:inherit}
 select{background:#15151c;color:#dcdce4;border:1px solid #2a2a34;border-radius:8px;padding:6px 9px;font-size:12px}
 button{cursor:pointer;border:none;border-radius:9px;padding:9px 15px;font-size:13px;font-weight:600}
 .btn-batch{background:linear-gradient(180deg,#5b8cff,#3358c8);color:#fff}
 .btn-sel{background:#1d1d26;color:#cfcfe0;border:1px solid #33333f}
 .hint{padding:10px 22px;color:#6a6a75;font-size:12px;border-bottom:1px solid #141419;line-height:1.7}
 .hint b{color:#9a9aa8}
 .wrap{max-width:1240px;margin:0 auto;padding:24px 22px 100px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:20px}
 .card{background:#101015;border:1px solid #1d1d25;border-radius:14px;overflow:hidden;transition:border-color .15s,box-shadow .15s}
 .card.sel{border-color:var(--blue);box-shadow:0 0 0 1px var(--blue),0 0 28px rgba(91,140,255,.22)}
 .thumb{position:relative;aspect-ratio:16/9;background:#06060a;cursor:pointer}
 .thumb img,.thumb video{width:100%;height:100%;object-fit:cover;display:block}
 .thumb .empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#50505a;font-size:12px;letter-spacing:.1em}
 .num{position:absolute;top:10px;left:10px;background:rgba(0,0,0,.62);color:var(--gold);font-weight:700;font-size:12px;padding:4px 9px;border-radius:7px}
 .act{position:absolute;top:10px;right:10px;background:rgba(91,140,255,.16);color:#a8c2ff;font-size:11px;padding:4px 9px;border-radius:7px;border:1px solid rgba(91,140,255,.3)}
 .chip{position:absolute;bottom:10px;left:10px;font-size:11px;font-weight:600;padding:4px 10px;border-radius:20px;display:none}
 .chip.wait{display:inline-block;background:#26262e;color:#9a9aa6}
 .chip.run{display:inline-block;background:rgba(224,161,58,.16);color:var(--run);border:1px solid rgba(224,161,58,.4)}
 .chip.done{display:inline-block;background:rgba(70,201,139,.14);color:var(--ok);border:1px solid rgba(70,201,139,.4)}
 .chip.err{display:inline-block;background:rgba(229,80,80,.16);color:#e57070;border:1px solid rgba(229,80,80,.4)}
 .selmark{position:absolute;bottom:10px;right:10px;width:24px;height:24px;border-radius:50%;border:2px solid #44445a;background:rgba(0,0,0,.4)}
 .card.sel .selmark{background:var(--blue);border-color:var(--blue)}
 .card.sel .selmark::after{content:"✓";position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;font-weight:700}
 .body{padding:13px 15px}
 .ko{font-size:14px;font-weight:600;color:#ededf2;line-height:1.4}
 .panel{margin-top:12px;border-top:1px solid #1d1d25;padding-top:12px;display:none}
 .card.sel .panel{display:block}
 .seg{display:inline-flex;background:#15151c;border:1px solid #2a2a34;border-radius:9px;padding:3px;margin-bottom:10px;gap:3px}
 .seg button{background:transparent;color:#9a9aa6;padding:6px 12px;font-size:12px;border-radius:6px;font-weight:600}
 .seg button.active{background:var(--blue);color:#fff}
 .card[data-vmode="video"] .seg button.s-vid,.card:not([data-vmode="video"]) .seg button.s-img{background:var(--blue);color:#fff}
 .recbadge{font-size:10px;color:var(--gold);margin:2px 0 6px;letter-spacing:.03em;display:none}
 .card[data-vmode="video"] .recbadge{display:block}
 .ctrls{display:flex;gap:8px;margin-bottom:9px;flex-wrap:wrap}
 .ctrls .f{display:flex;flex-direction:column;gap:3px}
 .ctrls .f span{font-size:10px;color:#6e6e7a;letter-spacing:.04em}
 textarea{width:100%;background:#08080c;color:#e8e6e0;border:1px solid #2a2a34;border-radius:9px;padding:10px 11px;font-size:13px;font-family:inherit;resize:none;overflow:hidden;min-height:46px;line-height:1.5}
 textarea:focus{outline:none;border-color:var(--blue)}
 .ent{margin-top:5px;font-size:11px;color:#5a5a66}
 .lb{position:fixed;inset:0;background:rgba(0,0,0,.93);display:none;align-items:center;justify-content:center;z-index:50;cursor:zoom-out}
 .lb img,.lb video{max-width:94vw;max-height:90vh;border-radius:6px}
 .toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1a1a22;border:1px solid #33333f;color:#e8e6e0;padding:11px 18px;border-radius:10px;font-size:13px;opacity:0;transition:opacity .2s;z-index:60}
 .toast.show{opacity:1}
 .selbar{position:fixed;left:0;right:0;bottom:0;z-index:40;display:none;align-items:center;gap:14px;background:rgba(12,12,16,.97);backdrop-filter:blur(8px);border-top:1px solid #2a2a34;padding:12px 20px}
 .selbar.show{display:flex}
 .selbar .selcount{color:#ff8a3d;font-weight:700;font-size:13px;white-space:nowrap}
 .selbar .sellist{color:#9a9aa6;font-size:12px;font-family:ui-monospace,monospace;white-space:nowrap;overflow-x:auto;flex:1}
 .selbar .selbtns{display:flex;gap:8px;margin-left:auto}
 .selbar .selbtns button{font-size:12px;padding:8px 14px;border-radius:8px}
 .selbar .b-all,.selbar .b-clear{background:#1d1d26;color:#cfcfe0;border:1px solid #33333f}
 .selbar .b-copy{background:linear-gradient(180deg,#ff8a3d,#e0631a);color:#1a0e05;font-weight:700}
 .selbar .b-vid{background:linear-gradient(180deg,#5b8cff,#3358c8);color:#fff;font-weight:700}
 .selbar .b-img{background:#23304a;color:#cfe0ff;border:1px solid #3a4a66;font-weight:700}
</style></head><body>
<header>
 <div class="htop">
   <div><div class="logo">EMBERTHRONE</div><div class="sub" id="modelbl">Storyboard Review</div></div>
   <div class="bar">
     <label>기본값</label>
     <select id="defModel" class="i-only"><option value="nano_banana_2">nano_banana_2</option><option value="gpt_image_2">gpt_image_2</option></select>
     <select id="defQualImg" class="i-only"><option>1k</option><option selected>2k</option><option>4k</option></select>
     <select id="defDur" class="v-only"><option value="4">4초</option><option value="5" selected>5초</option><option value="6">6초</option><option value="8">8초</option><option value="10">10초</option></select>
     <select id="defQualVid" class="v-only"><option selected>std</option><option>pro</option><option>4k</option></select>
     <button class="btn-sel" id="batchSel">선택 컷 일괄 수정</button>
     <button class="btn-sel" id="viewVids" onclick="window.open('/videos','_blank')">🎞️ 영상 보기</button>
     <button class="btn-batch" id="batchVid">전체 영상으로 돌리기 ▶</button>
   </div>
 </div>
</header>
<div class="hint" id="hint"></div>
<div class="wrap"><div class="grid" id="grid"></div></div>
<div class="lb" id="lb"></div>
<div class="selbar" id="selbar">
  <span class="selcount" id="selcount">0개 선택</span>
  <span class="sellist" id="sellist"></span>
  <div class="selbtns">
    <button class="b-all" id="selAll">전체선택</button>
    <button class="b-clear" id="selClear">선택해제</button>
    <button class="b-copy" id="selCopy">선택 목록 복사</button>
    <button class="b-img i-only" id="selImg">✎ 선택 이미지 수정</button>
    <button class="b-vid" id="selVid">🎬 선택 영상화 ▶</button>
  </div>
</div>
<div class="toast" id="toast"></div>
<script>
const CARDS = __CARDS__;
const IS_VIDEO = __ISVIDEO__;
const MEDIA = "/media/";
const MEDIADIR = __MEDIADIR__;
// 컷별 추천 영상(모션) 프롬프트 — '영상으로 전환' 시 자동 입력
const REC_VID = {
 "N1":"No background music. NO BGM. SFX only — fire crackle, ember whoosh. FAST dolly-in glide racing down the burning ruined corridor toward the fiery vanishing point, embers and ash streaking past, slight dutch roll, heavy motion blur.",
 "01":"No background music. NO BGM. SFX only — distant fire roar, wind. Slow DOLLY-OUT + crane-up revealing the burning kingdom skyline, ember motes rising, smoke columns drifting.",
 "01b":"No background music. NO BGM. SFX only — soft ember sizzle. Slow macro DOLLY-IN on smoke curling off glowing embers, sparks floating up, shallow rack focus.",
 "02":"No background music. NO BGM. SFX only — falling debris, faint wind. High crane-down ARC sweeping over the ruined throne hall, ash falling through light shafts, tattered banners swaying.",
 "03b":"No background music. NO BGM. SFX only — airy hush. Slow ARC through a hard god-ray as fine ash drifts and glints, dust motes passing the beam.",
 "03":"No background music. NO BGM. SFX only — metal tick, ember pop. FAST macro DOLLY-IN to the half-buried gauntlet in the ash, embers pulsing, sharp rack focus.",
 "04":"No background music. NO BGM. SFX only — leather creak, grip tighten. Quick DOLLY-IN as the steel-gauntleted hand closes on the broken hilt, embers swirling up.",
 "08b":"No background music. NO BGM. SFX only — knuckle creak. Tight ARC orbiting around the scarred hand gripping the hilt, knuckles tightening, ember rim flicker.",
 "05":"No background music. NO BGM. SFX only — low wind, embers. Slow ARC orbit around the kneeling rim-lit silhouette, cloak swaying, smoke drifting.",
 "05b":"No background music. NO BGM. SFX only — deep molten rumble, crackle. Slow macro DOLLY-IN along the glowing lava crack, heat shimmer, rising embers.",
 "N3":"No background music. NO BGM. SFX only — ominous wind, low stomps (no music). FAST ARC swing + slow DOLLY-OUT revealing the colossal dark army and warlord looming over the tiny hero, heavy wide-angle distortion.",
 "06":"No background music. NO BGM. SFX only — torch flutter, low murmur. Slow parallax ARC across the ridgeline horde, torches flickering, ragged banners waving.",
 "07":"No background music. NO BGM. SFX only — faint ember crackle. FAST DOLLY-IN to the hero's eye, ember fire flaring in the iris, ash passing.",
 "07b":"No background music. NO BGM. SFX only — slow breath. Subtle DOLLY-IN on the set jaw and mouth, visible breath, ember rim light flickering.",
 "08":"No background music. NO BGM. SFX only — breath, distant fire. Subtle handheld hold with a very slow DOLLY-IN on the three-quarter face as he speaks, lips moving, firelight flicker. (final lip-sync via Artlist AI Avatar over the Gideon VO)",
 "N2":"No background music. NO BGM. SFX only — spark hiss, whoosh. FAST macro ARC through a swirl of ember sparks and molten light, the sparks engulf the lens as a morph wipe into the next shot.",
 "09":"No background music. NO BGM. SFX only — steel ring, spark shower. Dramatic low DOLLY-IN + crane-up as the hero raises the reforged sword overhead, sparks showering, hard backlight burst.",
 "10":"No background music. NO BGM. SFX only — magical ignite crackle. Slow macro DOLLY along the blade as ember-fire runes ignite crawling down the steel, glow bloom.",
 "11":"No background music. NO BGM. SFX only — cloth whip, ember rush. FAST ARC orbit as the hero whips around, heavy cloak trailing, ash and sparks streaking, dutch tilt.",
 "N5":"No background music. NO BGM. SFX only — pounding footsteps, wind rush. FAST DOLLY-IN push-through low across the ember field as the hero charges, ash streaking past, motion blur.",
 "12":"No background music. NO BGM. SFX only — sprint footfalls, armor clank. FAST side-tracking ARC alongside the sprinting hero, ash kicking up, heavy motion blur, fire backlight.",
 "N4":"No background music. NO BGM. SFX only — low ember hum. ROBOT-ARM style top-down descend + slow rotate over the hero standing in the ring of embers, ash swirling outward.",
 "13":"No background music. NO BGM. SFX only — fiery boom, shockwave. FAST DOLLY-OUT recoiling from the arcane fire blast, shockwave expanding, silhouettes flaring.",
 "14":"No background music. NO BGM. SFX only — steel clash, spark burst. HARD FAST DOLLY-IN snap to the sword impact, sparks exploding, dutch camera shake, embers.",
 "N7":"No background music. NO BGM. SFX only — sharp metal shriek. EXTREME fast macro DOLLY-IN to the white-hot spark burst at the blade contact point.",
 "15":"No background music. NO BGM. SFX only — heavy breath. FAST DOLLY-IN to the gritted face, sweat and ember light flickering, shallow focus.",
 "N8":"No background music. NO BGM. SFX only — low whoosh. SNAP DOLLY-IN to the eye as ember fury flares, pupil sharp.",
 "16":"No background music. NO BGM. SFX only — blade swing, impact thud. FAST crane-down ARC following the decisive overhead strike, sparks raining, silhouette against fire.",
 "N9":"No background music. NO BGM. SFX only — heavy stomp, dust burst. FAST DOLLY-IN to the armored boot stomping into ash, cinders and sparks bursting up.",
 "17":"No background music. NO BGM. SFX only — falling body, ember blast. High-angle ARC as the warlord falls back, an ember shockwave bursting outward, debris flying, slight slow-mo.",
 "N10":"No background music. NO BGM. SFX only — concussive boom. Explosive DOLLY-OUT from the ember shockwave ring, debris and sparks flying toward the lens.",
 "18":"No background music. NO BGM. SFX only — wind, ember settle, breath. Slow heroic DOLLY-IN + crane-up to the hero standing atop the rubble, cloak and embers blowing, chest heaving.",
 "19":"No background music. NO BGM. SFX only — low dragon rumble, fire. Slow DOLLY-IN toward the lone hero as the colossal dragon looms out of the smoke above the burning throne.",
 "N12":"No background music. NO BGM. SFX only — wind rush, diegetic dragon roar. FAST DOLLY-IN glide upward toward the colossal dragon emerging from smoke, embers raining, awe of scale.",
 "20":"No background music. NO BGM. SFX only — soft ember drift, low sub-boom on logo. LOCKED-OFF static, drifting embers with a glow pulse blooming across the EMBERTHRONE forged-metal title.",
};
document.getElementById('modelbl').textContent = IS_VIDEO ? "Video Review · Kling 3.0" : "Storyboard Review · nano_banana_2 / gpt_image_2";
document.getElementById('hint').innerHTML = IS_VIDEO
 ? '카드를 <b>클릭해 선택</b> → 초수·모드 고르고 → 수정요청 입력 → <b>Enter</b> = Kling 3.0 재생성. 상단 <b>[전체 영상으로 돌리기]</b> = 스토리보드 전체를 한 번에 영상화.'
 : '카드를 <b>클릭해 선택</b> → <b>✎ 이미지 수정</b>(모델·화질) 또는 <b>🎬 영상으로 전환</b>(추천 모션 프롬프트 자동입력·Kling 3.0) → 수정요청 입력 → <b>Enter</b>. 상단 <b>[전체 영상으로 돌리기]</b> = 전체 일괄 영상화.';
document.querySelectorAll(IS_VIDEO ? '.i-only' : '.v-only').forEach(e=>e.style.display='none');

const grid = document.getElementById('grid');
const toast = (m)=>{const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove('show'),2200);};
// 입력창 내용에 맞춰 높이 자동 확장
function autoGrow(ta){ ta.style.height='auto'; ta.style.height=(ta.scrollHeight+2)+'px'; }

function mediaTag(c){
  if(!c.src) return `<div class="empty">생성 대기 중…</div>`;
  const url = MEDIA+encodeURIComponent(c.src)+`?t=${Date.now()}`;
  return IS_VIDEO
    ? `<video src="${url}" autoplay muted loop playsinline></video>`
    : `<img loading="lazy" src="${url}" alt="">`;
}
function imgCtrls(){
  return `<div class="f"><span>모델</span><select class="model"><option value="nano_banana_2">nano_banana_2</option><option value="gpt_image_2">gpt_image_2</option></select></div>
          <div class="f"><span>화질</span><select class="qual-img"><option>1k</option><option selected>2k</option><option>4k</option></select></div>`;
}
function vidCtrls(){
  return `<div class="f"><span>초수</span><select class="dur"><option>4</option><option selected>5</option><option>6</option><option>8</option><option>10</option></select></div>
          <div class="f"><span>모드(화질)</span><select class="qual-vid"><option selected>std</option><option>pro</option><option>4k</option></select></div>`;
}
function panelHTML(c){
  if(IS_VIDEO){
    return `<div class="ctrls">${vidCtrls()}</div>
      <textarea placeholder="예) 더 천천히 dolly-in, 룬 빛 강하게, 8초로"></textarea>
      <div class="ent">Enter = 제출 · Shift+Enter = 줄바꿈</div>`;
  }
  return `<div class="seg">
      <button type="button" class="s-img active">✎ 이미지 수정</button>
      <button type="button" class="s-vid">🎬 영상으로 전환</button></div>
    <div class="ctrls img-ctrls">${imgCtrls()}</div>
    <div class="ctrls vid-ctrls" style="display:none">${vidCtrls()}</div>
    <div class="recbadge">↓ 컷 추천 모션 프롬프트 자동입력됨 (그대로 Enter 또는 수정)</div>
    <textarea placeholder="예) 망토를 더 펄럭이게, 룬을 더 푸르게, 얼굴 더 또렷이"></textarea>
    <div class="ent">Enter = 제출 · Shift+Enter = 줄바꿈</div>`;
}
CARDS.forEach(c=>{
  const el=document.createElement('div'); el.className='card'; el.dataset.cut=c.n;
  el.innerHTML=`
   <div class="thumb">
     <div class="num">CUT ${c.n}</div><div class="act">${c.act}</div>
     ${mediaTag(c)}
     <span class="chip wait" style="display:none">대기</span>
     <div class="selmark"></div>
   </div>
   <div class="body">
     <div class="ko">${c.ko}</div>
     <div class="panel">${panelHTML(c)}</div>
   </div>`;
  grid.appendChild(el);
  el.dataset.vmode='image';

  const thumb=el.querySelector('.thumb');
  // 썸네일 클릭=확대, 선택은 체크마크/카드여백/번호
  thumb.addEventListener('click',(e)=>{
    if(e.target.closest('.selmark')){ el.classList.toggle('sel'); return; }
    const m=el.querySelector('img,video'); if(!m) return;
    const lb=document.getElementById('lb');
    lb.innerHTML = IS_VIDEO?`<video src="${m.src}" autoplay loop controls></video>`:`<img src="${m.src}">`;
    lb.style.display='flex';
  });
  el.querySelector('.ko').addEventListener('click',()=>el.classList.toggle('sel'));

  const ta=el.querySelector('textarea');
  // 이미지 콘솔: [이미지 수정 ↔ 영상으로 전환] 토글 + 추천 모션 프롬프트 자동입력
  if(!IS_VIDEO){
    const sImg=el.querySelector('.s-img'), sVid=el.querySelector('.s-vid');
    const imgC=el.querySelector('.img-ctrls'), vidC=el.querySelector('.vid-ctrls');
    let savedImgReq='';
    sVid.addEventListener('click',()=>{
      if(el.dataset.vmode==='video') return;
      el.dataset.vmode='video'; sVid.classList.add('active'); sImg.classList.remove('active');
      imgC.style.display='none'; vidC.style.display='flex';
      savedImgReq=ta.value;
      ta.value=REC_VID[c.n]||''; ta.placeholder='영상 모션 프롬프트 (추천 자동입력 · 수정 후 Enter)'; autoGrow(ta);
    });
    sImg.addEventListener('click',()=>{
      if(el.dataset.vmode==='image') return;
      el.dataset.vmode='image'; sImg.classList.add('active'); sVid.classList.remove('active');
      vidC.style.display='none'; imgC.style.display='flex';
      ta.value=savedImgReq; ta.placeholder='예) 망토를 더 펄럭이게, 룬을 더 푸르게, 얼굴 더 또렷이'; autoGrow(ta);
    });
  }
  ta.addEventListener('input',()=>autoGrow(ta));
  ta.addEventListener('keydown',ev=>{
    if(ev.key==='Enter' && !ev.shiftKey){ ev.preventDefault(); submit(el,[el]); }
  });
  autoGrow(ta);
});
function closeLb(){ const lb=document.getElementById('lb'); lb.style.display='none'; lb.innerHTML=''; }
document.getElementById('lb').addEventListener('click',e=>{ if(e.target.id==='lb') closeLb(); });
document.addEventListener('keydown',e=>{ if(e.key==='Escape' && document.getElementById('lb').style.display==='flex') closeLb(); });

function payloadFor(card){
  const cut=card.dataset.cut, req=card.querySelector('textarea').value.trim();
  if(IS_VIDEO || card.dataset.vmode==='video'){
    return {type:'video', cut, request:req,
      duration:parseInt(card.querySelector('.dur').value),
      quality:card.querySelector('.qual-vid').value};
  }
  return {type:'image', cut, request:req,
    model:card.querySelector('.model').value,
    quality:card.querySelector('.qual-img').value};
}
function setChip(card,cls,txt){
  const ch=card.querySelector('.chip'); ch.className='chip '+cls; ch.style.display='inline-block'; ch.textContent=txt;
}
async function send(body){
  const r=await fetch('/revise',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  return r.json();
}
async function submit(card,cards){
  const items=cards.map(payloadFor);
  if(!IS_VIDEO && items.every(i=>!i.request)){ toast('수정 요청을 입력하세요'); return; }
  for(const it of items){ await send(it); }
  cards.forEach(c=>setChip(c,'run','처리중'));
  toast(`${items.length}개 수정 요청 전송됨 — 에이전트가 처리합니다`);
  cards.forEach(c=>c.querySelector('textarea').value='');
}

document.getElementById('batchSel').addEventListener('click',()=>{
  const sel=[...document.querySelectorAll('.card.sel')];
  if(!sel.length){ toast('먼저 카드를 선택하세요'); return; }
  submit(null,sel);
});
document.getElementById('batchVid').addEventListener('click',async()=>{
  if(!confirm('확정 스토리보드 전체를 한 번에 영상으로 돌립니다. 진행할까요?')) return;
  await send({type:'batch_video',
    duration:parseInt(document.getElementById('defDur').value),
    quality:document.getElementById('defQualVid').value});
  document.querySelectorAll('.card').forEach(c=>setChip(c,'run','영상화 중'));
  toast('전체 영상화 요청 전송됨 — 완료되면 영상 콘솔이 뜹니다');
});

// 결과 폴링 — 4초마다 results.json 반영
async function poll(){
  try{
    const res=await (await fetch('/results?t='+Date.now())).json();
    for(const [k,v] of Object.entries(res)){
      const n=k.replace('cut','');
      const card=document.querySelector(`.card[data-cut="${n}"]`); if(!card) continue;
      if(v.status==='done' && v.src){
        const m=card.querySelector('img,video');
        const url=MEDIA+encodeURIComponent(v.src.replace('/media/',''))+'?t='+Date.now();
        if(m){ if(m.tagName==='VIDEO'){m.src=url;m.load();} else m.src=url; }
        else { card.querySelector('.thumb .empty')?.remove();
          card.querySelector('.thumb').insertAdjacentHTML('beforeend', IS_VIDEO?`<video src="${url}" autoplay muted loop playsinline></video>`:`<img src="${url}">`); }
        setChip(card,'done','완료'); setTimeout(()=>{card.querySelector('.chip').style.display='none';},2500);
        card.classList.remove('sel');
      } else if(v.status==='video_done'){ setChip(card,'done','🎬 영상 생성됨'); card.classList.remove('sel'); }
      else if(v.status==='running'){ setChip(card,'run',v.msg||'처리중'); }
      else if(v.status==='error'){ setChip(card,'err',v.msg||'실패'); }
    }
  }catch(e){}
  setTimeout(poll,4000);
}
// ── 하단 선택 바: 개수 + 파일 목록 + 전체선택/해제/복사 ──
function selCardInfo(cut){
  const cd=CARDS.find(x=>x.n===cut)||{};
  const rel=cd.src||cd.file||(cut+'.png');
  return {base:String(rel).split('/').pop(), path:MEDIADIR+'/'+rel};
}
function updateSelbar(){
  const sel=[...document.querySelectorAll('.card.sel')];
  const bar=document.getElementById('selbar');
  if(!sel.length){ bar.classList.remove('show'); window._selPaths=[]; return; }
  bar.classList.add('show');
  document.getElementById('selcount').textContent=sel.length+'개 선택';
  const infos=sel.map(c=>selCardInfo(c.dataset.cut));
  document.getElementById('sellist').textContent=infos.map(i=>i.base).join('   ·   ');
  window._selPaths=infos.map(i=>i.path);
}
new MutationObserver(updateSelbar).observe(grid,{subtree:true,attributes:true,attributeFilter:['class']});
document.getElementById('selAll').addEventListener('click',()=>document.querySelectorAll('.card').forEach(c=>c.classList.add('sel')));
document.getElementById('selClear').addEventListener('click',()=>document.querySelectorAll('.card.sel').forEach(c=>c.classList.remove('sel')));
document.getElementById('selCopy').addEventListener('click',async()=>{
  const paths=window._selPaths||[]; if(!paths.length){ toast('선택된 카드가 없습니다'); return; }
  const text=paths.join('\n');
  try{ await navigator.clipboard.writeText(text); }
  catch(e){ const t=document.createElement('textarea'); t.value=text; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); }
  toast(paths.length+'개 주소 복사됨');
});
// 선택한 카드 전부를 한 번에 영상 전환 큐로 (모드 토글 안 했어도 추천 프롬프트로 영상화)
document.getElementById('selVid').addEventListener('click',async()=>{
  const sel=[...document.querySelectorAll('.card.sel')];
  if(!sel.length){ toast('선택된 카드가 없습니다'); return; }
  const items=sel.map(card=>{
    const cut=card.dataset.cut, cd=CARDS.find(x=>x.n===cut)||{};
    const durEl=card.querySelector('.dur'), qEl=card.querySelector('.qual-vid');
    let req=(card.querySelector('textarea')?card.querySelector('textarea').value:'').trim();
    if(!req) req=REC_VID[cut]||'';
    return {type:'video', cut, src:cd.src||null, request:req,
      duration: durEl?parseInt(durEl.value):5, quality: qEl?qEl.value:'std'};
  });
  for(const it of items){ await send(it); }
  sel.forEach(c=>setChip(c,'run','영상화 중'));
  toast(items.length+'개 영상 전환 요청 전송됨 — 처리합니다');
});
// 선택한 카드 전부를 한 번에 이미지 수정 큐로 (공통 지시 입력, 카드별 개별 입력이 있으면 우선)
document.getElementById('selImg').addEventListener('click',async()=>{
  const sel=[...document.querySelectorAll('.card.sel')];
  if(!sel.length){ toast('선택된 카드가 없습니다'); return; }
  const shared=prompt('선택한 '+sel.length+'개 카드에 적용할 이미지 수정 요청을 입력하세요\n(카드에 직접 입력한 내용이 있으면 그게 우선됩니다)');
  if(shared===null) return;
  const items=sel.map(card=>{
    const cut=card.dataset.cut, cd=CARDS.find(x=>x.n===cut)||{};
    const mEl=card.querySelector('.model'), qEl=card.querySelector('.qual-img');
    let req=(card.querySelector('textarea')?card.querySelector('textarea').value:'').trim();
    if(!req) req=(shared||'').trim();
    return {type:'image', cut, src:cd.src||null, request:req,
      model: mEl?mEl.value:'nano_banana_2', quality: qEl?qEl.value:'2k'};
  }).filter(it=>it.request);
  if(!items.length){ toast('수정 요청이 비어 있습니다'); return; }
  for(const it of items){ await send(it); }
  sel.forEach(c=>setChip(c,'run','수정 중'));
  toast(items.length+'개 이미지 수정 요청 전송됨');
});
updateSelbar();
poll();
</script></body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
def _vnatkey(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


VIDEOS_TEMPLATE = r"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>EMBERTHRONE — 생성된 영상</title>
<style>
 :root{--blue:#5b8cff;--ok:#46c98b;--run:#e0a13a;}
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:#0a0a0c;color:#e8e6e0;font-family:"Pretendard","맑은 고딕",system-ui,sans-serif}
 header{position:sticky;top:0;z-index:10;background:rgba(10,10,12,.94);backdrop-filter:blur(8px);border-bottom:1px solid #1c1c22;padding:16px 22px;display:flex;align-items:center;gap:14px}
 .logo{font-size:20px;font-weight:800;letter-spacing:.1em;background:linear-gradient(180deg,#cfe0ff,var(--blue) 60%,#22418f);-webkit-background-clip:text;background-clip:text;color:transparent}
 .cnt{color:#c9a24b;font-size:12px;letter-spacing:.1em}
 a.back{margin-left:auto;background:#1d1d26;color:#cfcfe0;border:1px solid #33333f;border-radius:9px;padding:9px 15px;font-size:13px;text-decoration:none}
 .hint{padding:9px 22px;color:#6a6a75;font-size:12px;border-bottom:1px solid #141419;line-height:1.6}
 .hint b{color:#9a9aa8}
 .wrap{max-width:1240px;margin:0 auto;padding:24px 22px 90px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:20px}
 .card{background:#101015;border:1px solid #1d1d25;border-radius:14px;overflow:hidden}
 .thumb{position:relative}
 .card video{width:100%;aspect-ratio:16/9;background:#000;display:block}
 .card img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block}
 .thumb.dim img{opacity:.30;filter:grayscale(.25)}
 .badge{position:absolute;left:10px;top:10px;background:rgba(8,6,5,.78);border:1px solid #3a2a20;color:#cdbfb3;font-size:11px;padding:3px 9px;border-radius:7px;z-index:2}
 .miss{color:#7a6a5e;font-size:11px;white-space:nowrap}
 .chip{position:absolute;top:10px;right:10px;font-size:11px;font-weight:700;padding:4px 10px;border-radius:20px;display:none}
 .chip.run{display:inline-block;background:rgba(224,161,58,.16);color:var(--run);border:1px solid rgba(224,161,58,.4)}
 .chip.done{display:inline-block;background:rgba(70,201,139,.14);color:var(--ok);border:1px solid rgba(70,201,139,.4)}
 .body{padding:12px 15px}
 .top{display:flex;align-items:center;gap:10px;margin-bottom:9px}
 .num{background:rgba(0,0,0,.5);color:#c9a24b;font-weight:700;font-size:12px;padding:3px 8px;border-radius:6px}
 .ko{font-size:14px;color:#ededf2;font-weight:600;flex:1}
 .dl{color:#8aa0d8;font-size:12px;text-decoration:none;white-space:nowrap}
 .ctrls{display:flex;gap:8px;margin-bottom:8px}
 .ctrls .f{display:flex;flex-direction:column;gap:3px}
 .ctrls .f span{font-size:10px;color:#6e6e7a}
 select{background:#15151c;color:#dcdce4;border:1px solid #2a2a34;border-radius:8px;padding:6px 9px;font-size:12px}
 textarea{width:100%;background:#08080c;color:#e8e6e0;border:1px solid #2a2a34;border-radius:9px;padding:9px 11px;font-size:12.5px;font-family:inherit;resize:none;overflow:hidden;min-height:64px;line-height:1.5}
 textarea:focus{outline:none;border-color:var(--blue)}
 .row{display:flex;align-items:center;gap:8px;margin-top:7px}
 .row .ent{font-size:11px;color:#5a5a66;flex:1}
 button.regen{cursor:pointer;border:none;border-radius:8px;padding:8px 14px;font-size:12px;font-weight:700;background:linear-gradient(180deg,#5b8cff,#3358c8);color:#fff}
 .empty{color:#6a6a75;text-align:center;padding:70px;font-size:14px;line-height:1.8}
 .toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#1a1a22;border:1px solid #33333f;color:#e8e6e0;padding:10px 16px;border-radius:10px;font-size:13px;opacity:0;transition:opacity .2s}
 .toast.show{opacity:1}
</style></head><body>
<header>
 <div class="logo">EMBERTHRONE</div><div class="cnt">영상 __COUNT__</div>
 <a class="back" href="/">← 리뷰 콘솔로</a>
</header>
<div class="hint">전체 컷 표시 — <b>영상 있는 컷은 재생/재생성</b>, <b>아직 영상 없는 컷은 이미지(흐리게)+[영상화]</b>. 프롬프트 수정 후 Enter. BGM 없음·SFX only.</div>
<div class="hint" style="display:none">각 영상의 <b>프롬프트를 수정하고 [재생성]</b>(또는 Enter)하면 같은 시작이미지로 다시 영상화됩니다. 초수·모드 선택 가능. BGM 없음·SFX only.</div>
<div class="wrap"><div class="grid" id="grid"></div>
 <div class="empty" id="empty" style="display:none">아직 생성된 영상이 없습니다.<br>콘솔에서 카드를 영상화하면 여기에 모입니다.</div></div>
<div class="toast" id="toast"></div>
<script>
let VIDS=__VIDS__;
const grid=document.getElementById('grid');
const toast=(m)=>{const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove('show'),2200);};
function autoGrow(ta){ta.style.height='auto';ta.style.height=(ta.scrollHeight+2)+'px';}
const DUR=[4,5,6,8,10], QUAL=['std','pro','4k'];
function opts(arr,sel){return arr.map(x=>`<option${String(x)===String(sel)?' selected':''}>${x}</option>`).join('');}
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function setChip(el,cls,txt){const c=el.querySelector('.chip');c.className='chip '+cls;c.style.display='inline-block';c.textContent=txt;}
function mediaHTML(v){
  if(v.mode==='video' && v.file){
    return `<div class="thumb"><video src="/vmedia/${encodeURIComponent(v.file)}?t=${v.ts||0}" controls preload="metadata" playsinline></video><span class="chip"></span></div>`;
  }
  return `<div class="thumb dim"><img src="/media/${encodeURIComponent(v.imgsrc||v.src||'')}" alt=""><span class="badge">영상 미생성</span><span class="chip"></span></div>`;
}
function render(){
  grid.innerHTML='';
  if(!VIDS.length){document.getElementById('empty').style.display='block';return;}
  VIDS.forEach(v=>{
    const isVid=(v.mode==='video' && v.file);
    const el=document.createElement('div');el.className='card';el.dataset.cut=v.cut;el.dataset.ts=v.ts||0;el.dataset.mode=v.mode;
    el.innerHTML=`${mediaHTML(v)}
      <div class="body">
        <div class="top"><span class="num">CUT ${v.cut}</span><span class="ko">${esc(v.label)}</span>
          ${isVid?`<a class="dl" href="/vmedia/${encodeURIComponent(v.file)}" download>다운로드</a>`:`<span class="miss">미생성</span>`}</div>
        <div class="ctrls">
          <div class="f"><span>초수</span><select class="dur">${opts(DUR,v.duration||5)}</select></div>
          <div class="f"><span>모드</span><select class="qual">${opts(QUAL,v.quality||'std')}</select></div>
        </div>
        <textarea class="pr" placeholder="영상 모션 프롬프트 (수정 후 Enter)">${esc(v.prompt)}</textarea>
        <div class="row"><span class="ent">Enter = ${isVid?'재생성':'영상화'} · Shift+Enter = 줄바꿈</span>
          <button class="regen">${isVid?'재생성 ▶':'영상화 ▶'}</button></div>
      </div>`;
    grid.appendChild(el);
    const ta=el.querySelector('.pr'); autoGrow(ta);
    ta.addEventListener('input',()=>autoGrow(ta));
    ta.addEventListener('keydown',ev=>{if(ev.key==='Enter'&&!ev.shiftKey){ev.preventDefault();regen(el,v);}});
    el.querySelector('.regen').addEventListener('click',()=>regen(el,v));
  });
}
async function regen(el,v){
  const req=el.querySelector('.pr').value.trim(); if(!req){toast('프롬프트를 입력하세요');return;}
  const body={type:'video', cut:v.cut, src:v.src||null, request:req,
    duration:parseInt(el.querySelector('.dur').value), quality:el.querySelector('.qual').value};
  await fetch('/revise',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  setChip(el,'run', el.dataset.mode==='video'?'재생성 중':'영상화 중'); toast('요청 전송됨 — 에이전트가 처리합니다');
}
async function poll(){
  try{
    const fresh=await (await fetch('/vmeta?t='+Date.now())).json();
    document.querySelectorAll('.card').forEach(el=>{
      const m=fresh[el.dataset.cut]; if(!m||!m.file) return;
      if((m.ts||0) > Number(el.dataset.ts||0)){
        el.dataset.ts=m.ts; el.dataset.mode='video';
        const thumb=el.querySelector('.thumb'); thumb.className='thumb';
        thumb.innerHTML=`<video src="/vmedia/${encodeURIComponent(m.file)}?t=${m.ts}" controls preload="metadata" playsinline></video><span class="chip done" style="display:inline-block">갱신됨</span>`;
        const miss=el.querySelector('.miss'); if(miss){ miss.outerHTML=`<a class="dl" href="/vmedia/${encodeURIComponent(m.file)}" download>다운로드</a>`; }
        const btn=el.querySelector('.regen'); if(btn) btn.textContent='재생성 ▶';
        setTimeout(()=>{const c=el.querySelector('.chip'); if(c)c.style.display='none';},2600);
      }
    });
  }catch(e){}
  setTimeout(poll,4000);
}
render(); poll();
</script></body></html>"""


def load_video_meta():
    if VIDEO_DIR:
        f = Path(VIDEO_DIR) / "_video_meta.json"
        if f.is_file():
            try:
                return json.loads(f.read_text("utf-8"))
            except Exception:
                return {}
    return {}


def build_videos_html():
    vmeta = load_video_meta()
    vidfiles = {}
    if VIDEO_DIR and Path(VIDEO_DIR).is_dir():
        for p in Path(VIDEO_DIR).glob("*.mp4"):
            cid = p.stem[3:] if p.stem.startswith("cut") else p.stem
            vidfiles[cid] = p.name
    items, gen = [], 0
    for c in CUTS:
        n = c["n"]
        m = vmeta.get(n, {})
        if n in vidfiles:
            gen += 1
            items.append({"cut": n, "label": c["ko"], "mode": "video", "file": vidfiles[n],
                          "prompt": m.get("prompt", REC_VID_PY.get(n, "")), "src": m.get("src", ""),
                          "duration": m.get("duration", 5), "quality": m.get("quality", "std"), "ts": m.get("ts", 0)})
        else:
            isrc = current_src(n) or ""
            items.append({"cut": n, "label": c["ko"], "mode": "image", "file": "", "imgsrc": isrc,
                          "prompt": REC_VID_PY.get(n, ""), "src": isrc,
                          "duration": 5, "quality": "std", "ts": 0})
    return (VIDEOS_TEMPLATE
            .replace("__VIDS__", json.dumps(items, ensure_ascii=False))
            .replace("__COUNT__", "%d / %d 컷" % (gen, len(items))))


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html"):
            return self._send(200, "text/html; charset=utf-8", build_html().encode("utf-8"))
        if p == "/results":
            return self._send(200, "application/json",
                              RESULTS.read_bytes() if RESULTS.exists() else b"{}")
        if p == "/videos":
            return self._send(200, "text/html; charset=utf-8", build_videos_html().encode("utf-8"))
        if p == "/vmeta":
            return self._send(200, "application/json",
                              json.dumps(load_video_meta(), ensure_ascii=False).encode("utf-8"))
        if p.startswith("/vmedia/") and VIDEO_DIR:
            rel = urllib.parse.unquote(p[len("/vmedia/"):])
            vroot = Path(VIDEO_DIR).resolve()
            target = (vroot / rel).resolve()
            try:
                target.relative_to(vroot)
            except ValueError:
                return self._send(403, "text/plain", b"forbidden")
            if target.is_file():
                ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                return self._send(200, ctype, target.read_bytes())
            return self._send(404, "text/plain", b"not found")
        if p.startswith("/media/"):
            rel = urllib.parse.unquote(p[len("/media/"):])
            target = (MEDIA_DIR / rel).resolve()
            try:
                target.relative_to(MEDIA_DIR)
            except ValueError:
                return self._send(403, "text/plain", b"forbidden")
            if target.is_file():
                ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                return self._send(200, ctype, target.read_bytes())
            return self._send(404, "text/plain", b"not found")
        return self._send(404, "text/plain", b"not found")

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/revise":
            n = int(self.headers.get("Content-Length", "0") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, "application/json", b'{"ok":false}')
            body["ts"] = int(time.time())
            with open(QUEUE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(body, ensure_ascii=False) + "\n")
            return self._send(200, "application/json", b'{"ok":true}')
        return self._send(404, "text/plain", b"not found")

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["image", "video"], default="image")
    ap.add_argument("--media-dir", default=str(PKG / ".." / "_신규생성"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--video-dir", default=None, help="영상 보기 페이지가 읽을 폴더 (기본: 미디어폴더 상위의 _영상)")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    global MODE, MEDIA_DIR, PORT, VIDEO_DIR
    MODE = a.mode
    MEDIA_DIR = Path(a.media_dir).resolve()
    PORT = a.port
    VIDEO_DIR = Path(a.video_dir).resolve() if a.video_dir else (MEDIA_DIR.parent / "_영상")
    _set_runtime(MODE)
    # 세션마다 큐/결과 초기화
    QUEUE.write_text("", encoding="utf-8")
    RESULTS.write_text("{}", encoding="utf-8")
    (RUNTIME / ".agent_offset").write_text("0", encoding="utf-8")
    (RUNTIME / "mode.txt").write_text(MODE, encoding="utf-8")
    (RUNTIME / "media_dir.txt").write_text(str(MEDIA_DIR), encoding="utf-8")

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"\n  ▶ EMBERTHRONE 리뷰 콘솔({MODE}): http://localhost:{PORT}/")
    print(f"    media={MEDIA_DIR}")
    print(f"    큐={QUEUE}")
    print("    종료: Ctrl+C\n")
    if not a.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}/")).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  종료됨.")


if __name__ == "__main__":
    main()
