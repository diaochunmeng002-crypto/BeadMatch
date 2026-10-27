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
                self.assertTrue(demo.theme.strip())     # 主题标签
                self.assertIn(demo.level, d.LEVEL_NAMES)
                self.assertEqual(demo.path.stem, demo.id)     # 一个演示一个文件
                self.assertEqual(demo.path.parent.name, str(demo.level))

    def test_levels_count(self):
        info = d.levels()
        self.assertEqual(info["total"], len(d.iter_demos()))
        self.assertEqual(info["total"], 54)
        self.assertEqual([row["level"] for row in info["levels"]], list(range(1, 9)))
        self.assertEqual([row["count"] for row in info["levels"]], [7, 7, 8, 8, 6, 6, 6, 6])
        self.assertEqual([row["name"] for row in info["levels"]],
                         ["感知", "组合", "结构", "探索", "关系", "规律", "符号", "建模"])
        self.assertTrue(all(row["summary"].strip() for row in info["levels"]))
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
        for key in ("id", "level", "level_name", "theme", "title", "thing", "unit",
                    "materials", "steps", "answer", "why", "example"):
            self.assertIn(key, body)
        self.assertEqual(body["level_name"], "感知")
        self.assertEqual(body["theme"], "数与量")
        self.assertEqual(body["materials"], [{"bead": "R", "count": 3}])
        self.assertTrue(body["steps"][-1].endswith("？"))     # 最后一步就是那句"问"
        self.assertTrue(body["example"])

    def test_number_ceiling_by_level(self):
        """先练关系，不先考计算：L1 / L2 / L3-L4 的组量分别不超过 3 / 4 / 5。"""
        ceilings = {1: 3, 2: 4, 3: 5, 4: 5, 5: 5, 6: 5, 7: 5, 8: 5}
        for demo in d.iter_demos():
            ceiling = ceilings[demo.level]
            for row in demo.materials:
                self.assertLessEqual(row["count"], ceiling, demo.id)
            for example in demo.example:
                counts = {}
                for group in example["groups"]:
                    for bead in group:
                        counts[bead] = counts.get(bead, 0) + 1
                for bead, count in counts.items():
                    self.assertLessEqual(count, ceiling, (demo.id, example["label"], bead))

    def test_missing_topic_areas_are_covered(self):
        """除了数与运算，也要有图形、测量、数据、关系和实验过程。"""
        themes = {demo.theme for demo in d.iter_demos()}
        self.assertTrue({"图形空间", "测量", "数据", "关系", "实验过程"} <= themes)

    def test_unknown_level_is_empty(self):
        self.assertEqual(d.list_demos(9), [])


if __name__ == "__main__":
    unittest.main()
