# -*- coding: utf-8 -*-
"""移植正确性验证。

这里用一个**独立重写**的暴力广度优先搜索当参照物，去核对移植版：

1. multi 玩法（一次倒尽可能多）下，移植版给出的必须是**真正的最优步数**；
2. 两种玩法下，「有解 / 无解」的判断必须和暴力搜索**完全一致**；
3. 移植版给出的走法套到盘面上，必须真的能走成已解状态；
4. single 玩法（一次挪一颗）已知是近似最优，所以只要求
   「不比最优更短」且「走法合法、能解开」。

暴力搜索是照着规则另写的，没有复用被测代码，所以能起交叉验证的作用。

运行：
    python -m unittest test_kociemba_solver -v
"""

import os
import random
import sys
import unittest
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kociemba_solver import (  # noqa: E402
    EMPTY,
    ColorSortSolver,
    make_vial,
    random_puzzle,
    render,
)

#
# 独立的暴力参照实现
#


def canon(vials):
    """归一化：柱子排序，消除「空柱位置不同」造成的重复。"""
    return tuple(sorted(tuple(v) for v in vials))


def leading_zeros(v):
    n = 0
    for x in v:
        if x == EMPTY:
            n += 1
        else:
            break
    return n


def top_block(v):
    """返回 (颗数, 颜色)。空柱返回 (0, 0)。"""
    n = len(v)
    i = 0
    while i < n and v[i] == EMPTY:
        i += 1
    if i == n:
        return 0, 0
    col = v[i]
    c = 0
    while i < n and v[i] == col:
        c += 1
        i += 1
    return c, col


def is_solved(state):
    """真正的胜利条件：每根柱子要么空，要么**装满**同一种颜色。"""
    for v in state:
        seen = {x for x in v if x != EMPTY}
        if len(seen) > 1:
            return False
        if seen and len([x for x in v if x != EMPTY]) != len(v):
            return False
    return True


def is_monochrome(state):
    """弱一点的条件：每根柱子要么空，要么整根同色（可以没装满）。

    这是 single 玩法算法的终止条件，还需要收尾几步才真正解开。
    """
    for v in state:
        seen = {x for x in v if x != EMPTY}
        if len(seen) > 1:
            return False
    return True


def brute_optimal(vials, single_mode, node_limit=400_000):
    """暴力 BFS。返回最优步数；无解返回 -1；超出上限返回 None。"""
    start = canon(vials)
    if is_solved(start):
        return 0
    dist = {start: 0}
    q = deque([start])
    while q:
        s = q.popleft()
        d = dist[s]
        for ks in range(len(s)):
            tc, col = top_block(s[ks])
            if tc == 0:
                continue
            for kd in range(len(s)):
                if kd == ks:
                    continue
                dz = leading_zeros(s[kd])
                if dz == 0:
                    continue
                dc, dcol = top_block(s[kd])
                if dc > 0 and dcol != col:
                    continue
                cnt = 1 if single_mode else min(dz, tc)
                new = [list(v) for v in s]
                sz = leading_zeros(s[ks])  # 源柱顶珠所在下标
                for j in range(cnt):
                    new[kd][dz - 1 - j] = col
                    new[ks][sz + j] = EMPTY
                nxt = canon(new)
                if nxt in dist:
                    continue
                if is_solved(nxt):
                    return d + 1
                dist[nxt] = d + 1
                q.append(nxt)
        if len(dist) > node_limit:
            return None
    return -1


def apply_moves(vials, moves, single_mode):
    """把走法套到盘面上。moves 用的是初始柱子编号。"""
    cur = [[list(v), i] for i, v in enumerate(vials)]
    for src, dst in moves:
        si = next(i for i, (_, p) in enumerate(cur) if p == src)
        di = next(i for i, (_, p) in enumerate(cur) if p == dst)
        sv, dv = cur[si][0], cur[di][0]
        tc, col = top_block(sv)
        sz = leading_zeros(sv)
        dz = leading_zeros(dv)
        assert tc > 0, "源柱是空的"
        assert dz > 0, "目标柱已经满了"
        dc, dcol = top_block(dv)
        assert dc == 0 or dcol == col, "目标柱顶色对不上"
        cnt = 1 if single_mode else min(dz, tc)
        for j in range(cnt):
            dv[dz - 1 - j] = col
            sv[sz + j] = EMPTY
    return [v for v, _ in cur]


#
# 测试
#


class TestAgainstBruteForce(unittest.TestCase):
    """和暴力搜索对拍。"""

    SIZES = [
        (2, 2, 1),
        (2, 2, 2),
        (3, 2, 1),
        (3, 2, 2),
        (2, 3, 1),
        (2, 3, 2),
        (3, 3, 1),
        (4, 2, 2),
    ]
    TRIALS = 12

    def _run(self, single):
        rng = random.Random(20260911)
        checked = 0
        for n_colors, n_volume, n_empty in self.SIZES:
            for _ in range(self.TRIALS):
                vials = random_puzzle(n_colors, n_volume, n_empty, rng)
                want = brute_optimal(vials, single)
                if want is None:
                    continue
                solver = ColorSortSolver(
                    n_colors, n_volume, n_empty, single_mode=single, seed=12345
                )
                got = solver.solve(vials)
                label = "%dx%d+%d %s" % (
                    n_colors,
                    n_volume,
                    n_empty,
                    "single" if single else "multi",
                )

                if want == -1:
                    self.assertEqual(
                        got.status,
                        "unsolved",
                        "%s: 暴力搜索判定无解，移植版说 %s" % (label, got.status),
                    )
                    continue

                self.assertNotEqual(
                    got.status,
                    "unsolved",
                    "%s: 暴力搜索找到了 %d 步解，移植版却说无解" % (label, want),
                )

                mid = apply_moves(vials, got.moves, single)
                final = apply_moves(mid, got.correction_moves, single)
                self.assertTrue(
                    is_monochrome(canon(mid)),
                    "%s: 主体走法走完不是「每根柱子单色或空」\n%s"
                    % (label, render(mid, n_volume)),
                )
                self.assertTrue(
                    is_solved(canon(final)),
                    "%s: 走完（含收尾）还没解开\n%s"
                    % (label, render(final, n_volume)),
                )

                if not single:
                    self.assertEqual(
                        got.total_move_count,
                        want,
                        "%s: 移植版给了 %d 步，暴力搜索最优是 %d 步"
                        % (label, got.total_move_count, want),
                    )
                else:
                    self.assertGreaterEqual(
                        got.total_move_count,
                        want,
                        "%s: 移植版 %d 步比暴力搜索最优 %d 步还短，不可能"
                        % (label, got.total_move_count, want),
                    )
                checked += 1
        return checked

    def test_multi_is_optimal(self):
        n = self._run(single=False)
        self.assertGreater(n, 40, "有效样本太少，只跑了 %d 个" % n)

    def test_single_is_valid_and_not_better_than_optimal(self):
        n = self._run(single=True)
        self.assertGreater(n, 40, "有效样本太少，只跑了 %d 个" % n)

    def test_unsolvable_cases_are_detected(self):
        """确认真的存在无解局面，而且移植版能判出来。"""
        rng = random.Random(7)
        found = 0
        # 3 色 / 容量 3 / 只有 1 根空柱 —— 这个配置里无解局面很常见
        for _ in range(300):
            vials = random_puzzle(3, 3, 1, rng)
            if brute_optimal(vials, False) != -1:
                continue
            found += 1
            solver = ColorSortSolver(3, 3, 1, single_mode=False, seed=1)
            self.assertEqual(solver.solve(vials).status, "unsolved")
        self.assertGreater(found, 0, "样本里居然没有无解局面，测试没有意义")


class TestBasics(unittest.TestCase):
    def test_make_vial(self):
        # 容量 5，从下到上 红(2)、蓝(1)、绿(12)
        self.assertEqual(make_vial([2, 1, 12], 5), [EMPTY, EMPTY, 12, 1, 2])
        self.assertEqual(make_vial([], 3), [EMPTY, EMPTY, EMPTY])
        self.assertEqual(make_vial([4, 4, 4], 3), [4, 4, 4])

    def test_already_solved(self):
        vials = [[1] * 3, [2] * 3, [EMPTY] * 3]
        solver = ColorSortSolver(2, 3, 1, single_mode=False)
        r = solver.solve(vials)
        self.assertEqual(r.status, "solved")
        self.assertEqual(r.moves, [])

    def test_rejects_out_of_range_color(self):
        solver = ColorSortSolver(2, 3, 1, single_mode=False)
        with self.assertRaises(ValueError):
            solver.solve([[4, 4, 4], [2, 2, 2], [EMPTY, EMPTY, EMPTY]])

    def test_render_smoke(self):
        vials = [[EMPTY, EMPTY, 2], [EMPTY, 1, 1], [EMPTY, EMPTY, EMPTY]]
        text = render(vials, 3)
        self.assertEqual(len(text.splitlines()), 4)

    def test_deterministic_case_matches_brute(self):
        # 容量 3、2 色、1 根空柱：红红蓝 / 蓝蓝红 / 空
        vials = [[2, 2, 1], [1, 1, 2], [EMPTY, EMPTY, EMPTY]]
        want = brute_optimal(vials, False)
        solver = ColorSortSolver(2, 3, 1, single_mode=False, seed=1)
        r = solver.solve(vials)
        self.assertIsNotNone(want, "暴力搜索没跑完")
        if want == -1:
            self.assertEqual(r.status, "unsolved")
        else:
            self.assertEqual(r.total_move_count, want)
            self.assertTrue(is_solved(canon(apply_moves(vials, r.moves, False))))

    def test_big_board_already_solved(self):
        """和实物同量级的参数：6 色、容量 10、7 根柱子，已解状态。"""
        vials = [[c] * 10 for c in range(1, 7)] + [[EMPTY] * 10]
        solver = ColorSortSolver(6, 10, 1, single_mode=True)
        r = solver.solve(vials)
        self.assertEqual(r.status, "near-optimal")
        self.assertEqual(r.moves, [])
        self.assertEqual(r.correction_moves, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
