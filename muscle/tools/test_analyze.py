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
