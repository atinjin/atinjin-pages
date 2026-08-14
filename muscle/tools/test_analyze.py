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


if __name__ == "__main__":
    unittest.main()
