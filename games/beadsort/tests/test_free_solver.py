"""free_solver 的测试：规则、格式不变量、以及与独立暴力搜索对拍。"""

import random
import unittest
from collections import deque

from games.beadsort.core.free_solver import (
    EMPTY,
    apply_move,
    color_count,
    is_finished,
    key,
    legal_moves,
    solve_any,
    verify,
)


# --------------------------------------------------------------------------
# 造局面（内部格式：下标 0 = 最顶端，0 表示空位）
# --------------------------------------------------------------------------


def solved_state(colors: int, cap: int, empty: int):
    return [tuple([c] * cap) for c in range(1, colors + 1)] + [
        tuple([0] * cap) for _ in range(empty)
    ]


def random_walk(colors: int, cap: int, empty: int, steps: int, seed: int):
    rng = random.Random(seed)
    state = tuple(solved_state(colors, cap, empty))
    for _ in range(steps):
        moves = legal_moves(state)
        if not moves:
            break
        state = apply_move(state, rng.choice(moves))
    return state


# --------------------------------------------------------------------------
# 独立重写的暴力搜索（故意不调用 free_solver 的内部逻辑，用来对拍）
# --------------------------------------------------------------------------


def to_stacks(state):
    """内部格式 -> 紧凑的「从下到上」写法。"""
    return tuple(tuple(v for v in reversed(tube) if v != 0) for tube in state)


def independent_solved(stacks, cap):
    seen_color = set()
    for stack in stacks:
        if not stack:
            continue
        if len(set(stack)) != 1:
            return False
        if stack[0] in seen_color:
            return False
        seen_color.add(stack[0])
    return True


def independent_moves(stacks, cap):
    """独立重写的走法（竞技规则：目标柱空着，或顶色跟要搬的那颗一样）。"""
    out = []
    for i, src in enumerate(stacks):
        if not src:
            continue
        color = src[-1]
        for j, dst in enumerate(stacks):
            if i != j and len(dst) < cap and (not dst or dst[-1] == color):
                out.append((i, j))
    return out


def independent_apply(stacks, move):
    i, j = move
    new = list(stacks)
    new[i] = stacks[i][:-1]
    new[j] = stacks[j] + (stacks[i][-1],)
    return tuple(new)


def independent_bfs(state, cap, limit=300_000):
    """最短步数（与 free_solver 完全独立的实现）。搜不完返回 None。"""
    start = to_stacks(state)
    if independent_solved(start, cap):
        return 0
    seen = {tuple(sorted(start))}
    queue = deque([(start, 0)])
    while queue:
        cur, depth = queue.popleft()
        for move in independent_moves(cur, cap):
            nxt = independent_apply(cur, move)
            k = tuple(sorted(nxt))
            if k in seen:
                continue
            if independent_solved(nxt, cap):
                return depth + 1
            seen.add(k)
            if len(seen) > limit:
                return None
            queue.append((nxt, depth + 1))
    return None


class TestRules(unittest.TestCase):
    def test_goal_accepts_solved(self):
        self.assertTrue(is_finished(solved_state(3, 3, 1)))

    def test_goal_rejects_split_color(self):
        """一种颜色被拆到两根单色柱上 —— 按 2.3 不算赢。"""
        state = [(1, 1, 0), (1, 0, 0), (2, 2, 2), (3, 3, 3), (0, 0, 0)]
        self.assertFalse(is_finished(state))

    def test_goal_rejects_mixed_tube(self):
        state = [(1, 2, 0), (1, 1, 0), (2, 2, 2), (3, 3, 3), (0, 0, 0)]
        self.assertFalse(is_finished(state))

    def test_moves_only_onto_same_color_or_empty(self):
        """竞技规则：目标柱只能**空着**，或者**顶色跟要搬的那颗一样**。"""
        # 注意：下标 0 是最顶端，所以「上面还有空位」要写成 0 在前
        state = ((0, 1, 1), (0, 2, 2), (0, 0, 0))
        moves = set(legal_moves(state))
        self.assertNotIn((0, 1), moves)   # 1 色搬到 2 色上面：**不允许**（不同色）
        self.assertNotIn((1, 0), moves)   # 反过来也不行
        self.assertIn((0, 2), moves)  # 搬到空柱
        same = ((0, 1, 1), (0, 1, 1), (0, 0, 0))     # 两根柱子顶色都是 1，且都有空位
        self.assertIn((0, 1), set(legal_moves(same)))   # 顶色相同就允许
        # 目标柱满了就不行
        full = ((1, 1, 1), (2, 2, 2), (3, 3, 3))
        self.assertNotIn((0, 1), set(legal_moves(full)))

    def test_reversible_says_which_ball_can_be_taken(self):
        """施工式反走：只有"拎起来还露同色"（或拿空）的那颗才拿得动。"""
        from games.beadsort.core.free_solver import reversible
        mixed = ((0, 1, 2), (0, 2, 2), (0, 0, 0))     # 柱1 顶上 1、下面 2
        self.assertFalse(reversible(mixed, (0, 1)))    # 拿走 1 会露出 2 → 倒不回来
        self.assertTrue(reversible(mixed, (1, 0)))     # 柱2 顶上两颗都是 2 → 可以
        single = ((0, 0, 3), (0, 0, 0))                # 只有一颗 → 拿完就空，可以
        self.assertTrue(reversible(single, (0, 1)))

    def test_apply_move_keeps_invariants(self):
        """空位必须始终在每根柱子的前半段，球的颜色和数量不能变。"""
        state = random_walk(6, 10, 1, 120, seed=3)
        before = {c: sum(color_count(t, c) for t in state) for c in range(1, 7)}
        rng = random.Random(4)
        for _ in range(50):
            state = apply_move(state, rng.choice(legal_moves(state)))
            for tube in state:
                seen_ball = False
                for v in tube:
                    if v != EMPTY:
                        seen_ball = True
                    else:
                        self.assertFalse(seen_ball, "空位跑到珠子下面了")
        after = {c: sum(color_count(t, c) for t in state) for c in range(1, 7)}
        self.assertEqual(before, after)


class TestSolver(unittest.TestCase):
    def test_matches_independent_search_on_small(self):
        """小规模对拍：我们的解合法、能解开，而且不比最优短。"""
        for seed in (1, 2, 3, 4, 5):
            state = random_walk(3, 3, 2, 8 + seed, seed)
            best = independent_bfs(state, 3)
            moves = solve_any(state)
            self.assertIsNotNone(moves, "seed=%d 没解出来" % seed)
            self.assertTrue(verify(state, moves), "解是错的（seed=%d）" % seed)
            if best is not None:
                self.assertGreaterEqual(len(moves), best, "比最优还短，不可能")

    def test_real_parameters(self):
        """真实参数：6 色 / 10 颗 / 7 柱，乱走 60 步的题要能解出来。

        注意 100 步以上不是每道题都解得动 —— 那是出题器用"换个种子重走"兜底的
        （见 generator.generate 的 attempts）。

        预算给了 20 秒（原来是 5 秒）：这道题的解要搜十几秒，机器一忙 5 秒就不够，
        测试会随机器快慢时红时绿。要测的是"解得开"，不是"5 秒内解得开"。
        """
        state = random_walk(6, 10, 1, 60, seed=1)
        moves = solve_any(state, time_limit=20.0, node_limit=2_000_000)
        self.assertIsNotNone(moves, "真实参数的题没解出来")
        self.assertTrue(verify(state, moves))

    def test_already_solved(self):
        self.assertEqual(solve_any(solved_state(3, 3, 1)), [])


if __name__ == "__main__":
    unittest.main()
