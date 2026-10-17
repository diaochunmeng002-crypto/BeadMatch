"""后端接口测试（用 FastAPI 自带的 TestClient，不用真起服务）。"""

import os
import unittest

os.environ.setdefault("BEADMATCH_HISTORY", "off")   # 跑测试别往真实访问库里写

from fastapi.testclient import TestClient

from games.mathlab.api import app

client = TestClient(app)


class TestMathLab(unittest.TestCase):
    def test_health(self):
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_home_page_serves_frontend(self):
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("数学实验室", r.text)
        self.assertIn("static/app.js", r.text)
        self.assertIn("static/style.css", r.text)

    def test_levels_and_list(self):
        body = client.get("/api/levels").json()
        self.assertEqual(body["total"], 18)
        self.assertEqual(body["levels"],
                         [{"level": 1, "count": 4}, {"level": 2, "count": 4},
                          {"level": 3, "count": 5}, {"level": 4, "count": 5}])
        listed = client.get("/api/puzzles").json()
        self.assertEqual(listed["count"], 18)

    def test_get_demo(self):
        demo_id = client.get("/api/puzzles").json()["demos"][0]["id"]
        body = client.get("/api/puzzles/%s" % demo_id).json()
        self.assertEqual(body["id"], demo_id)
        self.assertEqual(body["level"], 1)
        for key in ("thing", "unit", "materials", "steps", "answer", "why", "example"):
            self.assertTrue(body[key])

    def test_random_by_level(self):
        r = client.get("/api/random", params={"level": 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["level"], 1)
        self.assertEqual(client.get("/api/random", params={"level": 4}).status_code, 200)
        self.assertEqual(client.get("/api/random", params={"level": 9}).status_code, 404)

    def test_unknown_demo_is_404(self):
        self.assertEqual(client.get("/api/puzzles/没有这个演示").status_code, 404)


if __name__ == "__main__":
    unittest.main()
