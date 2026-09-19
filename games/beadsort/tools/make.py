"""beadsort 的**唯一出题入口**（2026-09-18 起）：挑方法 + 跑 N 次 + 落盘。

```bash
# 默认写进 games/beadsort/puzzles
python -m games.beadsort.tools.make --method walk --n 100000

# 自定义目录（随机摆 + Kociemba 这类稀有产物建议单独放）
python -m games.beadsort.tools.make --method kociemba --n 100000 --out games/beadsort/puzzles_kociemba
```

公共层只管三件事 —— **跑 `--n` 次尝试 / 去重分档 / 落盘报表**；
"题是怎么造出来的"在 `core/methods/` 里，一个方法一个模块。

规则（2026-09-18 跟需求方对齐的）：

* ``--n`` **永远是"尝试多少次"**，不是"要出多少道"（两边产出率差 2000 倍：
  walk ≈ 每次必出，kociemba ≈ 0.05%）；
* 成功的按**解的长度**分档（level = 解长 ÷ 10 向上取整），每档最多留
  ``--per-level`` 道；**默认值按方法定**：walk 20、kociemba 0（不限）——
  后者产出太稀，截断就是白扔；
* 真的发生截断时，报表里必须写出来（不许偷偷丢）；
* 结果完全由 ``--n`` + ``--seed0`` 决定，可以复现。
"""

from __future__ import annotations

import argparse
import random
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..core import generator as g
from ..core import methods
from ..core.free_solver import format_moves, key

GAME_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = GAME_DIR / "puzzles"

# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------


def clear_library(root: Path) -> int:
    """把题库目录里的旧题目删掉（只删 <root>/<数字>/ 下的 *.txt）。"""
    removed = 0
    if not root.is_dir():
        return 0
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not d.name.isdigit():
            continue
        for f in sorted(d.glob("*.txt")):
            f.unlink()
            removed += 1
        if not any(d.iterdir()):
            d.rmdir()
    return removed


def resolve_seed0(raw) -> int:
    """把 `--seed0` 解析成整数。

    * 整数（默认 ``1``）—— 起点固定，**结果可复现**
    * ``random`` —— 用系统随机数取一个起点（**每次跑都不一样**；
      但每道题文件里都写着它自己那次尝试的 ``seed=``，所以单道仍然能精确重现）
    * ``time``   —— 用当前时间戳当起点（比 random 好记：看日志就知道是哪一批）
    """
    s = str(raw).strip().lower()
    if s in ("random", "rand", "r"):
        return random.SystemRandom().randrange(1, 2 ** 31)
    if s in ("time", "now", "t"):
        return int(time.time())
    return int(s)


def fmt_secs(sec: float) -> str:
    """把秒数写成人话：45s / 3m20s / 1h05m。"""
    sec = int(max(0, sec))
    if sec < 60:
        return "%ds" % sec
    m, s = divmod(sec, 60)
    if m < 60:
        return "%dm%02ds" % (m, s)
    h, m = divmod(m, 60)
    return "%dh%02dm" % (h, m)


def keep(bucket: List[methods.Candidate], cand: methods.Candidate, cap: int) -> None:
    """往这一档里塞一道题。``cap <= 0`` = 不限；满了就换掉分最低的那个
    （同分不换 = 先到先得；方法给了 rank 就是"最乱的先留"）。"""
    if cap <= 0 or len(bucket) < cap:
        bucket.append(cand)
        return
    worst = min(range(len(bucket)), key=lambda i: bucket[i].rank)
    if cand.rank > bucket[worst].rank:
        bucket[worst] = cand


def build_meta(cand: methods.Candidate, args, level: int, seed: int) -> Dict[str, object]:
    # id = 写盘的时刻 + 这道题自己的 seed。别再用随机后缀：一次写几千道时时间戳
    # 全都一样，随机后缀只有 4 位，几千个抢 65536 个桶，撞车是常态（而且撞在不同
    # 等级的目录里也照样算重名，`/puzzles/{id}` 会取错题）。seed 在一批里唯一。
    stamp = time.strftime("%Y%m%d-%H%M%S")
    meta: Dict[str, object] = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "created_by": g.CREATED_BY,
        "solution_by": cand.solution_by,
        "id": "%s-%04x" % (stamp, seed % 0x10000),
        "tubes": args.tubes,
        "colors": g.COLOR_LETTERS[: args.colors],
        "capacity": args.capacity or args.per,
        "balls_per_color": args.per,
        "level": level,
        "moves": len(cand.solution),
        "seed": seed,
        "generator": cand.generator,
        "seconds": round(cand.seconds, 3),
        "solution": format_moves(cand.solution),
    }
    if cand.steps:
        meta["steps"] = cand.steps              # 反走步数（只有 walk 有）
    for k in ("misplaced", "segments"):         # 乱度指标（方法给了就写）
        if k in cand.extra:
            meta[k] = cand.extra[k]
    return meta


def save_unique(root: Path, board, meta: Dict[str, object], tries: int = 50) -> Path:
    """写一道题；id 撞车就**换一个 id 再写**。

    为什么必须防：题目 id 是「秒级时间戳 + 4 位十六进制随机」，而落盘集中在最后
    几秒里 —— 一次写几千道，同一秒内几千个 id 抢 65536 个桶，生日问题下几乎必撞。
    老实现于是"题全出完了，最后一步 FileExistsError"，整批白跑。
    `save_board` 自己「不覆盖」是对的，撞了该换 id，而不是覆盖别人的题。
    """
    for _ in range(tries):
        try:
            return g.save_board(root, board, meta)
        except FileExistsError:
            meta = dict(meta)
            meta["id"] = g.make_id()
    raise RuntimeError("连着 %d 次都撞 id，这一道放弃：%s" % (tries, meta.get("id")))


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--method", required=True, choices=methods.names(),
                   help="出题方法（%s）" % " / ".join(methods.names()))
    p.add_argument("--rule", default="single", choices=("single",),
                   help="玩法规则：现在只有 single（一次一颗，只能放空柱或同色柱顶）")
    p.add_argument("--n", type=int, default=10000, help="尝试多少次（默认 10000）")
    p.add_argument("--puzzles", "--out", dest="out", default=str(DEFAULT_OUT),
                   metavar="目录",
                   help="题库目录（默认 %s；给相对路径就是相对仓库根）" % DEFAULT_OUT)
    p.add_argument("--per-level", type=int, default=None,
                   help="每档最多留几道（不给就按方法定：walk=20、kociemba=0 不限）")
    p.add_argument("--clear", action="store_true", help="先把题库里的旧题清掉")
    p.add_argument("--seed0", default="random",
                   help="起始种子：random = 每次真随机起点（默认，跑两次两批题）；"
                        "整数 = 固定起点、这一批可复现；time = 用当前时间戳当起点")
    p.add_argument("--progress", default="auto",
                   help="auto = 每 1000 次尝试打一行战绩（默认；总次数小就自动加密）；"
                        "every = 每次尝试打一行；写数字 = 每 N 次打一行；off = 不打")
    p.add_argument("--quiet", action="store_true", help="不打印任何中途进度（同 --progress off）")
    p.add_argument("--tubes", type=int, default=g.TUBES, help="柱子数（默认 %d）" % g.TUBES)
    p.add_argument("--colors", type=int, default=g.COLORS, help="颜色数（默认 %d）" % g.COLORS)
    p.add_argument("--per", type=int, default=g.BALLS_PER_COLOR,
                   help="每种颜色几颗（默认 %d）" % g.BALLS_PER_COLOR)
    p.add_argument("--capacity", type=int, default=None,
                   help="柱容量（不给就跟 --per 一样，也就是彩柱正好装满）")


def build_parser(method: Optional[methods.Method] = None) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="beadsort 出题：挑方法 + 跑 N 次 + 落盘")
    _add_common(p)
    if method is not None:
        method.add_args(p)                       # 方法专属参数由方法自己注册
    return p


def run(args) -> int:
    if args.capacity is None:
        args.capacity = args.per                 # 彩柱正好装满（本游戏的标准配置）
    args.seed0 = resolve_seed0(args.seed0)
    try:
        method = methods.get(args.method)
    except KeyError as exc:
        print(exc.args[0])
        return 2
    per_level = method.per_level_default if args.per_level is None else args.per_level
    root = Path(args.out)
    method.setup(args)

    print("出题：method=%s（generator=%s / solution_by=%s）"
          % (method.name, getattr(method, "generator", "?"), getattr(method, "solution_by", "?")))
    if hasattr(method, "describe"):
        print("     %s" % method.describe())
    print("棋盘：%d 柱 / %d 色 / 每色 %d 颗 / 柱容量 %d（空 %d 柱）"
          % (args.tubes, args.colors, args.per, args.capacity or args.per,
             args.tubes - args.colors))
    print("跑 %d 次尝试 → %s（每档最多 %s 道）"
          % (args.n, root, "不限" if per_level <= 0 else per_level))
    print("本批种子起点：seed0=%d（第 %d 次尝试用的种子是 %d；每道题文件里也各自写着它那次的 seed=）"
          % (args.seed0, args.n, args.seed0 + args.n - 1))
    print("想一字不差重跑这一批：加 --seed0 %d" % args.seed0)
    if args.clear:
        print("先把旧题清掉：删了 %d 个题目文件" % clear_library(root))
    print(flush=True)

    buckets: Dict[int, List[methods.Candidate]] = {}
    counts: Counter = Counter()
    seen = set()
    dup = 0
    kept = 0
    found = 0                                    # 方法成功产出的候选数（还没去重/分档）
    t0 = time.time()
    mode = str(args.progress).strip().lower()
    if args.quiet or mode in ("off", "none", "no"):
        verbose, period = False, 0                # 完全闭嘴
    elif mode in ("every", "all"):
        verbose, period = True, 1                 # 每次尝试一行
    elif mode in ("auto", ""):
        verbose = False
        period = min(1000, max(1, args.n // 10))  # 默认：每 1000 次一行，小批量自动加密
    else:
        verbose, period = False, max(1, int(mode))   # 每 N 次一行
    # 先报个平安：头一行早打一次（约 0.2~1 秒内），免得盯着空屏幕等一整个周期
    next_at = max(1, min(50, period // 10)) if period > 1 else 0

    for i in range(args.n):
        seed = args.seed0 + i
        t1 = time.time()
        cand = method.attempt(seed)
        dt = time.time() - t1
        if cand is None:
            if verbose:
                print("  %6d/%d  ✗ 没出   已出 %d 道  %6.2fs"
                      % (i + 1, args.n, kept, dt), flush=True)
        else:
            found += 1
            cand.seed = seed
            k = key(cand.board)
            if k in seen:                        # 同一个局面（柱子顺序不算）只留一份
                dup += 1
                if verbose:
                    print("  %6d/%d  ✗ 重复   已出 %d 道  %6.2fs"
                          % (i + 1, args.n, kept, dt), flush=True)
            else:
                seen.add(k)
                level = g.level_of(len(cand.solution))
                counts[level] += 1
                bucket = buckets.setdefault(level, [])
                before = len(bucket)
                keep(bucket, cand, per_level)
                if len(bucket) > before:
                    kept += 1
                if verbose:
                    print("  %6d/%d  ✓ 成功   已出 %d 道  %6.2fs  %d 级 / 解 %d 步 / 离位 %s"
                          % (i + 1, args.n, kept, dt, level, len(cand.solution),
                             cand.extra.get("misplaced", "—")), flush=True)
        # 战绩：不管这次成没成都打（kociemba 九成九是"没出"，写进成功分支就永远看不到）
        if period > 1 and (i + 1) >= next_at:
            next_at += period
            done = i + 1
            spent = time.time() - t0
            eta = spent / done * (args.n - done)
            print("  [%6d/%d]  出题 %d 道  命中率 %.3f%%  已留 %d 道  用时 %s  预计还要 %s"
                  % (done, args.n, found, 100 * found / done, kept,
                     fmt_secs(spent), fmt_secs(eta)), flush=True)
    written = 0
    for level in sorted(buckets):
        for cand in buckets[level]:
            meta = build_meta(cand, args, level, cand.seed)
            save_unique(root, cand.board, meta)
            written += 1

    # 报表
    print()
    print("难度   候选   写入   丢弃   解步数(最少~最多)   离位(最少/平均/最多)")
    for level in sorted(counts):
        bucket = buckets.get(level, [])
        moves = [len(c.solution) for c in bucket]
        mis = [c.extra.get("misplaced") for c in bucket if "misplaced" in c.extra]
        mis_txt = ("%d / %.1f / %d" % (min(mis), sum(mis) / len(mis), max(mis))
                   if mis else "—")
        mv_txt = "%d ~ %d" % (min(moves), max(moves)) if moves else "—"
        dropped = counts[level] - len(bucket)
        flag = "   ← 截断了" if dropped else ""
        print("%4d  %6d  %6d  %6d   %-18s %s%s"
              % (level, counts[level], len(bucket), dropped, mv_txt, mis_txt, flag))
    if not counts:
        print("（一道都没出 —— kociemba 那种方法产出本来就稀，把 --n 调大）")
    print()
    print("一共写了 %d 道（%d 个难度）到 %s；重复局面 %d 个；用时 %.0fs"
          % (written, len(buckets), root, dup, time.time() - t0))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(argv) if argv is not None else None
    # 先只认 --method，好知道要挂哪个方法的专属参数
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--method", choices=methods.names())
    known, _rest = pre.parse_known_args(argv)
    method = methods.get(known.method) if known.method else None
    args = build_parser(method).parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
