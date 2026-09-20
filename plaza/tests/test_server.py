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
        self.assertIn("访问清单", page.text)

        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn('href="/history"', home.text)


if __name__ == "__main__":
    unittest.main()
