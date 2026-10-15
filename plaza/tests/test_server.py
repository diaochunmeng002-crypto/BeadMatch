"""广场的访问清单：接口能查、页面能开、首页有入口。"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from plaza import history
from plaza.server import app


class HistoryPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Path(__file__).resolve().parent / ".tmp_history_server.db"
        self._remove()
        os.environ["BEADMATCH_HISTORY_DB"] = str(self.db)
        os.environ.pop("BEADMATCH_HISTORY", None)      # 强制打开，别被别的测试的 off 影响
        self.client = TestClient(app)

    def tearDown(self) -> None:
        os.environ.pop("BEADMATCH_HISTORY_DB", None)
        os.environ.pop("BEADMATCH_HISTORY", None)
        self._remove()

    def _remove(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.db) + suffix)
            if path.exists():
                path.unlink()

    def test_api_is_newest_first(self) -> None:
        history.record(game="calc", puzzle_id="old", level=1,
                       ts=datetime(2026, 9, 20, 1, 0, tzinfo=timezone.utc))
        history.record(game="logic", puzzle_id="new", level=2,
                       ts=datetime(2026, 9, 20, 2, 0, tzinfo=timezone.utc))

        data = self.client.get("/api/history", params={"limit": 200}).json()
        self.assertEqual(data["count"], 2)
        self.assertEqual([e["puzzle_id"] for e in data["events"]], ["new", "old"])
        self.assertEqual(data["events"][0]["game"], "logic")
        self.assertEqual(data["events"][0]["level"], 2)

    def test_api_honours_limit(self) -> None:
        for i in range(5):
            history.record(game="calc", puzzle_id="card-%d" % i)
        data = self.client.get("/api/history?limit=2").json()
        self.assertEqual(data["count"], 2)

    def test_game_endpoints_write_history(self) -> None:
        got = self.client.get("/api/games/calc/random", params={"level": 1})
        self.assertEqual(got.status_code, 200)
        card = got.json()

        rows = history.query(game="calc")
        self.assertEqual([e["source"] for e in rows], ["random"])
        self.assertEqual(rows[0]["puzzle_id"], card["id"])
        self.assertEqual(rows[0]["level"], 1)

        self.client.get("/api/games/calc/puzzles/%s" % card["id"])
        self.assertEqual([e["source"] for e in history.query(game="calc")], ["by_id", "random"])

    def test_kill_switch_stops_automatic_recording(self) -> None:
        os.environ["BEADMATCH_HISTORY"] = "off"
        try:
            self.client.get("/api/games/calc/random", params={"level": 1})
        finally:
            os.environ.pop("BEADMATCH_HISTORY", None)
        self.assertEqual(history.query(game="calc"), [])

    def test_history_page_and_home_link(self) -> None:
        page = self.client.get("/history")
        self.assertEqual(page.status_code, 200)
        self.assertIn("玩过什么", page.text)        # 页面上那行标题（原来写的是"访问清单"）

        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn('href="/history"', home.text)

    def test_history_page_link_points_at_the_puzzle(self) -> None:
        """「打开」得带上题目 id（/games/<游戏>/?p=<id>）—— 光回游戏首页就开成随机一道了。"""
        page = self.client.get("/history").text
        self.assertIn("'/games/' + encodeURIComponent(ev.game) + '/'", page)
        self.assertIn("'?p=' + encodeURIComponent(ev.puzzle_id)", page)

    def test_every_game_can_serve_a_puzzle_by_id(self) -> None:
        """深链接靠的是各游戏的 `/puzzles/{id}` —— 五个游戏都得能按 id 取题。"""
        games = self.client.get("/api/games").json()["games"]
        self.assertTrue(games)
        for game in games:
            levels = [row["level"] for row in (game.get("levels") or [])]
            if not levels:
                continue                                  # 题库是空的：没得取，跳过
            got = self.client.get("/api/games/%s/random" % game["id"],
                                  params={"level": levels[0]})
            self.assertEqual(got.status_code, 200, game["id"])
            picked = got.json()
            again = self.client.get("/api/games/%s/puzzles/%s" % (game["id"], picked["id"]))
            self.assertEqual(again.status_code, 200, game["id"])
            self.assertEqual(again.json()["id"], picked["id"], game["id"])
            self.assertEqual(again.json()["level"], picked["level"], game["id"])

    def test_game_url_without_slash_keeps_the_query(self) -> None:
        """/games/<游戏>?p=<id>（少个斜杠）跳过去时，题目 id 不能丢。"""
        got = self.client.get("/games/logic", params={"p": "X"}, follow_redirects=False)
        self.assertEqual(got.status_code, 307)
        self.assertTrue(got.headers["location"].endswith("/games/logic/?p=X"), got.headers)

    def test_frontend_says_no_cache(self) -> None:
        """前端资源要带 `Cache-Control: no-cache`。

        不发这个头，浏览器就按"启发式缓存"把 app.js 存上好几天（问都不问）：
        改了前端、刷新页面还是旧代码 —— 2026-10-16 就是这么被坑的（历史页的
        「打开」已经带上 ?p= 了，点进去却是旧前端的行为）。
        """
        page = self.client.get("/games/beadsort/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers.get("cache-control"), "no-cache")

        js = self.client.get("/games/beadsort/static/app.js")
        self.assertEqual(js.status_code, 200)
        self.assertEqual(js.headers.get("cache-control"), "no-cache")
        self.assertIn("WANT_ID", js.text)      # 顺手确认发出去的确实是新版前端


if __name__ == "__main__":
    unittest.main()
