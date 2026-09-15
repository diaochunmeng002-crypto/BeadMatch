"""中文 ↔ 记号：题目文件里写的是**原句**，程序得看懂它才能校验答案。

题目是人写的，句子怎么说没准（"红色在最前面" / "红色珠子排在最前面" / "红色第一个出发"
/ "绿色珠子第一个出发" / "紫色站在队伍最后"），所以这里**不按固定句型硬套，而是抓关键信息**：

1. 句子里**第一颗**提到的珠子 = 主语；
2. 有「**最后** / **最前** / **第 N**」→ 它在第几位：

       红色在最前面。              → R@1
       红色珠子排在最前面。        → R@1
       绿色珠子第一个出发。        → G@1
       蓝色坐在船头，也就是第一个。→ B@1
       橙色最后才来。              → O@6   （最后 = 参与者的个数）
       紫色站在队伍最后。          → P@6

3. 要不然看「**X 前面 / 后面**」——谁在谁的前面（挨着 / 隔着 / 夹在中间也认）：

       蓝色珠子紧跟在红色后面。    → B>R
       紫色睡在红色后面。          → P>R
       红色坐在蓝色前面。          → R<B
       黄色和绿色挨着。            → Y~G
       黄色和绿色不挨着。          → Y!~G
       绿色和黄色中间隔一个。      → G~~Y
       橙色在红色和绿色中间。      → R..O..G

一颗珠子可以写成汉字（`红` / `红色`）、字母（`R`）、emoji（`🔴`）—— 都认。
记号写法（`R@1` / `B>R`）也照收，所以老文件不用改。

⚠️ 「**紧跟** / **紧接着**」这类"还紧挨在旁边"的说法，现在按**更宽松**的「在…后面」处理
（丢掉了"紧挨着"这点信息）。万一哪道题因此变成多解，`python -m games.logic.core.puzzles`
会直接报出来。

看不懂的句子会报错，并把原句和"认出来的珠子"一起说出来（出题人好改）。
"""

from __future__ import annotations

import re
from typing import Dict, Sequence, Tuple

from .clues import Clue, parse_clue

# 每个字母的全部写法（字母 / 汉字 / emoji 都指向同一颗珠子）
_ALIASES: Dict[str, Tuple[str, ...]] = {
    "Y": ("黄色", "黄", "Y", "y", "🟡"),
    "G": ("绿色", "绿", "G", "g", "🟢"),
    "R": ("红色", "红", "R", "r", "🔴"),
    "P": ("紫色", "紫", "P", "p", "🟣"),
    "B": ("蓝色", "蓝", "B", "b", "🔵"),
    "O": ("橙色", "橙", "桔色", "桔", "O", "o", "🟠"),
}

_LETTER_OF: Dict[str, str] = {}
for _letter, _names in _ALIASES.items():
    for _name in _names:
        _LETTER_OF[_name] = _letter

# 在**中文句子**里找珠子：只认汉字和 emoji，不认单个字母
# （不然句子里随便一个 B/O 都会被当成珠子）
_CN_NAMES = tuple(name for name in _LETTER_OF if not re.fullmatch(r"[A-Za-z]", name))
_COLOR_RE = re.compile(
    "|".join(re.escape(name) for name in sorted(_CN_NAMES, key=len, reverse=True))
)

_CN_NUMBER = {"一": 1, "两": 2, "俩": 2, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# 「第几个」：`第三个` / `第 3 位` / `第一支` / `第四个位置` 都算
_AT_RE = re.compile(r"第\s*(?P<n>[一二两俩三四五六七八九十\d]+)")
# 「中间隔着 N 个」：`隔一个` / `隔着两个` / `相隔 3 个位置`
_GAP_RE = re.compile(r"隔(?:着)?\s*(?P<n>[一二两俩三四五六七八九十\d]+)?\s*个")
# 「一定在前/后 N 个位置」
_RANGE_RE = re.compile(r"(?P<side>[前后])\s*(?P<n>[一二两俩三四五六七八九十\d]+)\s*个")


def to_letter(token: str) -> str:
    """一颗珠子的一种写法 → 字母：``红`` / ``红色`` / ``🔴`` / ``R`` → ``R``。"""
    t = token.strip()
    if not t:
        raise ValueError("这里应该是珠子，但是空的")
    if t in _LETTER_OF:
        return _LETTER_OF[t]
    # ``🔴红`` 这种 emoji 跟汉字粘在一起的也认
    for name in sorted(_LETTER_OF, key=len, reverse=True):
        if name in t:
            return _LETTER_OF[name]
    raise ValueError("不认识的珠子：%r（可以写：红 蓝 绿 黄 紫 橙，或者 Y G R P B O）" % token)


_SPLIT_RE = re.compile(r"[\s,，、>→\-—+]+")


def to_letters(text: str) -> Tuple[str, ...]:
    """一串珠子 → 一串字母：``红 蓝 绿`` / ``🔴红、🔵蓝`` / ``R→B→G`` 都行。"""
    return tuple(to_letter(t) for t in _SPLIT_RE.split(text.strip()) if t)


def _clean(text: str) -> str:
    """去掉行首的杂七杂八（emoji、空格、序号、横线），只留句子本身。"""
    s = text.strip()
    s = re.sub(r"^[\s\-*•·.、:：()（）\[\]【】\d]+", "", s)
    s = re.sub(r"^[^\u4e00-\u9fffA-Za-z]+", "", s)
    return s


def _mentions(text: str) -> Tuple[str, ...]:
    """句子里提到的珠子，按**出现顺序**（同一个只记一次）。"""
    out: list = []
    for m in _COLOR_RE.finditer(text):
        letter = _LETTER_OF[m.group(0)]
        if letter not in out:
            out.append(letter)
    return tuple(out)


def _number(token: str) -> int:
    return _CN_NUMBER.get(token, 0) or int(token)


def parse_clue_text(text: str, participants: Sequence[str]) -> Tuple[Clue, ...]:
    """把一行题目（中文原句 **或** 记号 ``R@1``）解析成若干条 ``Clue``。

    ``Clue.text`` 存的是**原句一字不改**（这样写回文件时不会变形）；
    ``a / op / b / n`` 才是给程序判定用的。

    **一行可能出多条**：`绿色紧挨着蓝色，站在蓝色前面。` 一句话说了两件事
    （挨着 + 谁在前），所以会出 ``G~B`` 和 ``G<B`` 两条。
    """
    raw = text.strip()
    s = _clean(raw)
    if not s:
        raise ValueError("空线索")

    # 1) 记号写法（R@1 / B>R）—— 先试它，不然 "B>R" 会被当成"提到了 B 和 R"
    try:
        clue = parse_clue(s)
    except ValueError:
        clue = None
    if clue is not None:
        return (Clue(raw, clue.a, clue.op, b=clue.b, n=clue.n),)

    # 2) 中文句子：先认出提到了哪些珠子，**第一颗是主语**
    mentions = _mentions(s)
    if not mentions:
        raise ValueError("这句话里没看到珠子的颜色（红 蓝 绿 黄 紫 橙）")
    a = mentions[0]

    # 3) 「不能」+ 位置
    if "不能" in s or "不在" in s or "不许" in s:
        n = None
        if "最前" in s:
            n = 1
        elif "最后" in s:
            n = len(participants)
        else:
            m = _AT_RE.search(s)
            if m:
                n = _number(m.group("n"))
        if n is not None:
            return (Clue(raw, a, "!@", n=n),)

    # 3.4) 「一定在前/后 N 个位置」
    m = _RANGE_RE.search(s)
    if m and "位置" in s:
        n = _number(m.group("n"))
        return (Clue(raw, a, "front" if m.group("side") == "前" else "back", n=n),)

    # 3.5) 挨着 / 不挨着（"不能紧挨着" 算不挨着）
    apart = ("不挨" in s or "不靠" in s or "不能挨" in s or "不能紧挨" in s
             or "不能靠" in s)
    if apart:
        b = _need_second(mentions, s)
        out = [Clue(raw, a, "!~", b=b)]
        if "前" in s:
            out.append(Clue(raw, a, "<", b=b))
        elif "后" in s:
            out.append(Clue(raw, a, ">", b=b))
        return tuple(out)
    if "挨" in s or "靠" in s:          # 挨着 / 挨在一起 / 紧挨着
        if len(mentions) >= 2:
            b = mentions[1]
        elif any(word in s for word in ("两颗", "两个", "两粒", "两颗色")):
            b = a                     # 「两颗蓝色挨着」= 同色的那两颗挨着
        else:
            b = _need_second(mentions, s)
        out = [Clue(raw, a, "~", b=b)]
        # 同一句里往往还带了先后："…，站在蓝色前面"
        if b != a and "前" in s:
            out.append(Clue(raw, a, "<", b=b))
        elif b != a and "后" in s:
            out.append(Clue(raw, a, ">", b=b))
        return tuple(out)

    # 3.6) 中间隔着几个：默认一个
    if "隔" in s and len(mentions) >= 2:
        m = _GAP_RE.search(s)
        n = _number(m.group("n")) if (m and m.group("n")) else 1
        return (Clue(raw, a, "~~", b=mentions[1], n=n),)
    if "中间" in s and len(mentions) >= 3:
        return (Clue(raw, a, "mid", b=mentions[1], c=mentions[2]),)

    # 4) 在第几位：最后 / 最前 / 第 N
    if "最后" in s:
        return (Clue(raw, a, "@", n=len(participants)),)
    if "最前" in s:
        return (Clue(raw, a, "@", n=1),)
    m = _AT_RE.search(s)
    if m:
        return (Clue(raw, a, "@", n=_number(m.group("n"))),)

    # 5) 谁在谁前面 / 后面
    if len(mentions) >= 2:
        if "不能" in s or "不在" in s or "不许" in s:
            raise ValueError("带「不能」的关系句现在读不了（只支持「不能排在第 N 位」"
                             "和「不能紧挨着」）：%s" % raw)
        b = mentions[1]
        if "前" in s:
            return (Clue(raw, a, "<", b=b),)
        if "后" in s:
            return (Clue(raw, a, ">", b=b),)

    raise ValueError("看不懂这句话（认出来的珠子：%s）。要么换个说法，"
                     "要么用记号写法（R@1 表示第一个、B>R 表示 B 在 R 后面）"
                     % " ".join(mentions))


def _need_second(mentions: Sequence[str], text: str) -> str:
    if len(mentions) < 2:
        raise ValueError("这句话要在两颗珠子之间比较，但只认出一颗：%s" % text)
    return mentions[1]
