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
