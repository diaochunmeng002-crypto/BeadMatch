"""BeadMatch 出题器 —— 出一道题，存进题库，也能读回来给人看。

规则、格式、字段都按 docs/requirement.md 走（重点：§2.2 移动规则、§5 数据格式）。

出题流程：

    已解局面 ──按我们的规则随机乱走 WALK_STEPS 步──▶ 初始局面
              ──free_solver.solve() 求一条解──▶ 步数 → level

用法：

    python -m games.beadmatch.core.generator                        # 出一道题，存进题库，并打印
    python -m games.beadmatch.core.generator --steps 300 --seed 7   # 指定乱走步数 / 随机种子
    python -m games.beadmatch.core.generator --print-only           # 只打印，不落盘
    python -m games.beadmatch.core.generator --show <题目文件>      # 读一道题并打印
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import walk_gen
from .free_solver import (
    apply_move,
    format_moves,
    legal_moves,
    parse_moves,
    verify,
)

# --------------------------------------------------------------------------
# 全局参数（docs/requirement.md §3.1 / §3.3）
# --------------------------------------------------------------------------

TUBES = 7               # 柱子数
COLORS = 6              # 颜色数
BALLS_PER_COLOR = 10    # 每色珠子数
CAPACITY = 10           # 每根柱子的容量（能装几格）

# 出题时乱走多少步的兜底值（正常情况下由 difficulty × 10 算出来）。
WALK_STEPS = 100

# 题库目录（一题一文件，文件名 = <id>.txt）。
# **锚在文件位置上**，别用相对路径 —— 否则换个工作目录跑就悄悄写到别处去了。
PUZZLE_DIR = Path(__file__).resolve().parent.parent / "puzzles"

# 颜色写死就这 6 个，不许改（docs/requirement.md §3.2）。
# 顺序就是代码里 1..6 的编号：1=Y 2=G 3=R 4=P 5=B 6=O。
COLOR_NAMES = ("Yellow", "Green", "Red", "Purple", "Blue", "Orange")
COLOR_LETTERS = "YGRPBO"        # 下标 i 对应颜色编号 i+1
EMPTY = 0
EMPTY_LETTER = "X"

LEVEL_STEP = 10                 # 每 10 步一档

# 题目的「出身」（2026-09-14 加，为以后支持更多生成算法）
#   created_by —— 谁出的：工具名，或以后手工摆题时的人名/`manual`
#   generator  —— 用哪套算法出的：名字 + 版本，算法一改语义就变，所以带版本
CREATED_BY = "beadmatch"
GENERATOR = walk_gen.GENERATOR      # walk_guided@4，见 walk_gen.py

# 元信息区的输出顺序（第一行是创建时间，第二行是谁创建的）
META_ORDER = (
    "created_at", "created_by", "solution_by", "id", "tubes", "colors", "capacity",
    "balls_per_color", "level", "moves", "seed", "steps", "generator", "solution",
)


# --------------------------------------------------------------------------
# 局面
# --------------------------------------------------------------------------


def solved_state() -> List[List[int]]:
    """已解局面：每种颜色占满一根柱子，剩下的是空柱。"""
    pad = [EMPTY] * (CAPACITY - BALLS_PER_COLOR)
    state = [pad + [c] * BALLS_PER_COLOR for c in range(1, COLORS + 1)]
    state += [[EMPTY] * CAPACITY for _ in range(TUBES - COLORS)]
    return state


def random_step(state: Sequence[Sequence[int]], rng: random.Random):
    """按我们的规则随机走一步（落点只要有空位）。"""
    moves = legal_moves(state)
    if not moves:
        return [list(t) for t in state]
    return [list(t) for t in apply_move(state, rng.choice(moves))]


def walk_state(steps: int, rng: random.Random) -> List[List[int]]:
    """从已解局面开始，按我们的规则乱走 ``steps`` 步。"""
    state = solved_state()
    for _ in range(steps):
        state = random_step(state, rng)
    return state


def level_of(moves: int) -> int:
    """等级 = 步数 ÷ 10 向上取整（0 步 = 0 级，1~10 步 = 1 级……）。"""
    return (moves + LEVEL_STEP - 1) // LEVEL_STEP


def make_id(now: Optional[float] = None) -> str:
    """题目 id：时间 + 随机后缀，例如 ``20260912-100000-7f3a``。"""
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return "%s-%04x" % (stamp, random.randrange(0x10000))


# --------------------------------------------------------------------------
# 出题
# --------------------------------------------------------------------------


def generate(
    difficulty: int = 5,
    *,
    seed: Optional[int] = None,
    puzzle_id: Optional[str] = None,
    walk_steps: Optional[int] = None,
) -> Tuple[List[List[int]], Dict[str, object]]:
    """出一道题，返回 ``(局面, 元信息)``。**不写文件**（落盘交给调用方）。

    ``difficulty`` 就是目标等级（十步一档）：走 ``difficulty × 10`` 步，
    出来的解正好也是这个长度，于是等级就是它。也可以直接给 ``walk_steps`` 覆盖。

    出题方式是 **walk_gen 的引导式走法**，反走即解 —— 不需要求解器，也不会失败。
    """
    steps = int(walk_steps) if walk_steps is not None else max(1, int(difficulty) * LEVEL_STEP)
    used_seed = seed if seed is not None else random.randrange(1 << 30)
    state, raw, solution = walk_gen.walk(used_seed, steps)
    meta: Dict[str, object] = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "created_by": CREATED_BY,
        "solution_by": "walk",
        "id": puzzle_id or make_id(),
        "tubes": TUBES,
        "colors": COLOR_LETTERS[:COLORS],
        "capacity": CAPACITY,
        "balls_per_color": BALLS_PER_COLOR,
        "level": level_of(len(solution)),
        "moves": len(solution),
        "seed": used_seed,
        # steps = 走的目标步数（复现要 seed + steps 两个；实际走出的原始步数会略多，
        # 因为「同球连搬」的那些被合并掉了 —— 解的长度看 moves）
        "steps": steps,
        "generator": GENERATOR,
        "solution": format_moves(solution),
    }
    return [list(t) for t in state], meta


# --------------------------------------------------------------------------
# 渲染 / 解析（docs/requirement.md §5）
# --------------------------------------------------------------------------


def _letter(color: int) -> str:
    if color == EMPTY:
        return EMPTY_LETTER
    return COLOR_LETTERS[color - 1]


def render_board(
    matrix: Sequence[Sequence[int]],
    meta: Optional[Dict[str, object]] = None,
) -> str:
    """把局面渲染成文本。

    给了 ``meta`` 就出**完整三段式**（就是题库文件的内容）；
    不给就只出网格段（调试用）。
    """
    lines: List[str] = []
    if meta is not None:
        lines.append("# colors: " + " ".join(COLOR_NAMES[:COLORS]))
        lines.append("")
        for k in META_ORDER:
            if k in meta:
                lines.append("%s=%s" % (k, meta[k]))
        lines.append("")

    for p in range(len(matrix[0])):
        lines.append(" ".join(_letter(matrix[t][p]) for t in range(len(matrix))))
    return "\n".join(lines)


def print_board(matrix: Sequence[Sequence[int]], meta: Optional[Dict[str, object]] = None) -> None:
    print(render_board(matrix, meta))


_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_INT_KEYS = ("tubes", "capacity", "balls_per_color", "level", "moves", "seed", "steps")
_TEXT_KEYS = ("id", "colors", "solution", "generator", "created_by", "created_at",
              "solution_by")
_REQUIRED_KEYS = ("id", "tubes", "colors", "capacity", "balls_per_color", "level", "moves")
# 出身字段：**可选**（老文件没有也照样能读），有就校验格式，但不限定取值
_TAG_RE = re.compile(r"^[A-Za-z0-9_@.+-]{1,64}$")


def parse_board(text: str) -> Tuple[List[List[int]], Dict[str, object]]:
    """解析题目文本，返回 ``(局面, 元信息)``。

    规则见 docs/requirement.md §5.5：忽略所有 ``#`` 开头的行与空行；
    元信息按键名取值、不依赖顺序；网格按任意空白切分。
    读进来就校验，对不上直接报错。
    """
    raw: Dict[str, str] = {}
    rows: List[List[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _KEY_RE.match(line)
        if m:
            raw[m.group(1)] = m.group(2).strip()
        else:
            rows.append(line.split())

    for k in _REQUIRED_KEYS:
        if k not in raw:
            raise ValueError("题目文件缺少必需字段 %s=" % k)

    meta: Dict[str, object] = {}
    for k, v in raw.items():
        if k in _INT_KEYS:
            try:
                meta[k] = int(v)
            except ValueError:
                raise ValueError("字段 %s 不是整数：%r" % (k, v))
        elif k in _TEXT_KEYS:
            meta[k] = v
        else:
            meta[k] = v

    tubes = int(meta["tubes"])            # type: ignore[arg-type]
    capacity = int(meta["capacity"])      # type: ignore[arg-type]
    per_color = int(meta["balls_per_color"])  # type: ignore[arg-type]
    letters = str(meta["colors"])

    if len(rows) != capacity:
        raise ValueError("网格行数 %d != capacity %d" % (len(rows), capacity))
    for r, row in enumerate(rows):
        if len(row) != tubes:
            raise ValueError("第 %d 行有 %d 列，!= tubes %d" % (r + 1, len(row), tubes))

    known = set(COLOR_LETTERS[:COLORS])
    matrix = [[EMPTY] * capacity for _ in range(tubes)]
    used = set()
    for p, row in enumerate(rows):
        for t, cell in enumerate(row):
            if cell == EMPTY_LETTER:
                matrix[t][p] = EMPTY
            elif cell in known:
                matrix[t][p] = COLOR_LETTERS.index(cell) + 1
                used.add(cell)
            else:
                raise ValueError("第 %d 行第 %d 列出现未知记号 %r" % (p + 1, t + 1, cell))

    # 空位必须是每根柱子的前缀（位置 0 是最顶端那一格）
    for t in range(tubes):
        col = matrix[t]
        seen_ball = False
        for v in col:
            if v != EMPTY:
                seen_ball = True
            elif seen_ball:
                raise ValueError("第 %d 根柱子的空位不在顶端（前半段出现了空位）" % (t + 1))

    if used != set(letters):
        raise ValueError("colors=%s 与网格里实际用到的颜色 %s 对不上"
                         % (letters, "".join(sorted(used))))

    for c in range(1, COLORS + 1):
        letter = COLOR_LETTERS[c - 1]
        if letter not in used:
            continue
        n = sum(col.count(c) for col in matrix)
        if n != per_color:
            raise ValueError("颜色 %s 有 %d 颗，!= balls_per_color %d" % (letter, n, per_color))

    moves = int(meta["moves"])            # type: ignore[arg-type]
    level = int(meta["level"])            # type: ignore[arg-type]
    if level != level_of(moves):
        raise ValueError("level=%d 与 moves=%d 对不上（应为 %d）"
                         % (level, moves, level_of(moves)))
    if "solution" in meta:
        try:
            sol = parse_moves(str(meta["solution"]))
        except ValueError as exc:
            raise ValueError("solution 解析失败：%s" % exc)
        if len(sol) != moves:
            raise ValueError("solution 有 %d 步，!= moves=%d" % (len(sol), moves))
        if not verify(matrix, sol):
            raise ValueError("solution 套到这道题上解不开（文件被改坏了？）")
    for k in ("generator", "created_by", "solution_by"):
        if k in meta and not _TAG_RE.match(str(meta[k])):
            raise ValueError(
                "%s 的格式不对：%r（只允许字母数字和 _ @ . + -，最长 64）" % (k, meta[k])
            )
    if "created_at" in meta:
        stamp = str(meta["created_at"])
        if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", stamp):
            raise ValueError(
                "created_at 的格式不对：%r（要写成 2026-09-14 19:07:00）" % stamp
            )
    return matrix, meta


def load_board(path) -> Tuple[List[List[int]], Dict[str, object]]:
    """读一道题；顺带校验 id 与文件名一致。"""
    p = Path(path)
    matrix, meta = parse_board(p.read_text(encoding="utf-8"))
    if str(meta["id"]) != p.stem:
        raise ValueError("id=%s 与文件名 %s 对不上" % (meta["id"], p.stem))
    return matrix, meta


# --------------------------------------------------------------------------
# 题库索引（puzzles/index.csv）
# --------------------------------------------------------------------------


# 题库（puzzles/）的「唯一真相」是**文件本身**：目录名就是等级，文件名就是 id。
# 2026-09-14 之前这里读的是 index.csv，结果「save=true 新存的题不会出现在接口里」——
# 台账和文件打架。现在全部改成扫目录（实测 409 道全扫一遍约 20 毫秒）。


def read_head(path) -> Dict[str, str]:
    """只读题目文件的元信息段（读到网格就停），比整份读进来快。"""
    meta: Dict[str, str] = {}
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:          # 到网格了
                break
            k, v = s.split("=", 1)
            meta[k] = v
    return meta


def _level_dirs(root) -> List[Path]:
    """题库根目录下形如 ``1/ 2/ 3/`` 的等级目录，按等级排序。"""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted((d for d in root.iterdir() if d.is_dir() and d.name.isdigit()),
                  key=lambda d: int(d.name))


def list_levels(root=PUZZLE_DIR) -> List[Dict[str, int]]:
    """题库里每个等级各有多少道题 —— 直接数目录里的题目文件。"""
    return [{"level": int(d.name), "count": len(list(d.glob("*.txt")))}
            for d in _level_dirs(root) if list(d.glob("*.txt"))]


def list_puzzles(root=PUZZLE_DIR, level: Optional[int] = None) -> List[Dict[str, object]]:
    """列出题目（可按等级筛）—— 扫目录 + 只读每道题的文件头。"""
    out: List[Dict[str, object]] = []
    for d in _level_dirs(root):
        if level is not None and int(d.name) != level:
            continue
        for f in sorted(d.glob("*.txt")):
            head = read_head(f)
            out.append({
                "id": f.stem,
                "level": int(head.get("level", d.name)),
                "moves": int(head.get("moves") or 0),
                "series": int(head.get("steps") or 0),
                "seed": int(head.get("seed") or 0),
                "path": str(f),
            })
    return out


def find_puzzle_path(root, puzzle_id: str) -> Optional[Path]:
    """按 id 找题目文件：在等级目录里找同名文件。"""
    hits = sorted(Path(root).glob("*/%s.txt" % puzzle_id))
    return hits[0] if hits else None


def save_board(path, matrix: Sequence[Sequence[int]], meta: Dict[str, object],
               overwrite: bool = False) -> Path:
    """把题目写进文件。

    ``path`` 是**题库根目录**（已存在，或者没写扩展名，例如 ``puzzles``）时，
    按等级分文件夹：``<root>/<level>/<id>.txt``；
    否则就当是完整的文件路径。
    """
    p = Path(path)
    if p.is_dir() or not p.suffix:
        p = p / str(meta.get("level", 0)) / ("%s.txt" % meta["id"])
    if p.exists() and not overwrite:
        raise FileExistsError("文件已存在，不覆盖：%s" % p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_board(matrix, meta) + "\n", encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="BeadMatch 出题器")
    p.add_argument("--level", type=int, default=5,
                   help="难度等级（默认 5）：走 level × 10 步，解的长度正好是这个数")
    p.add_argument("--seed", type=int, default=None, help="随机种子（同 seed + 同 steps 能复现同一道题）")
    p.add_argument("--steps", type=int, default=None,
                   help="直接指定走多少步（不给就按 --level × 10 算）")
    p.add_argument("--out", default=str(PUZZLE_DIR), help="题库目录（默认 %s）" % PUZZLE_DIR)
    p.add_argument("--print-only", action="store_true", help="只打印，不写文件")
    p.add_argument("--show", metavar="FILE", help="读一道题并打印")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.show:
        matrix, meta = load_board(args.show)
        print_board(matrix, meta)
        print("# 等级 %s / 步数 %s / 柱子 %s / 颜色 %s"
              % (meta["level"], meta["moves"], meta["tubes"], meta["colors"]), file=sys.stderr)
        return 0

    t0 = time.time()
    matrix, meta = generate(args.level, seed=args.seed, walk_steps=args.steps)
    dt = time.time() - t0

    if not args.print_only:
        path = save_board(Path(args.out), matrix, meta)
    else:
        path = None

    print_board(matrix, meta)
    print("# id=%s 等级=%s 步数=%s 乱走=%s 步 用时=%.2fs%s"
          % (meta["id"], meta["level"], meta["moves"], meta["steps"], dt,
             "" if path is None else "  → %s" % path), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
