"""BeadMatch 的出题算法：从已解局面「引导式随机走」，**反走即解**。

为什么这样能出题（关键性质）：本项目的规则下（落点只要有空位就能放），
每一步都可逆 —— 把球从 B 搬回 A 一定合法（A 刚空出一格）。
所以**把走法倒过来就是一条合法解**，不需要任何求解器：
出题 100% 成功、毫秒级，而且再也不依赖第三方代码。

走法上的四条规则（2026-09-14 定）：

1. **不重复状态** —— 柱子排序后归一化，走过的局面不再进
2. **禁止立即回撤** —— 刚搬走的球不能马上搬回去
3. **两步前瞻** —— 选一步时，看「这步 + 之后最优的一步」的乱度合计收益
   （这样"先挖一步、下一步才有收益"的组合会被一次性发现）
4. **合并同球连搬** —— `A→B` 紧跟 `B→C` 等价于 `A→C`，前者不计步、也不进解法
"""

from __future__ import annotations

import random
from typing import Dict, List, Sequence, Tuple

from free_solver import EMPTY, apply_move, key, legal_moves

State = Tuple[Tuple[int, ...], ...]
Move = Tuple[int, int]

# 算法版本：换算法/改规则时递增，写进题目文件的 `generator` 字段
GENERATOR = "walk_guided@4"


# --------------------------------------------------------------------------
# 乱度指标
# --------------------------------------------------------------------------


def runs(tube: Sequence[int]) -> List[List[int]]:
    """同色连续段（从顶到底，忽略空位）→ ``[[颜色, 长度], ...]``"""
    out: List[List[int]] = []
    prev = None
    for v in tube:
        if v == EMPTY:
            continue
        if out and v == prev:
            out[-1][1] += 1
        else:
            out.append([v, 1])
        prev = v
    return out


def max_run(state: State) -> int:
    """最长同色连续段（越短越乱；1 = 完全没有相邻同色）"""
    return max((n for tube in state for _c, n in runs(tube)), default=0)


def bottom_run(state: State) -> int:
    """各柱子「最底下那一段」的长度之和（7 根相加，越小说明底部越被打散）"""
    return sum(runs(t)[-1][1] for t in state if runs(t))


def seg_total(state: State) -> int:
    """颜色段总数（越多越交错；上限 = 球数）"""
    return sum(len(runs(t)) for t in state)


def kinds_per_tube(state: State) -> float:
    """每根柱子平均有几种颜色"""
    return sum(len({v for v in t if v}) for t in state) / len(state)


def adjacent_same(state: State) -> int:
    """整盘里「相邻两颗同色」的对数（已解局面 = 54，完全交错 = 0）"""
    n = 0
    for tube in state:
        prev = None
        for v in tube:
            if v == EMPTY:
                continue
            if prev is not None and v == prev:
                n += 1
            prev = v
    return n


def scatter(state: State) -> int:
    """打散度（越大越乱）：段数越多越好，最长段/底部段越短越好。"""
    return 2 * seg_total(state) - 3 * max_run(state) - 2 * bottom_run(state)


def metrics(state: State) -> Dict[str, float]:
    """一次算齐所有指标（出题后报告用）。"""
    return {
        "max_run": max_run(state),
        "bottom_run": bottom_run(state),
        "bottom_run_per_tube": round(bottom_run(state) / len(state), 2),
        "seg_total": seg_total(state),
        "kinds_per_tube": round(kinds_per_tube(state), 2),
        "adjacent_same": adjacent_same(state),
    }


# --------------------------------------------------------------------------
# 走一步
# --------------------------------------------------------------------------


def longest_run_tube(state: State) -> int:
    """最长同色段所在的那根柱子（"挖"的时候从它下手）。"""
    best = (-1, 0)
    for i, tube in enumerate(state):
        rs = runs(tube)
        if rs:
            length = max(n for _c, n in rs)
            if length > best[0]:
                best = (length, i)
    return best[1]


def choose(state: State, prev, rng: random.Random,
           visited: set) -> Move | None:
    """两步前瞻：挑一步，使「它 + 之后最优的一步」的打散度合计最高。

    并列最优里随机挑一个（否则每个种子会走出同一条路）。
    """
    cur = scatter(state)
    undo = (prev[1], prev[0]) if prev else None
    cands = [m for m in legal_moves(state) if m != undo]
    fresh = [m for m in cands if key(apply_move(state, m)) not in visited]
    cands = fresh or cands
    if not cands:
        return None

    best_score = None
    tied: List[Move] = []
    for m1 in cands:
        s1 = apply_move(state, m1)
        gain1 = scatter(s1) - cur
        undo2 = (m1[1], m1[0])
        gain2 = 0
        for m2 in legal_moves(s1):
            if m2 == undo2:
                continue
            d = scatter(apply_move(s1, m2)) - scatter(s1)
            if d > gain2:
                gain2 = d
        score = gain1 + gain2
        if best_score is None or score > best_score:
            best_score, tied = score, [m1]
        elif score == best_score:
            tied.append(m1)
    return rng.choice(tied) if tied else None


def compact(moves: Sequence[Move]) -> Tuple[List[Move], int]:
    """合并「同一个球连搬两次」：``A→B`` 紧跟 ``B→C`` 等价于 ``A→C``。

    返回 ``(合并后的走法, 合并掉多少步)``。
    """
    out: List[Move] = []
    merged = 0
    for m in moves:
        out.append(m)
        while len(out) >= 2 and out[-1][0] == out[-2][1]:
            a, b = out[-2], out[-1]
            out.pop()
            out.pop()
            out.append((a[0], b[1]))
            merged += 1
    return out, merged


def walk(seed: int, steps: int) -> Tuple[State, List[Move], List[Move]]:
    """从已解局面引导式地走 ``steps`` 步（合并后计数）。

    返回 ``(最终局面, 原始走法, 解法)``；解法就是合并后的走法**反过来**、源和目标对调。
    """
    rng = random.Random(seed)
    state: State = tuple(tuple(t) for t in _solved_state())
    visited = {key(state)}
    raw: List[Move] = []
    moves: List[Move] = []
    prev = None
    guard = 0
    limit = max(1, steps) * 20
    while len(moves) < steps and guard < limit:
        guard += 1
        m = choose(state, prev, rng, visited)
        if m is None:
            break
        state = apply_move(state, m)
        raw.append(m)
        visited.add(key(state))
        moves, _ = compact(raw)
        prev = moves[-1] if moves else None
    solution = [(j, i) for i, j in reversed(moves)]
    return state, raw, solution


def _solved_state():
    """已解局面（延迟 import，避免和 generator 互相引用）。"""
    from generator import solved_state
    return solved_state()
