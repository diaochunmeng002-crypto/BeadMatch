"""彩珠机会屋接口与页面测试。"""

import os
import unittest

os.environ.setdefault("BEADMATCH_HISTORY", "off")

from fastapi.testclient import TestClient

from games.beadprob.api import app

client = TestClient(app)


class BeadProbAppTest(unittest.TestCase):
    def test_health(self) -> None:
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_home_page(self) -> None:
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("彩珠机会屋", response.text)
        self.assertIn("static/app.js", response.text)
        self.assertIn("static/style.css", response.text)

    def test_levels_and_random(self) -> None:
        data = client.get("/api/levels").json()
        self.assertEqual(data["total"], 180)
        self.assertEqual([row["level"] for row in data["levels"]], list(range(1, 10)))
        self.assertEqual([row["count"] for row in data["levels"]], [20] * 9)
        self.assertEqual(data["levels"][5]["name"], "三颗赛跑")
        self.assertEqual(data["levels"][-1]["name"], "不放回")

        for level in range(1, 10):
            puzzle = client.get("/api/random", params={"level": level}).json()
            self.assertEqual(puzzle["level"], level)
            self.assertTrue(puzzle["action"])
            if level == 6:
                self.assertEqual(puzzle["kind"], "race")
                self.assertEqual(puzzle["answer_text"], "")
            else:
                self.assertTrue(puzzle["answer_text"])
            self.assertEqual(puzzle["pool_size"], 20)

    def test_get_by_id(self) -> None:
        listed = client.get("/api/puzzles", params={"level": 7}).json()
        puzzle = client.get("/api/puzzles/%s" % listed["puzzles"][0]["id"]).json()
        self.assertEqual(puzzle["level"], 7)
        self.assertTrue(puzzle["prior"])
        self.assertTrue(puzzle["action"])

    def test_unknown_puzzle(self) -> None:
        self.assertEqual(client.get("/api/puzzles/nope").status_code, 404)

    def test_frontend_reports_current_puzzle_to_plaza(self) -> None:
        js = client.get("/static/app.js").text
        self.assertIn("__beadprob_loaded", js)
        self.assertIn("plazaSetPuzzle", js)
        self.assertIn("showAnswer", js)
        self.assertIn("'答案：' + puzzle.answer_text", js)
        self.assertIn("puzzle.kind === 'race' ? '看规律'", js)
        self.assertIn("$('result-title').textContent = race ? '规律' : '答案'", js)
        self.assertIn("anotherQuestion", js)
        self.assertIn("exclude=", js)
        self.assertIn("color-row", js)
        self.assertIn("row.name + ' ' + row.count + ' 颗'", js)
        self.assertIn("sort((a, b) => a.count - b.count", js)
        self.assertIn("renderSequence", js)
        self.assertNotIn("choose(", js)

        css = client.get("/static/style.css").text
        self.assertIn(".row-beads", css)
        self.assertIn("flex-wrap: nowrap", css)

    def test_page_has_no_screen_answer_buttons(self) -> None:
        page = client.get("/").text
        self.assertIn("线下摸珠", page)
        self.assertIn('id="action"', page)
        self.assertIn('id="next">换一题</button>', page)
        self.assertNotIn('id="options"', page)
        self.assertNotIn('id="retry"', page)

    def test_random_can_skip_the_current_question(self) -> None:
        first = client.get("/api/random", params={"level": 1}).json()
        for _ in range(5):
            nxt = client.get("/api/random", params={
                "level": 1,
                "exclude": first["id"],
            }).json()
            self.assertNotEqual(nxt["id"], first["id"])


if __name__ == "__main__":
    unittest.main()
