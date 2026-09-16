"""6 种颜色的唯一真相：字母 / 中文 / emoji / 英文名。

写死就这 6 个（跟串珠、推理、记忆同一套实物）：``Y`` 黄、``G`` 绿、``R`` 红、``P`` 紫、``B`` 蓝、``O`` 橙。

卡片里三种写法都认 —— ``R`` / ``红`` / ``🔴``；连写也行（``RRBB``、"红红蓝蓝"、"🔴🔴🔵🔵"）。
**写出去一律用字母**，这样题目文件永远是一种口径。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

# 颜色编号就是这里的下标（跟其它游戏同一套）
LETTERS: Tuple[str, ...] = ("Y", "G", "R", "P", "B", "O")

CN: Dict[str, str] = {"Y": "黄", "G": "绿", "R": "红", "P": "紫", "B": "蓝", "O": "橙"}
CN_FULL: Dict[str, str] = {"Y": "黄色", "G": "绿色", "R": "红色",
                           "P": "紫色", "B": "蓝色", "O": "橙色"}
EN: Dict[str, str] = {"Y": "Yellow", "G": "Green", "R": "Red",
                      "P": "Purple", "B": "Blue", "O": "Orange"}
EMOJI: Dict[str, str] = {"Y": "🟡", "G": "🟢", "R": "🔴",
                         "P": "🟣", "B": "🔵", "O": "🟠"}

# 每一种被接受的写法 → 字母（键统一小写，查的时候把 token 转小写）
_ALIASES: Dict[str, str] = {}
for _letter in LETTERS:
    for _name in (_letter, CN[_letter], CN_FULL[_letter], EN[_letter], EMOJI[_letter]):
        _ALIASES[_name.lower()] = _letter
_ALIASES["桔"] = "O"          # 橙的另一种叫法
_ALIASES["桔色"] = "O"

# 连写时先试长的写法（"黄色" 要赢过 "黄"）
_RUN_KEYS: List[str] = sorted(_ALIASES, key=len, reverse=True)

_SPLIT_RE = re.compile(r"[\s,，、/|]+")


def _split_run(text: str) -> Optional[List[str]]:
    """把连写的一串拆成字母；拆不动返回 ``None``。"""
    out: List[str] = []
    i = 0
    while i < len(text):
        for key in _RUN_KEYS:
            if text.startswith(key, i):
                out.append(_ALIASES[key])
                i += len(key)
                break
        else:
            return None
    return out


def to_letter(token: str) -> str:
    """一个 token → 一个字母。认不出来就报错。"""
    key = str(token).strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    run = _split_run(key)
    if run and len(run) == 1:
        return run[0]
    raise ValueError("认不出的颜色：%r（能用的是 Y/G/R/P/B/O、黄绿红紫蓝橙、🟡🟢🔴🟣🔵🟠）"
                     % token)


def to_letters(text) -> Tuple[str, ...]:
    """一串写法 → 一串字母（重复几次就是几颗）。

    分隔用空格/逗号都行（``"R R B B B"``），也可以连写（``"RRBBB"``、``"红红蓝蓝蓝"``、
    ``"🔴🔴🔵🔵🔵"``）。列表也直接收。
    """
    if isinstance(text, (list, tuple)):
        return tuple(to_letter(t) for t in text)

    out: List[str] = []
    for token in _SPLIT_RE.split(str(text).strip()):
        if not token:
            continue
        key = token.lower()
        if key in _ALIASES:
            out.append(_ALIASES[key])
            continue
        run = _split_run(key)
        if run is None:
            raise ValueError("认不出的写法：%r" % token)
        out.extend(run)
    return tuple(out)


def format_letters(letters: Sequence[str]) -> str:
    """一串字母 → 文件里那种写法：``("R","R","B")`` → ``"R R B"``。"""
    return " ".join(str(x).upper() for x in letters)


def format_seq(seq: Sequence[str]) -> str:
    """一串字母 → 给人看的 emoji：``"R R B"`` → ``"🔴 🔴 🔵"``。"""
    return " ".join(EMOJI.get(str(x).upper(), str(x)) for x in seq)


def counts_of(letters: Sequence[str]) -> List[Dict[str, object]]:
    """数一数每种颜色各几个（就是界面上的「材料清单」）。

    排序：**多的排前面**，一样多就按固定颜色顺序。
    """
    tally: Dict[str, int] = {}
    for letter in letters:
        key = str(letter).upper()
        tally[key] = tally.get(key, 0) + 1
    order = sorted(tally, key=lambda c: (-tally[c], LETTERS.index(c)))
    return [{"color": c, "name": CN_FULL[c], "cn": CN[c], "en": EN[c],
             "emoji": EMOJI[c], "count": tally[c]}
            for c in order]


def format_materials(letters: Sequence[str]) -> str:
    """材料清单 → 一行中文：``"🔴×3 + 🔵×4"``。"""
    return " + ".join("%s×%d" % (row["emoji"], row["count"]) for row in counts_of(letters))
