"""竞技串珠：**约束采样器** —— 把「反走」当成抽样器用，而不是出题器。

跟 `walk_gen.py`（现在出题用的那个）的区别：

| | `walk_gen`（出题） | `sampler`（抽样） |
| --- | --- | --- |
| 走法 | 两步前瞻的贪心（专挑最能打散的） | **纯随机** |
| 目标 | 走满指定步数 | **走不动 / 到上限 / 停滞就停** |
| 防打转 | 不走重复局面 | 禁立即反向 + 禁重复局面 + 停滞截断 |
| 产出 | 一条题 | 一大批题 + 乱度统计 |

为什么抽样用纯随机：实验里贪心会把搜索空间越走越窄（平均离位 8 颗，纯随机 12.7 颗）；
而「纯随机 + 防打转」的分布跟纯随机逐项相同、只是快好几倍。

**每一步都是合法的逆操作**（见 `walk_gen.py` 顶部）→ 最终局面**一定有解**：
把走过的路倒过来就是给玩家的解。所以这个采样器**永远不需要求解器**，
也不会采到不可解的题。

产出用来回答一个问题：

> 从完成状态反向随机走，到底能把珠子打散到什么程度？
> 那个「离位上上限」是结构性的，还是采样不够？

用法见 `games/beadsort/tools/sampler.py`（命令行）。
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import generator as g
from . import walk_gen
from .free_solver import apply_move, freeze, homes, key

State = Tuple[Tuple[int, ...], ...]
Move = Tuple[int, int]

# 出题算法版本：写进题目文件的 `generator` 字段（跟 walk_gen 的 `walk_guided@5` 区分开）
GENERATOR = "sampler@1"

# 默认走法（2026-09-17 实验定下来的）：
#   禁任何走过的局面（最快，分布跟纯随机逐项一致）
#   连续 12 步没刷新过「离位最高纪录」就提前收工
#   （允许离位上下波动，只是不许长期原地打转）
#   上限故意设高：走得到就走，走不到不算数
DEFAULT_MAX_STEPS = 500
DEFAULT_STAGNATION = 12
REPEATS = ("none", "recent", "allow")
STRATEGIES = ("random", "greedy")

# --------------------------------------------------------------------------
# 棋盘参数
# --------------------------------------------------------------------------


def configure(tubes: Optional[int] = None, colors: Optional[int] = None,
              per_color: Optional[int] = None,
              capacity: Optional[int] = None) -> Dict[str, object]:
    """临时改棋盘参数（不改就是本游戏默认的 7 柱 / 6 色 / 每色 10 颗 / 柱容量 10）。

    返回改完之后的参数，方便调用方写进题面或报表。
    """
    if tubes is not None:
        g.TUBES = int(tubes)
    if colors is not None:
        g.COLORS = int(colors)
    if per_color is not None:
        g.BALLS_PER_COLOR = int(per_color)
    if capacity is not None:
        g.CAPACITY = int(capacity)
    elif g.CAPACITY < g.BALLS_PER_COLOR:      # 每色珠子得装得下
        g.CAPACITY = g.BALLS_PER_COLOR
    return {
        "tubes": g.TUBES,
        "colors": g.COLORS,
        "balls_per_color": g.BALLS_PER_COLOR,
        "capacity": g.CAPACITY,
        "empty_tubes": g.TUBES - g.COLORS,
    }


def solved() -> State:
    """已解局面：每种颜色占满一根柱子，其余柱子空着。"""
    return freeze(g.solved_state())


# --------------------------------------------------------------------------
# 乱度
# --------------------------------------------------------------------------


def misplaced(state: Sequence[Sequence[int]]) -> int:
    """离位珠数：不在「自己家」（装这种颜色最多的那根柱子）的珠子有几颗。

    这同时是**解的下界**（每颗离位的球至少得搬一次），所以 `moves / misplaced`
    可以看出一条解啰不啰嗦。
    """
    home = homes(state)
    return sum(1 for t, tube in enumerate(state)
               for v in tube if v and home.get(v) != t)


def chaos(state: Sequence[Sequence[int]]) -> Dict[str, int]:
    """一次算齐所有乱度指标（前两个越大越乱，后两个越小越散）。"""
    return {
        "misplaced": misplaced(state),
        "segments": walk_gen.seg_total(state),      # 色段总数
        "max_run": walk_gen.max_run(state),         # 最长同色段
        "bottom_run": walk_gen.bottom_run(state),   # 各柱底部同色段之和
    }


# --------------------------------------------------------------------------
# 走一遍
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Walk:
    """一次反向走的结果（局面 + 走过的路 + 乱度）。"""

    seed: int
    board: State
    path: Tuple[Move, ...]           # 施工式反走的原始步子
    stop: str                        # cap / dead-end / stagnation
    misplaced: int
    segments: int
    max_run: int
    bottom_run: int

    @property
    def steps(self) -> int:
        """反走走出来的原始步数。"""
        return len(self.path)

    @property
    def solution(self) -> List[Move]:
        """给玩家的解 = 把「同一颗球连搬两次」合并掉、再倒过来。"""
        merged, _n = walk_gen.compact(self.path)
        return [(j, i) for i, j in reversed(merged)]

    @property
    def moves(self) -> int:
        """解的步数（合并过，就是题目里的 `moves`）。"""
        return len(self.solution)

    @property
    def level(self) -> int:
        """按现有口径算的等级 = 解的长度 ÷ 10 向上取整。"""
        return g.level_of(self.moves)

    @property
    def ratio(self) -> float:
        """解步数 ÷ 下界（离位数）。1 附近 = 好题，十几 = 啰嗦题。"""
        return (self.moves / self.misplaced) if self.misplaced else 0.0


def _pick(state: State, cands: Sequence[Move], rng: random.Random,
          strategy: str) -> Move:
    """从候选里挑一步。"""
    if strategy == "random":
        return rng.choice(list(cands))
    if strategy == "greedy":
        best, tied = None, []
        for m in cands:
            s = walk_gen.scatter(apply_move(state, m))
            if best is None or s > best:
                best, tied = s, [m]
            elif s == best:
                tied.append(m)
        return rng.choice(tied)
    raise ValueError("不认识的走法策略：%r（只能是 %s）"
                     % (strategy, " / ".join(STRATEGIES)))


def sample(seed: int, *, max_steps: int = DEFAULT_MAX_STEPS,
           repeat: str = "none", recent: int = 20,
           stagnation: Optional[int] = DEFAULT_STAGNATION,
           strategy: str = "random") -> Walk:
    """从完成状态反走一次，返回最终局面。

    * ``repeat="none"``   —— 走过的局面不再进（默认，最快）
    * ``repeat="recent"`` —— 只禁最近 ``recent`` 步里的局面（允许长周期绕回来）
    * ``repeat="allow"``  —— 只禁立即反向（= 老做法：纯随机硬走）

    ``stagnation`` = 连续多少步没刷新「离位最高纪录」就提前收工（``None`` = 不截断）。
    上限 ``max_steps`` 是刹车、不是目标：走到那儿就停，走不到就记走不到。
    """
    if repeat not in REPEATS:
        raise ValueError("repeat 只能是 %s" % " / ".join(REPEATS))
    if strategy not in STRATEGIES:
        raise ValueError("strategy 只能是 %s" % " / ".join(STRATEGIES))

    rng = random.Random(int(seed))
    state = solved()
    start = key(state)
    visited = {start}
    recent_keys = deque([start], maxlen=max(1, int(recent)))

    path: List[Move] = []
    best = misplaced(state)
    since = 0
    stop = "cap"

    for _ in range(max(0, int(max_steps))):
        cands = walk_gen.construction_moves(state)
        if path:                                      # 别立刻把刚搬的那颗搬回去
            undo = (path[-1][1], path[-1][0])
            cands = [m for m in cands if m != undo]
        if repeat == "none":
            cands = [m for m in cands if key(apply_move(state, m)) not in visited]
        elif repeat == "recent":
            seen = set(recent_keys)
            cands = [m for m in cands if key(apply_move(state, m)) not in seen]
        if not cands:
            stop = "dead-end"
            break

        pick = _pick(state, cands, rng, strategy)
        state = apply_move(state, pick)
        path.append(pick)
        k = key(state)
        visited.add(k)
        recent_keys.append(k)

        m = misplaced(state)
        if m > best:                                  # 刷新纪录 → 时钟归零
            best, since = m, 0
        else:
            since += 1
        if stagnation is not None and since >= int(stagnation):
            stop = "stagnation"
            break
    else:
        stop = "cap"

    c = chaos(state)
    return Walk(seed=int(seed), board=state, path=tuple(path), stop=stop, **c)


def verify(walk: Walk) -> bool:
    """把 `Walk.solution` 套回局面，确认真的解开了（自检用）。"""
    cur = walk.board
    for move in walk.solution:
        cur = apply_move(cur, move)
    return bool(g.is_finished(cur))
