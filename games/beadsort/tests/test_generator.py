"""generator 的测试：题目文件的渲染 / 解析 / 存读 / 校验。"""

import random
import shutil
import unittest
from pathlib import Path

from games.beadsort.core import generator as g
from games.beadsort.core import walk_gen
from games.beadsort.core.free_solver import is_finished, verify


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


class TestRenderParse(unittest.TestCase):
    def setUp(self):
        self.matrix, self.meta = g.generate(seed=1, walk_steps=20)

    def test_round_trip(self):
        text = g.render_board(self.matrix, self.meta)
        matrix, meta = g.parse_board(text)
        self.assertEqual(matrix, [list(t) for t in self.matrix])
        for k in meta:
            self.assertEqual(meta[k], self.meta[k], "字段 %s 不一致" % k)

    def test_save_load_round_trip(self):
        with TempDir("_tmp_generator_case1") as tmp:
            path = g.save_board(tmp, self.matrix, self.meta)
            self.assertEqual(path.name, "%s.txt" % self.meta["id"])
            self.assertEqual(path.parent.name, str(self.meta["level"]))  # 按等级分文件夹
            matrix, meta = g.load_board(path)
            self.assertEqual(matrix, [list(t) for t in self.matrix])
            self.assertEqual(meta["id"], self.meta["id"])
            self.assertEqual(meta["level"], self.meta["level"])

    def test_refuses_to_overwrite(self):
        with TempDir("_tmp_generator_case2") as tmp:
            path = g.save_board(tmp, self.matrix, self.meta)
            with self.assertRaises(FileExistsError):
                g.save_board(path, self.matrix, self.meta)

    def test_save_into_not_yet_existing_dir(self):
        """给一个还没建的目录名（没有扩展名）时，要当成目录，别写成一个同名文件。"""
        with TempDir("_tmp_generator_case4") as tmp:
            target = tmp / "puzzles"
            path = g.save_board(target, self.matrix, self.meta)
            self.assertTrue(target.is_dir())
            self.assertEqual(path.parent.parent, target)
            self.assertEqual(path.parent.name, str(self.meta["level"]))
            self.assertEqual(path.name, "%s.txt" % self.meta["id"])

    def test_solution_is_recorded_and_verified(self):
        """solution 写在元信息里，读回来要能套回去解开。"""
        self.assertIn("solution", self.meta)
        text = g.render_board(self.matrix, self.meta)
        self.assertIn("solution=", text)
        _matrix, meta = g.parse_board(text)
        self.assertEqual(meta["solution"], self.meta["solution"])

    def test_provenance_fields(self):
        """出身字段：新出的题必须带 created_by / generator，读回来一致。"""
        self.assertEqual(self.meta["created_by"], g.CREATED_BY)
        self.assertEqual(self.meta["generator"], g.GENERATOR)
        self.assertEqual(self.meta["solution_by"], "walk")
        text = g.render_board(self.matrix, self.meta)
        self.assertIn("created_by=%s" % g.CREATED_BY, text)
        self.assertIn("generator=%s" % g.GENERATOR, text)
        self.assertIn("solution_by=%s" % self.meta["solution_by"], text)
        _matrix, meta = g.parse_board(text)
        self.assertEqual(meta["created_by"], g.CREATED_BY)
        self.assertEqual(meta["generator"], g.GENERATOR)
        self.assertEqual(meta["solution_by"], self.meta["solution_by"])

    def test_solution_by_is_optional_and_checked(self):
        """solution_by 可选；写了就只校验格式。"""
        lines = [ln for ln in g.render_board(self.matrix, self.meta).splitlines()
                 if not ln.startswith("solution_by=")]
        _matrix, meta = g.parse_board("\n".join(lines))
        self.assertNotIn("solution_by", meta)
        bad = g.render_board(self.matrix, self.meta).replace(
            "solution_by=%s" % self.meta["solution_by"], "solution_by=kociemba v2")
        with self.assertRaises(ValueError):
            g.parse_board(bad)

    def test_created_at_is_first_and_created_by_is_second(self):
        """正文（元信息区）第一行是 created_at，第二行是 created_by。"""
        text = g.render_board(self.matrix, self.meta)
        body = [ln for ln in text.splitlines()
                if ln and not ln.startswith("#") and "=" in ln]
        self.assertTrue(body[0].startswith("created_at="))
        self.assertTrue(body[1].startswith("created_by="))
        self.assertNotIn("# created", text)          # 不再写进注释区
        _matrix, meta = g.parse_board(text)
        self.assertEqual(meta["created_at"], self.meta["created_at"])

    def test_bad_created_at_is_rejected(self):
        bad = g.render_board(self.matrix, self.meta).replace(
            "created_at=%s" % self.meta["created_at"], "created_at=2026/09/14")
        with self.assertRaises(ValueError):
            g.parse_board(bad)

    def test_provenance_fields_are_optional(self):
        """老文件（没有这两个字段）也要能读 —— 向后兼容。"""
        lines = [ln for ln in g.render_board(self.matrix, self.meta).splitlines()
                 if not ln.startswith(("generator=", "created_by="))]
        _matrix, meta = g.parse_board("\n".join(lines))
        self.assertNotIn("generator", meta)

    def test_bad_provenance_value_is_rejected(self):
        bad = g.render_board(self.matrix, self.meta).replace(
            "generator=%s" % g.GENERATOR, "generator=random walk@1")
        with self.assertRaises(ValueError):
            g.parse_board(bad)

    def test_header_lines_are_ignored(self):
        """# 开头的行（含以后再插的注释）一律不读。"""
        text = g.render_board(self.matrix, self.meta)
        text = text.replace("# colors:", "# whatever: xxx\n# colors:", 1)
        matrix, meta = g.parse_board(text)
        self.assertEqual(matrix, [list(t) for t in self.matrix])

    def test_grid_only_without_meta(self):
        text = g.render_board(self.matrix)
        self.assertNotIn("=", text)
        self.assertEqual(len(text.splitlines()), g.CAPACITY)


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.matrix, self.meta = g.generate(seed=2, walk_steps=20)
        self.text = g.render_board(self.matrix, self.meta)

    def test_missing_key(self):
        lines = [ln for ln in self.text.splitlines() if not ln.startswith("level=")]
        with self.assertRaises(ValueError):
            g.parse_board("\n".join(lines))

    def test_bad_row_count(self):
        lines = self.text.splitlines()
        del lines[-1]
        with self.assertRaises(ValueError):
            g.parse_board("\n".join(lines))

    def test_bad_level(self):
        bad = self.text.replace("level=%s" % self.meta["level"], "level=99")
        with self.assertRaises(ValueError):
            g.parse_board(bad)

    def test_unknown_letter(self):
        lines = self.text.splitlines()
        lines[-1] = "Q" + lines[-1][1:]
        with self.assertRaises(ValueError):
            g.parse_board("\n".join(lines))

    def test_id_must_match_filename(self):
        with TempDir("_tmp_generator_case3") as tmp:
            path = tmp / "wrong-name.txt"
            path.write_text(self.text, encoding="utf-8")
            with self.assertRaises(ValueError):
                g.load_board(path)

    def test_empty_must_be_on_top(self):
        """空位必须在前半段：第 4 根柱子写成「空、珠、空」应当报错。"""
        text = "\n".join([
            "id=20260912-000000-0001",
            "tubes=4",
            "colors=YGR",
            "capacity=3",
            "balls_per_color=3",
            "level=0",
            "moves=0",
            "",
            "X X X X",
            "Y G R Y",
            "Y G R X",
        ])
        with self.assertRaises(ValueError):
            g.parse_board(text)

    def test_broken_solution_is_rejected(self):
        """solution 被改坏（多一步，解不开）时，读入应当报错。"""
        bad = self.text.replace("solution=", "solution=9-9 ", 1)
        with self.assertRaises(ValueError):
            g.parse_board(bad)


class TestGenerate(unittest.TestCase):
    def test_meta_and_level(self):
        for seed in (1, 2, 3):
            matrix, meta = g.generate(seed=seed, walk_steps=20)
            self.assertEqual(meta["level"], g.level_of(meta["moves"]))
            self.assertEqual(meta["tubes"], g.TUBES)
            self.assertEqual(meta["colors"], g.COLOR_LETTERS[: g.COLORS])
            self.assertEqual(meta["steps"], 20)
            self.assertEqual(len(matrix), g.TUBES)
            self.assertEqual(len(matrix[0]), g.CAPACITY)
            # 用记录下来的 seed + steps 必须能复现出同一道题（新算法是确定性的）
            again, _raw, _sol = walk_gen.walk(meta["seed"], 20)
            self.assertEqual([list(t) for t in again], matrix)

    def test_generated_puzzle_is_solvable_and_solution_matches_moves(self):
        """题目自带的 solution 必须真的能解开，而且步数和 moves 对得上。"""
        matrix, meta = g.generate(seed=5, walk_steps=20)
        moves = g.parse_moves(str(meta["solution"]))
        self.assertEqual(len(moves), meta["moves"])
        self.assertTrue(verify(matrix, moves))

    def test_same_seed_reproduces(self):
        a, ma = g.generate(seed=7, walk_steps=20)
        b, mb = g.generate(seed=7, walk_steps=20)
        self.assertEqual(a, b)
        self.assertEqual(ma["moves"], mb["moves"])

    def test_puzzle_is_not_finished(self):
        matrix, _meta = g.generate(seed=9, walk_steps=20)
        self.assertFalse(is_finished(matrix))


if __name__ == "__main__":
    unittest.main()
