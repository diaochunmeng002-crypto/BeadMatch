"""方法一：**施工式反走**（就是现在题库用的那套）。

从已解局面出发、纯随机反走（`core/sampler.py`），走不动 / 到上限 / 停滞就停，
把最终局面当题。每一步都是合法的逆操作 → **起点一定有解**，不需要求解器。

* 一次尝试 = 反走一遍 ≈ 一道题（所以 10 万次尝试 ≈ 10 万道候选）
* 所以这个方法**必须**有每档上限（默认 20），不然一次就灌进去几万道
"""

from __future__ import annotations

import time
from typing import Optional

from .. import sampler as sp
from . import Candidate, Method, register


class WalkMethod(Method):
    name = "walk"
    generator = sp.GENERATOR            # sampler@1
    solution_by = "walk"
    per_level_default = 20

    def add_args(self, parser) -> None:
        parser.add_argument("--pick", default="first", choices=("first", "chaos"),
                            help="同一档留哪几道：first = 先到先得（默认）；"
                                 "chaos = 这一档里最乱的那些先留")
        parser.add_argument("--repeat", default="none", choices=sp.REPEATS,
                            help="防重复：none = 走过的局面不再进（默认）；"
                                 "recent = 只禁最近 --recent 步；allow = 只禁立即反向")
        parser.add_argument("--recent", type=int, default=20, help="--repeat recent 时回看多少步")
        parser.add_argument("--stagnation", type=int, default=sp.DEFAULT_STAGNATION,
                            help="连续多少步没刷新离位纪录就收工（0 = 不截断）")
        parser.add_argument("--max-steps", type=int, default=sp.DEFAULT_MAX_STEPS,
                            help="反走步数上限（刹车，不是目标）")

    def setup(self, args) -> None:
        sp.configure(args.tubes, args.colors, args.per, args.capacity)
        self.max_steps = args.max_steps
        self.repeat = args.repeat
        self.recent = args.recent
        self.stagnation = args.stagnation
        self.ranked = (args.pick == "chaos")     # 只有 chaos 才给候选打分

    def attempt(self, seed: int) -> Optional[Candidate]:
        t0 = time.time()
        w = sp.sample(seed, max_steps=self.max_steps, repeat=self.repeat,
                      recent=self.recent, stagnation=(self.stagnation or None),
                      strategy="random")
        # chaos 模式才需要打分（分档满了时按它换人）；first 模式全是 0 = 先到先得
        rank = float(w.misplaced * 1000 + w.segments) if self.ranked else 0.0
        return Candidate(
            board=w.board, solution=w.solution, generator=self.generator,
            solution_by=self.solution_by, seconds=time.time() - t0, steps=w.steps,
            rank=rank,
            extra={"misplaced": w.misplaced, "segments": w.segments},
        )


METHOD = register(WalkMethod())
