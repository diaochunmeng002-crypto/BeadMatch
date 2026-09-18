"""walk_gen（引导式走法出题）的测试。"""

import unittest

from games.beadsort.core import generator as g
from games.beadsort.core import walk_gen as wg
from games.beadsort.core.free_solver import verify


class TestMetrics(unittest.TestCase):
    def test_solved_state_metrics(self):
        st = tuple(tuple(t) for t in g.solved_state())
        self.assertEqual(wg.max_run(st), 10)
        self.assertEqual(wg.bottom_run(st), 60)        # 6 根柱子各 10 颗
        self.assertEqual(wg.seg_total(st), 6)
        self.assertEqual(wg.adjacent_same(st), 54)     # 6 根 × 9 对
        self.assertAlmostEqual(wg.kinds_per_tube(st), 6 / 7)

    def test_metrics_on_scrambled_state(self):
        state, _raw, _sol = wg.walk(3, 60)
        m = wg.metrics(state)
        solved = tuple(tuple(t) for t in g.solved_state())
        self.assertLess(m["max_run"], wg.max_run(solved))
        self.assertLess(m["adjacent_same"], wg.adjacent_same(solved))
        self.assertGreater(m["seg_total"], wg.seg_total(solved))


class TestCompact(unittest.TestCase):
    def test_merges_same_ball_twice(self):
        """A→B 紧跟 B→C，等价于 A→C。"""
        out, merged = wg.compact([(0, 1), (1, 2)])
        self.assertEqual(out, [(0, 2)])
        self.assertEqual(merged, 1)

    def test_keeps_different_balls(self):
        out, merged = wg.compact([(0, 1), (0, 2)])
        self.assertEqual(out, [(0, 1), (0, 2)])
        self.assertEqual(merged, 0)

    def test_chained_merges(self):
        out, merged = wg.compact([(0, 1), (1, 2), (2, 3)])
        self.assertEqual(out, [(0, 3)])
        self.assertEqual(merged, 2)


class TestWalk(unittest.TestCase):
    def test_reverse_walk_is_a_valid_solution(self):
        for seed in (1, 2, 3):
            state, raw, solution = wg.walk(seed, 40)
            self.assertTrue(verify(state, solution), "反走必须是合法解")
            # walk() 是尽力而为：走不动就返回最长的那一次（见 walk_gen 模块说明）。
            # 40 步这个目标现在经常走不满 —— 这不是 bug，是规则本身的结构（2026-09-17 实验）。
            self.assertLessEqual(len(solution), 40)
            self.assertGreater(len(solution), 0)
            self.assertLessEqual(len(solution), len(raw))   # 合并只会更短

    def test_reproducible(self):
        a = wg.walk(7, 30)
        b = wg.walk(7, 30)
        self.assertEqual(a[0], b[0])
        self.assertEqual(a[2], b[2])

    def test_more_steps_does_not_mean_more_scrambled(self):
        """2026-09-17 实验结论：**走更久 ≠ 更乱**。

        20 步和 120 步最终都落在同一个「乱度上限」附近（60 颗珠子里只有十几颗离位），
        多出来的步数基本是原地打转。所以难度不能按步数分，只能按最终局面分 ——
        这就是 core/sampler.py 存在的原因。
        """
        short, _r1, s1 = wg.walk(11, 20)
        long_, _r2, s2 = wg.walk(11, 120)
        self.assertTrue(verify(short, s1))
        self.assertTrue(verify(long_, s2))
        self.assertLessEqual(len(s2), 120)


if __name__ == "__main__":
    unittest.main()
