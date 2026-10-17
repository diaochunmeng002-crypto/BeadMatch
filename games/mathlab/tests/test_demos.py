"""演示清单：字段齐、示例摆法能画、每档数得清。"""

import unittest

from games.mathlab.core import demos as d


class DemosTest(unittest.TestCase):
    def test_every_demo_is_complete(self):
        self.assertEqual(d.check(), [])
        for demo in d.iter_demos():
            with self.subTest(demo=demo.id):
                self.assertTrue(demo.materials)         # 参与者
                self.assertGreaterEqual(len(demo.steps), 2)   # 题目：编号步骤
                self.assertTrue(demo.answer.strip())    # 答案 = 性质
                self.assertTrue(demo.why.strip())       # 为什么
                self.assertIn(demo.level, d.LEVEL_NAMES)
                self.assertEqual(demo.path.stem, demo.id)     # 一个演示一个文件
                self.assertEqual(demo.path.parent.name, str(demo.level))

    def test_levels_count(self):
        info = d.levels()
        self.assertEqual(info["total"], len(d.iter_demos()))
        self.assertEqual(info["total"], 18)              # 18 个演示
        self.assertEqual([row["level"] for row in info["levels"]], [1, 2, 3, 4])
        self.assertEqual([row["count"] for row in info["levels"]], [4, 4, 5, 5])
        self.assertEqual(sum(row["count"] for row in info["levels"]), len(d.iter_demos()))

    def test_lookup(self):
        first = d.iter_demos()[0]
        found = d.get(first.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, first.id)
        self.assertEqual(found.title, first.title)
        self.assertEqual(found.problems, [])
        self.assertIsNone(d.get("没有这个演示"))

    def test_payload_shape(self):
        body = d.payload(d.iter_demos()[0])
        for key in ("id", "level", "level_name", "title", "thing", "unit",
                    "materials", "steps", "answer", "why", "example"):
            self.assertIn(key, body)
        self.assertEqual(body["level_name"], "感知")
        self.assertEqual(body["materials"], [{"bead": "R", "count": 7}])
        self.assertTrue(body["steps"][-1].endswith("？"))     # 最后一步就是那句"问"
        self.assertTrue(body["example"])

    def test_unknown_level_is_empty(self):
        self.assertEqual(d.list_demos(9), [])


if __name__ == "__main__":
    unittest.main()
