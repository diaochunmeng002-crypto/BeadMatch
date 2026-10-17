"""后端接口测试（用 FastAPI 自带的 TestClient，不用真起服务）。"""

import os
import unittest

os.environ.setdefault("BEADMATCH_HISTORY", "off")   # 跑测试别往真实访问库里写

from fastapi.testclient import TestClient

from games.pattern.api import app

client = TestClient(app)


class TestLibrary(unittest.TestCase):
    def test_health(self):
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_home_page_serves_frontend(self):
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("找规律", r.text)
        self.assertIn("static/app.js", r.text)
        self.assertIn("static/style.css", r.text)

    def test_levels(self):
        body = client.get("/api/levels").json()
        self.assertEqual([r["level"] for r in body["levels"]], list(range(1, 11)))
        self.assertEqual([r["count"] for r in body["levels"]], [20] * 10)
        self.assertEqual(body["total"], 200)

    def test_list_and_get_puzzle(self):
        listed = client.get("/api/puzzles", params={"level": 1}).json()
        self.assertEqual(listed["count"], 20)
        card_id = listed["puzzles"][0]["id"]
        body = client.get("/api/puzzles/%s" % card_id).json()
        self.assertEqual(body["id"], card_id)
        self.assertEqual(body["level"], 1)
        self.assertTrue(body["answer"])
        self.assertIn("rule", body)
        self.assertIn("task", body)
        self.assertTrue(body["story"])             # 每道题都配了小故事
        self.assertTrue(body["rows"])
        self.assertTrue(body["reveal_rows"])

    def test_random_by_level(self):
        for level in range(1, 11):
            r = client.get("/api/random", params={"level": level})
            self.assertEqual(r.status_code, 200, level)
            self.assertEqual(r.json()["level"], level)

    def test_unknown_puzzle_is_404(self):
        self.assertEqual(client.get("/api/puzzles/不存在这道题").status_code, 404)

    def test_random_can_skip_the_current_one(self):
        """「换一题」会把现在这道剔掉，不然可能原地打转。"""
        first = client.get("/api/random", params={"level": 1}).json()
        for _ in range(5):
            nxt = client.get("/api/random", params={"level": 1,
                                                    "exclude": first["id"]}).json()
            self.assertNotEqual(nxt["id"], first["id"])

    def test_random_unknown_level_is_404(self):
        self.assertEqual(client.get("/api/random", params={"level": 99}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
