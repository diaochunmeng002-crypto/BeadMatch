"""logic 的题目文件：读写、校验、扫题库。

格式：**注释区 + 元信息区 + 正文区（题目原文）**。

    # colors: Yellow Green Red Purple Blue Orange

    created_at=2026-09-15 21:07:00
    created_by=manual
    solution_by=manual
    id=20260915-210700-b42e
    level=1
    participants=红 蓝 绿 黄 紫 橙
    answer=红 蓝 绿 黄 橙 紫

    🔴 红色在最前面。
    🟣 紫色在最后面。
    🔵 蓝色在红色后面。
    🟢 绿色在蓝色后面。
    🟡 黄色在绿色后面。

- **注释区**：``#`` 开头的行，给人看的，解析时整段忽略。
- **元信息区**：``key=value``，键名小写、不依赖顺序（前三行固定
  ``created_at`` / ``created_by`` / ``solution_by``）。
- **正文区**：**题目原文，一行一条，一字不改** —— 就是给孩子看的那几句。

| 字段 | 说明 |
| --- | --- |
| ``created_at`` | 什么时候生成的（正文第一行） |
| ``created_by`` | 谁出的（正文第二行）：``manual`` = 人给的题 |
| ``solution_by`` | 这条解是谁给的（正文第三行） |
| ``id`` | 时间 + 随机后缀；文件名就是它，生成后不变 |
| ``level`` | 难度等级（现在由出题人写） |
| ``participants`` | 参与珠子：``红 蓝 绿 黄 紫 橙`` |
| ``answer`` | 答案：从左到右的顺序，写法跟 ``participants`` 一样 |

正文那几行程序要看得懂才谈得上校验，翻译在 chinese.py：``红色在最前面。`` → ``R@1``、
``蓝色在红色后面。`` → ``B>R``。也接受**记号写法**（``R@1``），两种混着写都行 ——
所以以前写的题不用改。一颗珠子也可以写成 ``R`` 或 ``🔴``。

读进来就校验，对不上直接报错（不能默默读进来）：珠子合法且不重复、``answer`` 是参与者的一个排列、
**每条线索都看得懂**。

**``answer`` 不满足线索不算错**（只在"检查题库"里提示一句）：题目的真相是线索，答案只是给
"看答案"用的，游戏判定也是按线索走的 —— 所以答案跟线索打架不该让整道题读不进来。

``level`` 现在由出题人写（题目的难易出题人最清楚），口径等题目多了再议。

用法：

    python -m games.logic.core.puzzles                 # 检查本游戏题库里所有题
    python -m games.logic.core.puzzles --show <文件>    # 打印一道题（附带记号）
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .chinese import parse_clue_text, to_letters
from .clues import Clue, Order, format_order, holds, notation, solve

# 跟串珠用同一套（写死，不许改）：1=Y 黄 2=G 绿 3=R 红 4=P 紫 5=B 蓝 6=O 橙
COLOR_NAMES = ("Yellow", "Green", "Red", "Purple", "Blue", "Orange")
COLOR_LETTERS = "YGRPBO"
COLOR_CN = {"Y": "黄", "G": "绿", "R": "红", "P": "紫", "B": "蓝", "O": "橙"}

# 元信息区的输出顺序（正文前三行固定是 时间 / 谁出的 / 解是谁给的）
META_ORDER = ("created_at", "created_by", "solution_by", "id", "title",
              "level", "participants", "answer")
REQUIRED_KEYS = ("id", "participants", "level", "answer")
# 老文件里还有 beads / clues（都能从别处算出来），读得进来，只是不再往新文件里写
_INT_KEYS = ("beads", "level", "clues")
_TAG_RE = re.compile(r"^[A-Za-z0-9_@.+-]{1,64}$")
_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")

# 题库目录（一题一文件，文件名 = <id>.txt）
PUZZLE_DIR = Path(__file__).resolve().parent.parent / "puzzles"


@dataclass(frozen=True)
class Puzzle:
    """一道题：参与者、线索、答案。元信息（id / level / …）单独放在 ``meta`` 里。"""

    participants: Tuple[str, ...]
    clues: Tuple[Clue, ...]
    answer: Order


# --------------------------------------------------------------------------
# 出题人用的小工具
# --------------------------------------------------------------------------


def make_id(now: Optional[float] = None) -> str:
    """题目 id：时间 + 随机后缀，例如 ``20260915-210400-3f7a``。"""
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return "%s-%04x" % (stamp, random.randrange(0x10000))


def make_meta(
    puzzle: Puzzle,
    *,
    level: int = 1,
    puzzle_id: Optional[str] = None,
    created_by: str = "manual",
    solution_by: str = "manual",
) -> Dict[str, object]:
    """凑一份元信息（写文件时用）。``level`` 由出题人给，默认 1 级。"""
    return {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "created_by": created_by,
        "solution_by": solution_by,
        "id": puzzle_id or make_id(),
        "participants": format_order(puzzle.participants),
        "level": level,
        "answer": format_order(puzzle.answer),
    }


# --------------------------------------------------------------------------
# 渲染 / 解析
# --------------------------------------------------------------------------


def render_puzzle(puzzle: Puzzle, meta: Optional[Dict[str, object]] = None) -> str:
    """把一道题渲染成文本。给了 ``meta`` 就出完整三段式（就是文件内容）。"""
    lines: List[str] = []
    if meta is not None:
        lines.append("# colors: " + " ".join(COLOR_NAMES))
        lines.append("")
        for key in META_ORDER:
            if key in meta:
                lines.append("%s=%s" % (key, meta[key]))
        lines.append("")
    lines.extend(clue.text for clue in puzzle.clues)
    return "\n".join(lines)


def print_puzzle(puzzle: Puzzle, meta: Optional[Dict[str, object]] = None) -> None:
    print(render_puzzle(puzzle, meta))


def parse_puzzle(text: str) -> Tuple[Puzzle, Dict[str, object]]:
    """解析题目文本，返回 ``(题目, 元信息)``。读进来就校验，对不上直接报错。"""
    raw: Dict[str, str] = {}
    clue_lines: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _KEY_RE.match(s)
        if m:
            raw[m.group(1)] = m.group(2).strip()
        else:
            clue_lines.append(s)

    for key in REQUIRED_KEYS:
        if key not in raw:
            raise ValueError("题目文件缺少必需字段 %s=" % key)

    meta: Dict[str, object] = {}
    for key, value in raw.items():
        if key in _INT_KEYS:
            try:
                meta[key] = int(value)
            except ValueError:
                raise ValueError("字段 %s 不是整数：%r" % (key, value))
        else:
            meta[key] = value

    try:
        participants = to_letters(str(meta["participants"]))
    except ValueError as exc:
        raise ValueError("participants 读不了：%s" % exc)
    if not participants:
        raise ValueError("participants 是空的")
    if "beads" in meta and int(meta["beads"]) != len(participants):
        raise ValueError("beads=%s 与 participants 的个数 %d 对不上"
                         % (meta["beads"], len(participants)))

    parsed: List[Clue] = []
    for line in clue_lines:
        try:
            parsed.extend(parse_clue_text(line, participants))
        except ValueError as exc:
            raise ValueError("看不懂这条线索：%s\n    原因：%s" % (line, exc))
    clues = tuple(parsed)
    if "clues" in meta and int(meta["clues"]) != len(clues):
        raise ValueError("clues=%s 与实际的 %d 条线索对不上" % (meta["clues"], len(clues)))
    meta["clues"] = len(clues)

    for clue in clues:
        for letter in (clue.a, clue.b):
            if letter and letter not in participants:
                raise ValueError("线索 %s 里的 %s 不在参与者里（%s）"
                                 % (clue.text, letter, meta["participants"]))
        if clue.op == "@" and clue.n > len(participants):
            raise ValueError("线索 %s 的位置超出了珠子个数 %d"
                             % (clue.text, len(participants)))

    try:
        answer = to_letters(str(meta["answer"]))
    except ValueError as exc:
        raise ValueError("answer 读不了：%s" % exc)
    if sorted(answer) != sorted(participants):
        raise ValueError("answer 不是 participants 的一个排列：%s vs %s"
                         % (meta["answer"], meta["participants"]))
    # 答案跟线索对不上**不报错**（见模块顶部说明）：检查题库时会提示一句

    for key in ("generator", "created_by", "solution_by"):
        if key in meta and not _TAG_RE.match(str(meta[key])):
            raise ValueError("%s 的格式不对：%r（只允许字母数字和 _ @ . + -，最长 64）"
                             % (key, meta[key]))
    if "created_at" in meta and not _STAMP_RE.match(str(meta["created_at"])):
        raise ValueError("created_at 的格式不对：%r（要写成 2026-09-15 21:04:00）"
                         % meta["created_at"])

    return Puzzle(participants, clues, answer), meta


def load_puzzle(path) -> Tuple[Puzzle, Dict[str, object]]:
    """读一道题；顺带校验 id 与文件名一致。"""
    p = Path(path)
    puzzle, meta = parse_puzzle(p.read_text(encoding="utf-8"))
    if str(meta["id"]) != p.stem:
        raise ValueError("id=%s 与文件名 %s 对不上" % (meta["id"], p.stem))
    return puzzle, meta


def answer_mismatch(puzzle: Puzzle) -> List[Clue]:
    """答案满足不了的那几条线索（正常是空的；不空只是"提示"，不是错误）。"""
    return [clue for clue in puzzle.clues if not holds(clue, puzzle.answer)]


def save_puzzle(path, puzzle: Puzzle, meta: Dict[str, object],
                overwrite: bool = False) -> Path:
    """写题目文件。

    ``path`` 是**题库根目录**（已存在，或者没写扩展名，例如 ``puzzles``）时，
    按等级分文件夹：``<root>/<level>/<id>.txt``；否则就当是完整的文件路径。
    """
    p = Path(path)
    if p.is_dir() or not p.suffix:
        p = p / str(meta.get("level", 1)) / ("%s.txt" % meta["id"])
    if p.exists() and not overwrite:
        raise FileExistsError("文件已存在，不覆盖：%s" % p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_puzzle(puzzle, meta) + "\n", encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# 给人看的读法（界面/家长用）
# --------------------------------------------------------------------------

_CN_NUM = "零一二三四五六七八九十"


def _cn_number(n: int) -> str:
    if n <= 10:
        return _CN_NUM[n]
    if n < 20:
        return "十" + _CN_NUM[n - 10]
    return "%d" % n


def describe(clue: Clue) -> str:
    """把记号读成一句中文：``R@1`` → ``红色在第一个。``"""
    a = "%s色" % COLOR_CN.get(clue.a, clue.a)
    b = "%s色" % COLOR_CN.get(clue.b, clue.b)
    if clue.op == "@":
        return "%s在第%s个。" % (a, _cn_number(clue.n))
    if clue.op == ">":
        return "%s在%s后面。" % (a, b)
    if clue.op == "<":
        return "%s在%s前面。" % (a, b)
    if clue.op == "~":
        return "%s和%s挨着。" % (a, b)
    if clue.op == "!~":
        return "%s和%s不挨着。" % (a, b)
    if clue.op == "~~":
        return "%s和%s中间隔一个。" % (a, b)
    if clue.op == "mid":
        return "%s在%s和%s中间。" % (a, b, "%s色" % COLOR_CN.get(clue.c, clue.c))
    return clue.text


# --------------------------------------------------------------------------
# 题库索引（目录就是索引：等级看目录名、id 看文件名）
# --------------------------------------------------------------------------


def read_head(path) -> Dict[str, str]:
    """只读题目文件的元信息段（读到线索区就停）。"""
    meta: Dict[str, str] = {}
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:          # 到线索区了
                break
            key, value = s.split("=", 1)
            meta[key] = value
    return meta


def _level_dirs(root) -> List[Path]:
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted((d for d in root.iterdir() if d.is_dir() and d.name.isdigit()),
                  key=lambda d: int(d.name))


def list_levels(root=PUZZLE_DIR) -> List[Dict[str, int]]:
    """题库里每个等级各有多少道题。"""
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
                "level": int(head.get("level") or d.name),
                "beads": int(head.get("beads") or 0),
                "clues": int(head.get("clues") or 0),
                "path": str(f),
            })
    return out


def find_puzzle_path(root, puzzle_id: str) -> Optional[Path]:
    """按 id 找题目文件：在等级目录里找同名文件。"""
    hits = sorted(Path(root).glob("*/%s.txt" % puzzle_id))
    return hits[0] if hits else None


# --------------------------------------------------------------------------
# 检查题库
# --------------------------------------------------------------------------


def check_puzzle(path) -> Tuple[Puzzle, Dict[str, object], List[Order]]:
    """读一道题并解一遍，返回 ``(题目, 元信息, 所有满足线索的排法)``。"""
    puzzle, meta = load_puzzle(path)
    return puzzle, meta, solve(puzzle.participants, puzzle.clues)


def check_dir(root=PUZZLE_DIR, *, stream=sys.stdout) -> int:
    """扫一遍题库：报「读得进来吗 / 解有几个 / 答案跟线索对不对」。

    只有**读不进来**才算问题（返回值就是问题数）。多解、答案跟线索对不上，都只提示一句。
    """
    root = Path(root)
    files = sorted(root.glob("*/*.txt"))
    if not files:
        print("题库是空的：%s" % root, file=stream)
        return 0

    problems = 0
    warned = 0
    for path in files:
        rel = "%s/%s" % (path.parent.name, path.name)
        try:
            puzzle, meta, solutions = check_puzzle(path)
        except ValueError as exc:
            problems += 1
            print("× %s —— %s" % (rel, exc), file=stream)
            continue
        title = str(meta.get("title") or "").strip()
        head = "%slevel=%s 珠子=%s 线索=%s" % (
            (title + "  ") if title else "", meta.get("level"),
            len(puzzle.participants), len(puzzle.clues))
        if len(solutions) == 1:
            print("√ %s  %s  解=1（%s）" % (rel, head, format_order(solutions[0])), file=stream)
        else:
            samples = "、".join(format_order(s) for s in solutions[:3])
            more = "…" if len(solutions) > 3 else ""
            print("√ %s  %s  解=%d（%s%s）"
                  % (rel, head, len(solutions), samples, more), file=stream)

        bad = answer_mismatch(puzzle)
        if bad:
            warned += 1
            print("   ！你写的答案（%s）不满足：%s"
                  % (meta.get("answer"), "；".join(c.text for c in bad)), file=stream)

    print("", file=stream)
    print("共 %d 道题：读不进来 %d 道，答案跟线索对不上 %d 道。"
          % (len(files), problems, warned), file=stream)
    return problems


def _safe_console() -> None:
    """Windows 控制台是 GBK 时，打印 emoji 会直接崩 —— 让它换成 ? 而不是崩。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _safe_console()
    p = argparse.ArgumentParser(description="logic 题库：检查 / 打印")
    p.add_argument("--dir", default=str(PUZZLE_DIR), help="题库根目录（默认本游戏的 puzzles/）")
    p.add_argument("--show", metavar="FILE", help="打印一道题（附带程序读到的记号）")
    args = p.parse_args(argv)

    if args.show:
        puzzle, meta = load_puzzle(args.show)
        print(render_puzzle(puzzle, meta))
        print("")
        print("# 程序读到的是：参与者 %s ；答案 %s"
              % (format_order(puzzle.participants), format_order(puzzle.answer)))
        for clue in puzzle.clues:
            print("# %-5s %s" % (notation(clue), clue.text))
        return 0

    return 1 if check_dir(Path(args.dir)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
