# -*- coding: utf-8 -*-
"""Kociemba 颜色排序最优解算器 —— Python 移植版

原始项目
    https://github.com/hkociemba/WaterBallSortPuzzleOptimalSolver
    作者 Herbert Kociemba，Object Pascal（Lazarus / Free Pascal）
    算法说明
        https://kociemba.org/themen/waterball/algorithm.html
        https://kociemba.org/themen/waterball/algorithm2.html

本文件是 ``water.pas`` 的 Python 移植，保留了原算法的结构与语义。

两种玩法
    single : 一次只挪一颗珠子（球排序，也就是本项目的玩法）。
             原作者的说明写得很清楚：该玩法下这个算法**只能给近似最优解**。
    multi  : 一次把源柱顶上同色的珠子尽可能多地倒过去（水排序）。
             算法对该玩法给出**最优解**。

核心思路
    把局面按「颜色块」计数。

    * multi 玩法：任何合法移动都不会让块数增加，已解局面固定是
      ``n_colors`` 个块，所以需要恰好 ``块数 - n_colors`` 次「减少块数」的移动。
    * single 玩法：把**空柱也算一个块**（即用 ``块数 + 空柱数`` 计数），
      同样保证单调不增。

    于是可以做一个二维广度优先::

        state[x][y] = 用掉 x 次「减少块数」的移动、y 次「不减少块数」的
                      移动之后，能到达的全部局面

    一层层往下扩展，``state[目标x][*]`` 第一次非空就是解。

去重
    同一局面内的柱子按字典序排序做归一化，消除「空柱位置不同」造成的重复；
    再用 32 位随机哈希去重。原版用一个 2³² 位的位图（512 MB），
    这里默认用 ``set`` —— 语义完全等价（都是按 32 位哈希值去重），但更省内存。

数据表示
    一根柱子是一个长度 ``n_volume`` 的整数列表，**下标 0 是最顶上那颗珠子，
    下标 n_volume-1 是最底下那颗**，0 表示空位。

    例如容量 5 的柱子里，从下到上依次是 红、蓝、绿::

        [0, 0, 绿, 蓝, 红]

    空柱是 ``[0, 0, 0, 0, 0]``；装满 5 颗红的是 ``[红, 红, 红, 红, 红]``。

    注意：这与 tjwood100 那个仓库的 JSON 格式相反（那个下标 0 在最底下）。
    用 :func:`make_vial` 可以从「从下到上」的写法转过来。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

EMPTY = 0
N_NOT_DECREASE = 1000
N_MAX_NODES = 2_000_000

# 与原版 TCls 枚举一一对应（0 = EMPTY）
COLOR_NAMES = (
    "··",  # 0  EMPTY
    "蓝",  # 1  BLUE
    "红",  # 2  RED
    "柠",  # 3  LIME
    "黄",  # 4  YELLOW
    "紫",  # 5  FUCHSIA
    "青",  # 6  AQUA
    "灰",  # 7  GRAY
    "玫",  # 8  ROSE
    "橄",  # 9  OLIVE
    "靛",  # 10 BROWN
    "天",  # 11 LBROWN
    "绿",  # 12 GREEN
    "橙",  # 13 LBLUE
    "黑",  # 14 BLACK
)

TopInfo = Tuple[int, int, int]  # (empty, topcol, topvol)


class _Abort(Exception):
    """内部用：达到节点上限时中止搜索。"""


# --------------------------------------------------------------------------
# 基础数据结构
# --------------------------------------------------------------------------


class Vial:
    """一根柱子。``color[0]`` 是最顶上那颗，``color[-1]`` 是最底下那颗。"""

    __slots__ = ("color", "pos")

    def __init__(self, color: Sequence[int], pos: int):
        self.color: List[int] = list(color)
        # 这根柱子在**初始局面**里的编号，专门用来报告走法（排序后次序会变）
        self.pos: int = pos

    def copy(self) -> "Vial":
        return Vial(self.color, self.pos)

    def top_info(self, n_volume: int) -> TopInfo:
        """对应原版 ``TVial.getTopInfo``。

        返回 ``(empty, topcol, topvol)``：

        * ``empty``：顶上第一颗珠子所在的下标，也就是空位数量（满柱为 0）
        * ``topcol``：顶上那一块的颜色（空柱为 0）
        * ``topvol``：顶上那一块有几颗珠子
        """
        c = self.color
        if c[n_volume - 1] == EMPTY:
            return (n_volume, 0, 0)  # 空柱
        empty = -1
        cl = 0
        for i in range(n_volume):
            if c[i] != EMPTY:
                empty = i
                cl = c[i]
                break
        topvol = 1
        for i in range(empty + 1, n_volume):
            if c[i] == cl:
                topvol += 1
            else:
                break
        return (empty, cl, topvol)

    def blocks(self, n_volume: int) -> int:
        """对应原版 ``TVial.vialBlocks``。空柱算 0 个块。"""
        c = self.color
        result = 1
        for i in range(n_volume - 1):
            if c[i + 1] != c[i]:
                result += 1
        if c[0] == EMPTY:
            result -= 1
        return result

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return "Vial(pos=%d, %r)" % (self.pos, self.color)


class Node:
    """一个局面：一组柱子 + 到达这一步所走的最后一步。"""

    __slots__ = ("vial", "hash", "mv_src", "mv_dst", "mv_merged")

    def __init__(self, vials: Sequence[Vial]):
        self.vial: List[Vial] = [v.copy() for v in vials]
        self.hash: int = 0
        self.mv_src: int = 0
        self.mv_dst: int = 0
        self.mv_merged: bool = False

    def sort(self) -> None:
        """柱子按字典序排序（对应原版 ``sortNode``，这里用等价的稳定写法）。"""
        self.vial.sort(key=lambda v: v.color)

    def node_blocks(self, n_volume: int, n_vials: int) -> int:
        return sum(self.vial[i].blocks(n_volume) for i in range(n_vials))

    def empty_vials(self, n_volume: int, n_vials: int) -> int:
        return sum(
            1 for i in range(n_vials) if self.vial[i].color[n_volume - 1] == EMPTY
        )

    def equal_q(self, other: "Node", n_volume: int, n_vials: int) -> bool:
        """假定两边都已经排好序。"""
        for i in range(n_vials):
            a = self.vial[i].color
            b = other.vial[i].color
            for j in range(n_volume):
                if a[j] != b[j]:
                    return False
        return True

    def get_hash(self, hsh, n_volume: int, n_vials: int) -> int:
        result = 0
        for v in range(n_vials):
            col = self.vial[v].color
            for p in range(n_volume):
                result ^= hsh[col[p]][p][v]
        return result & 0xFFFFFFFF

    def n_last_moves(
        self, single_mode: bool, n_empty_vials: int, n_volume: int
    ) -> int:
        """对应原版 ``TNode.Nlastmoves``（收尾还要走几步的估计）。"""
        if single_mode:
            result = 0
            for i in range(n_empty_vials):
                result += self.vial[i].top_info(n_volume)[2]
            return result
        result = n_empty_vials
        for i in range(n_empty_vials):
            if self.vial[i].color[n_volume - 1] == EMPTY:
                result -= 1
        return result

    def last_moves(
        self, n_colors: int, n_vials: int, n_volume: int
    ) -> List[Tuple[int, int]]:
        """对应原版 ``TNode.lastmoves``：把还没归位的珠子补完所需的走法。

        返回 ``[(src, dst), ...]``，用的是**初始柱子编号**（0 起）。
        """
        result: List[Tuple[int, int]] = []
        for i in range(1, n_colors + 1):
            j = n_vials - 1
            while j >= 0 and self.vial[j].top_info(n_volume)[1] != i:
                j -= 1
            if j < 0:
                continue
            if self.vial[j].top_info(n_volume)[0] == 0:
                continue  # 这个颜色的柱子已经满了
            for k in range(j):
                ti = self.vial[k].top_info(n_volume)
                if ti[1] == i:
                    for _ in range(ti[2]):
                        result.append((self.vial[k].pos, self.vial[j].pos))
        return result


# --------------------------------------------------------------------------
# 求解结果
# --------------------------------------------------------------------------


@dataclass
class SolveResult:
    """一次求解的结果。``moves`` 里的柱子编号是 0 起的初始编号。"""

    status: str  # optimal / near-optimal / solved / unsolved / aborted
    moves: List[Tuple[int, int]] = field(default_factory=list)
    moves_text: str = ""
    nodes_generated: int = 0
    message: str = ""
    correction_moves: List[Tuple[int, int]] = field(default_factory=list)

    @property
    def move_count(self) -> int:
        return len(self.moves)

    @property
    def total_move_count(self) -> int:
        return len(self.moves) + len(self.correction_moves)

    def __str__(self) -> str:  # pragma: no cover - 展示用
        return self.moves_text


# --------------------------------------------------------------------------
# 解算器
# --------------------------------------------------------------------------


class ColorSortSolver:
    """Kociemba 颜色排序解算器。

    参数
        n_colors      : 颜色数 C（颜色编号 1..C）
        n_volume      : 每根柱子的容量 N
        n_empty_vials : 空柱数量 K
        single_mode   : True = 一次挪一颗（球排序）；False = 一次倒尽可能多（水排序）
        node_limit    : 生成节点上限，超过就中止（对应原版 ``N_MAXNODES``）
        seed          : 哈希表的随机种子，只影响去重，不影响结果
    """

    def __init__(
        self,
        n_colors: int,
        n_volume: int,
        n_empty_vials: int,
        single_mode: bool = False,
        node_limit: int = N_MAX_NODES,
        seed: Optional[int] = None,
    ):
        if n_colors < 1:
            raise ValueError("n_colors 至少要 1")
        if n_volume < 2:
            raise ValueError("n_volume 至少要 2")
        if n_empty_vials < 1:
            raise ValueError("n_empty_vials 至少要 1")
        self.n_colors = n_colors
        self.n_volume = n_volume
        self.n_empty_vials = n_empty_vials
        self.n_vials = n_colors + n_empty_vials
        self.single_mode = single_mode
        self.node_limit = node_limit
        self._seed = seed
        self.visited: set = set()
        self.hsh: List[List[List[int]]] = []
        self.total_nodes = 0

    # -- 哈希表与去重 ----------------------------------------------------

    def _init_hash(self) -> None:
        rng = random.Random(self._seed)
        # 对应原版 hsh[NCOLORS+1, NVOLUME, NVIALS]
        self.hsh = [
            [
                [rng.getrandbits(32) for _ in range(self.n_vials)]
                for _ in range(self.n_volume)
            ]
            for _ in range(self.n_colors + 1)
        ]
        self.visited = set()
        self.total_nodes = 0

    def _is_hashed_q(self, h: int) -> bool:
        return h in self.visited

    def _write_hashbit(self, h: int) -> None:
        self.visited.add(h)

    # -- 一步移动 --------------------------------------------------------

    def _apply_move(
        self,
        nd: Node,
        ks: int,
        kd: int,
        vi_s: Optional[TopInfo] = None,
        vi_d: Optional[TopInfo] = None,
    ) -> Optional[Tuple[Node, bool]]:
        """从 ``nd`` 走出「第 ks 根 -> 第 kd 根」这一步。

        不合法返回 ``None``；合法返回 ``(新节点, 这一步是否减少块数)``。
        """
        if kd == ks:
            return None
        n_volume = self.n_volume
        if vi_s is None:
            vi_s = nd.vial[ks].top_info(n_volume)
        if vi_s[0] == n_volume:
            return None  # 源柱是空的
        if vi_d is None:
            vi_d = nd.vial[kd].top_info(n_volume)

        if self.single_mode:
            if (
                vi_d[0] == 0  # 目标柱满
                or (vi_d[0] < n_volume and vi_s[1] != vi_d[1])  # 顶色不同
                or (
                    vi_d[0] == n_volume and vi_s[0] == n_volume - 1
                )  # 目标空，且源柱只有一颗
            ):
                return None
            block_decrease_q = (vi_s[2] == 1) and (vi_s[0] != n_volume - 1)
            ndnew = Node(nd.vial)
            ndnew.vial[kd].color[vi_d[0] - 1] = vi_s[1]
            ndnew.vial[ks].color[vi_s[0]] = EMPTY
        else:
            if (
                vi_d[0] == 0
                or (vi_d[0] < n_volume and vi_s[1] != vi_d[1])
                or (
                    vi_d[0] == n_volume and vi_s[2] + vi_s[0] == n_volume
                )  # 目标空，且源柱整根同色
            ):
                return None
            block_decrease_q = (vi_d[0] < n_volume) and (vi_d[0] >= vi_s[2])
            vmin = min(vi_d[0], vi_s[2])
            ndnew = Node(nd.vial)
            for j in range(1, vmin + 1):
                ndnew.vial[kd].color[vi_d[0] - j] = vi_s[1]
                ndnew.vial[ks].color[vi_s[0] - 1 + j] = EMPTY

        ndnew.sort()
        return ndnew, block_decrease_q

    # -- 主入口 ----------------------------------------------------------

    def solve(self, vials_def: Sequence[Sequence[int]]) -> SolveResult:
        """求解一个局面。``vials_def`` 的格式见模块头部说明。"""
        if len(vials_def) != self.n_vials:
            raise ValueError(
                "柱子数量不对：期望 %d 根，收到 %d 根" % (self.n_vials, len(vials_def))
            )
        for c in vials_def:
            if len(c) != self.n_volume:
                raise ValueError("柱子容量不对：期望 %d 个格子" % self.n_volume)
            for x in c:
                if not (0 <= x <= self.n_colors):
                    raise ValueError(
                        "颜色编号越界：%r（本局颜色数 %d，合法范围 0..%d）"
                        % (x, self.n_colors, self.n_colors)
                    )
        self._init_hash()
        if self.single_mode:
            return self._solve_single(vials_def)
        return self._solve_multi(vials_def)

    # -- 公共搜索骨架 ----------------------------------------------------

    def _search(self, vials_def: Sequence[Sequence[int]], goal_x: int, nblock_v: int):
        """两种玩法共用的二维广度优先骨架。

        返回 ``(state, found, y_end, total, aborted)``。
        """
        n_volume, n_vials = self.n_volume, self.n_vials
        nd = Node([Vial(c, i) for i, c in enumerate(vials_def)])
        nd.sort()
        nd.hash = nd.get_hash(self.hsh, n_volume, n_vials)

        y = 0
        state: Dict[Tuple[int, int], List[Node]] = {}
        # 列 0 要整列建好（原版：for i := 0 to nblockV-NCOLORS do state[i,y] := TList.Create）
        for i in range(goal_x + 1):
            state[(i, 0)] = []
        state[(0, 0)].append(nd)
        self._write_hashbit(nd.hash)
        total = 1
        found = False
        aborted = False

        try:
            while True:
                newnodes = 0
                for i in range(goal_x + 1):
                    state[(i, y + 1)] = []
                for x in range(goal_x):
                    for nd in state.get((x, y), ()):
                        for ks in range(n_vials):
                            vi_s = nd.vial[ks].top_info(n_volume)
                            if vi_s[0] == n_volume:
                                continue
                            for kd in range(n_vials):
                                if kd == ks:
                                    continue
                                vi_d = nd.vial[kd].top_info(n_volume)
                                res = self._apply_move(nd, ks, kd, vi_s, vi_d)
                                if res is None:
                                    continue
                                ndnew, block_decrease_q = res
                                ndnew.hash = ndnew.get_hash(
                                    self.hsh, n_volume, n_vials
                                )
                                if self._is_hashed_q(ndnew.hash):
                                    continue
                                self._write_hashbit(ndnew.hash)
                                total += 1
                                if total > self.node_limit:
                                    raise _Abort()
                                ndnew.mv_src = nd.vial[ks].pos
                                ndnew.mv_dst = nd.vial[kd].pos
                                if block_decrease_q:
                                    ndnew.mv_merged = True
                                    state[(x + 1, y)].append(ndnew)
                                else:
                                    ndnew.mv_merged = False
                                    state[(x, y + 1)].append(ndnew)
                                    newnodes += 1
                if state.get((goal_x, y)):
                    found = True
                y += 1
                if found or newnodes == 0:
                    break
                if y > N_NOT_DECREASE:
                    raise _Abort()
        except _Abort:
            aborted = True
        return state, found, y, total, aborted

    def _walk_back(
        self, state, x: int, y: int, nd: Node
    ) -> List[Tuple[int, int]]:
        """反向回溯出一条完整走法，返回正序列表。"""
        n_volume, n_vials = self.n_volume, self.n_vials
        rev: List[Tuple[int, int]] = []
        src, dst = nd.mv_src, nd.mv_dst
        rev.append((src, dst))
        if nd.mv_merged:
            x -= 1
        else:
            y -= 1
        while x != 0 or y != 0:
            for cand in state.get((x, y), ()):
                ks = next(i for i in range(n_vials) if cand.vial[i].pos == src)
                kd = next(i for i in range(n_vials) if cand.vial[i].pos == dst)
                res = self._apply_move(cand, ks, kd)
                if res is None:
                    continue
                ndcand, _ = res
                if nd.equal_q(ndcand, n_volume, n_vials):
                    nd = cand
                    src, dst = nd.mv_src, nd.mv_dst
                    rev.append((src, dst))
                    if nd.mv_merged:
                        x -= 1
                    else:
                        y -= 1
                    break
            else:
                break  # 理论上不会发生
        return list(reversed(rev))

    # -- 一次倒尽可能多（最优） -------------------------------------------

    def _solve_multi(self, vials_def: Sequence[Sequence[int]]) -> SolveResult:
        n_volume, n_vials, n_colors = self.n_volume, self.n_vials, self.n_colors
        nd0 = Node([Vial(c, i) for i, c in enumerate(vials_def)])
        nd0.sort()
        nblock_v = nd0.node_blocks(n_volume, n_vials)
        goal_x = nblock_v - n_colors

        state, found, y, total, aborted = self._search(vials_def, goal_x, nblock_v)
        self.total_nodes = total

        if aborted:
            return SolveResult(
                status="aborted",
                nodes_generated=total,
                message="达到节点上限 %d，已中止（原版 N_MAXNODES）" % self.node_limit,
            )
        if not found or not state.get((goal_x, y - 1)):
            return SolveResult(
                status="unsolved",
                nodes_generated=total,
                message="无解。请回退，或者换一个局面。",
            )
        if nblock_v == n_colors:
            return SolveResult(
                status="solved",
                nodes_generated=total,
                message="这个局面已经解开了。",
            )

        moves = self._walk_back(state, goal_x, y - 1, state[(goal_x, y - 1)][0])
        return SolveResult(
            status="optimal",
            moves=moves,
            moves_text=format_moves(moves),
            nodes_generated=total,
            message="最优解，共 %d 步" % len(moves),
        )

    # -- 一次挪一颗（近似最优） -------------------------------------------

    def _solve_single(self, vials_def: Sequence[Sequence[int]]) -> SolveResult:
        n_volume, n_vials, n_colors = self.n_volume, self.n_vials, self.n_colors
        nd0 = Node([Vial(c, i) for i, c in enumerate(vials_def)])
        nd0.sort()
        # 空柱也算一个块：用「块数 + 空柱数」计数才单调不增
        nblock_v = (
            nd0.node_blocks(n_volume, n_vials)
            + nd0.empty_vials(n_volume, n_vials)
            - self.n_empty_vials
        )
        goal_x = max(0, nblock_v - n_colors)

        state, found, y, total, aborted = self._search(vials_def, goal_x, nblock_v)
        self.total_nodes = total

        if aborted:
            return SolveResult(
                status="aborted",
                nodes_generated=total,
                message="达到节点上限 %d，已中止（原版 N_MAXNODES）" % self.node_limit,
            )
        if not found or not state.get((goal_x, y - 1)):
            return SolveResult(
                status="unsolved",
                nodes_generated=total,
                message="无解。请回退，或者换一个局面。",
            )

        # 原版：在终止列里挑一个「收尾走法最少」的局面
        col = state[(goal_x, y - 1)]
        best, best_n = 0, 10 ** 9
        for k, node in enumerate(col):
            n = node.n_last_moves(self.single_mode, self.n_empty_vials, n_volume)
            if n < best_n:
                best, best_n = k, n
        if best:
            col[0], col[best] = col[best], col[0]

        terminal = col[0]
        correction = terminal.last_moves(n_colors, n_vials, n_volume)

        if nblock_v <= n_colors:
            return SolveResult(
                status="near-optimal",
                moves=[],
                moves_text=format_moves(correction),
                correction_moves=correction,
                nodes_generated=total,
                message="只需收尾 %d 步" % len(correction),
            )

        moves = self._walk_back(state, goal_x, y - 1, terminal)
        text = format_moves(moves)
        if correction:
            text = text + "\n收尾：" + format_moves(correction)
        return SolveResult(
            status="near-optimal",
            moves=moves,
            moves_text=text,
            correction_moves=correction,
            nodes_generated=total,
            message="近似最优解：主体 %d 步 + 收尾 %d 步 = 共 %d 步"
            "（原版只报告主体步数）" % (len(moves), len(correction), len(moves) + len(correction)),
        )


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------


def format_moves(moves: Sequence[Tuple[int, int]], per_line: int = 10) -> str:
    """把走法列表拼成人类可读的字符串，柱子编号按 1 起算（与原版一致）。"""
    if not moves:
        return ""
    parts = ["%d->%d" % (s + 1, d + 1) for s, d in moves]
    lines = []
    for i in range(0, len(parts), per_line):
        lines.append("  ".join(parts[i : i + per_line]))
    return "\n".join(lines)


def make_vial(bottom_to_top: Sequence[int], n_volume: int) -> List[int]:
    """把「从下到上」的写法转成内部表示（下标 0 在最上面）。"""
    if len(bottom_to_top) > n_volume:
        raise ValueError("珠子数量超过柱子容量")
    pad = [EMPTY] * (n_volume - len(bottom_to_top))
    return pad + list(reversed(bottom_to_top))


def random_puzzle(
    n_colors: int,
    n_volume: int,
    n_empty_vials: int,
    rng: Optional[random.Random] = None,
) -> List[List[int]]:
    """随机打乱生成一个局面（对应原版 ``TBRandomClick`` 的 Fisher-Yates）。

    **注意：不保证有解**，与原版行为一致。
    """
    rng = rng or random.Random()
    flat: List[int] = []
    for c in range(1, n_colors + 1):
        flat.extend([c] * n_volume)
    rng.shuffle(flat)
    vials: List[List[int]] = []
    for i in range(n_colors):
        vials.append(flat[i * n_volume : (i + 1) * n_volume])
    for _ in range(n_empty_vials):
        vials.append([EMPTY] * n_volume)
    return vials


def render(
    vials: Sequence[Sequence[int]], n_volume: int, names=None, width: int = 2
) -> str:
    """把局面画成网格：横向是柱子，纵向从上到下。"""
    names = names or COLOR_NAMES
    lines = [
        "".join("%*s" % (width, i + 1) for i in range(len(vials)))
    ]
    for p in range(n_volume):
        row = []
        for c in vials:
            v = c[p]
            row.append("%*s" % (width, names[v] if v < len(names) else str(v)))
        lines.append("".join(row))
    return "\n".join(lines)


def load_puzzle(path: str) -> Tuple[List[List[int]], int]:
    """读 JSON 局面。支持两种格式：

    * 本移植版：``{"vials": [[顶部在前的整数], ...]}``
    * tjwood100 风格：``{"tubes": [[底部在前的字符], ...]}``

    返回 ``(局面, 颜色数)``。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "vials" in data:
        vials = [list(v) for v in data["vials"]]
        n_colors = max(max(v) for v in vials)
        return vials, n_colors
    if "tubes" in data:
        tubes = data["tubes"]
        n_volume = max(len(t) for t in tubes)
        order: Dict[str, int] = {}
        for t in tubes:
            for ch in t:
                if ch not in order:
                    order[ch] = len(order) + 1
        vials = [make_vial([order[ch] for ch in t], n_volume) for t in tubes]
        return vials, len(order)
    raise ValueError("JSON 里既没有 vials 也没有 tubes")


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Kociemba 颜色排序解算器（Python 移植版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例子：\n"
            "  --colors 6 --volume 10 --empty 1 --single --random\n"
            "  --colors 4 --volume 5  --empty 2 --multi  --random\n"
        ),
    )
    p.add_argument("--colors", type=int, help="颜色数 C")
    p.add_argument("--volume", type=int, help="每根柱子的容量 N")
    p.add_argument("--empty", type=int, default=2, help="空柱数量 K（默认 2）")
    p.add_argument(
        "--single",
        dest="single",
        action="store_true",
        default=None,
        help="一次挪一颗（球排序，近似最优）",
    )
    p.add_argument(
        "--multi",
        dest="single",
        action="store_false",
        help="一次倒尽可能多（水排序，最优）",
    )
    p.add_argument("--seed", type=int, default=None, help="随机种子")
    p.add_argument("--puzzle", help="从 JSON 文件读入局面")
    p.add_argument("--save", help="把（随机生成的）局面存成 JSON")
    p.add_argument("--node-limit", type=int, default=N_MAX_NODES, help="节点上限")
    p.add_argument("--quiet", action="store_true", help="只输出解，不输出局面")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    rng = random.Random(args.seed)

    if args.puzzle:
        vials, n_colors = load_puzzle(args.puzzle)
        n_volume = len(vials[0])
        n_empty = len(vials) - n_colors
    else:
        if not args.colors or not args.volume:
            print("需要 --colors 和 --volume（或用 --puzzle）", file=sys.stderr)
            return 2
        n_colors, n_volume, n_empty = args.colors, args.volume, args.empty
        vials = random_puzzle(n_colors, n_volume, n_empty, rng)

    single = bool(args.single)

    if not args.quiet:
        print("局面（每根柱子：从上到下）")
        print(render(vials, n_volume))
        print()
        print(
            "玩法：%s   颜色数 %d，容量 %d，空柱 %d，共 %d 根柱子"
            % (
                "一次一颗（球排序）" if single else "一次多颗（水排序）",
                n_colors,
                n_volume,
                n_empty,
                len(vials),
            )
        )
        print()

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "vials": vials,
                    "n_colors": n_colors,
                    "n_volume": n_volume,
                    "n_empty_vials": n_empty,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        print("已把局面存到 %s" % args.save)

    print("求解中……")
    solver = ColorSortSolver(
        n_colors=n_colors,
        n_volume=n_volume,
        n_empty_vials=n_empty,
        single_mode=single,
        node_limit=args.node_limit,
        seed=args.seed,
    )
    result = solver.solve(vials)
    print("状态：%s" % result.status)
    print("生成节点数：%d" % result.nodes_generated)
    if result.message:
        print(result.message)
    if result.moves_text:
        print()
        print("走法（柱子编号从 1 起）：")
        print(result.moves_text)
    return 0 if result.status in ("optimal", "near-optimal", "solved") else 1


if __name__ == "__main__":
    sys.exit(main())
