"""题库：10 道题全部能读、能算、能过校验；顺手测几个容易写错的地方。"""

import unittest
from pathlib import Path

from games.pattern.core import cards as k

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "puzzles"


class LibraryTest(unittest.TestCase):
    def test_all_puzzles_are_clean(self):
        """200 道题一道都不能有毛病（格式 / 规律 / 唯一解 / 物理上限）。"""
        cards = k.iter_cards(ROOT)
        self.assertEqual(len(cards), 200)
        for card in cards:
            with self.subTest(card=card.path.name):
                self.assertEqual(card.problems, [], card.title)
                self.assertEqual(card.path.stem, card.id)
                self.assertEqual(card.path.parent.name, str(card.level))

    def test_twenty_puzzles_per_level(self):
        rows = k.list_levels(ROOT)
        self.assertEqual([r["level"] for r in rows], list(range(1, 11)))
        self.assertEqual([r["count"] for r in rows], [20] * 10)

    def test_each_level_has_twenty_distinct_shapes(self):
        """同一档 20 道题 = **20 个不同形状**（不是"同一道题换个颜色"）。"""
        for level in range(1, 11):
            cards = [card for card in k.iter_cards(ROOT) if card.level == level]
            shapes = [k.shape_key(card) for card in cards]
            self.assertEqual(len(cards), 20, level)
            self.assertEqual(len(set(shapes)), 20, "第 %d 档有重复形状" % level)

    def test_every_puzzle_has_a_story(self):
        """每道题都配了一句小故事（假装是小汽车 / 小皮球……）。"""
        for card in k.iter_cards(ROOT):
            with self.subTest(card=card.path.name):
                self.assertTrue(card.meta.get("story", "").strip(), card.title)

    def test_reveal_fills_the_blanks(self):
        """揭晓用的题面：空位都填上了，而且标了"这是填进去的"。"""
        card = k.load_card(ROOT / "1" / "20261017-100101-1a01.txt")
        self.assertEqual(card.problems, [])
        self.assertEqual(card.answer, ["B"])
        self.assertTrue(card.meta["story"])       # 手写的那道也补了小故事
        reveal = k.reveal_rows(card)
        self.assertEqual(reveal[0][-1], {"bead": "B", "mark": "answer"})
        self.assertEqual("".join(c["bead"] for c in reveal[0]), "".join(card.full))

    def test_fix_puzzle_marks_the_bad_bead(self):
        """纠错题：揭晓时第 8 颗变成红，并且标出来。"""
        card = k.load_card(ROOT / "7" / "20261017-100107-7a07.txt")
        self.assertEqual(card.problems, [])
        self.assertEqual(card.fix, {"pos": 8, "kind": "swap", "from": "B", "to": "R"})
        self.assertIn("第 8 颗", k.fix_text(card))
        self.assertEqual(k.reveal_rows(card)[0][7], {"bead": "R", "mark": "fix"})

    def test_group_fix_and_answer_together(self):
        """L10：既有一颗补错，又有一整组要摆。"""
        card = k.load_card(ROOT / "10" / "20261017-100110-a10a.txt")
        self.assertEqual(card.problems, [])
        self.assertEqual(card.answer, ["B", "B", "B", "B"])
        self.assertIn("补一颗红", k.fix_text(card))
        self.assertEqual(len(k.reveal_rows(card)), 4)
        self.assertEqual([len(r) for r in k.reveal_rows(card)], [1, 2, 3, 4])

    def test_shortest_unit(self):
        self.assertEqual(k.shortest_unit(list("RBRBRB")), 2)
        self.assertEqual(k.shortest_unit(list("RRBRRBRRB")), 3)
        # 9 颗但单元是 6 颗（"走到头就回头"）：最短单元要比一半长
        self.assertEqual(k.shortest_unit(list("RBGGBRRBG")), 6)
        self.assertEqual(k.shortest_unit(list("RRRRRR")), 1)

    def test_apply_fix(self):
        self.assertEqual(k.apply_fix(["R", "B", "B", "R", "R"],
                                     {"pos": 5, "kind": "add", "bead": "R"}),
                         ["R", "B", "B", "R", "R", "R"])
        self.assertEqual(k.apply_fix(["R", "B"], {"pos": 2, "kind": "swap", "from": "B", "to": "G"}),
                         ["R", "G"])
        with self.assertRaises(ValueError):
            k.apply_fix(["R"], {"pos": 2, "kind": "swap", "from": "R", "to": "G"})

    def _write(self, text):
        path = HERE / "_tmp_pattern_card.txt"
        path.write_text(text, encoding="utf-8")
        self.addCleanup(path.unlink)
        return path

    def test_wrong_answer_is_caught(self):
        """答案跟规律对不上 —— 检查命令要报出来。"""
        path = self._write(
            "id=20261017-100101-1a01\nlevel=1\ntitle=x\nkind=repeat\nunit=RB\n"
            "shown=RBRBR?\nanswer=R\nrule=红蓝循环\n")
        card = k.load_card(path)
        self.assertTrue(any("answer" in p for p in card.problems), card.problems)

    def test_shorter_period_is_caught(self):
        """一整条都是红，却把单元写成两颗红 —— 其实一颗就够解释了，答案不唯一。"""
        path = self._write(
            "id=20261017-100101-1a01\nlevel=1\ntitle=x\nkind=repeat\nunit=RR\n"
            "shown=RRRRR?\nanswer=R\nrule=x\n")
        card = k.load_card(path)
        self.assertTrue(any("更短的周期" in p for p in card.problems), card.problems)


if __name__ == "__main__":
    unittest.main()
