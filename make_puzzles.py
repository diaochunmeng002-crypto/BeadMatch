"""批量出题，按等级存进题库，并把每道题的结果写成 index.csv。

用法：

    python make_puzzles.py                                   # 100 步 × 500 道 + 200 步 × 100 道
    python make_puzzles.py --series 100 200 --count 10 5
    python make_puzzles.py --series 100 --count 20 --ratio-max 2.5

产出：

    puzzles/
    ├─ index.csv         每道题一行（含没被收下的，keep=0）
    ├─ 2/<id>.txt        等级 2 的题
    ├─ 3/<id>.txt
    └─ ...

收题规则（2026-09-13 定）：

* 解不出来 → 不收；
* 解的长度 > 下界 × ratio_max（默认 2）→ 判为"绕远路的解"，**直接丢弃**，不进题库。
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generator as g  # noqa: E402
from free_solver import (  # noqa: E402
    format_moves,
    homes,
    solve,
    solve_by_old_rule,
    verify,
)


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


def run_one(series: int, seed: int, timeout: float, node_limit: int,
            ratio_max: float) -> Dict[str, object]:
    t0 = time.time()
    state = g.walk_state(series, random.Random(seed))
    lb = lower_bound(state)

    moves = solve_by_old_rule(state)
    source = "kociemba"
    if moves is None:
        moves = solve(state, time_limit=timeout, node_limit=node_limit, seed=seed)
        source = "dfs"

    ok = moves is not None and verify(state, moves)
    ratio = (len(moves) / lb) if (ok and lb) else None
    keep = bool(ok and ratio is not None and ratio <= ratio_max)
    return {
        "series": series,
        "seed": seed,
        "ok": int(ok),
        "keep": int(keep),
        "source": source if ok else "-",
        "moves": len(moves) if ok else "",
        "level": g.level_of(len(moves)) if keep else "",
        "lower_bound": lb,
        "ratio": round(ratio, 2) if ratio is not None else "",
        "seconds": round(time.time() - t0, 3),
        "id": g.make_id() if keep else "",
        "path": "",
        "_state": state if keep else None,
        "_moves": moves,
    }


def run_series(series: int, count: int, timeout: float, node_limit: int,
               seed0: int, ratio_max: float, root: Path,
               quiet: bool = False) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    kept = 0
    for k in range(count):
        row = run_one(series, seed0 + k, timeout, node_limit, ratio_max)
        if row["keep"]:
            path = g.save_board(root, row["_state"], build_meta(row, series, row["_state"]))
            row["path"] = str(path)
            kept += 1
        rows.append(row)
        if row["keep"]:
            note = "收 %s级 %s步(%.2f×)" % (row["level"], row["moves"], row["ratio"])
        elif row["ok"]:
            note = "丢 解太绕 %s步/%s下界=%.2f×" % (row["moves"], row["lower_bound"], row["ratio"])
        else:
            note = "丢 没解出来"
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
    p.add_argument("--series", type=int, nargs="+", default=[100, 200],
                   help="乱走步数（默认 100 200）")
    p.add_argument("--count", type=int, nargs="+", default=[500, 100],
                   help="每个系列多少道（默认 500 100；只给一个值时所有系列共用）")
    p.add_argument("--timeout", type=float, default=5.0, help="每道题求解的时间上限（秒）")
    p.add_argument("--node-limit", type=int, default=200_000, help="每道题求解的节点上限")
    p.add_argument("--ratio-max", type=float, default=2.0,
                   help="解的长度 / 下界 超过这个倍数就丢弃（默认 2）")
    p.add_argument("--seed0", type=int, default=1, help="起始随机种子")
    p.add_argument("--out-dir", default="puzzles", help="题库根目录（默认 puzzles）")
    p.add_argument("--index", default=None, help="index.csv 路径（默认 <题库>/index.csv）")
    p.add_argument("--quiet", action="store_true", help="不逐题打印，每 50 道报一次进度")
    args = p.parse_args(argv)

    counts = args.count if len(args.count) == len(args.series) else [args.count[0]] * len(args.series)
    root = Path(args.out_dir)
    index_path = Path(args.index) if args.index else root / "index.csv"

    all_rows: List[Dict[str, object]] = []
    for series, count in zip(args.series, counts):
        print("=== 乱走 %d 步 × %d 道 ===" % (series, count), flush=True)
        all_rows += run_series(series, count, args.timeout, args.node_limit,
                               args.seed0, args.ratio_max, root, args.quiet)

    fields = ["series", "seed", "ok", "keep", "source", "moves", "level",
              "lower_bound", "ratio", "seconds", "id", "generator", "created_by",
              "path"]
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in all_rows:
            row = dict(row, generator=g.GENERATOR, created_by=g.CREATED_BY)
            w.writerow(row)
    print()
    print("index 已写出：%s（%d 行）" % (index_path, len(all_rows)))
    summarize(all_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
