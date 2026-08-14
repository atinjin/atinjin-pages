#!/usr/bin/env python3
"""FORGE40 추천 전 분석 스크립트 — 집계·추세는 여기서, 판단은 AI가.

사용법: python3 muscle/tools/analyze.py [--date YYYY-MM-DD]
종목 메타데이터는 muscle/log/index.html의 SESSIONS 상수를 직접 파싱한다(중복 금지).
파싱 실패 시 즉시 에러 종료한다 — HTML 형식이 바뀌면 여기서 바로 드러나야 한다.
"""
import json
import re
import sys
from datetime import date as _date, timedelta
from pathlib import Path

MUSCLE_DIR = Path(__file__).resolve().parent.parent   # .../muscle
LOG_DIR = MUSCLE_DIR / "log"

WEIGHT_SESSIONS = ["upperA", "lowerA", "upperB", "lowerB"]  # 주간 빈도 감사 대상


def _js_to_json(src: str) -> str:
    """JS 객체 리터럴 → JSON. SESSIONS 블록의 형태(따옴표 문자열, 무따옴표 키,
    트레일링 콤마, // 주석)만 감당하면 된다. 문자열 내부를 건드리지 않도록
    문자열을 먼저 자리표시자로 빼둔다."""
    strings = []

    def stash(m):
        strings.append(m.group(0))
        return f'"\x00{len(strings) - 1}\x00"'

    src = re.sub(r'"(?:[^"\\]|\\.)*"', stash, src)
    src = re.sub(r"//[^\n]*", "", src)                      # 주석 제거
    src = re.sub(r"([{,]\s*)([A-Za-z_$][\w$]*|\d+)\s*:", r'\1"\2":', src)  # 키 인용 (WEEKDAY_MAP의 숫자 키 포함)
    src = re.sub(r",(\s*[}\]])", r"\1", src)                # trailing comma
    src = re.sub(r'"\x00(\d+)\x00"', lambda m: strings[int(m.group(1))], src)
    return src


def parse_js_object(src: str):
    """`const NAME = {...}` 의 우변(객체 리터럴)을 파싱. 실패 시 SystemExit."""
    try:
        return json.loads(_js_to_json(src))
    except (json.JSONDecodeError, IndexError) as e:
        sys.exit(f"오류: index.html의 JS 객체 파싱 실패 — HTML 형식이 바뀌었는지 확인 필요.\n{e}")


def _extract_const(html: str, name: str) -> str:
    """`const NAME = ` 부터 대응하는 `};` 까지의 객체 리터럴 텍스트를 추출."""
    m = re.search(rf"const {name}\s*=\s*\{{", html)
    if not m:
        sys.exit(f"오류: index.html에서 `const {name}` 를 찾지 못함.")
    start = m.end() - 1
    depth = 0
    in_str = False
    i = start
    while i < len(html):
        c = html[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return html[start : i + 1]
        i += 1
    sys.exit(f"오류: `const {name}` 블록이 닫히지 않음.")


def load_sessions():
    """log/index.html에서 (SESSIONS, WEEKDAY_MAP)을 파싱해 반환."""
    html = (LOG_DIR / "index.html").read_text(encoding="utf-8")
    sessions = parse_js_object(_extract_const(html, "SESSIONS"))
    wd_raw = parse_js_object(_extract_const(html, "WEEKDAY_MAP"))
    weekday_map = {int(k): v for k, v in wd_raw.items()}
    return sessions, weekday_map


def _load_json(path: Path):
    if not path.exists():
        sys.exit(f"오류: {path} 가 없음.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_history():
    return _load_json(LOG_DIR / "history.json")


def load_nutrition():
    return _load_json(LOG_DIR / "nutrition-history.json")


def load_weight():
    return _load_json(LOG_DIR / "weight-history.json")


def load_condition():
    return _load_json(LOG_DIR / "condition-history.json")


def recent(items, ref, days):
    lo = (_date.fromisoformat(ref) - timedelta(days=days - 1)).isoformat()
    return sorted((x for x in items if lo <= x["date"] <= ref), key=lambda x: x["date"])


def exercise_index(sessions):
    """종목명(별칭 포함) → ex 정의. 여러 세션에 같은 이름이 있으면 첫 정의 우선."""
    idx = {}
    for s in sessions.values():
        for ex in s.get("ex", []):
            for name in [ex["n"]] + ex.get("alias", []):
                idx.setdefault(name, ex)
    return idx


def _sets_of(entry):
    """log/index.html setsOf()와 동일: sets가 배열이면 그대로, 아니면 sets×(w,reps) 확장."""
    if isinstance(entry.get("sets"), list):
        return [{"w": float(s["w"]), "reps": int(s["reps"])} for s in entry["sets"]]
    n = max(1, int(entry.get("sets") or 1))
    return [{"w": float(entry.get("w", 0)), "reps": int(entry.get("reps", 0))}] * n


def weekly_volume(log, sessions, ref):
    idx = exercise_index(sessions)
    by_muscle = {}
    unknown = []
    for sess in recent(log, ref, 7):
        touched = set()
        for e in sess.get("entries", []):
            ex = idx.get(e["n"])
            if not ex or not ex.get("m"):
                if e["n"] not in unknown:
                    unknown.append(e["n"])
                continue
            m = ex["m"]
            rec = by_muscle.setdefault(m, {"sets": 0, "days": 0})
            rec["sets"] += len(_sets_of(e))
            touched.add(m)
        for m in touched:
            by_muscle[m]["days"] += 1
    return {"by_muscle": by_muscle, "unknown": unknown}


def session_frequency(log, ref):
    rec = [(s["date"], s["session"]) for s in recent(log, ref, 7)]
    rec.sort(reverse=True)
    present = {k for _, k in rec}
    return {"recent": rec, "missing": [k for k in WEIGHT_SESSIONS if k not in present]}


def _fmt_w(v):
    """무게 포맷팅: 정수면 정수로, 아니면 소수 1자리."""
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def pattern_of(sets):
    """세트 패턴 분류: "uniform" | "ramp" | "drop".
    - uniform: 모든 무게가 같음
    - ramp: 세트 순서상 비내림 (무게가 증가 또는 유지)
    - drop: 이전 세트보다 가벼워진 세트 존재
    """
    ws = [s["w"] for s in sets]
    if len(set(ws)) <= 1:
        return "uniform"
    return "ramp" if all(a <= b for a, b in zip(ws, ws[1:])) else "drop"


def history_for(log, ex, n=4):
    """종목(별칭 포함) 최근 n회 기록을 최신순으로 반환.
    각 항목: {"date": str, "sets": [{"w", "reps"}]}
    """
    names = set([ex["n"]] + ex.get("alias", []))
    out = []
    for s in sorted(log, key=lambda x: x["date"], reverse=True):
        for e in s.get("entries", []):
            if e["n"] in names:
                out.append({"date": s["date"], "sets": _sets_of(e)})
        if len(out) >= n:
            break
    return out[:n]


def baseline(ex, sets):
    """log/index.html recommend()의 파이썬 포팅 — 결론이 반드시 동일해야 한다.
    반환: {"cls": "new|up|down|hold", "text": str}
    """
    if not sets:
        return {"cls": "new", "text": f"시작: {ex.get('start', '?')} (RIR {ex.get('rir', '?')} · {ex['lo']}~{ex['hi']}회)"}

    ws = [s["w"] for s in sets]
    inc, lo, hi = ex["inc"], ex["lo"], ex["hi"]
    summ = " / ".join(f"{_fmt_w(s['w'])}×{s['reps']}" for s in sets)

    if ex.get("assist"):
        min_a = min(ws)                        # 보조가 가장 적은(=가장 힘든) 세트
        r_at_min = min(s["reps"] for s in sets if s["w"] == min_a)
        if max(ws) > min_a:
            return {"cls": "hold", "text": f"보조 {_fmt_w(min_a)}kg로 전 세트 (지난 {summ})"}
        if r_at_min >= hi:
            return {"cls": "up", "text": f"보조 ↓ {_fmt_w(max(0, min_a - inc))}kg (지난 {summ} — 상한 도달)"}
        if r_at_min < lo:
            return {"cls": "down", "text": f"보조 ↑ {_fmt_w(min_a + inc)}kg (지난 {summ} — 하한 미달)"}
        return {"cls": "hold", "text": f"보조 {_fmt_w(min_a)}kg 유지 · 반복 +1 (지난 {summ})"}

    top = max(ws)
    reps_at_top = min(s["reps"] for s in sets if s["w"] == top)
    if min(ws) < top:
        return {"cls": "hold", "text": f"{_fmt_w(top)}kg로 전 세트 채우기 (지난 {summ} — 채운 뒤 +{_fmt_w(inc)}kg)"}
    if reps_at_top >= hi:
        return {"cls": "up", "text": f"↑ {_fmt_w(top + inc)}kg × {lo}~{hi} (지난 {summ} — 상한 도달)"}
    if reps_at_top < lo:
        return {"cls": "down", "text": f"↓ {_fmt_w(max(0, top - inc))}kg × {lo}~{hi} (지난 {summ} — 하한 미달)"}
    return {"cls": "hold", "text": f"= {_fmt_w(top)}kg 유지 · 반복 +1 (지난 {summ})"}


def _top_key(rec):
    """진전 비교 키: (상단 무게, 상단 무게에서의 최소 반복)."""
    ws = [s["w"] for s in rec["sets"]]
    top = max(ws)
    return (top, min(s["reps"] for s in rec["sets"] if s["w"] == top))


def is_stalled(records):
    """최신순 records에서 최근 3회 연속 진전 없음이면 True. 3회 미만이면 False."""
    if len(records) < 3:
        return False
    r = records[:3]           # 최신 3회
    for newer, older in zip(r, r[1:]):
        nw, nr = _top_key(newer)
        ow, orp = _top_key(older)
        if nw > ow or (nw == ow and nr > orp):
            return False      # 한 번이라도 진전 있으면 정체 아님
    return True


def exercise_trends(log, sessions, session_key):
    """세션의 종목별 추세를 반환.
    반환: [{"n": 종목명, "records": [...], "pattern": str, "stalled": bool, "baseline": {...}}]
    """
    out = []
    for ex in sessions[session_key].get("ex", []):
        records = history_for(log, ex)
        last_sets = records[0]["sets"] if records else []
        out.append({
            "n": ex["n"],
            "records": records,
            "pattern": pattern_of(last_sets) if last_sets else None,
            "stalled": is_stalled(records),
            "baseline": baseline(ex, last_sets),
        })
    return out


if __name__ == "__main__":
    s, w = load_sessions()
    print(f"세션 {len(s)}개, 요일 매핑 {len(w)}개 파싱 완료")
