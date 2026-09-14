"""后端接口测试（用 FastAPI 自带的 TestClient，不用真起服务）。"""

import sys
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import generator as g  # noqa: E402
from free_solver import apply_move, is_finished, verify  # noqa: E402
from server.app import PUZZLE_DIR, app  # noqa: E402

client = TestClient(app)


class TestLibrary(unittest.TestCase):
    def test_health(self):
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_home_page_serves_frontend(self):
        """`web/index.html` 存在时，首页就是前端页面。"""
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("BeadMatch", r.text)
        self.assertIn("/static/app.js", r.text)
        self.assertIn("/static/style.css", r.text)

    def test_placeholder_when_no_frontend(self):
        """`web/index.html` 不存在时（比如前端还没做），退回说明页，要把接口都列出来。"""
        import server.app as app_module

        tmp = ROOT / "_tmp_server_web"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        old = app_module.WEB_DIR
        app_module.WEB_DIR = tmp
        try:
            r = client.get("/")
            self.assertEqual(r.status_code, 200)
            for path in ("/api/levels", "/api/puzzles", "/api/random",
                         "/api/next", "/api/play", "/api/generate", "/api/health", "/docs"):
                self.assertIn(path, r.text)
        finally:
            app_module.WEB_DIR = old
            shutil.rmtree(tmp, ignore_errors=True)

    def test_levels(self):
        r = client.get("/api/levels")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["total"], sum(x["count"] for x in body["levels"]))
        if body["levels"]:
            self.assertEqual(sorted(x["level"] for x in body["levels"]),
                             [x["level"] for x in body["levels"]])  # 有序

    def test_list_and_get_puzzle(self):
        listed = client.get("/api/puzzles", params={"level": 3}).json()
        if listed["count"] == 0:
            self.skipTest("题库里没有 3 级的题")
        item = listed["puzzles"][0]
        got = client.get("/api/puzzles/%s" % item["id"])
        self.assertEqual(got.status_code, 200)
        body = got.json()
        self.assertEqual(body["id"], item["id"])
        self.assertEqual(body["level"], 3)
        self.assertEqual(len(body["matrix"]), body["tubes"])
        self.assertEqual(len(body["matrix"][0]), body["capacity"])
        self.assertTrue(body["solution"], "题目应当带标准解法")
        self.assertEqual(len(body["solution"].split()), body["moves"])

    def test_unknown_puzzle_is_404(self):
        r = client.get("/api/puzzles/不存在这道题")
        self.assertEqual(r.status_code, 404)


class TestRandom(unittest.TestCase):
    def test_random_from_level(self):
        r = client.get("/api/random", params={"level": 3})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["level"], 3)
        self.assertTrue(body["solution"])
        self.assertTrue(verify(body["matrix"], g.parse_moves(body["solution"])))
        self.assertGreater(body["pool_size"], 0)

    def test_random_covers_every_level(self):
        for lv in (2, 3, 4, 5):
            r = client.get("/api/random", params={"level": lv})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["level"], lv)

    def test_random_unknown_level_is_404(self):
        r = client.get("/api/random", params={"level": 99})
        self.assertEqual(r.status_code, 404)

    def test_random_level_is_required(self):
        r = client.get("/api/random")
        self.assertEqual(r.status_code, 422)


class TestNext(unittest.TestCase):
    def _easy_puzzle(self):
        listed = client.get("/api/puzzles", params={"level": 2}).json()
        if listed["count"] == 0:
            listed = client.get("/api/puzzles").json()
        if listed["count"] == 0:
            self.skipTest("题库是空的")
        return client.get("/api/puzzles/%s" % listed["puzzles"][0]["id"]).json()

    def test_next_returns_legal_move(self):
        puzzle = self._easy_puzzle()
        r = client.post("/api/next", json={"matrix": puzzle["matrix"]})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["finished"])
        mv = (body["move"]["from"], body["move"]["to"])
        apply_move(puzzle["matrix"], mv)   # 走法不合法会直接抛错
        self.assertEqual(body["remaining"], len(body["solution"].split()))
        self.assertTrue(verify(puzzle["matrix"], g.parse_moves(body["solution"])))

    def test_next_on_finished_state(self):
        r = client.post("/api/next", json={"matrix": [list(t) for t in g.solved_state()]})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["finished"])

    def test_bad_matrix_is_rejected(self):
        bad = [list(t) for t in g.solved_state()]
        bad[0][0] = 99
        r = client.post("/api/next", json={"matrix": bad})
        self.assertEqual(r.status_code, 400)

    def test_matrix_not_on_top_is_rejected(self):
        bad = [list(t) for t in g.solved_state()]
        bad[0] = [1, 0] + [1] * 8        # 顶上是球、下面还有空位：不合法
        bad[6] = [0] * 9 + [1]           # 少的那颗补到空柱底部，颗数仍然对得上
        r = client.post("/api/next", json={"matrix": bad})
        self.assertEqual(r.status_code, 400)

    def test_play_returns_full_solution(self):
        puzzle = self._easy_puzzle()
        r = client.post("/api/play", json={"matrix": puzzle["matrix"]})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(verify(puzzle["matrix"], g.parse_moves(body["moves"])))
        self.assertEqual(body["count"], len(body["moves"].split()))


class TestGenerate(unittest.TestCase):
    def test_generate_returns_puzzle(self):
        r = client.post("/api/generate", json={"walk_steps": 60, "seed": 1})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["matrix"]), body["tubes"])
        self.assertEqual(len(body["matrix"][0]), body["capacity"])
        self.assertEqual(body["level"], g.level_of(body["moves"]))
        self.assertFalse(is_finished(body["matrix"]))
        self.assertTrue(verify(body["matrix"], g.parse_moves(body["solution"])))

    def test_generate_saves_when_asked(self):
        """落盘这一步要用临时题库目录，别污染真题库。"""
        import server.app as app_module

        tmp = ROOT / "_tmp_server_puzzles"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        old = app_module.PUZZLE_DIR
        app_module.PUZZLE_DIR = tmp
        try:
            r = client.post("/api/generate", json={"walk_steps": 60, "seed": 3, "save": True})
            self.assertEqual(r.status_code, 200)
            pid = r.json()["id"]
            self.assertIsNotNone(g.find_puzzle_path(tmp, pid))
            self.assertTrue(list(tmp.glob("*/*.txt")), "题目文件应当落在等级目录里")
        finally:
            app_module.PUZZLE_DIR = old
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
