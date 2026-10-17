"""珠子颜色：跟另外几个游戏共用同一套（6 色，字母 + 中文名 + 颜色值）。

实物那套珠子就是这 6 色（每色 10 颗）—— 题目里用到的颜色必须在里面，
屏幕上显示的也必须是这 6 色，孩子才能跟手上的珠子对上。
"""

from __future__ import annotations

LETTERS = "YGRPBO"
NAMES = ("黄", "绿", "红", "紫", "蓝", "橙")
CSS = ("#f2c231", "#4caf50", "#e5484d", "#9b59d0", "#3b82f6", "#f2811d")

PER_COLOR = 10          # 每种颜色手上有 10 颗（题目 + 答案加起来不能超过）
TOTAL = len(LETTERS) * PER_COLOR


def name(letter: str) -> str:
    """颜色字母 → 中文名（不认识就原样返回）。"""
    letter = (letter or "").strip().upper()
    if letter in LETTERS:
        return NAMES[LETTERS.index(letter)]
    return letter


def is_color(ch: str) -> bool:
    return bool(ch) and ch.upper() in LETTERS


def header() -> str:
    """题目文件第一行那句注释：`# colors: Yellow Green Red Purple Blue Orange`"""
    return "Yellow Green Red Purple Blue Orange"
