"""竞技串珠的出题算法：**施工式反走** —— 把一条合法解"倒着演一遍"，出来的就是题。

跟宝宝串珠那套的关键差别（那边是"合法乱走 + 反走即解"）：竞技规则下
**"合法走法"根本打不乱局面** —— "只能摞同色"意味着你永远没法把两种颜色混进一根柱子，
所以从已解局面合法乱走，出来的题每根柱子还是单色（只是柱子换了个位置）。

所以施工时**不要求这一步是"合法走法"**，只要求「**将来倒回来那一步合法**」：

1. 挑一根**拎起来还露着同色**的柱子（顶上那颗拿走后露出的还是同色；或者它就拿空了）
   —— 见 `free_solver.reversible()`；
2. 把它顶上那颗放到**任意还有空位**的柱子上 —— 放哪儿不限颜色，**混色就是这么来的**；
3. 重复若干步 → 得到题面；**把施工步骤倒过来**就是给玩家的解
   （第 1 条正好保证解里每一步都合法）。

好处：不依赖求解器、秒级、**起点一定有解**。坏处：解不一定最短（施工里有"来回蹭"，
`compact()` 会先合并掉一部分）。

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

from .free_solver import EMPTY, apply_move, has_room, key, reversible

State = Tuple[Tuple[int, ...], ...]
Move = Tuple[int, int]

# 算法版本：换算法/改规则时递增，写进题目文件的 `generator` 字段
GENERATOR = "walk_guided@5"      # @5 = 施工式反走（竞技规则）


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


def construction_moves(state: State) -> List[Move]:
    """施工式反走这一步能怎么走：拎得起（露同色或拿空）+ 放得下（有空位），**不限颜色**。

    反过来读就是给玩家的解：把一颗珠子搬到「同色柱顶或空柱」上 —— 正好是竞技规则。
    """
    return [(i, j) for i in range(len(state)) for j in range(len(state))
            if i != j and has_room(state[j]) and reversible(state, (i, j))]


def choose(state: State, prev, rng: random.Random,
           visited: set) -> Move | None:
    """两步前瞻：挑一步，使「它 + 之后最优的一步」的打散度合计最高。

    并列最优里随机挑一个（否则每个种子会走出同一条路）。
    """
    cur = scatter(state)
    undo = (prev[1], prev[0]) if prev else None
    # 施工式反走的可选走法（放哪儿不限颜色，见模块开头）
    cands = [m for m in construction_moves(state) if m != undo]
    fresh = [m for m in cands if key(apply_move(state, m)) not in visited]
    # 只走没到过的局面：退回走过的局面 = 原地打转（原始步数一直涨、合并后的步数不涨，
    # 最后白白耗光预算）。走不下去就让 `walk()` 换种子重来。
    cands = fresh
    if not cands:
        return None

    # 留退路：每走一步都会"用掉"一个能拿的球（球被压到别的颜色上就再也拎不起来了），
    # 所以优先选"走完之后**还有两个以上**球可拿"的走法；退而求其次"还有球可拿"；
    # 都不行就只能随便走（题仍然合法，只是很快走到头）。
    after = [(m, apply_move(state, m)) for m in cands]
    after = [(m, s1, construction_moves(s1)) for m, s1 in after]
    two = [x for x in after if len(x[2]) >= 2]
    one = [x for x in after if x[2]]
    pool = two or one or after

    best_score = None
    tied: List[Move] = []
    for m1, s1, nxt in pool:
        gain1 = scatter(s1) - cur
        undo2 = (m1[1], m1[0])
        gain2 = 0
        for m2 in nxt:
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


def _walk_once(seed: int, steps: int) -> Tuple[State, List[Move], List[Move]]:
    """走一次（不重试）。返回 ``(局面, 原始走法, 解法)``。"""
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


def walk(seed: int, steps: int, tries: int = 8) -> Tuple[State, List[Move], List[Move]]:
    """从已解局面引导式地走 ``steps`` 步（合并后计数），**要的是真的走满**。

    返回 ``(最终局面, 原始走法, 解法)``；解法就是合并后的走法**反过来**、源和目标对调。

    施工偶尔会走不下去（每个走法要么重复局面、要么把路走死）—— 那时题仍然合法、
    只是比目标短。所以换下一种子重来，最多试 ``tries`` 次；都不行就用手上最长的那次
    （``len(解法)`` 会照实小于 ``steps``，调用方照实写进 ``moves``）。
    """
    best = None
    for attempt in range(max(1, tries)):
        state, raw, solution = _walk_once(seed + attempt, steps)
        if best is None or len(solution) > len(best[2]):
            best = (state, raw, solution)
        if len(solution) >= steps:
            break
    return best                                  # type: ignore[return-value]


def _solved_state():
    """已解局面（延迟 import，避免和 generator 互相引用）。"""
    from .generator import solved_state
    return solved_state()
