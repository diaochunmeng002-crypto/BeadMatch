"""彩珠密令题卡：一把实体珠子 + 一条明确的线索约定。

程序不保存密令，也不计算对错。参与者把 ``beads=`` 里的珠子摆成一排藏起来；
另一方猜顺序，提供线索的人按照 ``clue_rule=`` 的约定回答。

    # colors: Yellow Green Red Purple Blue Orange

    created_at=2026-10-22 23:35:00
    created_by=manual
    id=20261022-233500-bc01
    level=1
    title=三色密令
    beads=RBY
    kind=positions
    clue_rule=每次只告诉位置对了几颗，不说是哪几个位置。

同一个字母出现几次，就表示手里有几颗这种颜色；例如 ``RRBY`` 是两颗红、
一颗蓝、一颗黄。珠子只规定材料，不规定密令的排列顺序。
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

GAME_DIR = Path(__file__).resolve().parent.parent
PUZZLE_DIR = GAME_DIR / "puzzles"

LETTERS = "YGRPBO"
COLOR_NAMES = {
    "Y": "黄",
    "G": "绿",
    "R": "红",
    "P": "紫",
    "B": "蓝",
    "O": "橙",
}

KINDS = {
    "position_marks": "直接标出正确位置",
    "positions": "位置正确数",
    "first_error": "第一处错误",
    "run": "连续正确结构",
    "choice": "自选线索类型",
    "questions": "限定是 / 否问题",
    "delayed": "延迟反馈",
}
REQUIRED = ("id", "level", "title", "beads", "kind", "clue_rule")
ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")


@dataclass
class Card:
    path: Path
    meta: Dict[str, str] = field(default_factory=dict)
    beads: Tuple[str, ...] = ()
    problems: List[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.meta.get("id", "")

    @property
    def level(self) -> int:
        try:
            return int(self.meta.get("level") or 0)
        except ValueError:
            return 0

    @property
    def title(self) -> str:
        return self.meta.get("title", "")

    @property
    def kind(self) -> str:
        return self.meta.get("kind", "")

    @property
    def clue_rule(self) -> str:
        return self.meta.get("clue_rule", "")

    @property
    def length(self) -> int:
        return len(self.beads)

    @property
    def colors(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(self.beads))


def _parse_meta(text: str) -> Tuple[Dict[str, str], List[str]]:
    meta: Dict[str, str] = {}
    problems: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            problems.append("这行不是「键=值」：%s" % line)
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            problems.append("这行缺少键名：%s" % line)
            continue
        if key in meta:
            problems.append("字段 %s 写了两次" % key)
        meta[key] = value.strip()
    return meta, problems


def to_letters(value: object) -> Tuple[str, ...]:
    compact = re.sub(r"[\s,，、/]+", "", str(value or ""))
    out: List[str] = []
    for ch in compact:
        upper = ch.upper()
        if upper in LETTERS:
            out.append(upper)
            continue
        matched = next((letter for letter, name in COLOR_NAMES.items() if name == ch), "")
        if matched:
            out.append(matched)
            continue
        raise ValueError("有不认识的颜色：%r" % ch)
    return tuple(out)


def possible_secrets(card: Card) -> List[Tuple[str, ...]]:
    """去掉重复排列后，符合这组实体珠子的所有密令。"""
    return sorted(set(itertools.permutations(card.beads)))


def structure_key(card: Card) -> str:
    """不看标题、不看文件的题目结构签名，用来防止同结构重复。"""
    counts = sorted((card.beads.count(ch) for ch in set(card.beads)), reverse=True)
    return "|".join((
        str(card.level),
        card.kind,
        str(card.length),
        ",".join(str(n) for n in counts),
        card.clue_rule,
    ))


def load_card(path: Path) -> Card:
    path = Path(path)
    card = Card(path=path)
    meta, problems = _parse_meta(path.read_text(encoding="utf-8"))
    card.meta = meta
    card.problems.extend(problems)

    for key in REQUIRED:
        if key not in meta or not meta[key]:
            card.problems.append("少了 `%s=`" % key)
    if card.problems:
        return card

    if not ID_RE.match(card.id):
        card.problems.append("id=%s 不像 `<日期>-<时间>-<4位>`" % card.id)
    if card.path.stem != card.id:
        card.problems.append("文件名（%s）跟 id（%s）对不上" % (card.path.stem, card.id))
    parent = card.path.parent.name
    if parent.isdigit() and parent != str(card.level):
        card.problems.append("放在 %s/ 里，可 level=%s" % (parent, card.level))
    if not 1 <= card.level <= 10:
        card.problems.append("level 必须在 1～10")
    if card.kind not in KINDS:
        card.problems.append("kind=%s 不认识（只能是 %s）"
                             % (card.kind, " / ".join(KINDS)))

    try:
        card.beads = to_letters(meta.get("beads", ""))
    except ValueError as exc:
        card.problems.append("beads 读不了：%s" % exc)
    if card.beads:
        if not 2 <= len(card.beads) <= 6:
            card.problems.append("beads 必须是 2～6 颗")
        if len(possible_secrets(card)) < 2:
            card.problems.append("所有珠子同色，排不出两种以上密令")
        for ch in set(card.beads):
            if card.beads.count(ch) > 10:
                card.problems.append("%s色超过实物的 10 颗" % COLOR_NAMES[ch])
    return card


def list_cards(root: Path = PUZZLE_DIR, level: Optional[int] = None) -> List[Dict[str, object]]:
    root = Path(root)
    if not root.is_dir():
        return []
    out: List[Dict[str, object]] = []
    for path in sorted(root.glob("*/*.txt")):
        if level is not None and path.parent.name != str(level):
            continue
        card = load_card(path)
        out.append({
            "id": card.id,
            "level": card.level,
            "title": card.title,
            "kind": card.kind,
            "path": path,
            "problems": card.problems,
        })
    return out


def list_levels(root: Path = PUZZLE_DIR) -> List[Dict[str, int]]:
    counts: Dict[int, int] = {}
    for row in list_cards(root):
        if row["problems"]:
            continue
        level = int(row["level"])
        counts[level] = counts.get(level, 0) + 1
    return [{"level": level, "count": counts[level]} for level in sorted(counts)]


def find_card_path(root: Path = PUZZLE_DIR, card_id: str = "") -> Optional[Path]:
    card_id = (card_id or "").strip()
    if not card_id:
        return None
    for path in sorted(Path(root).glob("*/*.txt")):
        if path.stem == card_id:
            return path
    return None


def payload(card: Card) -> Dict[str, object]:
    """页面只需要题卡：珠子材料、题目类型和线索约定。"""
    return {
        "id": card.id,
        "level": card.level,
        "title": card.title,
        "beads": list(card.beads),
        "kind": card.kind,
        "kind_name": KINDS[card.kind],
        "clue_rule": card.clue_rule,
        "created_at": card.meta.get("created_at", ""),
        "created_by": card.meta.get("created_by", ""),
        "generator": card.meta.get("generator", ""),
    }


def iter_cards(root: Path = PUZZLE_DIR) -> List[Card]:
    root = Path(root)
    return [load_card(path) for path in sorted(root.glob("*/*.txt"))] if root.is_dir() else []


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="彩珠密令题库：检查 / 列表")
    parser.add_argument("--dir", default=str(PUZZLE_DIR))
    parser.add_argument("--list", action="store_true", help="列出每级题数")
    args = parser.parse_args(argv)

    root = Path(args.dir)
    if not root.is_dir():
        print("题库目录不存在：%s" % root, file=sys.stderr)
        return 2

    cards = iter_cards(root)
    bad = 0
    for card in cards:
        rel = card.path.relative_to(root)
        if card.problems:
            bad += 1
            print("× %s 《%s》" % (rel, card.title or "?"))
            for problem in card.problems:
                print("    - %s" % problem)
        else:
            print("√ %s  L%s  《%s》  %d 颗 / %s / %d 种密令"
                  % (rel, card.level, card.title, card.length, card.kind,
                     len(possible_secrets(card))))
    if args.list:
        print()
        for row in list_levels(root):
            print("  %d 级：%d 道" % (row["level"], row["count"]))
    print()
    print("共 %d 道，%s" % (len(cards), "全部通过" if not bad else "%d 道有问题" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
