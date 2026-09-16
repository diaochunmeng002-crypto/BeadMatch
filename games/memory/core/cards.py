"""memory 的规则卡：读写、校验、扫卡片库。

一张卡 = 一道**规则**：用哪些颜色、各几颗、摆成什么形式、观察几秒、还原什么。

⚠️ **卡里没有答案。** 具体怎么摆，由出题人当场决定（这是这个游戏的根本规矩，
见 README §5）—— 所以这个文件里没有任何"求解/判定"的东西。

格式跟 logic 一样：**注释区 + 元信息区 + 正文区**。

    # colors: Yellow Green Red Purple Blue Orange

    created_at=2026-09-16 10:00:00
    created_by=manual
    id=1-01
    title=三红一黄
    level=1
    materials=R R R Y
    shape=row
    observe=3
    restore=order
    delay=0
    reverse=no
    demo=R Y R R

    把 4 颗珠子排成一排（顺序随意），给孩子看 3 秒后盖住，再让孩子凭记忆摆回原来的顺序。

| 字段 | 说明 |
| --- | --- |
| ``created_at`` / ``created_by`` | 什么时候、谁定的（头两行） |
| ``id`` | 文件名就是它 |
| ``title`` | 卡的名字（可选） |
| ``level`` | 难度等级 |
| ``materials`` | **用哪些颜色、各几颗**：``R R R Y`` = 红 3 颗 + 黄 1 颗 |
| ``shape`` | 摆成什么形式：``row`` / ``rows2`` / ``ring`` / ``triangle`` / ``grid`` / ``free`` |
| ``observe`` | 观察几秒 |
| ``restore`` | 还原什么：``order``（从左到右的顺序）/ ``layout``（每一颗的位置） |
| ``delay`` | 观察结束到开始还原之间空等几秒（高等级才用，可以没有） |
| ``reverse`` | 要不要反向还原（高等级才用，可以没有） |
| ``demo`` | **只示意**（可选）：给大人看"这题怎么玩"，不是要照着摆 |
| 正文 | 给出题人看的一句说明（可选），**程序原样显示，不改你的话** |

读进来就校验，对不上直接报错（不能默默读进来）：材料认得出、每色不超过实物的 10 颗、
形式和还原要求的记号认识、``level`` 跟它所在的等级文件夹对得上。

``demo`` 跟材料对不上**不算错**（demo 只是示意），但检查时会提示一句。

用法：

    python -m games.memory.core.cards                  # 检查卡片库
    python -m games.memory.core.cards --show <文件>     # 打印一张卡
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import colors as C

# 元信息区的输出顺序（时间 / 谁定的 固定在前两行）
META_ORDER = ("created_at", "created_by", "id", "title", "level", "materials",
              "shape", "observe", "restore", "delay", "reverse", "demo")
REQUIRED_KEYS = ("id", "level", "materials")
_INT_KEYS = ("level", "observe", "delay")
_BOOL_KEYS = ("reverse",)

# 排列形式（卡里写英文记号，中文名只说给人听）
SHAPES: Dict[str, str] = {
    "row": "一排",
    "rows2": "两排",
    "ring": "圆环",
    "triangle": "三角",
    "grid": "网格",
    "free": "自由图案",
}

# 还原什么
RESTS: Dict[str, str] = {
    "order": "从左到右的顺序",
    "layout": "每一颗的位置",
}

# 实物上限：一套串珠每色 10 颗（跟 beadmatch 一致）
PER_COLOR_MAX = 10
COLOR_KINDS = len(C.LETTERS)

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_TAG_RE = re.compile(r"^[A-Za-z0-9_@.+-]{1,64}$")
_TRUE = ("yes", "y", "true", "1", "on", "是")
_FALSE = ("no", "n", "false", "0", "off", "否")

# 卡片库目录（一卡一文件，文件名 = <id>.txt）
PUZZLE_DIR = Path(__file__).resolve().parent.parent / "puzzles"


@dataclass(frozen=True)
class Card:
    """一张规则卡：**只有规则，没有答案**。元信息（id / level / …）单独放在 ``meta`` 里。"""

    materials: Tuple[str, ...]      # 用哪些颜色、各几颗，一串字母，如 ("R","R","R","Y")
    shape: str                      # 摆成什么形式
    observe: int                    # 观察几秒
    restore: str                    # 还原什么
    delay: int                      # 观察后空等几秒（默认 0）
    reverse: bool                   # 要不要反向还原（默认 False）
    demo: Tuple[str, ...]           # 示意摆法（空 tuple = 没写）
    note: str                       # 正文：给出题人看的一句说明

    # ---- 顺手就能算出来的 ----

    @property
    def beads(self) -> int:
        """一共几颗珠子。"""
        return len(self.materials)

    @property
    def color_kinds(self) -> int:
        """用了几种颜色。"""
        return len(set(self.materials))


def _parse_bool(value: str) -> bool:
    key = str(value).strip().lower()
    if key in _TRUE:
        return True
    if key in _FALSE:
        return False
    raise ValueError("认不出的开关：%r（用 yes / no）" % value)


def _parse_int(value: str, key: str) -> int:
    try:
        return int(str(value).strip())
    except ValueError:
        raise ValueError("字段 %s 不是整数：%r" % (key, value))


# --------------------------------------------------------------------------
# 渲染 / 解析
# --------------------------------------------------------------------------


def render_card(card: Card, meta: Optional[Dict[str, object]] = None) -> str:
    """把一张卡渲染成文本。给了 ``meta`` 就出完整三段式（就是文件内容）。"""
    lines: List[str] = []
    if meta is not None:
        lines.append("# colors: " + " ".join(C.EN[c] for c in C.LETTERS))
        lines.append("")
        for key in META_ORDER:
            if key in meta:
                value = meta[key]
                if isinstance(value, bool):
                    value = "yes" if value else "no"
                lines.append("%s=%s" % (key, value))
        lines.append("")
    if card.note:
        lines.extend(card.note.splitlines())
    return "\n".join(lines)


def parse_card(text: str) -> Tuple[Card, Dict[str, object]]:
    """解析一张卡的文本，返回 ``(卡, 元信息)``。读进来就校验，对不上直接报错。"""
    raw: Dict[str, str] = {}
    note_lines: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _KEY_RE.match(s)
        if m:
            raw[m.group(1)] = m.group(2).strip()
        else:
            note_lines.append(s)

    for key in REQUIRED_KEYS:
        if key not in raw:
            raise ValueError("卡里缺少必需字段 %s=" % key)

    meta: Dict[str, object] = {}
    for key, value in raw.items():
        if key in _INT_KEYS:
            meta[key] = _parse_int(value, key)
        elif key in _BOOL_KEYS:
            meta[key] = _parse_bool(value)
        else:
            meta[key] = value

    level = int(meta["level"])
    if level < 0:
        raise ValueError("level 不能是负数：%s" % level)

    # ---- 材料：用哪些颜色、各几颗 ----
    try:
        materials = C.to_letters(str(meta["materials"]))
    except ValueError as exc:
        raise ValueError("materials 读不了：%s" % exc)
    if not materials:
        raise ValueError("materials 是空的 —— 这道题用几颗珠子？")
    if len(materials) > COLOR_KINDS * PER_COLOR_MAX:
        raise ValueError("materials 有 %d 颗，超过实物的 %d 颗（%d 色 × 每色 %d 颗）"
                         % (len(materials), COLOR_KINDS * PER_COLOR_MAX, COLOR_KINDS, PER_COLOR_MAX))
    for row in C.counts_of(materials):
        if int(row["count"]) > PER_COLOR_MAX:
            raise ValueError("%s 有 %d 颗，超过实物的 %d 颗"
                             % (row["name"], row["count"], PER_COLOR_MAX))

    # ---- 形式 / 还原 ----
    shape = str(meta.get("shape") or "").strip()
    if not shape:
        raise ValueError("卡里缺少 shape=（摆成什么形式：%s）" % " / ".join(SHAPES))
    if shape not in SHAPES:
        raise ValueError("认不出的 shape：%r（能用的是 %s）"
                         % (shape, " / ".join(SHAPES)))

    restore = str(meta.get("restore") or "").strip()
    if not restore:
        raise ValueError("卡里缺少 restore=（还原什么：%s）" % " / ".join(RESTS))
    if restore not in RESTS:
        raise ValueError("认不出的 restore：%r（能用的是 %s）"
                         % (restore, " / ".join(RESTS)))

    # ---- 时间 / 开关 ----
    observe = int(meta.get("observe") or 0)
    if observe <= 0:
        raise ValueError("observe 要大于 0（观察几秒）：现在写的是 %s" % meta.get("observe"))
    if observe > 300:
        raise ValueError("observe=%d 秒太长了（超过 5 分钟）" % observe)

    delay = int(meta.get("delay") or 0)
    if delay < 0:
        raise ValueError("delay 不能是负数：%s" % delay)

    reverse = bool(meta.get("reverse", False))
    if reverse and restore != "order":
        raise ValueError("reverse=yes 只跟 restore=order 一起用（反向念的是顺序）")

    # ---- demo：只示意，跟材料对不上不算错 ----
    demo: Tuple[str, ...] = ()
    if meta.get("demo"):
        try:
            demo = C.to_letters(str(meta["demo"]))
        except ValueError as exc:
            raise ValueError("demo 读不了：%s" % exc)

    # ---- 出身 ----
    for key in ("created_by",):
        if key in meta and not _TAG_RE.match(str(meta[key])):
            raise ValueError("%s 的格式不对：%r（只允许字母数字和 _ @ . + -，最长 64）"
                             % (key, meta[key]))
    if "created_at" in meta and not _STAMP_RE.match(str(meta["created_at"])):
        raise ValueError("created_at 的格式不对：%r（要写成 2026-09-16 10:00:00）"
                         % meta["created_at"])

    card = Card(materials=materials, shape=shape, observe=observe, restore=restore,
                delay=delay, reverse=reverse, demo=demo, note="\n".join(note_lines))
    return card, meta


def load_card(path) -> Tuple[Card, Dict[str, object]]:
    """读一张卡；顺带校验 id 与文件名一致、level 与所在的等级文件夹一致。"""
    p = Path(path)
    card, meta = parse_card(p.read_text(encoding="utf-8"))
    if str(meta["id"]) != p.stem:
        raise ValueError("id=%s 与文件名 %s 对不上" % (meta["id"], p.stem))
    folder = p.parent.name
    if folder.isdigit() and int(folder) != int(meta["level"]):
        raise ValueError("level=%s 与所在的文件夹 %s/ 对不上" % (meta["level"], folder))
    return card, meta


def demo_mismatch(card: Card) -> bool:
    """demo 用的珠子跟材料不是同一批（只是"提示"，不是错误 —— demo 本来就只是示意）。"""
    return bool(card.demo) and sorted(card.demo) != sorted(card.materials)


# --------------------------------------------------------------------------
# 卡片库索引（目录就是索引：等级看目录名、id 看文件名）
# --------------------------------------------------------------------------


def read_head(path) -> Dict[str, str]:
    """只读卡的元信息段（读到正文就停）。"""
    meta: Dict[str, str] = {}
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:          # 到正文了
                break
            key, value = s.split("=", 1)
            meta[key] = value.strip()
    return meta


def _level_dirs(root) -> List[Path]:
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted((d for d in root.iterdir() if d.is_dir() and d.name.isdigit()),
                  key=lambda d: int(d.name))


def list_levels(root=PUZZLE_DIR) -> List[Dict[str, int]]:
    """每个等级各有多少张卡（广场契约之一）。"""
    return [{"level": int(d.name), "count": len(list(d.glob("*.txt")))}
            for d in _level_dirs(root) if list(d.glob("*.txt"))]


def list_cards(root=PUZZLE_DIR, level: Optional[int] = None) -> List[Dict[str, object]]:
    """列出卡片（可按等级筛）—— 扫目录 + 只读每张卡的文件头。"""
    out: List[Dict[str, object]] = []
    for d in _level_dirs(root):
        if level is not None and int(d.name) != level:
            continue
        for f in sorted(d.glob("*.txt")):
            head = read_head(f)
            out.append({
                "id": f.stem,
                "title": head.get("title", ""),
                "level": int(head.get("level") or d.name),
                "beads": len(C.to_letters(head.get("materials", ""))),
                "shape": head.get("shape", ""),
                "observe": int(head.get("observe") or 0),
                "restore": head.get("restore", ""),
                "path": str(f),
            })
    return out


def find_card_path(root, card_id: str) -> Optional[Path]:
    """按 id 找卡片文件：在等级目录里找同名文件。"""
    hits = sorted(Path(root).glob("*/%s.txt" % card_id))
    return hits[0] if hits else None


# --------------------------------------------------------------------------
# 广场契约（docs/plaza.md §4.2）：list_levels / pick / load
# --------------------------------------------------------------------------


def pick(level: int = 1, root=PUZZLE_DIR) -> Tuple[Card, Dict[str, object]]:
    """从某个等级随机抽一张卡（「出题」的入口）。"""
    pool = list_cards(root, level)
    if not pool:
        raise LookupError("卡片库里没有 %s 级的卡" % level)
    path = find_card_path(root, str(random.choice(pool)["id"]))
    if path is None:                      # 理论上不会发生
        raise LookupError("抽到的卡找不到了")
    return load_card(path)


def load(card_id: str, root=PUZZLE_DIR) -> Tuple[Card, Dict[str, object]]:
    """按 id 取一张卡。"""
    path = find_card_path(root, card_id)
    if path is None:
        raise LookupError("没有这张卡：%s" % card_id)
    return load_card(path)


# --------------------------------------------------------------------------
# 给人看的一行摘要
# --------------------------------------------------------------------------


def describe(card: Card, meta: Optional[Dict[str, object]] = None) -> str:
    """一行摘要：``三红一黄  L1 珠子=4 颜色=2 一排 观察=3秒 还原=顺序``。"""
    meta = meta or {}
    title = str(meta.get("title") or "").strip()
    head = "%s  " % title if title else ""
    return "%s L%s 珠子=%d 颜色=%d %s 观察=%d秒 还原=%s%s" % (
        head, meta.get("level", "?"), card.beads, card.color_kinds,
        SHAPES.get(card.shape, card.shape), card.observe,
        RESTS.get(card.restore, card.restore),
        "（反向）" if card.reverse else "",
    )


def format_demo(card: Card) -> str:
    """示意摆法 → 一行 emoji（没写 demo 就是空字符串）。"""
    return C.format_seq(card.demo)


# --------------------------------------------------------------------------
# 检查卡片库
# --------------------------------------------------------------------------


def check_dir(root=PUZZLE_DIR, *, stream=sys.stdout) -> int:
    """扫一遍卡片库：报「读得进来吗 / 是什么难度 / demo 跟材料对不对」。

    只有**读不进来**才算问题（返回值就是问题数）；demo 跟材料对不上只提示一句。
    """
    root = Path(root)
    files = sorted(root.glob("*/*.txt"))
    if not files:
        print("卡片库是空的：%s" % root, file=stream)
        return 0

    problems = 0
    warned = 0
    for path in files:
        rel = "%s/%s" % (path.parent.name, path.name)
        try:
            card, meta = load_card(path)
        except ValueError as exc:
            problems += 1
            print("× %s —— %s" % (rel, exc), file=stream)
            continue

        print("√ %s  %s" % (rel, describe(card, meta)), file=stream)

        if card.demo:
            print("     示意 %s ；材料 %s"
                  % (format_demo(card), C.format_materials(card.materials)), file=stream)
        if demo_mismatch(card):
            warned += 1
            print("     ！demo（%s）不是这张卡的 %s 颗珠子"
                  % (format_demo(card), C.format_materials(card.materials)), file=stream)
        if card.note:
            print("     %s" % card.note.splitlines()[0], file=stream)

    print("", file=stream)
    print("共 %d 张卡：读不进来 %d 张，demo 跟材料对不上 %d 张。"
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
    p = argparse.ArgumentParser(description="memory 卡片库：检查 / 打印")
    p.add_argument("--dir", default=str(PUZZLE_DIR), help="卡片库根目录（默认本游戏的 puzzles/）")
    p.add_argument("--show", metavar="FILE", help="打印一张卡（附带程序读到的字段）")
    args = p.parse_args(argv)

    if args.show:
        card, meta = load_card(args.show)
        print(render_card(card, meta))
        print("")
        print("# 程序读到的是：%s" % describe(card, meta))
        print("# 材料：%s（%s）" % (C.format_materials(card.materials),
                                   C.format_letters(card.materials)))
        if card.demo:
            print("# 示意：%s（%s）" % (format_demo(card), C.format_letters(card.demo)))
        return 0

    return 1 if check_dir(Path(args.dir)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
