# -*- coding: utf-8 -*-
"""
범용 인터랙티브 리뷰 콘솔 (표준 라이브러리만, 파이썬 3.9+).

어떤 폴더든 가리키면 그 안의 이미지(또는 영상)를 POC 갤러리로 띄우고,
카드를 선택 → (이미지) 모델/화질 + 수정요청  또는  🎬 영상으로 전환(추천 모션 프롬프트 자동입력)
→ Enter 하면 runtime/<mode>/revision_queue.jsonl 에 한 줄 쌓인다.
실제 재생성은 Claude 에이전트가 큐를 읽어 Higgsfield MCP로 처리하고
runtime/<mode>/results.json 을 갱신 → 콘솔이 4초마다 폴링해 썸네일을 자동 교체한다.

브라우저 file:// 는 MCP·파일쓰기가 막혀 있어 [로컬서버 + 큐파일 + 에이전트 워처] 3단 브리지를 쓴다.

스토리 하드코딩 없음 — 폴더를 자동 스캔해 카드를 만든다.
폴더에 _console_meta.json 이 있으면 라벨/섹션/추천영상프롬프트를 보강한다(선택):
  {
    "title": "내 프로젝트",
    "subtitle": "Interactive MCP Review",
    "cards": {
      "<파일이름(확장자 제외)>": {"label":"한 줄 설명", "section":"1막", "rec_vid":"모션 프롬프트"}
    }
  }

실행:
  python3 app.py --mode image --media-dir /경로/이미지폴더 --port 8765
  python3 app.py --mode video --media-dir /경로/영상폴더   --port 8766
"""
import argparse, http.server, json, os, re, mimetypes, urllib.parse, webbrowser, threading, time
from pathlib import Path

PKG = Path(__file__).resolve().parent

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}

MODE = "image"
MEDIA_DIR = Path(".").resolve()
PORT = 8765
VIDEO_DIR = None  # main()에서 설정 (기본: 미디어폴더 상위의 _영상)
BRAND = "REVIEW CONSOLE"
SUBTITLE = "Interactive MCP Review"

RUNTIME = PKG / "runtime" / MODE
QUEUE = RUNTIME / "revision_queue.jsonl"
RESULTS = RUNTIME / "results.json"

DEFAULT_REC_VID = ("No background music. SFX only. Add subtle, motivated camera movement that fits this shot "
                   "(slow push-in / drift / gentle parallax); keep it photoreal; natural ambient motion "
                   "(light, particles, fabric).")


def _set_runtime(mode):
    global RUNTIME, QUEUE, RESULTS
    RUNTIME = PKG / "runtime" / mode
    RUNTIME.mkdir(parents=True, exist_ok=True)
    QUEUE = RUNTIME / "revision_queue.jsonl"
    RESULTS = RUNTIME / "results.json"


def _natkey(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def load_meta():
    f = MEDIA_DIR / "_console_meta.json"
    if f.is_file():
        try:
            return json.loads(f.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def prettify(stem):
    return re.sub(r"[_\-]+", " ", stem).strip()


def base_files():
    """미디어 폴더 최상위의 (모드별) 파일들을 자연정렬로."""
    exts = VIDEO_EXTS if MODE == "video" else IMAGE_EXTS
    files = [p for p in MEDIA_DIR.iterdir()
             if p.is_file() and p.suffix.lower() in exts and not p.name.startswith("_")]
    files.sort(key=lambda p: _natkey(p.name))
    return files


def latest_revision(stem):
    rev_dir = MEDIA_DIR / "_revisions"
    if not rev_dir.is_dir():
        return None
    exts = VIDEO_EXTS if MODE == "video" else IMAGE_EXTS
    revs = []
    for p in rev_dir.iterdir():
        m = re.match(re.escape(stem) + r"_rev(\d+)$", p.stem)
        if p.is_file() and p.suffix.lower() in exts and m:
            revs.append((int(m.group(1)), p.name))
    if not revs:
        return None
    revs.sort()
    return f"_revisions/{revs[-1][1]}"


def current_src(stem, base_name):
    """results.json > 최신 revision > 베이스 순으로 현재 보여줄 미디어 상대경로."""
    try:
        res = json.loads(RESULTS.read_text("utf-8")) if RESULTS.exists() else {}
    except Exception:
        res = {}
    item = res.get(stem)
    if item and item.get("status") == "done" and item.get("src"):
        return item["src"].replace("/media/", "")
    rev = latest_revision(stem)
    if rev:
        return rev
    return base_name


def build_cards():
    meta = load_meta()
    mcards = meta.get("cards", {})
    cards, recvid = [], {}
    for i, p in enumerate(base_files(), start=1):
        stem = p.stem
        m = mcards.get(stem, {})
        cards.append({
            "n": stem,
            "idx": f"{i:02d}",
            "file": p.name,
            "act": m.get("section", ""),
            "ko": m.get("label", prettify(stem)),
            "src": current_src(stem, p.name),
        })
        recvid[stem] = m.get("rec_vid", DEFAULT_REC_VID)
    return cards, recvid, meta


def build_html():
    cards, recvid, meta = build_cards()
    brand = meta.get("title", BRAND)
    subtitle = meta.get("subtitle", SUBTITLE)
    return (HTML_TEMPLATE
            .replace("__CARDS__", json.dumps(cards, ensure_ascii=False))
            .replace("__RECVID__", json.dumps(recvid, ensure_ascii=False))
            .replace("__ISVIDEO__", "true" if MODE == "video" else "false")
            .replace("__BRAND__", json.dumps(brand, ensure_ascii=False))
            .replace("__SUBTITLE__", json.dumps(subtitle, ensure_ascii=False))
            .replace("__TITLE__", (brand + " — Review Console"))
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
 .fn{font-size:11px;color:#5e5e6a;margin-top:3px;font-family:ui-monospace,monospace}
 .panel{margin-top:12px;border-top:1px solid #1d1d25;padding-top:12px;display:none}
 .card.sel .panel{display:block}
 .seg{display:inline-flex;background:#15151c;border:1px solid #2a2a34;border-radius:9px;padding:3px;margin-bottom:10px;gap:3px}
 .seg button{background:transparent;color:#9a9aa6;padding:6px 12px;font-size:12px;border-radius:6px;font-weight:600}
 .seg button.active{background:var(--blue);color:#fff}
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
   <div><div class="logo" id="brand"></div><div class="sub" id="modelbl">Review</div></div>
   <div class="bar">
     <label>기본값</label>
     <select id="defModel" class="i-only"><option value="nano_banana_pro">nano_banana_pro</option><option value="nano_banana_2">nano_banana_2</option><option value="gpt_image_2">gpt_image_2</option></select>
     <select id="defQualImg" class="i-only"><option>1k</option><option selected>2k</option><option>4k</option></select>
     <select id="defDur" class="v-only"><option value="4">4초</option><option value="5" selected>5초</option><option value="6">6초</option><option value="8">8초</option><option value="10">10초</option></select>
     <select id="defQualVid" class="v-only"><option selected>std</option><option>pro</option><option>4k</option></select>
     <button class="btn-sel" id="batchSel">선택 카드 일괄 수정</button>
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
const REC_VID = __RECVID__;
const IS_VIDEO = __ISVIDEO__;
const BRAND = __BRAND__;
const SUBTITLE = __SUBTITLE__;
const MEDIA = "/media/";
const MEDIADIR = __MEDIADIR__;

document.getElementById('brand').textContent = BRAND;
document.getElementById('modelbl').textContent = IS_VIDEO ? "Video Review · Kling 3.0" : (SUBTITLE + " · nano_banana_pro / gpt_image_2");
document.getElementById('hint').innerHTML = IS_VIDEO
 ? '카드를 <b>클릭해 선택</b> → 초수·모드 고르고 → 수정요청 입력 → <b>Enter</b> = Kling 3.0 재생성. 상단 <b>[전체 영상으로 돌리기]</b> = 전체를 한 번에 영상화.'
 : '카드를 <b>클릭해 선택</b> → <b>✎ 이미지 수정</b>(모델·화질) 또는 <b>🎬 영상으로 전환</b>(추천 모션 프롬프트 자동입력·Kling 3.0) → 수정요청 입력 → <b>Enter</b>. 상단 <b>[전체 영상으로 돌리기]</b> = 전체 일괄 영상화.';
document.querySelectorAll(IS_VIDEO ? '.i-only' : '.v-only').forEach(e=>e.style.display='none');

const grid = document.getElementById('grid');
const toast = (m)=>{const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove('show'),2200);};
function autoGrow(ta){ ta.style.height='auto'; ta.style.height=(ta.scrollHeight+2)+'px'; }

function mediaTag(c){
  if(!c.src) return `<div class="empty">생성 대기 중…</div>`;
  const url = MEDIA+encodeURIComponent(c.src)+`?t=${Date.now()}`;
  return IS_VIDEO
    ? `<video src="${url}" autoplay muted loop playsinline></video>`
    : `<img loading="lazy" src="${url}" alt="">`;
}
function imgCtrls(){
  return `<div class="f"><span>모델</span><select class="model"><option value="nano_banana_pro">nano_banana_pro</option><option value="nano_banana_2">nano_banana_2</option><option value="gpt_image_2">gpt_image_2</option></select></div>
          <div class="f"><span>화질</span><select class="qual-img"><option>1k</option><option selected>2k</option><option>4k</option></select></div>`;
}
function vidCtrls(){
  return `<div class="f"><span>초수</span><select class="dur"><option>4</option><option selected>5</option><option>6</option><option>8</option><option>10</option></select></div>
          <div class="f"><span>모드(화질)</span><select class="qual-vid"><option selected>std</option><option>pro</option><option>4k</option></select></div>`;
}
function panelHTML(c){
  if(IS_VIDEO){
    return `<div class="ctrls">${vidCtrls()}</div>
      <textarea placeholder="예) 더 천천히 dolly-in, 8초로, 빛 강하게"></textarea>
      <div class="ent">Enter = 제출 · Shift+Enter = 줄바꿈</div>`;
  }
  return `<div class="seg">
      <button type="button" class="s-img active">✎ 이미지 수정</button>
      <button type="button" class="s-vid">🎬 영상으로 전환</button></div>
    <div class="ctrls img-ctrls">${imgCtrls()}</div>
    <div class="ctrls vid-ctrls" style="display:none">${vidCtrls()}</div>
    <div class="recbadge">↓ 추천 모션 프롬프트 자동입력됨 (그대로 Enter 또는 수정)</div>
    <textarea placeholder="예) 색을 더 따뜻하게, 디테일 또렷이, 구도 살짝 더 로우앵글"></textarea>
    <div class="ent">Enter = 제출 · Shift+Enter = 줄바꿈</div>`;
}
CARDS.forEach(c=>{
  const el=document.createElement('div'); el.className='card'; el.dataset.cut=c.n;
  el.innerHTML=`
   <div class="thumb">
     <div class="num">${c.idx}</div>${c.act?`<div class="act">${c.act}</div>`:''}
     ${mediaTag(c)}
     <span class="chip wait" style="display:none">대기</span>
     <div class="selmark"></div>
   </div>
   <div class="body">
     <div class="ko">${c.ko}</div>
     <div class="fn">${c.file}</div>
     <div class="panel">${panelHTML(c)}</div>
   </div>`;
  grid.appendChild(el);
  el.dataset.vmode='image';

  const thumb=el.querySelector('.thumb');
  thumb.addEventListener('click',(e)=>{
    if(e.target.closest('.selmark')){ el.classList.toggle('sel'); return; }
    const m=el.querySelector('img,video'); if(!m) return;
    const lb=document.getElementById('lb');
    lb.innerHTML = IS_VIDEO?`<video src="${m.src}" autoplay loop controls></video>`:`<img src="${m.src}">`;
    lb.style.display='flex';
  });
  el.querySelector('.ko').addEventListener('click',()=>el.classList.toggle('sel'));

  const ta=el.querySelector('textarea');
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
      ta.value=savedImgReq; ta.placeholder='예) 색을 더 따뜻하게, 디테일 또렷이'; autoGrow(ta);
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

function fileFor(cut){ const c=CARDS.find(x=>x.n===cut); return c?c.file:''; }
function payloadFor(card){
  const cut=card.dataset.cut, req=card.querySelector('textarea').value.trim();
  if(IS_VIDEO || card.dataset.vmode==='video'){
    return {type:'video', cut, file:fileFor(cut), request:req,
      duration:parseInt(card.querySelector('.dur').value),
      quality:card.querySelector('.qual-vid').value};
  }
  return {type:'image', cut, file:fileFor(cut), request:req,
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
  toast(`${items.length}개 요청 전송됨 — 에이전트가 처리합니다`);
  cards.forEach(c=>c.querySelector('textarea').value='');
}

document.getElementById('batchSel').addEventListener('click',()=>{
  const sel=[...document.querySelectorAll('.card.sel')];
  if(!sel.length){ toast('먼저 카드를 선택하세요'); return; }
  submit(null,sel);
});
document.getElementById('batchVid').addEventListener('click',async()=>{
  if(!confirm('전체를 한 번에 영상으로 돌립니다. 진행할까요?')) return;
  await send({type:'batch_video',
    duration:parseInt(document.getElementById('defDur').value),
    quality:document.getElementById('defQualVid').value});
  document.querySelectorAll('.card').forEach(c=>setChip(c,'run','영상화 중'));
  toast('전체 영상화 요청 전송됨');
});

async function poll(){
  try{
    const res=await (await fetch('/results?t='+Date.now())).json();
    for(const [k,v] of Object.entries(res)){
      const card=document.querySelector(`.card[data-cut="${(window.CSS&&CSS.escape)?CSS.escape(k):k}"]`); if(!card) continue;
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
    return {type:'video', cut, file:(cd.file||null), src:cd.src||null, request:req,
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
    return {type:'image', cut, file:(cd.file||null), src:cd.src||null, request:req,
      model: mEl?mEl.value:'nano_banana_pro', quality: qEl?qEl.value:'2k'};
  }).filter(it=>it.request);
  if(!items.length){ toast('수정 요청이 비어 있습니다'); return; }
  for(const it of items){ await send(it); }
  sel.forEach(c=>setChip(c,'run','수정 중'));
  toast(items.length+'개 이미지 수정 요청 전송됨');
});
updateSelbar();
poll();
</script></body></html>"""


VIDEOS_TEMPLATE = r"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>생성된 영상</title>
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
 <div class="logo" id="brand"></div><div class="cnt">영상 __COUNT__</div>
 <a class="back" href="/">← 리뷰 콘솔로</a>
</header>
<div class="hint">전체 카드 표시 — <b>영상 있는 건 재생/재생성</b>, <b>아직 영상 없는 건 이미지(흐리게)+[영상화]</b>. 프롬프트 수정 후 Enter.</div>
<div class="wrap"><div class="grid" id="grid"></div>
 <div class="empty" id="empty" style="display:none">아직 생성된 영상이 없습니다.<br>콘솔에서 카드를 영상화하면 여기에 모입니다.</div></div>
<div class="toast" id="toast"></div>
<script>
let VIDS=__VIDS__; const BRAND=__BRAND__;
document.getElementById('brand').textContent=BRAND;
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
        <div class="top"><span class="num">${v.cut}</span><span class="ko">${esc(v.label)}</span>
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
    meta = load_meta()
    brand = meta.get("title", BRAND)
    cards, recvid, _ = build_cards()
    vmeta = load_video_meta()
    vidfiles = {}
    if VIDEO_DIR and Path(VIDEO_DIR).is_dir():
        for p in Path(VIDEO_DIR).glob("*.mp4"):
            vidfiles[p.stem] = p.name
    items, gen = [], 0
    for c in cards:
        n = c["n"]
        m = vmeta.get(n, {})
        if n in vidfiles:
            gen += 1
            items.append({"cut": n, "label": c["ko"], "mode": "video", "file": vidfiles[n],
                          "prompt": m.get("prompt", recvid.get(n, "")), "src": m.get("src", ""),
                          "duration": m.get("duration", 5), "quality": m.get("quality", "std"), "ts": m.get("ts", 0)})
        else:
            isrc = c.get("src", "") or ""
            items.append({"cut": n, "label": c["ko"], "mode": "image", "file": "", "imgsrc": isrc,
                          "prompt": recvid.get(n, ""), "src": isrc,
                          "duration": 5, "quality": "std", "ts": 0})
    return (VIDEOS_TEMPLATE.replace("__VIDS__", json.dumps(items, ensure_ascii=False))
            .replace("__COUNT__", "%d / %d 컷" % (gen, len(items)))
            .replace("__BRAND__", json.dumps(brand, ensure_ascii=False)))


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
    ap.add_argument("--media-dir", required=True)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--brand", default=None, help="상단 로고 텍스트(미지정 시 메타 title 또는 기본값)")
    ap.add_argument("--video-dir", default=None, help="영상 보기 페이지가 읽을 폴더 (기본: 미디어폴더 상위의 _영상)")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    global MODE, MEDIA_DIR, PORT, BRAND, VIDEO_DIR
    MODE = a.mode
    MEDIA_DIR = Path(a.media_dir).resolve()
    PORT = a.port
    VIDEO_DIR = Path(a.video_dir).resolve() if a.video_dir else (MEDIA_DIR.parent / "_영상")
    if a.brand:
        BRAND = a.brand
    _set_runtime(MODE)
    QUEUE.write_text("", encoding="utf-8")
    RESULTS.write_text("{}", encoding="utf-8")
    (RUNTIME / ".agent_offset").write_text("0", encoding="utf-8")
    (RUNTIME / "mode.txt").write_text(MODE, encoding="utf-8")
    (RUNTIME / "media_dir.txt").write_text(str(MEDIA_DIR), encoding="utf-8")

    n_cards = len(base_files())
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"\n  ▶ Review Console ({MODE}): http://localhost:{PORT}/")
    print(f"    media={MEDIA_DIR}  ({n_cards} cards)")
    print(f"    queue={QUEUE}")
    print("    stop: Ctrl+C\n")
    if not a.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}/")).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")


if __name__ == "__main__":
    main()
