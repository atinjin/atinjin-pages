# AI 코칭 프로토콜 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "오늘 운동 추천해줘" 요청 시 AI가 따르는 정밀 추천 체계 — 분석 스크립트(`muscle/tools/analyze.py`) + 운영 매뉴얼(`muscle/COACHING-PROTOCOL.md`) + 컨디션 기록(`muscle/log/condition-history.json`) — 를 구축한다.

**Architecture:** 세기·집계·추세 감지는 파이썬 스크립트가 결정론적으로 수행하고, AI는 그 출력과 대화 체크인을 놓고 판단만 한다. 종목 메타데이터(근육군·반복범위·증량스텝)는 `muscle/log/index.html`의 `SESSIONS` 상수가 단일 진실 공급원이며, 스크립트가 이를 직접 파싱한다(파싱 실패 시 즉시 에러 종료).

**Tech Stack:** Python 3 표준 라이브러리만 (json, re, argparse, datetime, unittest). 외부 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-08-14-ai-coaching-protocol-design.md`

## Global Constraints

- 외부 패키지 금지 — python3 표준 라이브러리만 사용
- `muscle/log/index.html`의 JS 로직·UI는 절대 수정하지 않는다 (파싱 대상일 뿐)
- 근육군 매핑·종목 정의를 스크립트에 하드코딩(중복)하지 않는다 — HTML 파싱만
- SESSIONS/WEEKDAY_MAP 파싱 실패 시 조용히 넘어가지 않고 `SystemExit`(비0 종료)
- 볼륨·빈도 기준값은 ACSM 문서 그대로: 부위별 주 10세트↑ · 주 2회↑
- 영양 목표는 v12 그대로: kcal 2700↑ · 단백질 130g↑ · 지방 55g↑ (최소 충족), 탄수 375g은 참고용
- 체중 페이스 목표: +0.3kg/월
- 테스트 실행: `cd muscle/tools && python3 -m unittest test_analyze -v`
- 모든 사용자 대면 텍스트(스크립트 출력·문서)는 한국어

## File Structure

| 파일 | 책임 |
|---|---|
| `muscle/tools/analyze.py` | 전체 분석 스크립트 (파서 + 집계 + 추세 + 리포트, 단일 파일) |
| `muscle/tools/test_analyze.py` | unittest 테스트 (실제 커밋 JSON을 픽스처로 사용) |
| `muscle/log/condition-history.json` | 체크인 기록 (초기값 `[]`) |
| `muscle/COACHING-PROTOCOL.md` | 운영 매뉴얼 (AI가 따르는 절차 전문) |
| `muscle/ACSM-GUIDELINES.md` (수정) | 8절 도입부에 위임 문구 1줄 |
| `muscle/CHANGELOG.md` (수정) | v15 결정 기록 |

경로 규칙: `analyze.py`는 `Path(__file__).resolve().parent.parent`(= `muscle/`)를 기준으로 `log/*.json`과 `log/index.html`을 찾는다. 어느 디렉토리에서 실행해도 동작한다.

---

### Task 1: SESSIONS/WEEKDAY_MAP 파서

**Files:**
- Create: `muscle/tools/analyze.py`
- Create: `muscle/tools/test_analyze.py`

**Interfaces:**
- Produces: `load_sessions() -> tuple[dict, dict]` — `(sessions, weekday_map)`.
  - `sessions`: 키 `"upperA"` 등 → `{"name": str, "ex": [{"n": str, "sets": int, "m": str, "lo": int, "hi": int, "inc": float, "alias": list[str] (없으면 키 없음), "assist": bool (없으면 키 없음), "start": str, ...}], "cardio": bool (유산소만)}`
  - `weekday_map`: `{2: "upperA", 3: "lowerA", ...}` (int 키)
- Produces: `MUSCLE_DIR: Path` (= `muscle/`), `parse_js_object(src: str) -> object`

- [ ] **Step 1: 실패하는 테스트 작성**

`muscle/tools/test_analyze.py`:

```python
import unittest
import analyze


class TestParser(unittest.TestCase):
    def test_load_sessions_reads_real_html(self):
        sessions, weekday_map = analyze.load_sessions()
        # 5개 웨이트 세션 + 유산소 3종
        for k in ["upperA", "lowerA", "upperB", "lowerB", "upperM", "running", "swim", "other"]:
            self.assertIn(k, sessions)
        bench = next(e for e in sessions["upperA"]["ex"] if e["n"] == "벤치프레스")
        self.assertEqual(bench["m"], "chest")
        self.assertEqual(bench["lo"], 5)
        self.assertEqual(bench["hi"], 8)
        self.assertEqual(bench["inc"], 2.5)
        # alias 파싱 확인
        pullup = next(e for e in sessions["upperB"]["ex"] if e.get("assist"))
        self.assertIn("어시스트 풀업", pullup["alias"])
        # weekday_map: int 키
        self.assertEqual(weekday_map[2], "upperA")
        self.assertEqual(weekday_map[1], "other")

    def test_parse_failure_exits(self):
        with self.assertRaises(SystemExit):
            analyze.parse_js_object("const X = { broken: ")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd muscle/tools && python3 -m unittest test_analyze -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'analyze'`)

- [ ] **Step 3: 최소 구현**

`muscle/tools/analyze.py`:

```python
#!/usr/bin/env python3
"""FORGE40 추천 전 분석 스크립트 — 집계·추세는 여기서, 판단은 AI가.

사용법: python3 muscle/tools/analyze.py [--date YYYY-MM-DD]
종목 메타데이터는 muscle/log/index.html의 SESSIONS 상수를 직접 파싱한다(중복 금지).
파싱 실패 시 즉시 에러 종료한다 — HTML 형식이 바뀌면 여기서 바로 드러나야 한다.
"""
import json
import re
import sys
from pathlib import Path

MUSCLE_DIR = Path(__file__).resolve().parent.parent   # .../muscle
LOG_DIR = MUSCLE_DIR / "log"


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


if __name__ == "__main__":
    s, w = load_sessions()
    print(f"세션 {len(s)}개, 요일 매핑 {len(w)}개 파싱 완료")
```

주의: `_js_to_json`의 독스트링에 오타(러시아어 자동완성 등)가 섞이지 않게 그대로 옮겨 적되, "트레일링 콤마"로 표기한다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd muscle/tools && python3 -m unittest test_analyze -v`
Expected: PASS (2 tests)

`WEEKDAY_MAP` 추출이 `{...}` 블록 대응 방식이므로 한 줄짜리 `{ 2:"upperA", ... }`에도 동작하는지 이 테스트가 검증한다.

- [ ] **Step 5: 커밋**

```bash
git add muscle/tools/analyze.py muscle/tools/test_analyze.py
git commit -m "feat(tools): SESSIONS/WEEKDAY_MAP HTML parser for analyze.py"
```

---

### Task 2: 데이터 로드 + 주간 볼륨 + 세션 빈도

**Files:**
- Modify: `muscle/tools/analyze.py`
- Modify: `muscle/tools/test_analyze.py`
- Create: `muscle/log/condition-history.json` (내용: `[]`)

**Interfaces:**
- Consumes: `load_sessions()`, `MUSCLE_DIR`, `LOG_DIR` (Task 1)
- Produces:
  - `load_history() / load_nutrition() / load_weight() / load_condition() -> list` — 각 JSON 로드(파일 없으면 SystemExit)
  - `recent(items: list, ref: str, days: int) -> list` — `date` 필드가 `[ref-(days-1), ref]` 범위(포함)인 항목
  - `exercise_index(sessions) -> dict[str, dict]` — 종목명·별칭 → ex 정의(별칭도 키로 등록)
  - `weekly_volume(log: list, sessions: dict, ref: str) -> dict` — `{"by_muscle": {m: {"sets": int, "days": int}}, "unknown": [운동명,...]}` (최근 7일, days=해당 근육을 만진 서로 다른 날짜 수)
  - `session_frequency(log: list, ref: str) -> dict` — `{"recent": [(date, session_key), ...] 최신순, "missing": [7일간 안 나온 웨이트 세션 키]}` (웨이트 세션 = upperA/lowerA/upperB/lowerB)

- [ ] **Step 1: condition-history.json 생성**

`muscle/log/condition-history.json` 내용:

```json
[]
```

- [ ] **Step 2: 실패하는 테스트 작성**

`test_analyze.py`에 추가:

```python
class TestAggregation(unittest.TestCase):
    def setUp(self):
        self.sessions, _ = analyze.load_sessions()
        self.log = analyze.load_history()

    def test_recent_window_inclusive(self):
        items = [{"date": "2026-08-07"}, {"date": "2026-08-08"}, {"date": "2026-08-14"}]
        got = analyze.recent(items, "2026-08-14", 7)
        self.assertEqual([x["date"] for x in got], ["2026-08-08", "2026-08-14"])

    def test_weekly_volume_reflects_0813_lowerA(self):
        # 2026-08-13 하체A: 스미스 머신 스쿼트 3세트(quad) + 고블릿 없음, RDL 4세트(hamstring) 등
        vol = analyze.weekly_volume(self.log, self.sessions, "2026-08-14")
        self.assertGreaterEqual(vol["by_muscle"]["quad"]["sets"], 3)
        self.assertGreaterEqual(vol["by_muscle"]["hamstring"]["sets"], 4)
        # "스미스 머신 힙 쓰러스트"는 SESSIONS에 없음 → unknown으로 보고돼야 함
        self.assertIn("스미스 머신 힙 쓰러스트", vol["unknown"])

    def test_session_frequency_missing(self):
        freq = analyze.session_frequency(self.log, "2026-08-14")
        keys = [k for _, k in freq["recent"]]
        self.assertIn("lowerA", keys)          # 8/13 기록 존재
        for k in freq["missing"]:
            self.assertNotIn(k, keys)

    def test_condition_file_loads(self):
        self.assertIsInstance(analyze.load_condition(), list)
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd muscle/tools && python3 -m unittest test_analyze -v`
Expected: FAIL (`AttributeError: module 'analyze' has no attribute 'load_history'` 등)

- [ ] **Step 4: 구현**

`analyze.py`에 추가:

```python
from datetime import date as _date, timedelta

WEIGHT_SESSIONS = ["upperA", "lowerA", "upperB", "lowerB"]  # 주간 빈도 감사 대상


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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd muscle/tools && python3 -m unittest test_analyze -v`
Expected: PASS (Task 1 포함 6 tests)

주의: `test_weekly_volume_reflects_0813_lowerA`는 실행 시점의 실제 `history.json`에 의존한다. 8/13 하체A 세션(`id: 20260813-lowerA`)이 있는 현재 커밋 기준으로 작성됐다 — 만약 데이터가 갱신돼 실패하면 단언 값만 현행 데이터에 맞게 조정한다(로직 버그가 아님).

- [ ] **Step 6: 커밋**

```bash
git add muscle/tools/analyze.py muscle/tools/test_analyze.py muscle/log/condition-history.json
git commit -m "feat(tools): weekly volume + session frequency aggregation"
```

---

### Task 3: 종목별 추세 + 베이스라인 추천 (recommend() 포팅)

**Files:**
- Modify: `muscle/tools/analyze.py`
- Modify: `muscle/tools/test_analyze.py`

**Interfaces:**
- Consumes: `_sets_of`, `exercise_index`, `load_history` (Task 2)
- Produces:
  - `pattern_of(sets: list) -> str` — `"uniform" | "ramp" | "drop"` (ramp=무게가 세트 순서상 비내림, drop=이전 세트보다 가벼워진 세트 존재)
  - `history_for(log, ex, n=4) -> list` — 해당 종목(별칭 포함) 최근 n회 기록, 최신순. 각 항목 `{"date": str, "sets": [{"w","reps"}]}`
  - `baseline(ex: dict, sets: list) -> dict` — `{"cls": "new|up|down|hold", "text": str}` — log/index.html `recommend()`와 동일 결론
  - `is_stalled(records: list) -> bool` — 최근 3회 연속 진전 없음(상단 무게↑도, 상단 무게 동률에서 반복↑도 없음)
  - `exercise_trends(log, sessions, session_key: str) -> list[dict]` — 세션의 종목별 `{"n", "records", "pattern", "stalled", "baseline"}`

- [ ] **Step 1: 실패하는 테스트 작성**

`test_analyze.py`에 추가:

```python
class TestTrends(unittest.TestCase):
    EX = {"n": "테스트", "sets": 3, "m": "chest", "lo": 5, "hi": 8, "inc": 2.5, "start": "40kg"}

    def test_pattern_classification(self):
        self.assertEqual(analyze.pattern_of([{"w": 40, "reps": 8}] * 3), "uniform")
        self.assertEqual(analyze.pattern_of(
            [{"w": 30, "reps": 12}, {"w": 40, "reps": 10}, {"w": 40, "reps": 10}]), "ramp")
        self.assertEqual(analyze.pattern_of(
            [{"w": 40, "reps": 8}, {"w": 40, "reps": 6}, {"w": 35, "reps": 8}]), "drop")

    def test_baseline_matches_js_recommend(self):
        # 전 세트 상한 도달 → 증량
        r = analyze.baseline(self.EX, [{"w": 40, "reps": 8}] * 3)
        self.assertEqual(r["cls"], "up")
        self.assertIn("42.5", r["text"])
        # 하한 미달 → 감량
        r = analyze.baseline(self.EX, [{"w": 40, "reps": 4}] * 3)
        self.assertEqual(r["cls"], "down")
        self.assertIn("37.5", r["text"])
        # 드롭(램프 포함, JS와 동일) → 상단 무게 전 세트 채우기
        r = analyze.baseline(self.EX, [{"w": 30, "reps": 12}, {"w": 40, "reps": 10}])
        self.assertEqual(r["cls"], "hold")
        self.assertIn("40", r["text"])
        # 기록 없음 → 시작값
        r = analyze.baseline(self.EX, [])
        self.assertEqual(r["cls"], "new")

    def test_baseline_assist_reversed(self):
        ex = dict(self.EX, assist=True, inc=5, lo=6, hi=10)
        # 보조 최소 무게 기준 상한 도달 → 보조를 줄임(↓)
        r = analyze.baseline(ex, [{"w": 30, "reps": 10}] * 3)
        self.assertEqual(r["cls"], "up")
        self.assertIn("25", r["text"])

    def test_is_stalled(self):
        same = {"date": "d", "sets": [{"w": 40, "reps": 6}] * 3}
        self.assertTrue(analyze.is_stalled([same, same, same]))
        progressed = [
            {"date": "d3", "sets": [{"w": 40, "reps": 7}] * 3},
            {"date": "d2", "sets": [{"w": 40, "reps": 6}] * 3},
            {"date": "d1", "sets": [{"w": 40, "reps": 6}] * 3},
        ]
        self.assertFalse(analyze.is_stalled(progressed))
        self.assertFalse(analyze.is_stalled([same, same]))  # 3회 미만이면 판정 안 함

    def test_exercise_trends_real_data(self):
        sessions, _ = analyze.load_sessions()
        log = analyze.load_history()
        trends = analyze.exercise_trends(log, sessions, "lowerA")
        names = [t["n"] for t in trends]
        self.assertIn("스미스 머신 스쿼트", names)
        sq = next(t for t in trends if t["n"] == "스미스 머신 스쿼트")
        self.assertTrue(sq["records"])          # 8/13 기록 존재
        self.assertIn(sq["pattern"], ("uniform", "ramp", "drop"))
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd muscle/tools && python3 -m unittest test_analyze -v`
Expected: FAIL (`AttributeError: ... 'pattern_of'`)

- [ ] **Step 3: 구현**

`analyze.py`에 추가:

```python
def _fmt_w(v):
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def pattern_of(sets):
    ws = [s["w"] for s in sets]
    if len(set(ws)) <= 1:
        return "uniform"
    return "ramp" if all(a <= b for a, b in zip(ws, ws[1:])) else "drop"


def history_for(log, ex, n=4):
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
    """log/index.html recommend()의 파이썬 포팅 — 결론이 반드시 동일해야 한다."""
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd muscle/tools && python3 -m unittest test_analyze -v`
Expected: PASS (11 tests)

- [ ] **Step 5: 커밋**

```bash
git add muscle/tools/analyze.py muscle/tools/test_analyze.py
git commit -m "feat(tools): per-exercise trend, stall detection, baseline port of recommend()"
```

---

### Task 4: 영양·체중·컨디션 요약

**Files:**
- Modify: `muscle/tools/analyze.py`
- Modify: `muscle/tools/test_analyze.py`

**Interfaces:**
- Consumes: `recent`, `load_nutrition`, `load_weight`, `load_condition` (Task 2)
- Produces:
  - `NUT_TARGET = {"kcal": 2700, "p": 130, "f": 55}` (최소 충족 목표; 탄수는 참고라 제외)
  - `nutrition_summary(nut, ref) -> dict` — `{"days": [{"date", "kcal", "p", "f", "ok_kcal": bool, "ok_p": bool}] 최근 3일 최신순, "consec_shortfall": int}` (shortfall=kcal 또는 단백질 미달인 날이 ref에서 거슬러 연속 몇 일인지; 기록 없는 날은 판정 불가로 연속 계산 중단)
  - `weight_summary(weights, ref) -> dict | None` — `{"last": {"date","kg"}, "monthly_pace": float | None, "stale_days": int}` (pace는 최근 14일 구간 환산, 데이터 2개 미만이면 None; stale_days=마지막 기록 후 경과일)
  - `condition_flags(conds, ref) -> dict` — `{"recent": 최근 7일 기록 리스트, "open_pain": [{"date","site","level","note"}]}` (open_pain=최근 7일 내 pain 항목 전부, 최신순)

- [ ] **Step 1: 실패하는 테스트 작성**

`test_analyze.py`에 추가:

```python
class TestSummaries(unittest.TestCase):
    def test_nutrition_consecutive_shortfall(self):
        nut = [
            {"date": "2026-08-12", "kcal": 2000, "p": 100, "f": 40},
            {"date": "2026-08-13", "kcal": 2800, "p": 140, "f": 60},
            {"date": "2026-08-14", "kcal": 2000, "p": 100, "f": 40},
        ]
        s = analyze.nutrition_summary(nut, "2026-08-14")
        self.assertEqual(s["consec_shortfall"], 1)   # 8/14만 미달, 8/13 충족에서 끊김
        self.assertEqual(s["days"][0]["date"], "2026-08-14")
        self.assertFalse(s["days"][0]["ok_p"])

    def test_nutrition_sums_multiple_meals(self):
        nut = [
            {"date": "2026-08-14", "kcal": 1500, "p": 70, "f": 30},
            {"date": "2026-08-14", "kcal": 1400, "p": 70, "f": 30},
        ]
        s = analyze.nutrition_summary(nut, "2026-08-14")
        self.assertEqual(s["days"][0]["kcal"], 2900)
        self.assertTrue(s["days"][0]["ok_kcal"])
        self.assertEqual(s["consec_shortfall"], 0)

    def test_weight_pace_and_staleness(self):
        w = [{"date": "2026-07-17", "kg": 65.0}, {"date": "2026-07-31", "kg": 65.4}]
        s = analyze.weight_summary(w, "2026-08-14")
        self.assertEqual(s["last"]["kg"], 65.4)
        self.assertAlmostEqual(s["monthly_pace"], 0.4 / 14 * 30, places=2)
        self.assertEqual(s["stale_days"], 14)
        self.assertIsNone(analyze.weight_summary([], "2026-08-14"))

    def test_condition_flags(self):
        conds = [
            {"date": "2026-08-13", "pain": [{"site": "어깨", "level": "mild", "note": "숄더프레스"}]},
            {"date": "2026-08-01", "pain": [{"site": "무릎", "level": "mild"}]},  # 7일 밖
            {"date": "2026-08-14", "normal": True},
        ]
        f = analyze.condition_flags(conds, "2026-08-14")
        self.assertEqual(len(f["open_pain"]), 1)
        self.assertEqual(f["open_pain"][0]["site"], "어깨")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd muscle/tools && python3 -m unittest test_analyze -v`
Expected: FAIL (`AttributeError: ... 'nutrition_summary'`)

- [ ] **Step 3: 구현**

`analyze.py`에 추가:

```python
NUT_TARGET = {"kcal": 2700, "p": 130, "f": 55}   # v12: 최소 충족 목표(탄수는 참고용이라 제외)
WEIGHT_TARGET_KG_PER_MONTH = 0.3


def nutrition_summary(nut, ref):
    by_day = {}
    for x in nut:
        d = by_day.setdefault(x["date"], {"kcal": 0, "p": 0.0, "f": 0.0})
        d["kcal"] += x.get("kcal", 0)
        d["p"] += x.get("p", 0)
        d["f"] += x.get("f", 0)

    days = []
    for d in sorted(by_day, reverse=True):
        if d > ref:
            continue
        t = by_day[d]
        days.append({"date": d, "kcal": round(t["kcal"]), "p": round(t["p"], 1), "f": round(t["f"], 1),
                     "ok_kcal": t["kcal"] >= NUT_TARGET["kcal"], "ok_p": t["p"] >= NUT_TARGET["p"]})
        if len(days) == 3:
            break

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
    return {"days": days, "consec_shortfall": consec}


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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd muscle/tools && python3 -m unittest test_analyze -v`
Expected: PASS (15 tests)

- [ ] **Step 5: 커밋**

```bash
git add muscle/tools/analyze.py muscle/tools/test_analyze.py
git commit -m "feat(tools): nutrition/weight/condition summaries"
```

---

### Task 5: CLI + 통합 리포트 출력

**Files:**
- Modify: `muscle/tools/analyze.py` (기존 `if __name__` 블록 교체)
- Modify: `muscle/tools/test_analyze.py`

**Interfaces:**
- Consumes: Task 1~4의 모든 함수
- Produces: `build_report(ref: str) -> str` — 전체 리포트 텍스트. CLI: `python3 muscle/tools/analyze.py [--date YYYY-MM-DD]` (기본값 오늘)

- [ ] **Step 1: 실패하는 테스트 작성**

`test_analyze.py`에 추가:

```python
class TestReport(unittest.TestCase):
    def test_build_report_sections(self):
        r = analyze.build_report("2026-08-14")
        for header in ["오늘 기준", "주간 볼륨", "세션 빈도", "종목별 추세",
                       "영양", "체중", "컨디션"]:
            self.assertIn(header, r)
        self.assertIn("lowerA", r)        # 8/13 기록 반영
        self.assertIn("스미스 머신 힙 쓰러스트", r)  # unknown 종목 노출

    def test_cli_runs(self):
        import subprocess, sys as _sys
        p = subprocess.run([_sys.executable, "analyze.py", "--date", "2026-08-14"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("주간 볼륨", p.stdout)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd muscle/tools && python3 -m unittest test_analyze -v`
Expected: FAIL (`AttributeError: ... 'build_report'`)

- [ ] **Step 3: 구현**

`analyze.py`의 기존 `if __name__ == "__main__":` 블록을 아래로 교체:

```python
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

    L.append("\n## 영양 (최근 3일, 최소 충족: 2700kcal·단백질 130g·지방 55g)")
    ns = nutrition_summary(load_nutrition(), ref)
    for day in ns["days"]:
        L.append(f"- {day['date']}: {day['kcal']}kcal ({'✅' if day['ok_kcal'] else '⚠️'}) · "
                 f"단백질 {day['p']}g ({'✅' if day['ok_p'] else '⚠️'}) · 지방 {day['f']}g")
    L.append(f"- 연속 미달일: {ns['consec_shortfall']}일"
             + (" → 2일↑이면 증량 보류, 3일↑이면 볼륨 조정 검토 (프로토콜 6절)" if ns["consec_shortfall"] >= 2 else ""))

    L.append("\n## 체중 (목표 +0.3kg/월)")
    wsum = weight_summary(load_weight(), ref)
    if wsum:
        pace = f"{wsum['monthly_pace']:+.2f}kg/월" if wsum["monthly_pace"] is not None else "계산 불가"
        L.append(f"- 최근 {wsum['last']['date']}: {wsum['last']['kg']}kg · 페이스 {pace}")
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
```

- [ ] **Step 4: 테스트 통과 + 실물 출력 확인**

Run: `cd muscle/tools && python3 -m unittest test_analyze -v`
Expected: PASS (17 tests)

Run: `python3 muscle/tools/analyze.py --date 2026-08-14`
Expected: 7개 섹션이 모두 보이고, 8/13 하체A가 빈도·추세에 반영돼 있으며, 체중 stale 경고(7/31 이후 공백)가 뜬다. 출력을 눈으로 훑어 어색한 라벨·깨진 표기를 잡는다.

- [ ] **Step 5: 커밋**

```bash
git add muscle/tools/analyze.py muscle/tools/test_analyze.py
git commit -m "feat(tools): analyze.py CLI + integrated pre-recommendation report"
```

---

### Task 6: COACHING-PROTOCOL.md 작성

**Files:**
- Create: `muscle/COACHING-PROTOCOL.md`

**Interfaces:**
- Consumes: analyze.py CLI (Task 5), condition-history.json 스키마 (Task 2)
- Produces: AI가 추천 시 따르는 운영 매뉴얼 전문

- [ ] **Step 1: 문서 작성**

`muscle/COACHING-PROTOCOL.md` 전문:

````markdown
# FORGE40 코칭 프로토콜 — "오늘 운동 추천" 운영 매뉴얼

AI(Claude)가 "오늘 운동 추천해줘" 류 요청을 받으면 **이 문서의 절차를 그대로** 따른다.
근거(왜 이렇게 하는지)는 [ACSM-GUIDELINES.md](ACSM-GUIDELINES.md), 결정 이력은 [CHANGELOG.md](CHANGELOG.md).

## 0. 절차 요약 (8단계)

1. `python3 muscle/tools/analyze.py` 실행 — **수치 암산 금지**, 집계·추세·베이스라인은 전부 스크립트 출력 사용
2. 한 메시지 체크인 (§1) — 직전 이상 신호가 있으면 그 항목만 콕 집어 되묻기
3. 세션 결정 — 요일 기본값보다 최근 7일 공백 보충 우선 (v14: 빠진 세션은 가장 빠른 기회에)
4. 조정 매트릭스 적용 (§3) — 우선순위: 통증 > 시간 > 피로/수면
5. 종목별 중량 = 스크립트 베이스라인 + 오버라이드 규칙 (§5, 사유 명시 필수)
6. 영양 연동 블록 (§4, 해당 시)
7. 고정 출력 형식으로 제시 (§6)
8. 체크인 내용을 `muscle/log/condition-history.json`에 append (§2)

## 1. 체크인 (한 메시지)

스크립트 실행 후, 추천 전에 **딱 한 번** 묻는다:

> 수면·통증·피로·가용 시간에 특이사항 있으면 알려주세요. 없으면 "평소대로"라고 하시면 됩니다.
> (직전 기록에 통증 등 이상 신호가 있으면: "지난번 ○○ 통증은 지금 어떤가요?"를 덧붙인다)

- "평소대로" / 무언급 항목 → 정상으로 간주하고 바로 진행.
- 추가 질문으로 늘어지지 않는다. 이 한 번이 전부.

## 2. condition-history.json 기록 규칙

언급된 필드만 기록한다. 특이사항 없는 날은 `{"date": "...", "normal": true}` 한 줄.

```json
{
  "date": "2026-08-14",
  "sleepH": 5,
  "fatigue": "high",
  "pain": [{"site": "어깨", "level": "mild", "note": "숄더프레스 시 불편"}],
  "timeMin": 40,
  "note": "전날 회식"
}
```

- `fatigue`: `low | normal | high` · `pain[].level`: `mild | moderate | severe`
- 추천 대화가 끝나기 전에 append한다 (배열 끝에 추가, 날짜 중복 시 그날 항목을 갱신).

## 3. Readiness 조정 매트릭스

원칙: **세션 통째 취소는 최후 수단** — 벌크업 집중기이므로 축소·대체로 소화한다.
우선순위: **통증 > 시간 > 피로/수면** (안전 > 현실 제약 > 최적화).

| 신호 | 조치 |
|---|---|
| 수면 ≤5h 또는 피로 high | 핵심 종목 유지 + RIR 3으로 여유(증량 보류) · 보조 종목 2→1세트 또는 생략 |
| 통증 mild | 해당 부위에 직접 부하 걸리는 종목만 대체(§3.1) · 나머지 정상 진행 |
| 통증 moderate 이상 | 해당 부위 완전 회피 + 다른 부위 세션으로 교체 제안 · 반복되면 병원 권유 |
| 가용 시간 부족 | 핵심 종목만 남기고 보조 컷 — **종목 수를 줄이지, 무게를 줄이지 않는다** |
| 빠진 세션 감지 | 가장 빠른 다음 기회에 최우선 보충 (v14) |
| 3회 연속 정체 | 원인 순서대로 점검: ① 수면·영양 ② 드롭 패턴 ③ 디로드 시점(6~8주) — 무작정 증량 금지 |
| 사용자 본인이 보고한 관절 이력 | 일반론보다 항상 우선 (ACSM 8절 5항) |

핵심 종목(v11, 축소 금지): 화 벤치프레스·버티컬 트랙션 / 수 스미스 스쿼트·덤벨 RDL·글루트 / 금 인클라인 덤벨 프레스·어시스트 풀업·랫풀다운 / 토 글루트·스미스 RDL·고블릿 스쿼트

### 3.1 통증 부위별 대체 테이블

| 부위 | 제외/주의 | 대체 |
|---|---|---|
| 어깨 | 숄더 프레스·레터럴 레이즈·딥스 제외 | 가슴은 체스트 프레스(가동범위 짧게)·펙토랄 플라이로, 등은 로우 계열 유지. 심하면 하체 세션으로 스왑 |
| 무릎 | 스쿼트류·레그 익스텐션 계열 제외 | 힙 힌지(덤벨/스미스 RDL)·글루트·어브덕터로 하체 볼륨 유지 + 무릎 5원칙 웜업 |
| 허리 | 데드리프트·RDL·로우백·복근 크런치 제외 | 머신 위주(글루트·레그 컬·체스트 프레스 등) — 척추 압박 없는 종목만 |
| 손목·팔꿈치 | 바벨 종목(벤치·바벨컬) 제외 | 같은 근육군의 머신/덤벨 중립 그립 종목으로 |
| 발목·종아리 | 카프 레이즈·러닝 제외 | 유산소는 수영·자전거로 |

## 4. 영양 연동 (훈련 유지 + 식사 보정)

판정 기준(v12): 최소 충족 — kcal 2700↑ · 단백질 130g↑ · 지방 55g↑. 탄수는 참고용.
스크립트의 "연속 미달일"을 기준으로:

| 연속 미달 | 훈련 | 식사 |
|---|---|---|
| 1일 | 그대로 | 출력에 "식사 보정" 블록: 운동 전 탄수(바나나·주먹밥 등) + 운동 후 단백질, 부족분을 g/kcal 단위로 |
| 2일 | 유지하되 **증량 제안 보류**(전 세션 무게 반복) | 보정 강화 |
| 3일↑ | 보조 종목 축소 언급 | 미달이 구조적인지(입맛·일정) 대화로 원인 확인 |

당일: 마지막 식사가 운동 3시간 이상 전이면 운동 전 간식 제안.
지방·탄수는 그램 초과를 지적하지 않고 **출처·질**(불포화 vs 포화, 정제당)을 코멘트한다.

## 5. 중량 오버라이드 규칙

스크립트 베이스라인(이중 점진법)이 출발점. 아래 상황에서만 바꾸고, **바꾸면 사유를 표에 명시**한다.

| 상황 (스크립트 ⚑ 플래그) | 오버라이드 |
|---|---|
| 드롭 (40→40→35) | 증량 대신 "상단 무게로 전 세트 채우기" (베이스라인이 이미 이 결론 — 그대로 따름) |
| 램프업 (30→40→40) | **마지막 무게 기준으로 판정** — 첫 세트는 웜업으로 간주. 베이스라인의 "전 세트 채우기"가 과하게 보수적이면 여기서 조정 |
| 추세 상승 + 컨디션 정상 | 베이스라인 그대로 (잘 되는 건 건드리지 않는다) |
| 정체 + 컨디션 신호 있음 | §3 매트릭스 우선 — 무게 문제로 해석하지 않음 |
| 정체 + 컨디션 정상 + 6~8주 경과 | 디로드 주 제안 (무게 −10~15%, 1주) |
| 직전 기록이 반복 상한 크게 초과 (lo5~hi8에 15회 등) | 초기 무게 오류로 보고 1스텝 초과 증량 가능 — 단, RIR 확인 질문 후 |
| 첫 시도 종목 | `start` 값 + 유사 종목 기록으로 보수적 제안, 첫 세트에서 조정 안내 |

**금지**: 실패까지 밀라는 안내(RIR 1~3 유지) · 기구 우열 뉘앙스 · 복잡한 주기화 도입.

## 6. 출력 형식 (고정)

```
## 오늘의 추천 — {날짜} {세션명}

**판단 근거**: (스크립트 요약 + 체크인 핵심 2~3줄)

| 종목 | 무게×반복×세트 | 전회 기록 | 조정 사유 |
|---|---|---|---|

**식사 보정** (해당 시에만): …
**주의** (통증 대체·웜업 등 해당 시에만): …
```

- "조정 사유"에는 "베이스라인 그대로"인지, 무엇 때문에 바꿨는지가 항상 보이게 한다.
- 그날만의 이슈(장비 고장 등)는 프로그램을 바꾸지 않고 임시 대체만 제안한다 (ACSM 8절 6항).
````

- [ ] **Step 2: 자기 점검**

스펙 10절의 모호성 체크: 4가지 시나리오(정상일 / 수면부족일 / 통증일 / 영양미달일)를 각각 이 문서만 보고 머릿속으로 실행해, 추천이 한 가지로 결정되는지 확인한다. 두 갈래로 갈리는 문장이 있으면 즉시 수정.

- [ ] **Step 3: 커밋**

```bash
git add muscle/COACHING-PROTOCOL.md
git commit -m "docs(muscle): add COACHING-PROTOCOL.md — AI recommendation operating manual"
```

---

### Task 7: ACSM 위임 문구 + CHANGELOG v15

**Files:**
- Modify: `muscle/ACSM-GUIDELINES.md` (8절 도입부)
- Modify: `muscle/CHANGELOG.md` (v15 추가)

- [ ] **Step 1: ACSM-GUIDELINES.md 8절에 위임 문구 추가**

8절 제목 바로 아래("## 8. "오늘 운동 프로그램" 생성 절차" 다음 줄)에 삽입:

```markdown
> **2026-08-14부터**: 이 절차의 상세 운영 버전은 [COACHING-PROTOCOL.md](COACHING-PROTOCOL.md)를 따른다 — 분석 스크립트(`muscle/tools/analyze.py`) 실행, 컨디션 체크인, 조정 매트릭스, 영양 연동이 추가됐다. 아래 1~7항은 근거 원칙으로 유지된다.
```

- [ ] **Step 2: CHANGELOG.md에 v15 추가**

파일 끝에 추가:

```markdown
## v15 — AI 코칭 프로토콜: 컨디션·영양·추세를 반영한 정밀 추천 체계
- **입력**: "기존 기록, 식단, 영양 상태, 그날 그날의 특이점 등을 고려하여 AI에게 어떻게 추천하면 좋을지 지시하는 방안을 마련한다"
- **구성** (C안 — 프로토콜 문서 + 분석 스크립트):
  - `muscle/COACHING-PROTOCOL.md` — 운영 매뉴얼: 8단계 절차, 한 메시지 체크인, Readiness 조정 매트릭스(통증>시간>피로), 통증 부위별 대체 테이블, 영양 연동(훈련 유지+식사 보정), 중량 오버라이드 규칙, 고정 출력 형식
  - `muscle/tools/analyze.py` — 추천 전 필수 실행 스크립트: 주간 부위별 볼륨(ACSM 10세트↑·2일↑ 대비), 세션 공백 감지, 종목별 추세(드롭/램프/3회 정체)와 이중 점진법 베이스라인, 영양 연속 미달일, 체중 페이스, 컨디션 플래그. 종목 메타데이터는 `log/index.html`의 SESSIONS를 직접 파싱(중복 없음, 파싱 실패 시 즉시 에러)
  - `muscle/log/condition-history.json` — 체크인 기록 누적 (언급된 필드만, 정상일은 `normal: true` 한 줄)
- **역할 분담**: 세기·집계·추세 감지는 스크립트(결정론), 판단(종목 대체·RIR 조정·식사 보정)은 AI. "수치 암산 금지"를 프로토콜에 명시.
- **영양 개입 방향**: 벌크업 중이므로 미달 시에도 훈련은 유지하고 식사 보정 우선. 2일 연속 미달부터 증량 보류, 3일 이상부터 볼륨 조정 검토.
- **웹 앱 AI 내장은 범위 밖** — 대화 기반 프로토콜 검증 후 별도 과제로.
```

- [ ] **Step 3: 전체 테스트 재실행**

Run: `cd muscle/tools && python3 -m unittest test_analyze -v`
Expected: PASS (17 tests)

- [ ] **Step 4: 커밋**

```bash
git add muscle/ACSM-GUIDELINES.md muscle/CHANGELOG.md
git commit -m "docs(muscle): delegate ACSM §8 to COACHING-PROTOCOL.md, log v15 decision"
```

---

## 완료 기준

- [ ] `python3 muscle/tools/analyze.py` 가 인자 없이(오늘 날짜) 정상 실행되고 7개 섹션을 출력
- [ ] 17개 테스트 전부 통과
- [ ] COACHING-PROTOCOL.md의 8단계 절차가 스펙 9절과 일치
- [ ] ACSM-GUIDELINES.md 근거 원칙(1~7절)은 무변경
- [ ] `log/index.html` 무변경 (git diff에 나타나지 않음)
