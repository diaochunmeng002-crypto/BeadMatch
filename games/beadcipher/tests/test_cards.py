"""30 张彩珠密令题卡的题库测试。"""

import unittest
from pathlib import Path

from games.beadcipher.core import cards as k

ROOT = Path(__file__).resolve().parent.parent / "puzzles"
EXPECTED_KINDS = [
    ["position_marks", "position_marks", "position_marks", "position_marks"],
    ["first_error", "first_error"],
    ["run", "run", "run"],
    ["positions", "positions", "positions", "positions"],
    ["choice", "choice", "questions", "questions"],
    ["positions", "first_error"],
    ["delayed", "delayed"],
]
EXPECTED_COUNTS = [4, 2, 3, 4, 4, 2, 2]


class CardTest(unittest.TestCase):
    def test_library_has_seventeen_cards_in_five_levels(self) -> None:
        cards = k.iter_cards(ROOT)
        self.assertEqual(len(cards), 21)
        for card in cards:
            with self.subTest(card=card.path.name):
                self.assertEqual(card.problems, [])
                self.assertNotIn("answer", card.meta)

        self.assertEqual(k.list_levels(ROOT), [
            {"level": level, "count": count}
            for level, count in enumerate(EXPECTED_COUNTS, start=1)
        ])

    def test_each_level_uses_one_clue_language(self) -> None:
        cards = k.iter_cards(ROOT)
        for level, expected in enumerate(EXPECTED_KINDS, start=1):
            with self.subTest(level=level):
                kinds = [card.kind for card in cards if card.level == level]
                self.assertEqual(kinds, expected)

    def test_cards_in_a_level_have_distinct_structures(self) -> None:
        cards = k.iter_cards(ROOT)
        for level, count in enumerate(EXPECTED_COUNTS, start=1):
            with self.subTest(level=level):
                keys = [k.structure_key(card) for card in cards if card.level == level]
                self.assertEqual(len(keys), count)
                self.assertEqual(len(set(keys)), count)

    def test_duplicate_beads_are_handled(self) -> None:
        card = k.load_card(ROOT / "1" / "20261022-235102-b102.txt")
        self.assertEqual(card.beads, ("R", "R", "B"))
        self.assertEqual(len(k.possible_secrets(card)), 3)

    def test_payload_is_a_rule_card_without_answer(self) -> None:
        card = k.load_card(ROOT / "1" / "20261022-233500-bc01.txt")
        body = k.payload(card)
        self.assertEqual(body["beads"], ["R", "B", "Y"])
        self.assertEqual(body["kind"], "position_marks")
        self.assertEqual(body["kind_name"], "直接标出正确位置")
        self.assertIn("哪几个位置正确", body["clue_rule"])
        self.assertNotIn("answer", body)


if __name__ == "__main__":
    unittest.main()
