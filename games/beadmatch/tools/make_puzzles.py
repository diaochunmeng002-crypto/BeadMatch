"""批量出题，按等级存进题库。

用法：

    python -m games.beadmatch.tools.make_puzzles                          # 默认：走 85 步 × 10 道（9 级）
    python -m games.beadmatch.tools.make_puzzles --series 85 160 --count 50 20
    python -m games.beadmatch.tools.make_puzzles --series 40 --count 100

产出：

    games/beadmatch/puzzles/
    ├─ 4/<id>.txt        等级 4 的题（走 40 步 → 解 40 步）
    ├─ 9/<id>.txt
    └─ …

出题方式（2026-09-14 起）：`walk_gen` 的引导式走法，**反走即解** ——
不再需要求解器，出题 100% 成功。**不写任何台账**：题目文件本身就是记录
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
        "solution_by": row["source"],
        "solution": format_moves(row["_moves"]),
    }


def run_one(series: int, seed: int) -> Dict[str, object]:
    t0 = time.time()
    state, raw, solution = walk_gen.walk(seed, series)
    lb = lower_bound(state)
    ok = verify(state, solution)
    ratio = (len(solution) / lb) if (ok and lb) else None
    keep = bool(ok)
    return {
        "series": series,
        "seed": seed,
        "ok": int(ok),
        "keep": int(keep),
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
               quiet: bool = False) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    kept = 0
    for k in range(count):
        row = run_one(series, seed0 + k)
        if row["keep"]:
            path = g.save_board(root, row["_state"], build_meta(row, series, row["_state"]))
            row["path"] = str(path)
            kept += 1
        rows.append(row)
        note = ("收 %s级 %s步(%.2f×)" % (row["level"], row["moves"], row["ratio"])
                if row["keep"] else "丢 没解出来")
        if not quiet:
            print("  %3d 步 seed=%-4d %-28s %.2fs"
                  % (series, row["seed"], note, row["seconds"]), flush=True)
        elif (k + 1) % 50 == 0:
            print("  …… %d 步已跑 %d/%d（收下 %d）" % (series, k + 1, count, kept),
                  flush=True)
    print("  —— %d 步这一轮：收下 %d / %d" % (series, kept, count), flush=True)
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
    p.add_argument("--out-dir", default=str(PUZZLE_DIR),
                   help="题库根目录（默认本游戏的 puzzles/）")
    p.add_argument("--quiet", action="store_true", help="不逐题打印，每 50 道报一次进度")
    args = p.parse_args(argv)

    counts = args.count if len(args.count) == len(args.series) else [args.count[0]] * len(args.series)
    root = Path(args.out_dir)

    all_rows: List[Dict[str, object]] = []
    for series, count in zip(args.series, counts):
        print("=== 乱走 %d 步 × %d 道 ===" % (series, count), flush=True)
        all_rows += run_series(series, count, args.seed0, root, args.quiet)

    print()
    summarize(all_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
