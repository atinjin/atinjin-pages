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
    dates_by_muscle = {}
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
            dates_by_muscle.setdefault(m, set()).add(sess["date"])
    for m, dates in dates_by_muscle.items():
        by_muscle[m]["days"] = len(dates)      # 세션 레코드 수가 아닌 고유 날짜 수 (F3)
    return {"by_muscle": by_muscle, "unknown": unknown}


def session_frequency(log, ref):
    rec = [(s["date"], s["session"]) for s in recent(log, ref, 7)]
    rec.sort(reverse=True)
    present = {k for _, k in rec}
    return {"recent": rec, "missing": [k for k in WEIGHT_SESSIONS if k not in present]}


def _fmt_w(v):
    """무게 포맷팅: 정수면 정수로, 아니면 소수 1자리."""
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def pattern_of(sets, assist=False):
    """세트 패턴 분류: "uniform" | "ramp" | "drop".
    - uniform: 모든 무게가 같음
    - ramp: 세트 순서상 비내림 (무게가 증가 또는 유지)
    - drop: 이전 세트보다 가벼워진 세트 존재
    assist=True(어시스트 종목)면 무게를 부호 반전해서 판정한다 — 어시스트는
    무게가 클수록 도움이 커서(=더 쉬워서) baseline()의 최소 보조 무게 기준과
    방향이 반대이기 때문(F4).
    """
    ws = [s["w"] for s in sets]
    if assist:
        ws = [-w for w in ws]
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
            "pattern": pattern_of(last_sets, assist=ex.get("assist", False)) if last_sets else None,
            "stalled": is_stalled(records),
            "baseline": baseline(ex, last_sets),
        })
    return out


NUT_TARGET = {"kcal": 2700, "p": 130, "f": 55}   # v12: 최소 충족 목표(탄수는 참고용이라 제외)
KCAL_SOFT_CAP = 3000                             # v16: 서프러스 상한 — 2700(최소)~3000(상한) 밴드
WEIGHT_TARGET_KG_PER_MONTH = 0.7                 # v16: 실측 페이스(7/13~8/17 +2.52kg/5주)가 기존 0.3 목표를 크게 초과해 하향 조정, 0.6~0.8 밴드의 중앙값


def nutrition_summary(nut, ref):
    by_day = {}
    for x in nut:
        d = by_day.setdefault(x["date"], {"kcal": 0, "p": 0.0, "f": 0.0})
        qty = x.get("qty", 1)          # 레코드는 인분당 값 — qty 배수 적용 (F1, index.html sumDay()와 동일)
        d["kcal"] += x.get("kcal", 0) * qty
        d["p"] += x.get("p", 0) * qty
        d["f"] += x.get("f", 0) * qty

    days = []
    for d in sorted(by_day, reverse=True):
        if d > ref:
            continue
        t = by_day[d]
        days.append({"date": d, "kcal": round(t["kcal"]), "p": round(t["p"], 1), "f": round(t["f"], 1),
                     "ok_kcal": t["kcal"] >= NUT_TARGET["kcal"], "ok_p": t["p"] >= NUT_TARGET["p"],
                     "ok_f": t["f"] >= NUT_TARGET["f"], "over_cap": t["kcal"] > KCAL_SOFT_CAP})
        if len(days) == 3:
            break

    ref_recorded = ref in by_day       # 기준일 기록 유무 — 없으면 "0일 미달"과 구분해서 판정 불가 처리 (F2)
    consec = 0
    cur = _date.fromisoformat(ref)
    while True:
        d = cur.isoformat()
        if d not in by_day:
            break                      # 기록 없는 날 → 판정 불가, 연속 계산 중단
        t = by_day[d]
        if t["kcal"] >= NUT_TARGET["kcal"] and t["p"] >= NUT_TARGET["p"]:
            break
        consec += 1
        cur -= timedelta(days=1)
    return {"days": days, "consec_shortfall": consec, "ref_recorded": ref_recorded}


def weight_summary(weights, ref):
    ws = sorted((w for w in weights if w["date"] <= ref), key=lambda w: w["date"])
    if not ws:
        return None
    last = ws[-1]
    cutoff = (_date.fromisoformat(last["date"]) - timedelta(days=14)).isoformat()
    win = [w for w in ws if w["date"] >= cutoff]
    pace = None
    if len(win) >= 2:
        span = (_date.fromisoformat(win[-1]["date"]) - _date.fromisoformat(win[0]["date"])).days
        if span > 0:
            pace = (win[-1]["kg"] - win[0]["kg"]) / span * 30
    stale = (_date.fromisoformat(ref) - _date.fromisoformat(last["date"])).days
    return {"last": last, "monthly_pace": pace, "stale_days": stale}


def condition_flags(conds, ref):
    week = recent(conds, ref, 7)
    open_pain = []
    for c in sorted(week, key=lambda x: x["date"], reverse=True):
        for p in c.get("pain", []):
            open_pain.append({"date": c["date"], **p})
    return {"recent": week, "open_pain": open_pain}


MUSCLE_KO = {   # 출력용 한국어 라벨 (MUSCLE_LABELS는 UI 상수라 파싱하지 않고 여기 유지)
    "chest": "가슴", "back": "등", "shoulder": "어깨", "sideDelt": "어깨(측면)",
    "rearDelt": "어깨(후면)", "biceps": "이두", "triceps": "삼두", "quad": "대퇴사두",
    "hamstring": "햄스트링", "glute": "둔근", "hipAbductor": "고관절(외전)",
    "calf": "종아리", "abs": "복근", "lowerBack": "하부요추",
}
KO_WD = ["월", "화", "수", "목", "금", "토", "일"]  # date.weekday() 순서


def build_report(ref):
    sessions, weekday_map = load_sessions()
    log = load_history()
    L = []
    d = _date.fromisoformat(ref)
    js_wd = (d.weekday() + 1) % 7            # JS getDay(): 일=0
    default_key = weekday_map.get(js_wd, "other")
    default = sessions[default_key]["name"]
    L.append(f"# 오늘 기준: {ref} ({KO_WD[d.weekday()]}) — 요일 기본 세션: {default} ({default_key})")

    L.append("\n## 주간 볼륨 (최근 7일, ACSM: 부위별 10세트↑·2일↑)")
    vol = weekly_volume(log, sessions, ref)
    for m, v in sorted(vol["by_muscle"].items(), key=lambda kv: -kv[1]["sets"]):
        flag = "✅" if v["sets"] >= 10 and v["days"] >= 2 else ("⚠️ 세트 부족" if v["sets"] < 10 else "⚠️ 빈도 부족")
        L.append(f"- {MUSCLE_KO.get(m, m)}: {v['sets']}세트 / {v['days']}일 {flag}")
    if vol["unknown"]:
        L.append(f"- ❓ SESSIONS에 없는 종목(볼륨 미집계, AI가 수동 판단): {', '.join(vol['unknown'])}")

    L.append("\n## 세션 빈도 (최근 7일)")
    freq = session_frequency(log, ref)
    for dt, k in freq["recent"]:
        L.append(f"- {dt}: {sessions[k]['name']} ({k})")
    if freq["missing"]:
        L.append(f"- 🚨 7일간 없음: {', '.join(freq['missing'])} → 빠진 세션은 가장 빠른 기회에 보충 (v14)")

    L.append("\n## 종목별 추세 & 베이스라인 (이중 점진법)")
    for key in WEIGHT_SESSIONS + ["upperM"]:
        L.append(f"\n### {sessions[key]['name']} ({key})")
        for t in exercise_trends(log, sessions, key):
            marks = []
            if t["pattern"] == "drop":
                marks.append("드롭")
            if t["pattern"] == "ramp":
                marks.append("램프업(마지막 무게 기준 판정)")
            if t["stalled"]:
                marks.append("🔴 3회 정체")
            hist = " ← ".join(
                f"{r['date'][5:]}: " + " / ".join(f"{_fmt_w(s['w'])}×{s['reps']}" for s in r["sets"])
                for r in t["records"]) or "기록 없음"
            L.append(f"- {t['n']} [{t['baseline']['cls']}] {t['baseline']['text']}"
                     + (f"  ⚑ {', '.join(marks)}" if marks else ""))
            L.append(f"    최근: {hist}")

    L.append("\n## 영양 (최근 기록 3일, 최소 충족: 2700kcal·단백질 130g·지방 55g)")
    ns = nutrition_summary(load_nutrition(), ref)
    for day in ns["days"]:
        L.append(f"- {day['date']}: {day['kcal']}kcal ({'✅' if day['ok_kcal'] else '⚠️'}"
                 f"{' · 🔺상한초과' if day['over_cap'] else ''}) · "
                 f"단백질 {day['p']}g ({'✅' if day['ok_p'] else '⚠️'}) · "
                 f"지방 {day['f']}g ({'✅' if day['ok_f'] else '⚠️'})")
    if ns["ref_recorded"]:
        L.append(f"- 연속 미달일: {ns['consec_shortfall']}일"
                 + (" → 2일↑이면 증량 보류, 3일↑이면 볼륨 조정 검토 (프로토콜 4절)" if ns["consec_shortfall"] >= 2 else ""))
    else:
        L.append(f"- 연속 미달일: 판정 불가 — {ref} 기록 없음")

    L.append(f"\n## 체중 (목표 +{WEIGHT_TARGET_KG_PER_MONTH}kg/월, 0.6~0.8 밴드)")
    wsum = weight_summary(load_weight(), ref)
    if wsum:
        pace = f"{wsum['monthly_pace']:+.2f}kg/월" if wsum["monthly_pace"] is not None else "계산 불가"
        L.append(f"- 최근 {wsum['last']['date']}: {wsum['last']['kg']}kg · 페이스 {pace}")
        if wsum["monthly_pace"] is not None and wsum["monthly_pace"] > WEIGHT_TARGET_KG_PER_MONTH * 1.5:
            L.append(f"- ⚠️ 페이스가 목표 밴드보다 빠름 — 서프러스(칼로리 상한 {KCAL_SOFT_CAP}kcal) 점검 권장")
        if wsum["stale_days"] > 7:
            L.append(f"- ⚠️ 체중 기록 {wsum['stale_days']}일째 없음 — 측정 권장")
    else:
        L.append("- 기록 없음")

    L.append("\n## 컨디션 (최근 7일)")
    cf = condition_flags(load_condition(), ref)
    if cf["open_pain"]:
        for p in cf["open_pain"]:
            L.append(f"- 🩹 {p['date']} {p['site']} {p['level']}" + (f" — {p.get('note', '')}" if p.get("note") else ""))
        L.append("- → 체크인에서 위 통증의 현재 상태를 콕 집어 확인할 것")
    elif not cf["recent"]:
        L.append("- 기록 없음")
    else:
        L.append("- 특이사항 없음")
    return "\n".join(L)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="FORGE40 추천 전 분석 리포트")
    ap.add_argument("--date", default=_date.today().isoformat(), help="기준일 YYYY-MM-DD (기본: 오늘)")
    args = ap.parse_args()
    print(build_report(args.date))
