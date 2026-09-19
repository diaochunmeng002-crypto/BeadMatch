"""统一出题入口（tools/make.py）的测试。"""

import shutil
import unittest
from pathlib import Path

from games.beadmatch.core import generator as g
from games.beadmatch.tools import make


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


class TestMake(unittest.TestCase):
    def test_defaults(self):
        args = make.build_parser().parse_args([])
        self.assertEqual(args.n, 10)
        self.assertEqual(args.level, 5)
        self.assertEqual(args.out, str(make.DEFAULT_OUT))

    def test_only_three_options(self):
        """就这三个参数：--n / --level / --out。"""
        opts = sorted(s for a in make.build_parser()._actions
                      for s in a.option_strings if s not in ("-h", "--help"))
        self.assertEqual(opts, ["--level", "--n", "--out"])

    def test_run_writes_puzzles_that_load_back(self):
        with TempDir("_tmp_make") as tmp:
            rc = make.main(["--n", "3", "--level", "2", "--out", str(tmp)])
            self.assertEqual(rc, 0)
            files = sorted(tmp.glob("*/*.txt"))
            self.assertEqual(len(files), 3)
            for f in files:
                _matrix, meta = g.load_board(f)      # 读入即逐步验合法性
                self.assertEqual(meta["level"], 2)
                self.assertEqual(meta["moves"], 20)
                self.assertEqual(meta["generator"], g.GENERATOR)

    def test_level_decides_the_folder(self):
        with TempDir("_tmp_make_lv") as tmp:
            make.main(["--n", "1", "--level", "7", "--out", str(tmp)])
            f = sorted(tmp.glob("*/*.txt"))[0]
            self.assertEqual(f.parent.name, "7")


if __name__ == "__main__":
    unittest.main()
