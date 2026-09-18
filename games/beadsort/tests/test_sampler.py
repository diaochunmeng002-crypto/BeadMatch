"""采样器（core/sampler.py）的测试：约束、指标、可复现、导出。"""

import shutil
import unittest
from pathlib import Path

from games.beadsort.core import generator as g
from games.beadsort.core import sampler as sp
from games.beadsort.core.free_solver import apply_move, key


class TempDir:
    """临时目录放在工作区里（系统的 temp 目录在沙箱里删不掉）。"""

    def __init__(self, name):
        self.path = Path(__file__).resolve().parent / name

    def __enter__(self):
        shutil.rmtree(self.path, ignore_errors=True)
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)
        return False


class TestChaos(unittest.TestCase):
    def test_solved_state_is_not_chaotic(self):
        c = sp.chaos(sp.solved())
        self.assertEqual(c["misplaced"], 0)
        self.assertEqual(c["segments"], g.COLORS)
        self.assertEqual(c["max_run"], g.BALLS_PER_COLOR)
        self.assertEqual(c["bottom_run"], g.COLORS * g.BALLS_PER_COLOR)

    def test_walking_makes_it_chaotic(self):
        w = sp.sample(4, stagnation=None, max_steps=40)
        self.assertGreater(w.misplaced, 0)
        self.assertGreater(w.segments, g.COLORS)
        self.assertLess(w.max_run, g.BALLS_PER_COLOR)


class TestConstraints(unittest.TestCase):
    def _replay(self, walk):
        """按 path 重走一遍，返回每一步的局面。"""
        cur = sp.solved()
        out = [cur]
        for m in walk.path:
            cur = apply_move(cur, m)
            out.append(cur)
        return out

    def test_reverse_walk_is_a_valid_solution(self):
        """反走出来的局面，把路倒过来一定解得开（这是出题的前提）。"""
        for seed in (1, 2, 3, 11, 42):
            w = sp.sample(seed)
            self.assertTrue(sp.verify(w), "seed=%d 的解套回局面竟然解不开" % seed)
            self.assertEqual(w.steps, len(w.path))
            self.assertGreater(w.moves, 0)

    def test_no_immediate_undo(self):
        w = sp.sample(9, stagnation=None, max_steps=60)
        for (a, b), (c, d) in zip(w.path, w.path[1:]):
            self.assertFalse(c == b and d == a, "走了立即反悔的一步：%d-%d" % (a, b))

    def test_repeat_none_never_revisits(self):
        w = sp.sample(5, repeat="none", stagnation=None, max_steps=200)
        keys = [key(s) for s in self._replay(w)]
        self.assertEqual(len(keys), len(set(keys)), "repeat=none 不该走回老局面")

    def test_allow_mode_walks_long_but_goes_nowhere(self):
        """老做法（只禁立即反向）：能硬走很久，但一路都在原地打转 —— 所以才有这个采样器。"""
        steps = [sp.sample(s, repeat="allow", stagnation=None, max_steps=200).steps
                 for s in range(1, 31)]
        self.assertGreater(sum(steps) / len(steps), 100)
        self.assertGreater(max(steps), min(steps))        # 有的走满、有的半路撞死路
        self.assertTrue(all(s >= 4 for s in steps))

    def test_stagnation_stops_early(self):
        w = sp.sample(6, stagnation=8, max_steps=500)
        self.assertIn(w.stop, ("stagnation", "dead-end"))
        self.assertLess(w.steps, 500)

    def test_cap_stops_exactly_at_max_steps(self):
        w = sp.sample(7, stagnation=None, max_steps=5)
        self.assertEqual(w.stop, "cap")
        self.assertEqual(w.steps, 5)

    def test_deterministic(self):
        a = sp.sample(123)
        b = sp.sample(123)
        self.assertEqual(a.board, b.board)
        self.assertEqual(a.path, b.path)
        self.assertEqual(a.misplaced, b.misplaced)

    def test_different_seeds_differ(self):
        self.assertNotEqual(sp.sample(1).board, sp.sample(2).board)

    def test_bad_arguments_are_rejected(self):
        with self.assertRaises(ValueError):
            sp.sample(1, repeat="whatever")
        with self.assertRaises(ValueError):
            sp.sample(1, strategy="whatever")


class TestSizes(unittest.TestCase):
    def tearDown(self):
        sp.configure(7, 6, 10, 10)          # 别把参数漏给别的测试

    def test_other_sizes_still_solvable(self):
        sp.configure(6, 4, 5, 5)
        w = sp.sample(3)
        self.assertTrue(sp.verify(w))
        self.assertEqual(len(w.board), 6)

    def test_more_empty_tubes_walk_further(self):
        """空柱越多，能走的路越多 —— 7 柱 6 色（1 空）vs 7 柱 4 色（3 空）。"""
        sp.configure(7, 6, 10, 10)
        tight = [sp.sample(s).steps for s in range(1, 31)]
        sp.configure(7, 4, 10, 10)
        loose = [sp.sample(s).steps for s in range(1, 31)]
        self.assertGreater(sum(loose) / len(loose), sum(tight) / len(tight))


class TestExport(unittest.TestCase):
    def test_walk_can_be_saved_as_a_puzzle_file(self):
        """采样器的乱度字段要能写进题目文件、再原样读回来。"""
        w = sp.sample(21)
        meta = {
            "created_at": "2026-09-17 12:00:00",
            "created_by": g.CREATED_BY,
            "id": "20260917-120000-abcd",
            "tubes": g.TUBES,
            "colors": g.COLOR_LETTERS[: g.COLORS],
            "capacity": g.CAPACITY,
            "balls_per_color": g.BALLS_PER_COLOR,
            "level": w.level,
            "moves": w.moves,
            "seed": w.seed,
            "steps": w.steps,
            "generator": g.GENERATOR,
            "seconds": 0.01,
            "solution_by": "walk",
            "solution": g.format_moves(w.solution),
            "misplaced": w.misplaced,
            "segments": w.segments,
        }
        with TempDir("_tmp_sampler_case1") as tmp:
            path = g.save_board(tmp, [list(t) for t in w.board], meta)
            matrix, back = g.load_board(path)
            self.assertEqual(matrix, [list(t) for t in w.board])
            self.assertEqual(back["misplaced"], w.misplaced)
            self.assertEqual(back["segments"], w.segments)
            self.assertEqual(back["level"], w.level)


if __name__ == "__main__":
    unittest.main()
