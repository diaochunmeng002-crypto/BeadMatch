"""宝宝串珠的统一出题入口（2026-09-19 起）：``--n`` 道 / ``--level`` 档 / ``--out`` 目录。

出题方式还是 ``walk_gen`` 的引导式反走 —— **反走即解**，不需要求解器，也出得来，
所以 ``--n`` 既是尝试次数也是出题数（跟 beadsort 那边的 ``--n`` 一个口径）。

    python -m games.beadmatch.tools.make                                        # 默认 10 道 5 级
    python -m games.beadmatch.tools.make --n 50 --level 9 --out games/beadmatch/puzzles_new

默认：``--n 10`` / ``--level 5`` / ``--out games/beadmatch/puzzles``。
老的 ``core.generator``（单道 + ``--show``）和 ``tools.make_puzzles``（按步数分批）还在，没动。
"""

from __future__ import annotations

import argparse
import random
import time
from pathlib import Path
from typing import Optional, Sequence

from ..core import generator as g

GAME_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = GAME_DIR / "puzzles"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="宝宝串珠出题：--n 道 / --level 档 / --out 目录")
    p.add_argument("--n", type=int, default=10, help="出几道（默认 10）")
    p.add_argument("--level", type=int, default=5,
                   help="难度等级（默认 5）：走 level × %d 步" % g.LEVEL_STEP)
    p.add_argument("--out", default=str(DEFAULT_OUT),
                   help="题库目录（默认 %s）" % DEFAULT_OUT)
    return p


def save_unique(root: Path, matrix, meta: dict, tries: int = 50) -> Path:
    """写一道题；id 撞车就换一个 id 再写（一口气写几百上千道时，落盘都挤在
    同一秒里，秒级时间戳 + 4 位随机后缀很容易撞）。"""
    for _ in range(tries):
        try:
            return g.save_board(root, matrix, meta)
        except FileExistsError:
            meta = dict(meta)
            meta["id"] = g.make_id()
    raise RuntimeError("连着 %d 次都撞 id，这一道放弃：%s" % (tries, meta.get("id")))


def run(args) -> int:
    root = Path(args.out)
    seed0 = random.SystemRandom().randrange(1, 2 ** 31)     # 每次都是新的一批；打印出来备查
    steps = args.level * g.LEVEL_STEP
    print("出题：%d 级（走 %d 步）× %d 道 → %s" % (args.level, steps, args.n, root))
    print("本批种子起点：seed0=%d（每道题文件里也各自写着它的 seed）" % seed0)
    print(flush=True)

    period = min(50, max(1, args.n // 10))                  # 小批量逐道打，大批量每 N 道一行
    levels: dict = {}
    t0 = time.time()
    for i in range(args.n):
        seed = seed0 + i
        matrix, meta = g.generate(args.level, seed=seed)
        save_unique(root, matrix, meta)
        levels[meta["level"]] = levels.get(meta["level"], 0) + 1
        if period == 1 or (i + 1) % period == 0 or i + 1 == args.n:
            print("  %5d/%d  %s  等级 %s / %s 步" % (i + 1, args.n, meta["id"],
                                                     meta["level"], meta["moves"]), flush=True)

    print()
    print("一共写了 %d 道到 %s（等级 %s）；用时 %.1fs"
          % (args.n, root, " / ".join(str(lv) for lv in sorted(levels)),
             time.time() - t0))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
