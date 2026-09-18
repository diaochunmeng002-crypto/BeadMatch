"""题库目录可以换：后端的 `--puzzles` / 环境变量，广场的 `--puzzles 游戏id=目录`。"""

import os
import subprocess
import sys
import unittest

import run as runpy                     # 仓库根的 run.py

from games.beadsort import api
from games.beadsort.core import generator as g


class TestApiPuzzlesDir(unittest.TestCase):
    def test_default_is_puzzles(self):
        self.assertEqual(api.PUZZLE_DIR, g.PUZZLE_DIR)
        self.assertEqual(api.PUZZLE_DIR.name, "puzzles")

    def test_env_var_overrides_the_default(self):
        """api 在导入时读 BEADSORT_PUZZLES —— 广场就是靠它换库的。

        换个进程验（同一进程里 reload 会把 app 对象换掉，怕影响别的测试）。
        """
        code = ("import os; os.environ['BEADSORT_PUZZLES'] = 'games/beadsort/puzzles_kociemba';"
                "from games.beadsort import api; print(api.PUZZLE_DIR.name)")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "puzzles_kociemba")


class TestPlazaPuzzlesFlag(unittest.TestCase):
    def test_apply_puzzles_sets_env(self):
        os.environ.pop("BEADSORT_PUZZLES", None)
        runpy.apply_puzzles(["beadsort=games/beadsort/puzzles_kociemba"])
        self.assertEqual(os.environ["BEADSORT_PUZZLES"], "games/beadsort/puzzles_kociemba")
        os.environ.pop("BEADSORT_PUZZLES", None)

    def test_apply_puzzles_handles_several(self):
        runpy.apply_puzzles(["beadsort=A", "logic=B"])
        self.assertEqual(os.environ["BEADSORT_PUZZLES"], "A")
        self.assertEqual(os.environ["LOGIC_PUZZLES"], "B")
        for k in ("BEADSORT_PUZZLES", "LOGIC_PUZZLES"):
            os.environ.pop(k, None)

    def test_bad_format_is_rejected(self):
        with self.assertRaises(SystemExit):
            runpy.apply_puzzles(["beadsort"])


if __name__ == "__main__":
    unittest.main()
