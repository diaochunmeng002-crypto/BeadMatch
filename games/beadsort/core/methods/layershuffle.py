"""方法三：**按层构造 + Kociemba 筛**（2026-09-19 加）。

跟 kociemba 方法的唯一区别是"局面怎么来"：

* kociemba      —— 60 颗球纯随机丢进柱子，绝大多数摆法无解（实测出题率 0.05%）；
* layershuffle  —— **按层**摆。横着看，每一排（所有彩柱的同一层）正好 6 颗球，
  规则要求这一排 **6 种颜色各一颗，不能多也不能少**；每一排各自真随机排列，
  10 排互不相干。柱子竖着看完全自由，怎么乱都行。

其余照抄 kociemba：摆好 → 丢给求解器 → **解出来才留** → `verify` 兜一道 → 交 `Candidate`。
两个标签各记一事：`generator=layershuffle@1`（局面是谁造的）、
`solution_by=kociemba`（解是谁给的）。

``--shuffle N``：**打乱几下**。给了就从"已解局面"出发，随机挑一排、把那一排的两颗
球对调，做 N 次（换位只在排内进行，所以"每排 6 色各一"照样成立）。N 越大越乱：

    N=3  ≈ 2~7 级      N=6  ≈ 4~10 级     N=10 ≈ 4~13 级     N≥20 ≈ 12 级往上

不给就是**每排完全随机排列**（原来的行为，实测已经是这一族里最乱的一头，
离位中位 40、解长中位 161，≈ N 在 40~60 的饱和区）。等级最终还是按解长自动分档，
一个 N 值对应的是一段区间、不是某一级。

为什么每档默认留 20 道（不像 kociemba 那样不限）：这种构造很可能接近 100% 有解，
一次尝试就出一道，不给上限的话 `--n 100` 会一口气灌进去 100 道。

用法：

    python -m games.beadsort.tools.make --method layershuffle --n 20 --out games/beadsort/puzzles_layershuffle
"""

from __future__ import annotations

import random
from typing import List

from .. import kociemba_solver as ks
from . import register
from .kociemba import KociembaMethod


class LayerShuffleMethod(KociembaMethod):
    """按层构造：每一排（同一层的所有彩柱）6 色各一颗，排与排之间独立真随机。"""

    name = "layershuffle"
    generator = "layershuffle@1"
    solution_by = "kociemba"
    per_level_default = 20              # 产出率接近 1（像 walk），所以必须刹车

    def add_args(self, parser) -> None:
        """只留求解器参数：kociemba 的 --spread（怎么摆）对这套构造没意义。"""
        parser.add_argument("--node-limit", type=int, default=ks.N_MAX_NODES,
                            help="求解器节点上限，超了算放弃（默认 %d）" % ks.N_MAX_NODES)
        parser.add_argument("--shuffle", type=int, default=None, metavar="次数",
                            help="从已解局面做几次换位（每次挑一排、对调两颗球）；"
                                 "不给 = 每排完全随机。给小值出中低等级："
                                 "3≈2~7 级、6≈4~10 级、10≈4~13 级、20 以上≈12 级往上")

    def setup(self, args) -> None:
        # 父类的 setup 会读 args.spread；这里摆法由规则定死，补个占位再交给它。
        if not hasattr(args, "spread"):
            args.spread = "a"
        super().setup(args)
        self.shuffle = getattr(args, "shuffle", None)
        if self.shuffle is not None and self.shuffle < 0:
            raise ValueError("--shuffle 不能是负数（0 = 已解局面，不给 = 每排完全随机）")

    # -- 按层构造 ----------------------------------------------------------

    def _random_puzzle(self, rng: random.Random) -> List[List[int]]:
        """给了 --shuffle 就从已解局面换位；不给就是每排一个全排列。空柱留在最后。"""
        if self.shuffle is not None:
            return self._shuffled_puzzle(rng)
        board = [[ks.EMPTY] * self.volume for _ in range(self.width)]
        for row in range(self.volume):
            colors = list(range(1, self.colors + 1))
            rng.shuffle(colors)
            for tube in range(self.colors):
                board[tube][row] = colors[tube]
        return board

    def _shuffled_puzzle(self, rng: random.Random) -> List[List[int]]:
        """已解局面 + self.shuffle 次换位（每次挑一排，对调那一排的两颗球）。"""
        board = [[ks.EMPTY] * self.volume for _ in range(self.width)]
        for tube in range(self.colors):               # 先摆成已解：每根彩柱单色
            for row in range(self.volume):
                board[tube][row] = tube + 1
        if self.colors < 2:
            return board
        for _ in range(self.shuffle):
            row = rng.randrange(self.volume)
            a, b = rng.sample(range(self.colors), 2)
            board[a][row], board[b][row] = board[b][row], board[a][row]
        return board

    def describe(self) -> str:
        if self.shuffle is not None:
            return ("从已解局面做 %d 次换位（每排仍是 %d 色各一颗）；"
                    "%d 色 / 容量 %d / 空 %d 柱"
                    % (self.shuffle, self.colors, self.colors, self.volume, self.empty))
        return ("按层构造：%d 排，每排 %d 色各一颗（排间独立真随机）；"
                "%d 色 / 容量 %d / 空 %d 柱"
                % (self.volume, self.colors, self.colors, self.volume, self.empty))


METHOD = register(LayerShuffleMethod())
