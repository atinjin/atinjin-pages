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


if __name__ == "__main__":
    unittest.main()
