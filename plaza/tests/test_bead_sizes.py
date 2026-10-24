"""除两个串珠模块外，各游戏的屏幕小球统一为 34px。"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def block(css: str, selector: str) -> str:
    match = re.search(r"%s\s*\{([^}]*)\}" % re.escape(selector), css)
    if match is None:
        raise AssertionError("找不到 CSS 选择器：%s" % selector)
    return match.group(1)


class BeadSizeTest(unittest.TestCase):
    def test_non_beadmatch_games_use_the_same_bead_size(self) -> None:
        checks = {
            "calc": (".material .dot",),
            "memory": (".material .dot", ".demo .dot"),
            "mathlab": (".material .bead", ".example .bead"),
            "beadcipher": (".bead",),
            "beadprob": (".row-beads .bead", ".sequence-beads .bead"),
        }
        for game, selectors in checks.items():
            css = (ROOT / "games" / game / "web" / "style.css").read_text(encoding="utf-8")
            for selector in selectors:
                rules = block(css, selector)
                with self.subTest(game=game, selector=selector):
                    self.assertRegex(rules, r"width:\s*34px")
                    self.assertRegex(rules, r"height:\s*34px")

    def test_variable_sized_games_set_thirty_four(self) -> None:
        for game in ("logic", "pattern"):
            css = (ROOT / "games" / game / "web" / "style.css").read_text(encoding="utf-8")
            with self.subTest(game=game):
                self.assertIn("--ball: 34px", css)

    def test_beadprob_bags_stack_to_keep_ten_large_beads_on_one_row(self) -> None:
        css = (ROOT / "games" / "beadprob" / "web" / "style.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: minmax(0, 1fr)", block(css, ".bags"))
        self.assertIn("flex-wrap: nowrap", block(css, ".row-beads"))


if __name__ == "__main__":
    unittest.main()
