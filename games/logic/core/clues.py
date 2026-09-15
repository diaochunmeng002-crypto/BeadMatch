"""logic 游戏的「线索」：记号、解析、判定、求解。

一条线索一行，用最少的记号写清「谁在哪儿」「谁在谁前面」：

    R@1     R 在第 1 位（位置从 1 起，跟题目里的"第一个"对齐）
    B>R     B 在 R 的后面（右边）
    P<R     P 在 R 的前面（左边）
    G~B     G 和 B 挨着（左边右边都算）
    G!~R    G 和 R 不挨着
    G~~B    G 和 B 中间隔着一颗（距离 2）
    G~2~B   G 和 B 中间隔着两颗（距离 3）—— 隔着几颗就写几
    R..O..G R 在 O 和 G 中间（夹在它们之间，不管左右顺序）
    R@<3    R 一定在前 3 个位置里
    R@>3    R 一定在后 3 个位置里
    R!@1    R 不能在第 1 位

记号就这几个：够用、能一眼看懂；以后不够再加（加的时候顺手写进 README）。
这一层只认字母（R/B/G…），不关心字母代表什么颜色 —— 颜色表在 puzzles.py。
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Order = Tuple[str, ...]          # 从左到右的一串珠子，例如 ("R", "B", "G")

# 一行线索的全部写法：一个字母 + 一个记号 + （一个字母 或 一个位置数字）
# 注意 !~ / ~~ 要写在 ~ 前面，否则会被拆成别的
CLUE_RE = re.compile(r"^([A-Z])(!~|~~|@|>|<|~)([A-Z]|[0-9]+)$")
# "R..O..G"：中间那个在两边那两个之间
MID_RE = re.compile(r"^([A-Z])\.\.([A-Z])\.\.([A-Z])$")
# "R~2~G"：中间隔着两颗
GAP_RE = re.compile(r"^([A-Z])~([1-9][0-9]*)~([A-Z])$")
# "R@<3" / "R@>3"：一定在前/后 3 个位置里
RANGE_RE = re.compile(r"^([A-Z])@([<>])([1-9][0-9]*)$")


@dataclass(frozen=True)
class Clue:
    """一条线索。

    ``n`` 只有 ``@`` 用得上；``b`` 是"另一颗珠子"；``c`` 只有"在 B 和 C 中间"用得上。
    """

    text: str            # 原文，例如 "B>R"（出错时照原样给人看）
    a: str               # 左边的珠子
    op: str              # @ !@ > < ~ !~ ~~ mid front back
    b: str = ""          # 右边的珠子
    n: int = 0           # 位置（1 起）/ 隔着几颗 / 前几个
    c: str = ""          # "在 B 和 C 中间"里的 C


def parse_clue(text: str) -> Clue:
    """把 ``"B>R"`` / ``"R@1"`` 这类记号解析成 ``Clue``。写错了就报错。"""
    s = text.strip()

    m = MID_RE.match(s)
    if m:
        left, middle, right = m.groups()
        if len({left, middle, right}) != 3:
            raise ValueError("「中间」那条线索要用三颗**不同**的珠子：%r" % s)
        return Clue(s, middle, "mid", b=left, c=right)

    m = GAP_RE.match(s)
    if m:
        left, count, right = m.groups()
        if left == right:
            raise ValueError("「隔几个」要写两颗**不同**的珠子：%r" % s)
        return Clue(s, left, "~~", b=right, n=int(count))

    m = RANGE_RE.match(s)
    if m:
        letter, sign, count = m.groups()
        return Clue(s, letter, "front" if sign == "<" else "back", n=int(count))

    m = CLUE_RE.match(s)
    if not m:
        raise ValueError("线索写错了：%r（写法见 clues.py 顶部：R@1 / B>R / P<R / G~B / G!~R）" % text)
    a, op, rest = m.groups()

    if op == "@":
        if int(rest) < 1:
            raise ValueError("位置从 1 起，不能是 0：%r" % s)
        return Clue(s, a, op, n=int(rest))

    if op == "!@":
        if int(rest) < 1:
            raise ValueError("位置从 1 起，不能是 0：%r" % s)
        return Clue(s, a, op, n=int(rest))

    if rest.isdigit():
        raise ValueError("%s 的右边要写珠子字母，不是数字：%r" % (op, s))
    if rest == a:
        raise ValueError("线索两边的珠子不能是同一颗：%r" % s)
    return Clue(s, a, op, b=rest)


def parse_clues(lines: Sequence[str]) -> Tuple[Clue, ...]:
    """一行一条线索，一次解析一串。"""
    return tuple(parse_clue(line) for line in lines if line.strip())


def _positions(letter: str, order: Sequence[str]) -> List[int]:
    """这颗珠子出现的所有位置（**同色有两颗时会有两个**）。"""
    hits = [i for i, x in enumerate(order) if x == letter]
    if not hits:
        raise ValueError("线索里的 %s 不在参与者里" % letter)
    return hits


def holds(clue: Clue, order: Sequence[str]) -> bool:
    """这条线索在这条排法（从左到右）上成立吗？

    **同色有两颗时按"存在"理解**：两颗一模一样的珠子本身没法区分，所以
    "红色在蓝色前面"= 存在一颗红、一颗蓝（红在前）；"红色在第二个"= 有一颗红在第二个。
    """
    mine = _positions(clue.a, order)

    # 「不能」类：一颗都不许满足
    if clue.op == "!@":
        return all(i != clue.n - 1 for i in mine)
    if clue.op == "!~":
        theirs = _positions(clue.b, order)
        return not any(abs(i - j) == 1 for i in mine for j in theirs if i != j)

    # 「一定在前/后几个」：存在一颗落在那个范围里
    if clue.op == "front":
        return any(i < clue.n for i in mine)
    if clue.op == "back":
        return any(i >= len(order) - clue.n for i in mine)

    for i in mine:
        if clue.op == "@":
            if i == clue.n - 1:
                return True
            continue

        for j in _positions(clue.b, order):
            if i == j:
                continue
            if clue.op == "~~":
                if abs(i - j) == clue.n + 1:
                    return True
            elif clue.op == "mid":
                for k in _positions(clue.c, order):
                    if k != i and min(j, k) < i < max(j, k):
                        return True
            elif clue.op == ">" and i > j:
                return True
            elif clue.op == "<" and i < j:
                return True
            elif clue.op == "~" and abs(i - j) == 1:
                return True
    return False


def solve(
    participants: Sequence[str],
    clues: Sequence[Clue],
    limit: Optional[int] = None,
) -> List[Order]:
    """把所有排法过一遍，返回满足线索的那几种（从左到右）。

    参与者最多 6 个（6! = 720 种），全枚举是毫秒级 —— 所以不需要什么聪明算法。
    ``limit`` 给了的话，凑够这么多就停（只想判断"是不是唯一解"时用）。
    """
    for clue in clues:
        for letter in (clue.a, clue.b):
            if letter and letter not in participants:
                raise ValueError("线索 %s 里的 %s 不在参与者 %s 里"
                                 % (clue.text, letter, format_order(participants)))

    found: List[Order] = []
    seen = set()
    for order in itertools.permutations(participants):
        if order in seen:          # 同色两颗时，全排列会出重复，算一次就够
            continue
        seen.add(order)
        if all(holds(clue, order) for clue in clues):
            found.append(order)
            if limit is not None and len(found) >= limit:
                break
    return found


def notation(clue: Clue) -> str:
    """把线索写回记号：``R@1`` / ``B>R``（题目文件用中文原句，这个是给程序看的）。"""
    if clue.op == "@":
        return "%s@%d" % (clue.a, clue.n)
    if clue.op == "!@":
        return "%s!@%d" % (clue.a, clue.n)
    if clue.op == "front":
        return "%s@<%d" % (clue.a, clue.n)
    if clue.op == "back":
        return "%s@>%d" % (clue.a, clue.n)
    if clue.op == "~~":
        return ("%s~~%s" % (clue.a, clue.b) if clue.n <= 1
                else "%s~%d~%s" % (clue.a, clue.n, clue.b))
    if clue.op == "mid":
        return "%s..%s..%s" % (clue.b, clue.a, clue.c)
    return "%s%s%s" % (clue.a, clue.op, clue.b)


def format_order(order: Sequence[str]) -> str:
    """``("R", "B")`` → ``"R B"``（就是题目文件里 participants / answer 的写法）。"""
    return " ".join(order)


def parse_order(text: str) -> Order:
    """把答案解析成一串珠子。

    三种写法都认：``"R B G"``、``"RBG"``、``"R→B→G"``（最后一种是给人看的箭头版）。
    """
    parts = [p for p in re.split(r"[\s,，、>→\-]+", text.strip()) if p]
    if len(parts) == 1 and len(parts[0]) > 1:
        parts = list(parts[0])
    return tuple(parts)
