"""`tools/merge.py`：把几个题库临时拼成一个（目标先清空、源只读、按原来的档拼）。"""

import io
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from games.beadsort.tools import merge


class TempDir:
    """临时目录放在工作区里（系统的 temp 目录在沙箱里删不掉，见 test_make.py）。"""

    def __init__(self, name):
        self.path = Path(__file__).resolve().parent / name

    def __enter__(self):
        shutil.rmtree(self.path, ignore_errors=True)
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)
        return False


def make_lib(root: Path, levels: dict) -> None:
    """造个假题库：`{档: 道数}`，题目文件叫 `<库名>-<级>-<序号>.txt`。

    名字里带库名，好让两个库的同档题目**不重名**（真实 id 里带时间戳，本来也不重）。
    """
    for level, count in levels.items():
        d = root / str(level)
        d.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            name = "%s-%d-%02d.txt" % (root.name, level, i)
            (d / name).write_text("题", encoding="utf-8")


def levels_of(root: Path) -> dict:
    """题库里每档几道。"""
    out = {}
    for d in root.iterdir():
        if d.is_dir() and d.name.isdigit():
            out[int(d.name)] = len(list(d.glob("*.txt")))
    return out


def run(argv) -> int:
    """跑一趟 merge，把它 print 的东西吞掉（免得跟测试报告混在一起）。"""
    with redirect_stdout(io.StringIO()):
        return merge.main(argv)


class TestMerge(unittest.TestCase):
    def test_merges_by_level_into_a_cleared_target(self):
        with TempDir("_tmp_merge_a") as tmp:
            a, b, out = tmp / "puzzles_a", tmp / "puzzles_b", tmp / "puzzles"
            make_lib(a, {1: 2, 2: 1})
            make_lib(b, {1: 3})
            make_lib(out, {1: 7})                        # 目标里的旧题必须被清掉
            (out / "index.txt").write_text("旧台账", encoding="utf-8")

            self.assertEqual(run([str(out), str(a), str(b)]), 0)

            self.assertEqual(levels_of(out), {1: 5, 2: 1})
            self.assertFalse((out / "index.txt").exists(), "目标里的非题库文件也该删掉")

    def test_sources_are_only_read(self):
        with TempDir("_tmp_merge_b") as tmp:
            a, out = tmp / "puzzles_a", tmp / "puzzles"
            make_lib(a, {1: 2})

            run([str(out), str(a)])

            self.assertEqual(levels_of(a), {1: 2})       # 源一个字不动（是 copy 不是 move）
            self.assertEqual(levels_of(out), {1: 2})

    def test_same_name_keeps_the_first_one(self):
        with TempDir("_tmp_merge_c") as tmp:
            a, b, out = tmp / "puzzles_a", tmp / "puzzles_b", tmp / "puzzles"
            (a / "1").mkdir(parents=True)
            (b / "1").mkdir(parents=True)
            (a / "1" / "撞名.txt").write_text("先到的", encoding="utf-8")
            (b / "1" / "撞名.txt").write_text("后到的", encoding="utf-8")

            self.assertEqual(run([str(out), str(a), str(b)]), 0)

            self.assertEqual(levels_of(out), {1: 1})
            self.assertEqual((out / "1" / "撞名.txt").read_text(encoding="utf-8"), "先到的")

    def test_source_can_be_a_glob_and_target_skips_itself(self):
        with TempDir("_tmp_merge_d") as tmp:
            make_lib(tmp / "puzzles_a", {1: 2})
            make_lib(tmp / "puzzles_b", {3: 1})
            out = tmp / "puzzles_out"                    # 名字也匹配 puzzles_*

            self.assertEqual(run([str(out), str(tmp / "puzzles_*")]), 0)

            self.assertEqual(levels_of(out), {1: 2, 3: 1})

    def test_no_source_does_nothing(self):
        with TempDir("_tmp_merge_e") as tmp:
            out = tmp / "puzzles"
            make_lib(out, {1: 2})

            self.assertEqual(run([str(out), str(tmp / "puzzles_没有这个")]), 2)

            self.assertEqual(levels_of(out), {1: 2})     # 没源就原样不动

    def test_refuses_a_target_that_contains_a_source(self):
        with TempDir("_tmp_merge_f") as tmp:
            make_lib(tmp / "puzzles_a", {1: 2})

            self.assertEqual(run([str(tmp), str(tmp / "puzzles_a")]), 2)

            self.assertEqual(levels_of(tmp / "puzzles_a"), {1: 2})


if __name__ == "__main__":
    unittest.main()
