"""彩珠密令接口测试：只发题卡，不提供程序答案。"""

import os
import unittest

os.environ.setdefault("BEADMATCH_HISTORY", "off")

from fastapi.testclient import TestClient

from games.beadcipher.api import app

client = TestClient(app)


class BeadCipherApiTest(unittest.TestCase):
    def test_home_is_a_simple_rule_card(self) -> None:
        page = client.get("/").text
        self.assertIn("彩珠密令", page)
        self.assertIn("参与者", page)
        self.assertIn("题目", page)
        self.assertIn('id="clues"', page)
        self.assertIn('id="level"', page)
        self.assertIn('id="next"', page)
        self.assertNotIn("藏起来的密令", page)
        self.assertNotIn("你的猜测", page)
        self.assertNotIn("给线索", page)
        self.assertNotIn("出题人", page)
        self.assertNotIn("做题人", page)

    def test_bead_size_matches_the_logic_game(self) -> None:
        css = client.get("/static/style.css").text
        marker = ".bead {"
        block = css[css.index(marker):css.index("}", css.index(marker))]
        self.assertIn("width: 34px", block)
        self.assertIn("height: 34px", block)

    def test_five_levels_with_a_quality_first_card_count(self) -> None:
        body = client.get("/api/levels").json()
        self.assertEqual(body["levels"], [
            {"level": 1, "count": 4},
            {"level": 2, "count": 2},
            {"level": 3, "count": 3},
            {"level": 4, "count": 4},
            {"level": 5, "count": 4},
            {"level": 6, "count": 2},
            {"level": 7, "count": 2},
        ])
        self.assertEqual(body["total"], 21)

    def test_random_returns_public_rule_card_only(self) -> None:
        for level in range(1, 8):
            with self.subTest(level=level):
                body = client.get("/api/random", params={"level": level}).json()
                self.assertEqual(body["level"], level)
                self.assertTrue(body["beads"])
                self.assertTrue(body["kind"])
                self.assertTrue(body["kind_name"])
                self.assertTrue(body["clue_rule"])
                self.assertNotIn("answer", body)

    def test_random_can_switch_to_another_card(self) -> None:
        first = client.get("/api/random", params={"level": 1}).json()
        for _ in range(5):
            again = client.get("/api/random", params={
                "level": 1, "exclude": first["id"],
            }).json()
            self.assertNotEqual(again["id"], first["id"])

    def test_there_is_no_automatic_solver(self) -> None:
        card_id = "20261022-233500-bc01"
        self.assertEqual(client.get("/api/puzzles/%s/solution" % card_id).status_code, 404)
        self.assertEqual(client.post("/api/guess", json={
            "id": card_id, "guess": "RBY",
        }).status_code, 404)

    def test_unknown_level_and_puzzle(self) -> None:
        self.assertEqual(client.get("/api/random", params={"level": 99}).status_code, 404)
        self.assertEqual(client.get("/api/puzzles/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
