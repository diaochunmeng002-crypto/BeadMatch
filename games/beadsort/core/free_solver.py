"""竞技串珠的求解器 —— 按**竞技规则**求解。

规则（商业球排序 / 水排序那套）：

* 一次只拿某根柱子**最顶上的一颗**珠子；
* 目标柱子**要么空着、要么顶色跟这颗一样** —— 也就是「只能摞在同色上面」；
* 结束：**每种颜色全部集中在同一根柱子**上，其余柱子空着。

⚠️ 这跟 `games/beadmatch/`（宝宝串珠，"落点只要有空位就能放"）是**两套规则**
—— 那套的题解在这套规则下多半不合法，两边的题库不能混用。

局面格式（与 generator.py、题库文件完全一致）：

    state = [tube, ...]
    tube  = 长度 CAPACITY 的序列，下标 0 = **最顶端那一格**，
            最底下那颗在下标 CAPACITY - 1；0 表示空位。

柱子没满时，空位都在前面（前缀），珠子堆在后面 —— 这个不变量由
``apply_move`` 和出题时的随机走法共同维持。

求解用的是 **DFS + 启发式排序**（不是 BFS）：BFS 才是"最少步数"，
但这个规则下状态空间大到算不动（实测 6 色 7 柱的题，60 秒只搜到第 6~7 层），
所以这里求的是**可行解**，只保证能解开，不保证步数最少。
"""

from __future__ import annotations

import random
import time
from typing import Dict, List, Optional, Sequence, Tuple

EMPTY = 0

# 默认参数：7 柱 / 6 色 / 每色 10 颗 / 柱容量 10
TUBES = 7
COLORS = 6
CAPACITY = 10
BALLS_PER_COLOR = 10

Move = Tuple[int, int]
State = Tuple[Tuple[int, ...], ...]


class BudgetExceeded(Exception):
    """搜索超过节点/时间上限。"""


# --------------------------------------------------------------------------
# 基本查询
# --------------------------------------------------------------------------


def freeze(state: Sequence[Sequence[int]]) -> State:
    """把可变局面转成可哈希的元组。"""
    return tuple(tuple(t) for t in state)


def top_index(tube: Sequence[int]) -> Optional[int]:
    """顶珠的下标；空柱返回 ``None``（空位是前缀）。"""
    for k, v in enumerate(tube):
        if v != EMPTY:
            return k
    return None


def top_color(tube: Sequence[int]) -> int:
    k = top_index(tube)
    return EMPTY if k is None else tube[k]


def is_empty(tube: Sequence[int]) -> bool:
    return tube[-1] == EMPTY


def has_room(tube: Sequence[int]) -> bool:
    return tube[0] == EMPTY


def color_count(tube: Sequence[int], color: int) -> int:
    return sum(1 for v in tube if v == color)


def is_monochrome(tube: Sequence[int]) -> bool:
    """柱子要么空着，要么整根同色。"""
    c = EMPTY
    for v in tube:
        if v == EMPTY:
            continue
        if c == EMPTY:
            c = v
        elif v != c:
            return False
    return True


def is_complete(tube: Sequence[int], balls_per_color: int = BALLS_PER_COLOR) -> bool:
    """这根柱子已经"完成"：整根同色，且该颜色的珠子一颗不少。"""
    c = top_color(tube)
    return c != EMPTY and is_monochrome(tube) and color_count(tube, c) == balls_per_color


def blocks(tube: Sequence[int]) -> int:
    """柱子里同色连续段的数量（忽略空位）。"""
    n = 0
    prev = EMPTY
    for v in tube:
        if v == EMPTY:
            continue
        if v != prev:
            n += 1
        prev = v
    return n


def total_blocks(state: Sequence[Sequence[int]]) -> int:
    return sum(blocks(t) for t in state)


def is_finished(state: Sequence[Sequence[int]]) -> bool:
    """按 docs/requirement.md §2.3 判定胜利。

    每根柱子要么空着，要么整根同色，**且每种颜色只出现在一根柱子上**
    （一种颜色被拆成两根单色柱不算赢）。
    """
    used = set()
    for tube in state:
        balls = [v for v in tube if v != EMPTY]
        if not balls:
            continue
        c = balls[0]
        if any(v != c for v in balls):
            return False
        if c in used:
            return False
        used.add(c)
    return True


# --------------------------------------------------------------------------
# 走一步
# --------------------------------------------------------------------------


def legal_moves(state: Sequence[Sequence[int]]) -> List[Move]:
    """所有合法走法：目标柱**空着**，或者**顶色跟要搬的那颗一样**。

    这是竞技串珠唯一的那条规则 —— 全项目只有这里定义它（反走、求解、校验都走这儿）。
    """
    out: List[Move] = []
    for i, src in enumerate(state):
        color = top_color(src)
        if color == EMPTY:
            continue
        for j, dst in enumerate(state):
            if i == j or not has_room(dst):
                continue
            below = top_color(dst)
            if below == EMPTY or below == color:      # 空柱，或同色柱顶
                out.append((i, j))
    return out


def reversible(state: Sequence[Sequence[int]], move: Move) -> bool:
    """从这根柱子顶上拿一颗下来，**将来还能原样倒回来**吗（竞技规则专用）。

    倒回来的那个动作是"把这颗放到它的原位" —— 按竞技规则，得**原位露出来的那颗同色**
    （或者原位空了）才行。所以出题（施工式反走）时只能拿：
    **顶上两颗同色**的，或者**这颗就是柱底那颗**（拿完柱子就空了）。

    拿得动 + 放得下（随便放哪根有空位的柱子，颜色不限），就是 `walk_gen.construction_moves()`。
    """
    i, _j = move
    tube = state[i]
    k = top_index(tube)
    if k is None:
        return False
    if k == len(tube) - 1:          # 这颗就是最底下那颗 → 搬完源柱就空了
        return True
    return tube[k + 1] == tube[k]   # 下面那颗同色 → 搬完露出同色，倒得回去


def apply_move(state: Sequence[Sequence[int]], move: Move) -> State:
    """返回走完这一步的新局面（原局面不动）。"""
    i, j = move
    new = [list(t) for t in state]
    k = top_index(new[i])
    if k is None:
        raise ValueError("源柱是空的：%r" % (move,))
    if not has_room(new[j]):
        raise ValueError("目标柱已经满了：%r" % (move,))
    ball = new[i][k]
    new[i][k] = EMPTY
    e = 0
    while e < len(new[j]) and new[j][e] == EMPTY:
        e += 1
    new[j][e - 1] = ball
    return freeze(new)


def key(state: Sequence[Sequence[int]]) -> State:
    """归一化：柱子排序后去重（空柱位置不同、柱子顺序不同都算同一个局面）。"""
    return tuple(sorted(freeze(state)))


# --------------------------------------------------------------------------
# 启发式
# --------------------------------------------------------------------------


def move_score(
    state: Sequence[Sequence[int]],
    move: Move,
    balls_per_color: int = BALLS_PER_COLOR,
) -> int:
    """给一步打分，越大越优先。只做局部计算，不复制整个局面。"""
    i, j = move
    src, dst = state[i], state[j]
    c = top_color(src)

    # 源柱搬走顶珠后露出来的那个颜色
    under = EMPTY
    k = top_index(src)
    for v in src[k + 1:]:
        if v != EMPTY:
            under = v
            break
    src_delta = -1 if under != c else 0
    dst_top = top_color(dst)
    dst_delta = 0 if (dst_top == c and not is_empty(dst)) else 1
    score = -(src_delta + dst_delta) * 10

    # 目标柱搬完之后的颜色（dst 现在的全部珠子 + 这颗）
    dst_balls = [v for v in dst if v != EMPTY]
    dst_after = dst_balls + [c]
    if len(dst_after) == balls_per_color and all(v == c for v in dst_after):
        score += 100  # 正好凑满一根同色柱：完成
    elif all(v == c for v in dst_after):
        score += 25  # 目标柱变纯色

    if is_complete(src, balls_per_color) or is_complete(dst, balls_per_color):
        score -= 1000  # 已经完成的柱子不该动
    if is_empty(dst):
        score -= 5  # 往空柱上放通常只是"停车场"
    return score


def homes(state: Sequence[Sequence[int]],
          balls_per_color: int = BALLS_PER_COLOR) -> Dict[int, int]:
    """给每种颜色挑一根柱子"当家"：按「这根柱子里该色最多」贪心配对。

    柱子数 > 颜色数，所以一定能配上（剩下的柱子空着）。
    """
    colors = set()
    pairs = []
    for t, tube in enumerate(state):
        for v in tube:
            if v == EMPTY:
                continue
            colors.add(v)
        for c in set(v for v in tube if v != EMPTY):
            pairs.append((color_count(tube, c), c, t))
    pairs.sort(key=lambda x: (-x[0], x[1], x[2]))

    home: Dict[int, int] = {}
    taken = set()
    for _n, c, t in pairs:
        if c in home or t in taken:
            continue
        home[c] = t
        taken.add(t)
    for c in sorted(colors):
        if c in home:
            continue
        for t in range(len(state)):
            if t not in taken:
                home[c] = t
                taken.add(t)
                break
    return home


def state_score(
    state: Sequence[Sequence[int]],
    home: Optional[Dict[int, int]] = None,
    balls_per_color: int = BALLS_PER_COLOR,
) -> int:
    """给整个局面打分，越大越接近解。

    * ``misplaced``：不在自己家里的球数（这是**下界**，最短步数不会比它少）
    * ``blocks``：交错程度
    * ``done``：已经完成的柱子数
    """
    home = homes(state, balls_per_color) if home is None else home
    misplaced = 0
    for t, tube in enumerate(state):
        for v in tube:
            if v != EMPTY and home.get(v) != t:
                misplaced += 1
    done = sum(1 for tube in state if is_complete(tube, balls_per_color))
    return -misplaced * 10 - total_blocks(state) + done * 30


def ordered_moves(
    state: Sequence[Sequence[int]],
    balls_per_color: int = BALLS_PER_COLOR,
    home: Optional[Dict[int, int]] = None,
) -> List[Move]:
    """合法走法，按启发式分数从高到低排。"""
    home = homes(state, balls_per_color) if home is None else home
    scored = []
    for m in legal_moves(state):
        # 主排序：走完之后整个局面离目标有多近；次排序：这一步自身的局部好坏
        total = state_score(apply_move(state, m), home, balls_per_color) * 100
        total += move_score(state, m, balls_per_color)
        scored.append((-total, m))
    scored.sort()
    return [m for _s, m in scored]


# --------------------------------------------------------------------------
# 求解
# --------------------------------------------------------------------------


def solve(
    state: Sequence[Sequence[int]],
    max_depth: int = 200,
    node_limit: int = 200_000,
    time_limit: float = 5.0,
    trials: int = 200,
    trial_nodes: int = 3_000,
    seed: int = 12345,
    balls_per_color: int = BALLS_PER_COLOR,
) -> Optional[List[Move]]:
    """求一条可行解；找不到（或超预算）返回 ``None``。

    返回的是走法列表 ``[(源柱, 目标柱), ...]``，柱子编号 0 起，
    对应传进来的这个局面。已经解开时返回空列表。

    做法是**随机化的贪心 DFS + 重开**：每次按启发式排序走，但把最靠前的几步
    打乱重试；一条路走不通就换个顺序重开，比死磕一条路稳得多。

    **不保证步数最少**（见模块说明）。
    """
    start = freeze(state)
    if is_finished(start):
        return []

    deadline = time.monotonic() + time_limit
    rng = random.Random(seed)
    used_nodes = 0

    for _trial in range(trials):
        if time.monotonic() > deadline or used_nodes >= node_limit:
            return None
        result, nodes = _greedy_dfs(
            start, max_depth, trial_nodes, rng, balls_per_color,
            home=homes(start, balls_per_color),
        )
        used_nodes += nodes
        if result is not None:
            return result
    return None


def _shuffle_head(moves: List[Move], rng: random.Random, k: int = 3) -> List[Move]:
    """把排在最前面的几步打乱（并列最优里随机挑一个先试）。"""
    if len(moves) <= 1:
        return moves
    head = moves[:k]
    rng.shuffle(head)
    return head + moves[k:]


def _greedy_dfs(
    start: State,
    depth_limit: int,
    node_budget: int,
    rng: random.Random,
    balls_per_color: int,
    home: Optional[Dict[int, int]] = None,
) -> Tuple[Optional[List[Move]], int]:
    """一次随机化的贪心 DFS。返回 ``(走法 或 None, 展开的节点数)``。"""
    seen: Dict[State, int] = {}
    path: List[Move] = []
    counter = [0]

    def dfs(cur: State, remaining: int) -> bool:
        if is_finished(cur):
            return True
        if remaining <= 0:
            return False
        counter[0] += 1
        if counter[0] > node_budget:
            raise BudgetExceeded("节点数超过 %d" % node_budget)
        k = key(cur)
        prev = seen.get(k)
        # 同一个局面，之前用「不少于现在的剩余深度」搜过并且失败了，才敢跳过
        if prev is not None and prev >= remaining:
            return False
        seen[k] = remaining

        for move in _shuffle_head(ordered_moves(cur, balls_per_color, home), rng):
            path.append(move)
            if dfs(apply_move(cur, move), remaining - 1):
                return True
            path.pop()
        return False

    try:
        if dfs(start, depth_limit):
            return list(path), counter[0]
    except (BudgetExceeded, RecursionError):
        pass
    return None, counter[0]


def verify(state: Sequence[Sequence[int]], moves: Sequence[Move]) -> bool:
    """把走法套到局面上，检查是不是真的解开了。"""
    cur = freeze(state)
    try:
        for move in moves:
            cur = apply_move(cur, move)
    except ValueError:
        return False
    return is_finished(cur)


def solve_any_with_source(
    state: Sequence[Sequence[int]],
    **kwargs,
) -> Tuple[Optional[List[Move]], str]:
    """求一条解，并把「这条解是谁给的」一起返回：``dfs`` / ``-``。

    2026-09-14：原来会先借 Kociemba（旧规则）求短解，现已删除（见 docs/solver_research.md）。
    现在只剩我们自己的 DFS —— 它**只保证能解开、不保证步数最少**，而且能力有限；
    不过出题已经不依赖它了（`walk_gen` 的反走就是解）。
    """
    moves = solve(state, **kwargs)
    if moves is not None:
        return moves, "dfs"
    return None, "-"


def solve_any(
    state: Sequence[Sequence[int]],
    **kwargs,
) -> Optional[List[Move]]:
    """求一条解，失败返回 ``None``（``solve_any_with_source`` 的薄包装）。"""
    return solve_any_with_source(state, **kwargs)[0]


def format_moves(moves: Sequence[Move]) -> str:
    """走法文本（给人看，也写进题目文件）：柱子编号从 **1** 起，空格分隔。

    例：``"3-7 1-2 5-3"`` 表示「柱子 3 顶上那颗搬到柱子 7，然后 1 → 2……」
    """
    return " ".join("%d-%d" % (i + 1, j + 1) for i, j in moves)


def parse_moves(text: str) -> List[Move]:
    """``format_moves`` 的逆向：把 ``"3-7 1-2"`` 解析成 0 起的 ``[(2, 6), (0, 1)]``。"""
    out: List[Move] = []
    for token in text.split():
        if "-" not in token:
            raise ValueError("走法片段看不懂：%r" % token)
        a, b = token.split("-", 1)
        try:
            i, j = int(a), int(b)
        except ValueError:
            raise ValueError("走法片段不是数字：%r" % token)
        if i < 1 or j < 1:
            raise ValueError("走法里的柱子编号从 1 起：%r" % token)
        out.append((i - 1, j - 1))
    return out
