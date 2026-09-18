"""竞技串珠：**采样器命令行** —— 大批量抽样，看乱度分布，导出候选题目。

它回答的是这个问题：

> 从完成状态反向随机走，到底能把珠子打散到什么程度？
> 那个「离位上上限」是结构性的，还是采样不够？

跟出题器（`tools/make_puzzles.py`）的分工：

* `make_puzzles` —— 要「走满 N 步」的题，走不满就走人（现在出 L1 用这个）
* `sampler`      —— **不追求步数**，让随机过程充分探索，按最终局面的**乱度**分档

两种用法：

```bash
# 1) 抽样看分布（最常用）：跑 1 万道，看离位最高能到几颗
python -m games.beadsort.tools.sampler survey --n 10000

# 2) 扫样本量：1 千 / 1 万 / 5 万 各跑一遍，看天花板会不会继续涨
python -m games.beadsort.tools.sampler survey --scales 1000 10000 50000

# 3) 导出最乱的那几道（存进候选目录，不进正式题库）
python -m games.beadsort.tools.sampler dump --min-misplaced 20 --count 5
```

想看「加了防打转到底有没有用」，就对比这两条：

```bash
python -m games.beadsort.tools.sampler survey --n 2000 --repeat allow --stagnation 0
python -m games.beadsort.tools.sampler survey --n 2000
```
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..core import generator as g
from ..core import sampler as sp
from ..core.free_solver import format_moves, key

GAME_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = GAME_DIR / "puzzles_candidates"

# 离位分数档（0-4 / 5-8 / ...），报表和直方图共用
BUCKETS = ((0, 4), (5, 8), (9, 12), (13, 16), (17, 19), (20, 21), (22, 23), (24, 999))
BUCKET_LABEL = {
    (0, 4): "0- 4", (5, 8): "5- 8", (9, 12): " 9-12", (13, 16): "13-16",
    (17, 19): "17-19", (20, 21): "20-21", (22, 23): "22-23", (24, 999): "  ≥24",
}


def _pct(seq: Sequence[float], q: float) -> float:
    """分位数（下标取整，够用就行）。"""
    if not seq:
        return 0.0
    return sorted(seq)[min(len(seq) - 1, int(len(seq) * q))]


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--strategy", default="random", choices=sp.STRATEGIES,
                   help="走法：random = 纯随机（默认）；greedy = 每步挑最乱的（对照用）")
    p.add_argument("--repeat", default="none", choices=sp.REPEATS,
                   help="防重复：none = 走过的局面不再进（默认）；"
                        "recent = 只禁最近 --recent 步；allow = 只禁立即反向（老做法）")
    p.add_argument("--recent", type=int, default=20, help="--repeat recent 时回看多少步")
    p.add_argument("--stagnation", type=int, default=sp.DEFAULT_STAGNATION,
                   help="连续多少步没刷新离位纪录就收工（0 = 不截断）")
    p.add_argument("--max-steps", type=int, default=sp.DEFAULT_MAX_STEPS,
                   help="反走步数上限（刹车，不是目标）")
    p.add_argument("--seed0", type=int, default=1, help="起始随机种子（从它开始连续取）")
    p.add_argument("--tubes", type=int, default=None, help="柱子数（默认 7）")
    p.add_argument("--colors", type=int, default=None, help="颜色数（默认 6）")
    p.add_argument("--per", type=int, default=None, help="每种颜色几颗（默认 10）")
    p.add_argument("--capacity", type=int, default=None, help="柱容量（默认跟 --per 一样）")


def _describe(cfg: Dict[str, object], args) -> str:
    stag = args.stagnation if args.stagnation else "关"
    return ("%d 柱 / %d 色 / 每色 %d 颗（空 %d 柱） | 策略 %s | 防重复 %s | "
            "停滞 %s | 上限 %d 步"
            % (cfg["tubes"], cfg["colors"], cfg["balls_per_color"], cfg["empty_tubes"],
               args.strategy, args.repeat, stag, args.max_steps))


# --------------------------------------------------------------------------
# 抽样
# --------------------------------------------------------------------------


def _walk_kwargs(args) -> Dict[str, object]:
    return {
        "max_steps": args.max_steps,
        "repeat": args.repeat,
        "recent": args.recent,
        "stagnation": (args.stagnation or None),
        "strategy": args.strategy,
    }


def _sample_scale(n: int, args, *, progress: bool = False) -> Dict[str, object]:
    """跑 n 道，只留统计（不留全部局面，几万道也不吃内存）。"""
    t0 = time.time()
    steps: List[int] = []
    moves: List[int] = []
    mis: List[int] = []
    segs: List[int] = []
    ratios: List[float] = []
    levels: Dict[int, int] = {}
    stops: Dict[str, int] = {}
    unique = set()
    rows: List[Dict[str, object]] = []
    every = max(1, n // 10)

    for i in range(n):
        w = sp.sample(args.seed0 + i, **_walk_kwargs(args))
        is_new = w.board not in unique
        unique.add(w.board)
        steps.append(w.steps)
        moves.append(w.moves)
        mis.append(w.misplaced)
        segs.append(w.segments)
        ratios.append(round(w.ratio, 2))
        levels[w.level] = levels.get(w.level, 0) + 1
        stops[w.stop] = stops.get(w.stop, 0) + 1
        rows.append({
            "seed": w.seed, "steps": w.steps, "moves": w.moves, "level": w.level,
            "misplaced": w.misplaced, "segments": w.segments,
            "max_run": w.max_run, "bottom_run": w.bottom_run,
            "ratio": round(w.ratio, 2), "stop": w.stop, "unique": int(is_new),
        })
        if progress and (i + 1) % every == 0:
            print("    …%d/%d（%.0fs）" % (i + 1, n, time.time() - t0), flush=True)

    dt = time.time() - t0
    hist = {b: 0 for b in BUCKETS}
    for m in mis:
        for b in BUCKETS:
            if b[0] <= m <= b[1]:
                hist[b] += 1
                break
    return {
        "n": n, "secs": dt, "unique": len(unique),
        "steps": steps, "moves": moves, "misplaced": mis, "segments": segs,
        "ratios": ratios, "levels": levels, "stops": stops, "hist": hist,
        "ge": {k: sum(1 for m in mis if m >= k) for k in (18, 20, 22, 24, 26, 28)},
        "rows": rows,
    }


def _report(res: Dict[str, object]) -> None:
    n = res["n"]
    mis, steps, segs = res["misplaced"], res["steps"], res["segments"]
    print("样本量 %d" % n)
    print("  用时 %.1fs（%.2fms/道）   唯一局面 %d（%.1f%%）"
          % (res["secs"], 1000 * res["secs"] / n,
             res["unique"], 100 * res["unique"] / n))
    print("  步数   平均 %.1f / 90分位 %d / 最大 %d"
          % (sum(steps) / n, _pct(steps, 0.9), max(steps)))
    print("  离位   平均 %.1f / 90分位 %d / 最大 %d"
          % (sum(mis) / n, _pct(mis, 0.9), max(mis)))
    print("  色段   平均 %.1f / 最大 %d" % (sum(segs) / n, max(segs)))
    print("  解步数 平均 %.1f / 最大 %d（除以 10 向上取整 = 等级）"
          % (sum(res["moves"]) / n, max(res["moves"])))
    print("  收工   " + " / ".join("%s %d" % (k, v)
                                  for k, v in sorted(res["stops"].items())))
    print("  离位分布")
    top = max(res["hist"].values()) or 1
    for b in BUCKETS:
        c = res["hist"][b]
        bar = "#" * max(0, int(round(20 * c / top)))
        print("    %-6s %6d  %5.2f%%  %s" % (BUCKET_LABEL[b], c, 100 * c / n, bar))
    print("  长尾   " + "  ".join("≥%d:%d" % (k, res["ge"][k]) for k in sorted(res["ge"])))


def _compare(results: List[Dict[str, object]]) -> None:
    """样本量 vs 天花板：看最高离位会不会随样本量继续涨。"""
    print("=== 样本量 vs 天花板 ===")
    print("%8s %10s %8s %8s %8s %7s %7s %7s %8s"
          % ("样本量", "唯一局面", "离位均", "离位max", "解步max", "≥20", "≥22", "≥24", "用时"))
    for r in results:
        n = r["n"]
        print("%8d %10d %8.1f %8d %8d %7d %7d %7d %7.1fs"
              % (n, r["unique"], sum(r["misplaced"]) / n, max(r["misplaced"]),
                 max(r["moves"]), r["ge"][20], r["ge"][22], r["ge"][24], r["secs"]))
    print()


def cmd_survey(args) -> int:
    cfg = sp.configure(args.tubes, args.colors, args.per, args.capacity)
    scales = args.scales or [args.n]
    print("竞技串珠采样器：从完成状态反走（每一步都是合法逆操作 → 局面一定有解），"
          "走不动 / 到上限 / 停滞就停")
    print("参数：" + _describe(cfg, args))
    print()
    results: List[Dict[str, object]] = []
    for n in scales:
        res = _sample_scale(n, args, progress=(n >= 20000 and not args.quiet))
        results.append(res)
        _report(res)
        print()
    if len(results) > 1:
        _compare(results)

    if args.csv:
        path = Path(args.csv)
        path.parent.mkdir(parents=True, exist_ok=True)
        cols = list(results[-1]["rows"][0].keys())
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["scale"] + cols)
            w.writeheader()
            for r in results:
                for row in r["rows"]:
                    w.writerow(dict(row, scale=r["n"]))
        print("逐题明细写到 %s" % path)

    if args.top:
        print()
        print("=== 最乱的 %d 道 ===" % args.top)
        best = sorted(results[-1]["rows"], key=lambda r: -r["misplaced"])[: args.top]
        for row in best:
            print("  seed=%-5d 离位 %2d / 色段 %2d / 反走 %2d 步 / 解 %2d 步 / %s 级 / %s"
                  % (row["seed"], row["misplaced"], row["segments"], row["steps"],
                     row["moves"], row["level"], row["stop"]))
        print("  想看这些题长什么样：python -m games.beadsort.tools.sampler dump "
              "--min-misplaced %d --count %d" % (best[-1]["misplaced"], args.top))
    return 0


# --------------------------------------------------------------------------
# 导出候选题目
# --------------------------------------------------------------------------


def _build_meta(w, series: int, seconds: float) -> Dict[str, object]:
    return {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "created_by": g.CREATED_BY,
        "id": g.make_id(),
        "tubes": g.TUBES,
        "colors": g.COLOR_LETTERS[: g.COLORS],
        "capacity": g.CAPACITY,
        "balls_per_color": g.BALLS_PER_COLOR,
        "level": w.level,
        "moves": w.moves,
        "seed": w.seed,
        "steps": series,
        "generator": sp.GENERATOR,
        "seconds": round(seconds, 3),
        "solution_by": "walk",
        "solution": format_moves(w.solution),
        "misplaced": w.misplaced,
        "segments": w.segments,
    }


def cmd_dump(args) -> int:
    cfg = sp.configure(args.tubes, args.colors, args.per, args.capacity)
    root = Path(args.out_dir)
    print("采样并导出：%s" % _describe(cfg, args))
    print("只要 离位 %d ~ %s 的题，最多导出 %d 道（去重），写进 %s"
          % (args.min_misplaced, args.max_misplaced or "∞", args.count, root))

    kept = 0
    seen = set()
    attempts = 0
    t0 = time.time()
    while kept < args.count and attempts < args.max_attempts:
        attempts += 1
        t1 = time.time()
        w = sp.sample(args.seed0 + attempts - 1, **_walk_kwargs(args))
        dt = time.time() - t1
        if w.board in seen or w.misplaced < args.min_misplaced:
            continue
        if args.max_misplaced and w.misplaced > args.max_misplaced:
            continue
        if not sp.verify(w):
            print("  !! seed=%d 解不自洽，跳过（不该发生）" % w.seed)
            continue
        seen.add(w.board)
        if args.ratio and w.ratio > args.ratio:
            continue
        meta = _build_meta(w, w.steps, dt)
        path = g.save_board(root, w.board, meta)
        kept += 1
        print()
        print("[%d/%d] 离位 %d / 色段 %d / 反走 %d 步 / 解 %d 步 / %s 级 / %s / %s"
              % (kept, args.count, w.misplaced, w.segments, w.steps, w.moves,
                 w.level, w.stop, path.name))
        print(g.render_board([list(t) for t in w.board]))
    print()
    if kept < args.count:
        print("只凑到 %d / %d 道（试了 %d 个种子）——把 --min-misplaced 往下降，"
              "或者把 --count 减小" % (kept, args.count, attempts))
    print("用时 %.1fs" % (time.time() - t0))
    return 0


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# 按步数建库
# --------------------------------------------------------------------------


def _clear_library(root: Path) -> int:
    """把题库目录里的旧题目文件删掉（只删 <root>/<数字>/ 下的 *.txt）。"""
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


def cmd_build(args) -> int:
    """跑一批采样，**按解的长度（= 难度）分档**写进题库，每档最多 `--per-level` 道。"""
    cfg = sp.configure(args.tubes, args.colors, args.per, args.capacity)
    root = Path(args.out_dir)
    print("采样建库：%s" % _describe(cfg, args))
    print("跑 %d 道，按解的长度分档写进 %s，每档最多 %d 道"
          % (args.n, root, args.per_level), flush=True)

    if args.clear:
        removed = _clear_library(root)
        print("先把旧题清掉：删了 %d 个题目文件" % removed, flush=True)

    buckets: Dict[int, List] = {}
    counts: Dict[int, int] = {}
    seen = set()
    dup = 0
    keep_all = args.pick == "chaos"        # chaos 要看到全部候选；first 只留够用的就行
    t0 = time.time()
    every = max(1, args.n // 10)
    for i in range(args.n):
        t1 = time.time()
        w = sp.sample(args.seed0 + i, **_walk_kwargs(args))
        dt = time.time() - t1
        k = key(w.board)
        if k in seen:                          # 同一道题（柱子顺序不算）只留一份
            dup += 1
        else:
            seen.add(k)
            if not args.min_misplaced or w.misplaced >= args.min_misplaced:
                counts[w.level] = counts.get(w.level, 0) + 1
                pool = buckets.setdefault(w.level, [])
                if keep_all or len(pool) < args.per_level:
                    pool.append((w, dt))
        if not args.quiet and (i + 1) % every == 0:
            print("   …采了 %d/%d（%.0fs）" % (i + 1, args.n, time.time() - t0), flush=True)
    print("采完：%d 道，去掉重复 %d 道，用时 %.1fs" % (args.n, dup, time.time() - t0))
    print()

    rows = []
    written = 0
    for level in sorted(buckets):
        pool = buckets[level]
        if args.pick == "chaos":               # 这一档里最乱的先挑
            pool = sorted(pool, key=lambda x: (-x[0].misplaced, -x[0].segments, x[0].seed))
        picks = pool[: args.per_level]
        for w, dt in picks:
            g.save_board(root, w.board, _build_meta(w, w.steps, dt))
        written += len(picks)
        mis = [w.misplaced for w, _dt in picks]
        moves = [w.moves for w, _dt in picks]
        rows.append({
            "level": level, "have": counts[level], "wrote": len(picks),
            "mis_min": min(mis), "mis_avg": sum(mis) / len(mis), "mis_max": max(mis),
            "mv_min": min(moves), "mv_max": max(moves),
        })

    print("难度   候选   写入   离位(最少/平均/最多)   解步数(最少~最多)")
    for r in rows:
        print("%4d  %6d  %6d   %2d / %5.1f / %2d        %2d ~ %2d"
              % (r["level"], r["have"], r["wrote"], r["mis_min"], r["mis_avg"],
                 r["mis_max"], r["mv_min"], r["mv_max"]))
    if not rows:
        print("（一道都没采到，把 --min-misplaced 降下来或者把 --n 加大）")
    print()
    print("一共写了 %d 道（%d 个难度）到 %s" % (written, len(rows), root))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="竞技串珠：约束采样器")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("survey", help="抽样看乱度分布（默认动作）")
    s.add_argument("--n", type=int, default=2000, help="跑多少道（默认 2000）")
    s.add_argument("--scales", type=int, nargs="+", default=None,
                   help="一次跑多个样本量，例如 --scales 1000 10000 50000（看天花板涨不涨）")
    s.add_argument("--csv", default=None, help="把逐题明细写成 CSV")
    s.add_argument("--top", type=int, default=0, help="另外列出最乱的 N 道（默认不列）")
    s.add_argument("--quiet", action="store_true", help="不打印中途进度")
    _add_common(s)
    s.set_defaults(func=cmd_survey)

    d = sub.add_parser("dump", help="把最乱的题导出成候选题目文件")
    d.add_argument("--count", type=int, default=5, help="导出几道（默认 5）")
    d.add_argument("--min-misplaced", type=int, default=18, help="离位至少要几颗（默认 18）")
    d.add_argument("--max-misplaced", type=int, default=0, help="离位最多几颗（0 = 不限）")
    d.add_argument("--ratio", type=float, default=0.0,
                   help="解步数 ÷ 下界 的上限，超过就扔掉（0 = 不限；3 附近的题不啰嗦）")
    d.add_argument("--max-attempts", type=int, default=200000, help="最多试多少个种子")
    d.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                   help="写到哪儿（默认 %s，不是正式题库）" % DEFAULT_OUT_DIR)
    _add_common(d)
    d.set_defaults(func=cmd_dump)

    b = sub.add_parser("build", help="跑一批采样，按步数分档写进题库")
    b.add_argument("--n", type=int, default=10000, help="跑多少道（默认 10000）")
    b.add_argument("--per-level", type=int, default=20, help="每个难度最多几道（默认 20）")
    b.add_argument("--pick", default="first", choices=("first", "chaos"),
                   help="同一难度挑哪几道：first = 按种子顺序先到先得（默认）；"
                        "chaos = 这一档里最乱的先挑")
    b.add_argument("--min-misplaced", type=int, default=0,
                   help="离位少于这么多的直接扔（默认 0 = 不扔）")
    b.add_argument("--out-dir", default=str(GAME_DIR / "puzzles"),
                   help="写进哪个题库（默认 %s）" % (GAME_DIR / "puzzles"))
    b.add_argument("--clear", action="store_true", help="先把题库里的旧题清掉")
    b.add_argument("--quiet", action="store_true", help="不打印中途进度")
    _add_common(b)
    b.set_defaults(func=cmd_build)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
