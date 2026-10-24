"""彩珠机会屋题库：160 道都能读、答案能验、结构不重复。"""

from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path

from games.beadprob.core import cards as k

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "puzzles"


class LibraryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cards = k.iter_cards(ROOT)

    def test_all_180_cards_are_clean(self) -> None:
        self.assertEqual(len(self.cards), 180)
        for card in self.cards:
            with self.subTest(card=card.path.name):
                self.assertEqual(card.problems, [], card.title)
                self.assertEqual(card.path.stem, card.id)
                self.assertEqual(card.path.parent.name, str(card.level))

    def test_twenty_cards_per_level(self) -> None:
        rows = k.list_levels(ROOT)
        self.assertEqual([row["level"] for row in rows], list(range(1, 10)))
        self.assertEqual([row["count"] for row in rows], [20] * 9)

    def test_each_level_has_twenty_distinct_shapes(self) -> None:
        for level in range(1, 10):
            cards = [card for card in self.cards if card.level == level]
            shapes = [k.shape_key(card) for card in cards]
            self.assertEqual(len(cards), 20, level)
            self.assertEqual(len(set(shapes)), 20, "第 %d 档有重复结构" % level)

    def test_every_card_has_an_offline_action(self) -> None:
        for card in self.cards:
            with self.subTest(card=card.path.name):
                self.assertTrue(card.meta["action"].strip())
                self.assertIn("摸", card.meta["action"])

    def test_level_three_uses_equal_totals(self) -> None:
        for card in (card for card in self.cards if card.level == 3):
            self.assertEqual(card.bags[0].total, card.bags[1].total)
            self.assertNotEqual(card.bags[0].chance(card.target),
                                card.bags[1].chance(card.target))

    def test_level_one_covers_four_outcome_types_evenly(self) -> None:
        rows = Counter()
        for card in (card for card in self.cards if card.level == 1):
            bag = card.bags[0]
            target_count = bag.count_of(card.target)
            if card.meta["ask"] == "may":
                rows["may_yes" if target_count else "may_no"] += 1
            else:
                rows["certain_yes" if target_count == bag.total else "certain_no"] += 1
        self.assertEqual(rows, Counter({
            "may_yes": 5,
            "may_no": 5,
            "certain_yes": 5,
            "certain_no": 5,
        }))

    def test_level_four_has_the_absolute_count_trap(self) -> None:
        for card in (card for card in self.cards if card.level == 4):
            left = card.bags[0]
            right = card.bags[1]
            self.assertNotEqual(left.total, right.total)
            more_count = ("left" if left.count_of(card.target) > right.count_of(card.target)
                          else "right")
            self.assertNotEqual(k.infer_answer(card), more_count)

    def test_level_five_has_equal_chances(self) -> None:
        for card in (card for card in self.cards if card.level == 5):
            self.assertNotEqual(card.bags[0].total, card.bags[1].total)
            self.assertAlmostEqual(card.bags[0].chance(card.target),
                                   card.bags[1].chance(card.target))
            self.assertEqual(k.infer_answer(card), "same")

    def test_level_six_is_the_three_bead_race(self) -> None:
        cards = [card for card in self.cards if card.level == 6]
        self.assertEqual(Counter(card.meta["ask"] for card in cards),
                         Counter({"majority": 5, "even": 5, "upset": 5, "rounds": 5}))
        for card in cards:
            self.assertEqual(card.kind, "race")
            self.assertFalse(card.removed)
            self.assertFalse(card.prior)
            self.assertNotIn("answer", card.meta)
            self.assertTrue(all(row["count"] <= 7 for row in card.bags[0].counts))

    def test_level_seven_is_replacement_only(self) -> None:
        for card in (card for card in self.cards if card.level == 7):
            self.assertTrue(card.prior)
            self.assertFalse(card.removed)
            self.assertEqual(card.meta["answer"], "same")

    def test_level_eight_has_two_milestones(self) -> None:
        for card in (card for card in self.cards if card.level == 8):
            self.assertGreater(card.first_draws, 0)
            self.assertLessEqual(card.first_draws, card.total_draws)
            self.assertLessEqual(card.total_draws, 30)
            self.assertEqual(card.meta["answer"], "later")

    def test_level_nine_tracks_removed_beads(self) -> None:
        for card in (card for card in self.cards if card.level == 9):
            self.assertTrue(card.removed)
            self.assertIn(card.meta["answer"], ("larger", "smaller", "same"))

    def test_physical_bead_limit_across_both_bags(self) -> None:
        """两只袋子同时摆出来时，每种颜色合计也不能超过 10 颗。"""
        for card in self.cards:
            used = {}
            for bag in card.bags:
                for row in bag.counts:
                    used[row["bead"]] = used.get(row["bead"], 0) + row["count"]
            self.assertTrue(all(count <= 10 for count in used.values()), card.id)

    def test_wrong_answer_is_caught(self) -> None:
        text = """\
created_at=2026-10-24
created_by=manual
id=20261024-120001-a101
level=3
title=测试
kind=compare
target=B
question=哪边更容易？
action=两只袋子轮流摸 5 次，每次放回。
bag=左边|R:5 B:3
bag=右边|G:7 B:1
answer=right
hint=数一数
explain=右边蓝珠更多
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20261024-120001-a101.txt"
            path.write_text(text, encoding="utf-8")
            card = k.load_card(path)
        self.assertTrue(any("answer 应是 left" in problem for problem in card.problems),
                        card.problems)


if __name__ == "__main__":
    unittest.main()
