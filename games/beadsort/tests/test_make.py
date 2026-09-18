"""统一出题入口（tools/make.py）与两个出题方法的测试。"""

import shutil
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from games.beadsort.core import generator as g
from games.beadsort.core import methods
from games.beadsort.core import sampler as sp
from games.beadsort.core.free_solver import verify
from games.beadsort.tools import make


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


class TestRegistry(unittest.TestCase):
    def test_two_methods_registered(self):
        self.assertEqual(methods.names(), ["kociemba", "walk"])

    def test_per_level_default_is_per_method(self):
        """walk 有产出压力所以要刹车；kociemba 产出太稀，默认不限。"""
        self.assertEqual(methods.get("walk").per_level_default, 20)
        self.assertEqual(methods.get("kociemba").per_level_default, 0)

    def test_unknown_method(self):
        with self.assertRaises(KeyError):
            methods.get("没有这个方法")


class TestKeep(unittest.TestCase):
    """分档截断：cap=0 不限；满了换掉分最低的；同分先到先得。"""

    @staticmethod
    def _cand(rank):
        return methods.Candidate(board=(), solution=[], generator="t",
                                 solution_by="t", rank=rank)

    def test_unlimited(self):
        bucket = []
        for _ in range(5):
            make.keep(bucket, self._cand(0), 0)
        self.assertEqual(len(bucket), 5)

    def test_first_come_first_served_on_ties(self):
        bucket = []
        for _ in range(5):
            make.keep(bucket, self._cand(0), 3)
        self.assertEqual(len(bucket), 3)

    def test_higher_rank_replaces_the_worst(self):
        bucket = [self._cand(r) for r in (1, 2, 3)]
        make.keep(bucket, self._cand(9), 3)
        self.assertEqual(sorted(c.rank for c in bucket), [2, 3, 9])
        make.keep(bucket, self._cand(0), 3)          # 比最差的还差 → 不收
        self.assertEqual(sorted(c.rank for c in bucket), [2, 3, 9])


class TestWalkMethod(unittest.TestCase):
    def tearDown(self):
        sp.configure(7, 6, 10, 10)                   # walk 会改全局参数，恢复掉

    def _args(self, more=()):
        method = methods.get("walk")
        args = make.build_parser(method).parse_args(["--method", "walk"] + list(more))
        if args.capacity is None:
            args.capacity = args.per
        method.setup(args)
        return method

    def test_attempt_gives_a_solvable_puzzle(self):
        cand = self._args().attempt(7)
        self.assertIsNotNone(cand)
        self.assertTrue(verify(cand.board, cand.solution))
        self.assertEqual(cand.generator, sp.GENERATOR)
        self.assertEqual(cand.solution_by, "walk")
        self.assertIn("misplaced", cand.extra)

    def test_chaos_pick_ranks_the_worst_first(self):
        method = self._args(["--pick", "chaos"])
        cand = method.attempt(3)
        self.assertGreater(cand.rank, 0)             # chaos 才打分
        self.assertEqual(self._args().attempt(3).rank, 0.0)

    def test_run_writes_puzzles_that_load_back(self):
        with TempDir("_tmp_make_walk") as tmp:
            rc = make.main(["--method", "walk", "--n", "300", "--per-level", "2",
                            "--out", str(tmp), "--quiet", "--seed0", "1"])
            self.assertEqual(rc, 0)
            files = sorted(tmp.glob("*/*.txt"))
            self.assertTrue(files)
            per_level = {}
            for f in files:
                _matrix, meta = g.load_board(f)      # 读入即逐步验合法性
                self.assertEqual(meta["generator"], sp.GENERATOR)
                self.assertEqual(meta["solution_by"], "walk")
                self.assertEqual(meta["level"], g.level_of(meta["moves"]))
                per_level[f.parent.name] = per_level.get(f.parent.name, 0) + 1
            self.assertTrue(all(n <= 2 for n in per_level.values()), per_level)


class TestKociembaMethod(unittest.TestCase):
    SMALL = ["--method", "kociemba", "--colors", "4", "--per", "4", "--tubes", "6"]

    def _method(self, more=(), argv=None):
        method = methods.get("kociemba")
        args = make.build_parser(method).parse_args(argv or (self.SMALL + list(more)))
        if args.capacity is None:
            args.capacity = args.per
        method.setup(args)
        return method

    def test_attempt_gives_a_solvable_puzzle(self):
        method = self._method()                      # 小棋盘：一两次尝试就能出
        for seed in range(1, 6):
            cand = method.attempt(seed)
            if cand is None:
                continue
            self.assertTrue(verify(cand.board, cand.solution),
                            "求解器给的解必须能套回局面")
            self.assertEqual(cand.generator, "kociemba@1")
            self.assertEqual(cand.solution_by, "kociemba")
            return
        self.fail("小棋盘 5 次尝试一道都没出来")

    def test_attempt_can_give_up(self):
        """真配置（6 色 10 颗 1 空柱）随机摆几乎必然无解 → 返回 None，不是报错。"""
        method = self._method(argv=["--method", "kociemba"])
        self.assertIsNone(method.attempt(1))

    def test_spread_b_also_works(self):
        method = self._method(["--spread", "b"])
        cand = None
        for seed in range(1, 20):
            cand = method.attempt(seed)
            if cand is not None:
                break
        self.assertIsNotNone(cand)
        self.assertTrue(verify(cand.board, cand.solution))

    def test_default_is_unlimited_so_nothing_is_dropped(self):
        with TempDir("_tmp_make_koci") as tmp:
            rc = make.main(self.SMALL + ["--n", "20", "--out", str(tmp),
                                         "--quiet", "--seed0", "1"])
            self.assertEqual(rc, 0)
            files = sorted(tmp.glob("*/*.txt"))
            self.assertTrue(files)
            for f in files:
                _matrix, meta = g.load_board(f)
                self.assertEqual(meta["generator"], "kociemba@1")
                self.assertEqual(meta["solution_by"], "kociemba")

    def test_progress_prints_even_when_every_attempt_fails(self):
        """2026-09-18 的坑：战绩行原本写在"成功"分支里，而 kociemba 九成九失败
        （被 continue 跳过）→ 跑了半天一行都不打。这条钉住它。"""
        with TempDir("_tmp_make_koci2") as tmp:
            buf = StringIO()
            with redirect_stdout(buf):
                rc = make.main(["--method", "kociemba", "--n", "30", "--progress", "10",
                                "--seed0", "1", "--out", str(tmp)])
            self.assertEqual(rc, 0)
            text = buf.getvalue()
            self.assertEqual(text.count("✓"), 0, "真配置下这 30 次应该一次都没出")
            bars = [ln for ln in text.splitlines() if ln.strip().startswith("[")]
            self.assertGreaterEqual(len(bars), 3, "一次没出也必须照打战绩：\n" + text)
            self.assertIn("命中率", bars[0])


class TestCli(unittest.TestCase):
    def test_seed0_accepts_number_random_time(self):
        """固定数字 = 可复现；random / time = 每次换一批。"""
        self.assertEqual(make.resolve_seed0("7"), 7)
        self.assertEqual(make.resolve_seed0(7), 7)
        self.assertAlmostEqual(make.resolve_seed0("time"), time.time(), delta=5)
        self.assertTrue(1 <= make.resolve_seed0("random") < 2 ** 31)
        with self.assertRaises(ValueError):
            make.resolve_seed0("随便写的")

    def test_seed0_defaults_to_random(self):
        """默认就是真随机起点：同一条命令跑两次，是两批不同的题。"""
        args = make.build_parser(methods.get("walk")).parse_args(["--method", "walk"])
        self.assertEqual(args.seed0, "random")
        draws = {make.resolve_seed0(args.seed0) for _ in range(5)}
        self.assertGreater(len(draws), 1)            # 五次里总不至于全撞上

    def test_rule_only_single_for_now(self):
        with self.assertRaises(SystemExit):
            make.main(["--method", "walk", "--rule", "multi"])

    def test_method_is_required(self):
        with self.assertRaises(SystemExit):
            make.main([])

    def test_capacity_follows_per(self):
        """不给 --capacity 时柱容量跟着 --per 走（彩柱正好装满）。"""
        args = make.build_parser(methods.get("walk")).parse_args(
            ["--method", "walk", "--per", "4"])
        self.assertIsNone(args.capacity)

    def test_puzzles_is_an_alias_of_out(self):
        """--puzzles 和 --out 是同一个参数（题库目录就是写出的地方）。"""
        parser = make.build_parser(methods.get("walk"))
        a = parser.parse_args(["--method", "walk"])
        b = parser.parse_args(["--method", "walk", "--puzzles", "D:/别的库"])
        c = parser.parse_args(["--method", "walk", "--out", "D:/别的库"])
        self.assertEqual(a.out, str(make.DEFAULT_OUT))
        self.assertEqual(b.out, c.out)


if __name__ == "__main__":
    unittest.main()
