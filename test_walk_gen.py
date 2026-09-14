"""walk_gen（引导式走法出题）的测试。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generator as g  # noqa: E402
import walk_gen as wg  # noqa: E402
from free_solver import verify  # noqa: E402


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
            self.assertEqual(len(solution), 40)
            self.assertLessEqual(len(solution), len(raw))   # 合并只会更短

    def test_reproducible(self):
        a = wg.walk(7, 30)
        b = wg.walk(7, 30)
        self.assertEqual(a[0], b[0])
        self.assertEqual(a[2], b[2])

    def test_more_steps_means_more_scrambled(self):
        short, _r1, _s1 = wg.walk(11, 20)
        long_, _r2, _s2 = wg.walk(11, 120)
        self.assertGreater(wg.scatter(long_), wg.scatter(short))   # 打散度越大越乱


if __name__ == "__main__":
    unittest.main()
