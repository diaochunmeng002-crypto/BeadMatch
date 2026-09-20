"""访问日志最小版：能插、能查、能按题汇总。"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path

from plaza import history


class HistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Path(__file__).resolve().parent / ".tmp_history_test.db"
        self._remove()
        os.environ["BEADMATCH_HISTORY_DB"] = str(self.db)

    def tearDown(self) -> None:
        os.environ.pop("BEADMATCH_HISTORY_DB", None)
        self._remove()

    def _remove(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.db) + suffix)
            if path.exists():
                path.unlink()

    def test_db_path_uses_env_override(self) -> None:
        self.assertEqual(history.db_path(), self.db)

    def test_record_and_query(self) -> None:
        when = datetime(2026, 9, 20, 10, 30, tzinfo=timezone.utc)
        new_id = history.record(game="calc", puzzle_id="card-1", level=9,
                                source="random", ts=when)

        rows = history.query(game="calc")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["id"], new_id)
        self.assertEqual(row["game"], "calc")
        self.assertEqual(row["puzzle_id"], "card-1")
        self.assertEqual(row["level"], 9)
        self.assertEqual(row["event"], "served")
        self.assertEqual(row["source"], "random")
        self.assertEqual(row["day"], when.astimezone().strftime("%Y-%m-%d"))
        self.assertIn("+", row["ts"])          # 带时区，能直接看懂"什么时候"

    def test_query_filters(self) -> None:
        history.record(game="calc", puzzle_id="card-1", level=1)
        history.record(game="calc", puzzle_id="card-2", level=2)
        history.record(game="logic", puzzle_id="card-1", level=1, player="kid")

        self.assertEqual([r["puzzle_id"] for r in history.query(game="calc", level=1)], ["card-1"])
        self.assertEqual(len(history.query(game="calc")), 2)
        self.assertEqual(len(history.query(puzzle_id="card-1")), 2)
        self.assertEqual(len(history.query(player="kid")), 1)
        self.assertEqual([r["game"] for r in history.query(since_day="2100-01-01")], [])
        self.assertEqual(history.summary(game="calc", since_day="2100-01-01"), [])

    def test_summary_counts_and_oldest_first(self) -> None:
        early = datetime(2026, 9, 20, 1, 0, tzinfo=timezone.utc)
        late = datetime(2026, 9, 20, 2, 0, tzinfo=timezone.utc)
        history.record(game="calc", puzzle_id="card-1", level=1, ts=early)
        history.record(game="calc", puzzle_id="card-1", level=1, ts=late)
        history.record(game="calc", puzzle_id="card-2", level=1, ts=late)

        rows = history.summary(game="calc", level=1)
        self.assertEqual([r["puzzle_id"] for r in rows], ["card-1", "card-2"])  # card-1 更早玩过
        by_id = {r["puzzle_id"]: r for r in rows}
        self.assertEqual(by_id["card-1"]["times"], 2)
        self.assertEqual(by_id["card-2"]["times"], 1)

    def test_record_safe_does_not_raise(self) -> None:
        os.environ["BEADMATCH_HISTORY_DB"] = str(Path(__file__).resolve().parent)  # 是个目录，写不进去
        with self.assertLogs(history.log, level="ERROR"):
            self.assertIsNone(history.record_safe(game="calc", puzzle_id="card-1"))


if __name__ == "__main__":
    unittest.main()
