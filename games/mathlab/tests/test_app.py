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
        self.assertIn('id="level-menu"', r.text)       # 当前等级类型用一行顿号文字
        self.assertIn("static/app.js", r.text)
        self.assertIn("static/style.css", r.text)

    def test_levels_and_list(self):
        body = client.get("/api/levels").json()
        self.assertEqual(body["total"], 54)
        self.assertEqual([row["level"] for row in body["levels"]], list(range(1, 9)))
        self.assertEqual([row["name"] for row in body["levels"]],
                         ["感知", "组合", "结构", "探索", "关系", "规律", "符号", "建模"])
        self.assertEqual([row["count"] for row in body["levels"]],
                         [7, 7, 8, 8, 6, 6, 6, 6])
        self.assertTrue(all(row["summary"].strip() for row in body["levels"]))
        listed = client.get("/api/puzzles").json()
        self.assertEqual(listed["count"], 54)

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
        self.assertEqual(client.get("/api/random", params={"level": 8}).status_code, 200)
        self.assertEqual(client.get("/api/random", params={"level": 9}).status_code, 404)

    def test_unknown_demo_is_404(self):
        self.assertEqual(client.get("/api/puzzles/没有这个演示").status_code, 404)


if __name__ == "__main__":
    unittest.main()
