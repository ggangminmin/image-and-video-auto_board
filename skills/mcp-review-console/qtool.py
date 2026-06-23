# -*- coding: utf-8 -*-
"""
워처 에이전트용 큐 헬퍼 (표준 라이브러리만).

  python3 qtool.py wait [--timeout 600]
      .agent_offset 이후의 새 큐 줄이 생길 때까지 블로킹 대기 →
      새 항목을 JSON 배열로 stdout 출력(각 항목에 _idx 부여). 타임아웃이면 [] 출력.
      (offset 은 건드리지 않음. 처리 끝나면 result 가 offset 을 올린다.)

  python3 qtool.py result --cut 05 --status done --src /media/_revisions/cut05_rev1.png
  python3 qtool.py result --cut 05 --status running --msg "생성 중"
      runtime/results.json 에 해당 컷 상태를 머지. status=done/error 면 그 항목까지 offset 자동 전진.

  python3 qtool.py offset --set 7        # 처리한 줄 수 수동 지정(선택)
  python3 qtool.py status                 # 현재 offset / 큐 줄 수 / results 요약
"""
import argparse, json, os, sys, time
from pathlib import Path

PKG = Path(__file__).resolve().parent
# RT 는 --mode 에 따라 main()에서 확정 (runtime/image · runtime/video)
RT = PKG / "runtime" / "image"
QUEUE = RESULTS = OFFSET = None


def _set_mode(mode):
    global RT, QUEUE, RESULTS, OFFSET
    RT = PKG / "runtime" / mode
    RT.mkdir(parents=True, exist_ok=True)
    QUEUE = RT / "revision_queue.jsonl"
    RESULTS = RT / "results.json"
    OFFSET = RT / ".agent_offset"


def _lines():
    if not QUEUE.exists():
        return []
    return [l for l in QUEUE.read_text("utf-8").splitlines() if l.strip()]


def _offset():
    try:
        return int(OFFSET.read_text("utf-8").strip() or "0")
    except Exception:
        return 0


def cmd_wait(a):
    deadline = time.time() + a.timeout
    while time.time() < deadline:
        lines = _lines()
        off = _offset()
        if len(lines) > off:
            out = []
            for i in range(off, len(lines)):
                try:
                    item = json.loads(lines[i])
                except Exception:
                    continue
                item["_idx"] = i
                out.append(item)
            print(json.dumps(out, ensure_ascii=False))
            return
        time.sleep(2)
    print("[]")


def cmd_result(a):
    res = {}
    if RESULTS.exists():
        try:
            res = json.loads(RESULTS.read_text("utf-8"))
        except Exception:
            res = {}
    entry = {"status": a.status, "ts": int(time.time())}
    if a.src:
        entry["src"] = a.src
    if a.msg:
        entry["msg"] = a.msg
    res[a.cut] = entry
    RESULTS.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    # 완료/실패/영상완료면 offset 전진(처리한 항목 인덱스+1까지)
    if a.status in ("done", "error", "video_done") and a.idx is not None:
        cur = _offset()
        OFFSET.write_text(str(max(cur, a.idx + 1)), encoding="utf-8")
    print(json.dumps({"ok": True, "cut": a.cut, "status": a.status}, ensure_ascii=False))


def cmd_offset(a):
    OFFSET.write_text(str(a.set), encoding="utf-8")
    print(json.dumps({"ok": True, "offset": a.set}))


def cmd_status(a):
    print(json.dumps({
        "offset": _offset(),
        "queue_lines": len(_lines()),
        "results": json.loads(RESULTS.read_text("utf-8")) if RESULTS.exists() else {},
    }, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="image", choices=["image", "video"],
                    help="runtime/image 또는 runtime/video (이미지·영상 콘솔 분리)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("wait"); w.add_argument("--timeout", type=int, default=600); w.set_defaults(fn=cmd_wait)
    r = sub.add_parser("result")
    r.add_argument("--cut", required=True); r.add_argument("--status", required=True)
    r.add_argument("--src", default=None); r.add_argument("--msg", default=None)
    r.add_argument("--idx", type=int, default=None); r.set_defaults(fn=cmd_result)
    o = sub.add_parser("offset"); o.add_argument("--set", type=int, required=True); o.set_defaults(fn=cmd_offset)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    a = ap.parse_args()
    _set_mode(a.mode)
    a.fn(a)


if __name__ == "__main__":
    main()
