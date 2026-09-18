"""方法二：**随机摆 + Kociemba 筛**（2026-09-18 加）。

一次尝试 = 随机摆一个局面 → 丢给还原回来的 Kociemba（`core/kociemba_solver.py`，
``single`` 模式 = 我们的"一次一颗、只能放空柱或同色柱顶"）→ **解出来才留**。

为什么这个方法"便宜"：失败是**秒判**（约 0.01 秒就报 unsolved），成功才真搜
（0.03~0.15 秒）。所以广撒网不心疼 —— 实测 1 万次尝试 ≈ 50 秒。

为什么每档默认**不限**（`per_level_default = 0`）：产出率极低（实测 0.05%），
再按 20 截断就是白扔稀有的东西。walk 那边才需要刹车。

两种"随机摆"（``--spread``）：

* ``a`` 每根彩柱**正好装满** + K 根空柱 —— 原版 ``TBRandomClick`` 的做法（实测 5/10000）
* ``b`` 每颗球随机丢进**还有位置的柱子**（柱子可以不装满）—— 更接近"把 60 颗珠子
  倒进 7 根柱子"的物理样子
"""

from __future__ import annotations

import random
import time
from typing import List, Optional

from .. import kociemba_solver as ks
from .. import sampler as sp
from ..free_solver import EMPTY, freeze, verify
from ..generator import COLOR_LETTERS
from . import Candidate, Method, register

OK_STATUS = ("optimal", "near-optimal", "solved")


class KociembaMethod(Method):
    name = "kociemba"
    generator = "kociemba@1"
    solution_by = "kociemba"
    per_level_default = 0               # 不限：产出太稀，舍不得截

    def add_args(self, parser) -> None:
        parser.add_argument("--spread", default="a", choices=("a", "b"),
                            help="随机摆的分布：a = 彩柱装满+空柱（默认，原版做法）；"
                                 "b = 每颗球随便丢进还有位置的柱子")
        parser.add_argument("--node-limit", type=int, default=ks.N_MAX_NODES,
                            help="求解器节点上限，超了算放弃（原版 N_MAXNODES，默认 %d）"
                                 % ks.N_MAX_NODES)

    def setup(self, args) -> None:
        self.colors = int(args.colors)
        self.volume = int(args.per)                  # 每根彩柱正好装 per 颗
        self.empty = int(args.tubes) - int(args.colors)
        self.width = self.colors + self.empty
        self.spread = args.spread
        self.node_limit = args.node_limit
        if self.colors > len(COLOR_LETTERS):
            raise ValueError("题目文件的颜色字母只有 %s 六种，颜色数先别超过 6"
                             % COLOR_LETTERS)
        if self.empty < 1:
            raise ValueError("至少要留 1 根空柱（现在 %d 柱 %d 色）"
                             % (args.tubes, args.colors))

    # -- 随机摆 ----------------------------------------------------------

    def _random_puzzle(self, rng: random.Random) -> List[List[int]]:
        if self.spread == "a":                       # 彩柱装满 + 空柱（原版）
            return ks.random_puzzle(self.colors, self.volume, self.empty, rng)
        board = [[EMPTY] * self.volume for _ in range(self.width)]
        balls = [c for c in range(1, self.colors + 1) for _ in range(self.volume)]
        rng.shuffle(balls)
        for c in balls:
            t = rng.choice([t for t in range(self.width) if board[t][0] == EMPTY])
            e = 0
            while e < self.volume and board[t][e] == EMPTY:
                e += 1
            board[t][e - 1] = c
        return board

    # -- 一次尝试 --------------------------------------------------------

    def attempt(self, seed: int) -> Optional[Candidate]:
        t0 = time.time()
        rng = random.Random(seed)
        vials = self._random_puzzle(rng)
        solver = ks.ColorSortSolver(self.colors, self.volume, self.empty,
                                    single_mode=True, node_limit=self.node_limit)
        res = solver.solve(vials)
        if res.status not in OK_STATUS:
            return None                              # 放弃了（unsolved / aborted）
        board = freeze(vials)                        # 它的 vial[0] = 顶上那颗，跟我们的格式同向
        moves = list(res.moves) + list(res.correction_moves)
        if not verify(board, moves):                 # 保险：解必须能套回局面
            return None
        return Candidate(
            board=board, solution=moves, generator=self.generator,
            solution_by=self.solution_by, seconds=time.time() - t0,
            extra={"solver_status": res.status, **sp.chaos(board)},
        )

    def describe(self) -> str:
        return "%s 模式（%d 色 / 容量 %d / 空 %d 柱）" % (
            "彩柱装满" if self.spread == "a" else "随便丢", self.colors, self.volume, self.empty)

METHOD = register(KociembaMethod())
