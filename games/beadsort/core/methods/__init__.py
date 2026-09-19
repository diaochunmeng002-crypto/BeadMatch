"""beadsort 的**出题方法**（method）：一种方法 = 「给我一个候选」。

分工（2026-09-18 定）：

* 公共那半 —— 跑多少次、去重、分档、落盘、报表 —— 在 `tools/make.py`；
* 方法这半 —— 怎么把一个局面造出来 —— 在这个包里，一个方法一个模块。

所以加第三种方法 = **加一个模块 + 注册一行**，公共层和前端一个字都不用动。

两个轴别混（见 `docs/requirement.md`）：

* ``--rule``   玩法规则：现在只有 ``single``（一次一颗，只能放空柱或同色柱顶）；
  以后要加 ``multi``（一次倒一摞）时，规则多一个值，**方法不用动**。
* ``--method`` 出题方法：``walk``（施工式反走）/ ``kociemba``（随机摆 + 求解器筛）。
  写进题目文件的 `generator=`；解是谁给的就写 `solution_by=`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

State = Tuple[Tuple[int, ...], ...]
Move = Tuple[int, int]


@dataclass
class Candidate:
    """一道题：局面 + 一条解 + 出处。落盘交给公共层。"""

    board: State
    solution: List[Move]
    generator: str                                  # 题目文件的 generator=
    solution_by: str                                # 题目文件的 solution_by=
    seed: int = 0                                   # 是哪一次尝试出的（公共层填）
    seconds: float = 0.0                            # 造这一道花了多久
    steps: int = 0                                  # 反走步数（只有 walk 有；0 = 不写进文件）
    rank: float = 0.0                               # 分档截断时谁先留（越大越先留）
    extra: Dict[str, object] = field(default_factory=dict)   # misplaced / segments …


class Method:
    """出题方法。子类要定：``name``、``per_level_default``、``attempt()``。"""

    name = "?"
    per_level_default = 20          # 每档最多留几道（0 = 不限）；kociemba 会覆盖成 0

    def add_args(self, parser) -> None:
        """加方法专属参数（公共参数由 `tools/make.py` 加）。"""

    def setup(self, args) -> None:
        """拿到参数后做一次性准备（改棋盘参数之类）。"""

    def attempt(self, seed: int):
        """跑**一次**尝试：出得来返回 `Candidate`，出不来返回 ``None``。"""
        raise NotImplementedError


REGISTRY: Dict[str, Method] = {}


def register(method: Method) -> Method:
    REGISTRY[method.name] = method
    return method


def get(name: str) -> Method:
    if name not in REGISTRY:
        raise KeyError("没有这个出题方法：%s（有的是 %s）"
                       % (name, " / ".join(names()) or "（一个都没有）"))
    return REGISTRY[name]


def names() -> List[str]:
    return sorted(REGISTRY)


# 导入即注册（放最后：上面那些名字得先定义好）
from . import kociemba as _kociemba      # noqa: E402,F401
from . import layershuffle as _layers    # noqa: E402,F401
from . import walk as _walk              # noqa: E402,F401
