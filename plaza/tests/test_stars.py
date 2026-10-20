"""收藏：能收、能取消、幂等、一道题只存一条。"""

import os
import unittest
from pathlib import Path

from plaza import stars


class StarsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Path(__file__).resolve().parent / ".tmp_stars_test.db"
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

    def test_add_and_list(self) -> None:
        state = stars.set_starred("logic", "p1", 5)
        self.assertTrue(state["starred"])
        self.assertEqual(state["level"], 5)
        self.assertTrue(stars.is_starred("logic", "p1"))

        rows = stars.list_stars()
        self.assertEqual([row["puzzle_id"] for row in rows], ["p1"])
        self.assertEqual(rows[0]["game"], "logic")
        self.assertTrue(rows[0]["created_at"])

    def test_idempotent(self) -> None:
        """连收两次还是一条；连取消两次也不报错。"""
        stars.set_starred("logic", "p1", 5)
        stars.set_starred("logic", "p1", 5)
        self.assertEqual(len(stars.list_stars()), 1)

        self.assertFalse(stars.set_starred("logic", "p1", None, False)["starred"])
        self.assertFalse(stars.set_starred("logic", "p1", None, False)["starred"])
        self.assertEqual(stars.list_stars(), [])

    def test_level_filled_in_later(self) -> None:
        """先收（不知道等级），后一次带上等级 —— 补进去，不新开一条。"""
        stars.set_starred("calc", "c1")
        self.assertIsNone(stars.get("calc", "c1")["level"])
        stars.set_starred("calc", "c1", 3)
        rows = stars.list_stars()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["level"], 3)

    def test_filters(self) -> None:
        stars.set_starred("logic", "l5", 5)
        stars.set_starred("logic", "l1", 1)
        stars.set_starred("calc", "c1", 1)
        self.assertEqual(len(stars.list_stars()), 3)
        self.assertEqual([r["puzzle_id"] for r in stars.list_stars("calc")], ["c1"])
        self.assertEqual({r["puzzle_id"] for r in stars.list_stars(level=1)}, {"l1", "c1"})

    def test_same_id_in_two_games(self) -> None:
        """题目 id 只在游戏里唯一 —— logic 的 p1 和 calc 的 p1 是两道题。"""
        stars.set_starred("logic", "p1")
        stars.set_starred("calc", "p1")
        self.assertEqual(len(stars.list_stars()), 2)
        stars.set_starred("logic", "p1", None, False)
        self.assertEqual([r["game"] for r in stars.list_stars()], ["calc"])

    def test_empty_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            stars.set_starred("", "p1")
        with self.assertRaises(ValueError):
            stars.set_starred("logic", "   ")


if __name__ == "__main__":
    unittest.main()
