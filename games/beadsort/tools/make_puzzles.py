"""批量出题，按等级存进题库。

用法：

    python -m games.beadsort.tools.make_puzzles                          # 默认：走 85 步 × 10 道（9 级）
    python -m games.beadsort.tools.make_puzzles --series 85 160 --count 50 20
    python -m games.beadsort.tools.make_puzzles --series 40 --count 100

产出：

    games/beadsort/puzzles/
    ├─ 4/<id>.txt        等级 4 的题（走 40 步 → 解 40 步）
    ├─ 9/<id>.txt
    └─ …

出题方式：`walk_gen` 的**施工式反走**（把一条合法解倒着演一遍 → 题面）——
不需要求解器，出题 100% 成功、**起点一定有解**。**不写任何台账**：题目文件本身就是记录
（等级看目录名、id 看文件名、来源看 `generator` / `solution_by`）。
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Dict, List

from ..core import generator as g
from ..core import walk_gen
from ..core.free_solver import format_moves, homes, verify

# 题库默认写进本游戏自己的 puzzles/（锚在文件位置上，跟工作目录无关）
PUZZLE_DIR = Path(__file__).resolve().parent.parent / "puzzles"


def lower_bound(state) -> int:
    """下界：按「每色归到珠子最多的那根柱子」算，至少有几颗球要挪。"""
    home = homes(state)
    return sum(1 for t, tube in enumerate(state) for v in tube if v and home.get(v) != t)


def build_meta(row: Dict[str, object], series: int, state) -> Dict[str, object]:
    return {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "created_by": g.CREATED_BY,
        "id": row["id"],
        "tubes": g.TUBES,
        "colors": g.COLOR_LETTERS[: g.COLORS],
        "capacity": g.CAPACITY,
        "balls_per_color": g.BALLS_PER_COLOR,
        "level": row["level"],
        "moves": row["moves"],
        "seed": row["seed"],
        "steps": series,
        "generator": g.GENERATOR,
        "seconds": row["seconds"],          # 这一道出题花了多久（秒）
        "solution_by": row["source"],
        "solution": format_moves(row["_moves"]),
    }


def run_one(series: int, seed: int) -> Dict[str, object]:
    t0 = time.time()
    state, raw, solution = walk_gen.walk(seed, series)
    lb = lower_bound(state)
    ok = verify(state, solution)
    ratio = (len(solution) / lb) if (ok and lb) else None
    # 收下的三条：解合法；**真的走满目标步数**（施工偶尔走不下去）；解别比下界啰嗦太多
    # （如果靠"回到走过的局面"硬凑长度，ratio 会飙到十倍以上 —— 那种解合法、但最短解短得多，
    #   拿来当"高难度"是骗人的）
    reached = len(solution) == series
    tight = ratio is not None and ratio <= 3.0
    keep = bool(ok and reached and tight)
    return {
        "series": series,
        "seed": seed,
        "ok": int(ok),
        "keep": int(keep),
        "reached": int(reached),
        "tight": int(tight),
        "source": "walk" if ok else "-",
        "moves": len(solution) if ok else "",
        "level": g.level_of(len(solution)) if keep else "",
        "lower_bound": lb,
        "ratio": round(ratio, 2) if ratio is not None else "",
        "seconds": round(time.time() - t0, 3),
        "id": g.make_id() if keep else "",
        "path": "",
        "_state": state if keep else None,
        "_moves": solution,
        "_raw": len(raw),
    }


def run_series(series: int, count: int, seed0: int, root: Path,
               quiet: bool = False, max_attempts: int = None) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    kept = 0
    attempts = 0
    # 凑够 count 道才停（长题很稀有，一个种子一道题是抽不到的）；上限防死循环
    cap = max(max_attempts or 0, count * 50, 200)
    while kept < count and attempts < cap:
        attempts += 1
        row = run_one(series, seed0 + attempts - 1)
        rows.append(row)
        if row["keep"]:
            path = g.save_board(root, row["_state"], build_meta(row, series, row["_state"]))
            row["path"] = str(path)
            kept += 1
        if row["keep"]:
            note = "收 %s级 %s步(%.2f×)" % (row["level"], row["moves"], row["ratio"])
        elif not row["ok"]:
            note = "丢 解不合法"
        elif not row["reached"]:
            note = "丢 只走到 %s 步（目标 %d）" % (row["moves"], series)
        else:
            note = "丢 解太啰嗦（%s× 下界）" % row["ratio"]
        if not quiet:
            print("  %3d 步 seed=%-4d %-28s %.2fs"
                  % (series, row["seed"], note, row["seconds"]), flush=True)
        elif attempts % 50 == 0:
            print("  …… %d 步已试 %d 次（收下 %d/%d）" % (series, attempts, kept, count),
                  flush=True)
    print("  —— %d 步这一轮：收下 %d / %d（共试 %d 次）" % (series, kept, count, attempts),
          flush=True)
    return rows


def summarize(rows: List[Dict[str, object]]) -> None:
    print()
    print("系列   收下/总数   解出率   步数(min/avg/max)   等级分布            用时")
    print("-----  ---------  -------  ------------------  ------------------  ----------")
    for series in sorted({r["series"] for r in rows}):
        group = [r for r in rows if r["series"] == series]
        ok = [r for r in group if r["ok"]]
        good = [r for r in group if r["keep"]]
        lv: Dict[int, int] = {}
        for r in good:
            lv[int(r["level"])] = lv.get(int(r["level"]), 0) + 1
        lv_txt = " ".join("%d级×%d" % (k, lv[k]) for k in sorted(lv)) or "-"
        if good:
            mv = [int(r["moves"]) for r in good]
            move_txt = "%d / %.1f / %d" % (min(mv), sum(mv) / len(mv), max(mv))
        else:
            move_txt = "-"
        secs = sum(float(r["seconds"]) for r in group)
        print("%5d  %4d/%-4d  %5.0f%%  %-18s  %-18s %.0fs"
              % (series, len(good), len(group), 100 * len(ok) / len(group),
                 move_txt, lv_txt, secs))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="批量出题，按等级存进题库")
    p.add_argument("--series", type=int, nargs="+", default=[85],
                   help="走多少步（默认 85 → 9 级）")
    p.add_argument("--count", type=int, nargs="+", default=[10],
                   help="每个系列多少道（默认 10；只给一个值时所有系列共用）")
    p.add_argument("--seed0", type=int, default=1, help="起始随机种子")
    p.add_argument("--max-attempts", type=int, default=None,
                   help="每个系列最多试多少种种子（默认 数量×50，最少 200；长题很稀少就调大）")
    p.add_argument("--tubes", type=int, default=None, help="柱子数（默认本游戏的 7）")
    p.add_argument("--colors", type=int, default=None, help="用几种颜色（默认 6）")
    p.add_argument("--per", type=int, default=None, help="每种颜色几颗（默认 10）")
    p.add_argument("--out-dir", default=str(PUZZLE_DIR),
                   help="题库根目录（默认本游戏的 puzzles/）")
    p.add_argument("--quiet", action="store_true", help="不逐题打印，每 50 道报一次进度")
    args = p.parse_args(argv)

    counts = args.count if len(args.count) == len(args.series) else [args.count[0]] * len(args.series)
    root = Path(args.out_dir)

    # 参数可以临时覆盖（每道题的参数会写进题目文件，所以题库里混着几种参数也没关系）
    if args.tubes:
        g.TUBES = args.tubes
    if args.colors:
        g.COLORS = args.colors
    if args.per:
        g.BALLS_PER_COLOR = args.per
    print("参数：%d 柱 / %d 色 / 每色 %d 颗（空 %d 根柱子）"
          % (g.TUBES, g.COLORS, g.BALLS_PER_COLOR, g.TUBES - g.COLORS), flush=True)

    all_rows: List[Dict[str, object]] = []
    started = time.time()
    for series, count in zip(args.series, counts):
        print("=== 乱走 %d 步 × %d 道 ===" % (series, count), flush=True)
        all_rows += run_series(series, count, args.seed0, root, args.quiet, args.max_attempts)

    print()
    summarize(all_rows)
    print()
    print("总用时 %.1f 秒（墙钟；逐题的用时写在每道题的 seconds 字段里）"
          % (time.time() - started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
