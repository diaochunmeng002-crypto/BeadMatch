"""珠子颜色：跟其它游戏共用同一套 6 色。

题目里只认这套字母，页面上也只画这 6 种颜色，保证屏幕和实物珠子对得上。
"""

from __future__ import annotations

LETTERS = "YGRPBO"
NAMES = ("黄", "绿", "红", "紫", "蓝", "橙")
CSS = ("#f2c231", "#4caf50", "#e5484d", "#9b59d0", "#3b82f6", "#f2811d")


def header() -> str:
    """题卡注释区那行颜色说明。"""
    return "Yellow Green Red Purple Blue Orange"


def name(letter: str) -> str:
    letter = (letter or "").strip().upper()
    return NAMES[LETTERS.index(letter)] if letter in LETTERS else letter


def is_color(ch: str) -> bool:
    return bool(ch) and ch.upper() in LETTERS
