"""彩珠机会屋题卡：九档难度、物理操作说明、答案与解释。

题目统一是“屏幕出题，线下摸珠”。题卡会写明这道题要摸几颗、是否放回，
但页面不提供可点选项，也不记录孩子逐次摸到了什么。

题卡放在 ``puzzles/<等级>/<id>.txt``，格式是注释区 + 一行一个 ``键=值``：

    created_at=2026-10-24
    created_by=beadprob
    generator=make_puzzles@1
    id=20261024-120000-0a01
    level=3
    title=蓝珠去哪只袋子？
    story=先看清两只袋子的珠子组成，再动手试试。
    kind=compare
    target=B
    question=哪只袋子更容易摸到蓝珠？
    action=两只袋子轮流摸 5 次，每次放回并摇匀。
    bag=左边的袋子|R:4 B:4
    bag=右边的袋子|R:6 B:2
    answer=right
    hint=两边珠子总数一样，比一比蓝珠有几颗。
    explain=两只袋子都有 8 颗珠子，右边有 4 颗蓝珠，左边只有 2 颗。

答案字段使用机器可校验的固定值：

* L1 ``outcome``：``yes`` / ``no``
* L2 ``most``：颜色字母，例如 ``R``
* L3~L5 ``compare``：``left`` / ``right`` / ``same``
* L6 ``race``：没有固定答案，实际摸出来的赢家取决于随机结果
* L7 ``independence``：``same``
* L8 ``convergence``：``later``
* L9 ``without``：``larger`` / ``smaller`` / ``same``
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import colors as c

GAME_DIR = Path(__file__).resolve().parent.parent
PUZZLE_DIR = GAME_DIR / "puzzles"

LEVEL_NAMES = {
    1: "可能性",
    2: "单袋比较",
    3: "两袋比较",
    4: "比例陷阱",
    5: "相同机会",
    6: "三颗赛跑",
    7: "放回与随机",
    8: "多试几次",
    9: "不放回",
}
LEVEL_KINDS = {
    1: "outcome",
    2: "most",
    3: "compare",
    4: "compare",
    5: "compare",
    6: "race",
    7: "independence",
    8: "convergence",
    9: "without",
}
KINDS = set(LEVEL_KINDS.values())

META_KEYS = {
    "created_at", "created_by", "generator", "id", "level", "title", "story",
    "kind", "target", "ask", "question", "action", "bag", "answer", "hint",
    "explain", "prior", "removed", "first", "total",
}
REQUIRED = ("id", "level", "title", "kind", "question", "action", "explain")

MAX_BAG_SIZE = 12
MAX_COLOR_TOTAL = 10
_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")


@dataclass
class Bag:
    label: str
    counts: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(int(row["count"]) for row in self.counts)

    def count_of(self, letter: str) -> int:
        letter = (letter or "").upper()
        return sum(int(row["count"]) for row in self.counts if row["bead"] == letter)

    def chance(self, letter: str) -> float:
        return self.count_of(letter) / self.total if self.total else 0.0

    @property
    def beads(self) -> List[str]:
        return [str(row["bead"]) for row in self.counts for _ in range(int(row["count"]))]


@dataclass
class Card:
    path: Path
    meta: Dict[str, str] = field(default_factory=dict)
    bags: List[Bag] = field(default_factory=list)
    prior: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
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
    def kind(self) -> str:
        return self.meta.get("kind", "")

    @property
    def title(self) -> str:
        return self.meta.get("title", "")

    @property
    def target(self) -> str:
        return (self.meta.get("target") or "").strip().upper()

    @property
    def first_draws(self) -> int:
        try:
            return int(self.meta.get("first") or 0)
        except ValueError:
            return 0

    @property
    def total_draws(self) -> int:
        try:
            return int(self.meta.get("total") or 0)
        except ValueError:
            return 0


def _parse_error(text: str, problems: List[str]) -> None:
    problems.append(text)


def _parse_bag(text: str, problems: List[str]) -> Optional[Bag]:
    label, sep, body = (text or "").partition("|")
    label = label.strip()
    if not sep or not label:
        _parse_error("bag 要写成「袋子名字|R:6 B:2」：%r" % text, problems)
        return None

    rows: List[Dict[str, Any]] = []
    seen = set()
    for token in body.split():
        bead, sep2, raw_count = token.partition(":")
        bead = bead.strip().upper()
        if not sep2 or not c.is_color(bead):
            _parse_error("%s 里的 %r 要写成「颜色:颗数」" % (label, token), problems)
            continue
        if bead in seen:
            _parse_error("%s 里同一种颜色写了两次：%s" % (label, bead), problems)
            continue
        try:
            count = int(raw_count)
        except ValueError:
            _parse_error("%s 里的 %r 颗数不是整数" % (label, token), problems)
            continue
        if count <= 0:
            _parse_error("%s 里的 %r 要大于 0 颗" % (label, token), problems)
            continue
        seen.add(bead)
        rows.append({"bead": bead, "count": count})

    if not rows:
        _parse_error("%s 里没有可用的珠子" % label, problems)
        return None
    return Bag(label=label, counts=rows)


def _parse_sequence(text: str, field_name: str, problems: List[str]) -> List[str]:
    raw = re.sub(r"[\s,，]+", "", text or "").upper()
    out: List[str] = []
    for ch in raw:
        if not c.is_color(ch):
            _parse_error("%s 里有不是颜色的字符：%r" % (field_name, ch), problems)
        else:
            out.append(ch)
    return out


def _truth(card: Card) -> str:
    """按题卡实际数据算答案；数据不完整时返回空串。"""
    if not card.bags:
        return ""
    if card.kind == "outcome":
        bag = card.bags[0]
        count = bag.count_of(card.target)
        if card.meta.get("ask") == "may":
            return "yes" if count > 0 else "no"
        if card.meta.get("ask") == "certain":
            return "yes" if count == bag.total else "no"
        return ""
    if card.kind == "most":
        bag = card.bags[0]
        ranked = sorted(bag.counts, key=lambda row: int(row["count"]), reverse=True)
        if len(ranked) != 2 or ranked[0]["count"] == ranked[1]["count"]:
            return ""
        return str(ranked[0]["bead"])
    if card.kind == "compare":
        if len(card.bags) != 2:
            return ""
        left = card.bags[0].chance(card.target)
        right = card.bags[1].chance(card.target)
        if abs(left - right) < 1e-12:
            return "same"
        return "left" if left > right else "right"
    if card.kind == "race":
        return ""
    if card.kind == "independence":
        return "same"
    if card.kind == "convergence":
        return "later"
    if card.kind == "without":
        bag = card.bags[0]
        removed = Counter(card.removed)
        if any(removed[ch] > bag.count_of(ch) for ch in removed):
            return ""
        after_total = bag.total - len(card.removed)
        after_count = bag.count_of(card.target) - removed[card.target]
        if after_total <= 0:
            return ""
        before = bag.chance(card.target)
        after = after_count / after_total
        if abs(before - after) < 1e-12:
            return "same"
        return "larger" if after > before else "smaller"
    return ""


def infer_answer(card: Card) -> str:
    """按袋子组成和操作条件算答案（出题器用它生成 answer 字段）。"""
    return _truth(card)


def _check(card: Card) -> None:
    for key in REQUIRED:
        if not str(card.meta.get(key, "")).strip():
            _parse_error("少了 %s=" % key, card.problems)
    if card.level not in LEVEL_NAMES:
        _parse_error("level=%r 不认识（只能是 1～9）" % card.meta.get("level"), card.problems)
        return
    if card.kind not in KINDS:
        _parse_error("kind=%r 不认识" % card.kind, card.problems)
        return
    if card.kind != LEVEL_KINDS[card.level]:
        _parse_error("第 %d 档的 kind 应该是 %s，不是 %s"
                     % (card.level, LEVEL_KINDS[card.level], card.kind), card.problems)

    expected_bags = 2 if card.kind == "compare" else 1
    if len(card.bags) != expected_bags:
        _parse_error("%s 题要 %d 只袋子，现在有 %d 只"
                     % (card.kind, expected_bags, len(card.bags)), card.problems)
        return
    if len({bag.label for bag in card.bags}) != len(card.bags):
        _parse_error("袋子名字不能重复", card.problems)

    used: Counter = Counter()
    for bag in card.bags:
        if not 4 <= bag.total <= MAX_BAG_SIZE:
            _parse_error("%s 要有 4～%d 颗珠子，现在有 %d 颗"
                         % (bag.label, MAX_BAG_SIZE, bag.total), card.problems)
        if not 1 <= len(bag.counts) <= 3:
            _parse_error("%s 要用 1～3 种颜色，现在有 %d 种"
                         % (bag.label, len(bag.counts)), card.problems)
        for row in bag.counts:
            used[str(row["bead"])] += int(row["count"])
    for bead, count in used.items():
        if count > MAX_COLOR_TOTAL:
            _parse_error("两只袋子合起来要 %d 颗%s珠，可手上一共只有 %d 颗"
                         % (count, c.name(bead), MAX_COLOR_TOTAL), card.problems)

    if card.kind not in ("most", "race") and not c.is_color(card.target):
        _parse_error("target=%r 不是认识的珠子颜色" % card.target, card.problems)

    if card.kind == "outcome":
        if card.meta.get("ask") not in ("may", "certain"):
            _parse_error("outcome 题要写 ask=may 或 ask=certain", card.problems)
    elif card.kind == "most":
        if len(card.bags[0].counts) != 2:
            _parse_error("most 题要用两种颜色", card.problems)
    elif card.kind == "race":
        ask = card.meta.get("ask")
        if ask not in ("majority", "even", "upset", "rounds"):
            _parse_error("race 题要写 ask=majority / even / upset / rounds", card.problems)
        bag = card.bags[0]
        if len(bag.counts) < 2:
            _parse_error("三颗赛跑至少要有两种颜色", card.problems)
        for row in bag.counts:
            if int(row["count"]) > 7:
                _parse_error("%s色要 %d 颗，袋外还要留 3 颗做计分珠，最多只能放 7 颗"
                             % (c.name(row["bead"]), int(row["count"])), card.problems)
        if card.prior or card.removed:
            _parse_error("三颗赛跑由现场实际摸出结果，不要预设 prior / removed", card.problems)
    elif card.kind == "independence":
        if not card.prior:
            _parse_error("independence 题要写之前摸到的 prior=", card.problems)
        if card.removed:
            _parse_error("independence 题是每次放回，不能再写 removed=", card.problems)
    elif card.kind == "convergence":
        if card.first_draws <= 0 or card.total_draws <= card.first_draws:
            _parse_error("convergence 题要写 first= 和更大的 total=", card.problems)
        if card.total_draws > 30:
            _parse_error("单道题最多累计 30 次，别把线下操作拉太长", card.problems)
    elif card.kind == "without":
        if not card.removed:
            _parse_error("without 题要写拿出的 removed=", card.problems)
        bag = card.bags[0]
        removed = Counter(card.removed)
        for bead, count in removed.items():
            if count > bag.count_of(bead):
                _parse_error("拿出的%s珠比袋里原有的还多" % c.name(bead), card.problems)
        if bag.total - len(card.removed) <= 0:
            _parse_error("不能把袋里的珠子全部拿光", card.problems)

    if card.kind == "compare" and len(card.bags) == 2:
        left, right = card.bags
        if card.level == 3:
            if left.total != right.total:
                _parse_error("第 3 档两只袋子的总数要一样", card.problems)
            if abs(left.chance(card.target) - right.chance(card.target)) < 1e-12:
                _parse_error("第 3 档要能分出哪只袋子更容易", card.problems)
        elif card.level == 4:
            if left.total == right.total:
                _parse_error("第 4 档两只袋子的总数要不同", card.problems)
            left_count = left.count_of(card.target)
            right_count = right.count_of(card.target)
            more_count = "left" if left_count > right_count else "right"
            better = _truth(card)
            if left_count == right_count:
                _parse_error("第 4 档要让一边目标珠更多，另一边机会更大", card.problems)
            elif more_count == better:
                _parse_error("第 4 档必须是“目标珠更多的一边反而不更容易”", card.problems)
        elif card.level == 5:
            if left.total == right.total:
                _parse_error("第 5 档两只袋子的总数要不同", card.problems)
            if abs(left.chance(card.target) - right.chance(card.target)) >= 1e-12:
                _parse_error("第 5 档两只袋子摸到目标颜色的机会要一样", card.problems)

    if card.kind == "race":
        if (card.meta.get("answer") or "").strip():
            _parse_error("race 题没有固定赢家，不要写 answer=", card.problems)
        return

    if not (card.meta.get("answer") or "").strip():
        _parse_error("少了 answer=", card.problems)
    truth = _truth(card)
    answer = (card.meta.get("answer") or "").strip()
    if not truth:
        _parse_error("根据题卡数据算不出答案，请检查袋子、prior 或 removed", card.problems)
    elif answer != truth:
        _parse_error("按实际数据算，answer 应是 %s，题卡写的是 %s"
                     % (truth, answer or "空"), card.problems)


def parse_card(text: str, path: Path = Path("card.txt")) -> Card:
    """把一段题卡文本读成 ``Card``，同时收集所有问题。"""
    card = Card(path=Path(path))
    bag_lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or key not in META_KEYS:
            _parse_error("这行不是认识的「键=值」：%s" % line, card.problems)
            continue
        value = value.strip()
        if key == "bag":
            bag_lines.append(value)
        else:
            card.meta[key] = value

    card.bags = [bag for bag in (_parse_bag(text, card.problems) for text in bag_lines)
                 if bag is not None]
    card.prior = _parse_sequence(card.meta.get("prior", ""), "prior", card.problems)
    card.removed = _parse_sequence(card.meta.get("removed", ""), "removed", card.problems)
    _check(card)
    return card


def load_card(path: Path) -> Card:
    path = Path(path)
    return parse_card(path.read_text(encoding="utf-8"), path)


def answer_text(card: Card) -> str:
    answer = (card.meta.get("answer") or "").strip()
    if card.kind == "outcome":
        if card.meta.get("ask") == "may":
            return "可能" if answer == "yes" else "不可能"
        return "一定" if answer == "yes" else "不一定"
    if card.kind == "most":
        return c.name(answer) + "珠更常见"
    if card.kind == "compare":
        if answer == "left":
            return card.bags[0].label
        if answer == "right":
            return card.bags[1].label
        return "两只袋子一样容易"
    if card.kind == "independence":
        return "不会，机会和刚才一样"
    if card.kind == "convergence":
        return "摸得更多的那一份累计记录"
    if card.kind == "without":
        return {
            "larger": "更大",
            "smaller": "更小",
            "same": "不变",
        }.get(answer, "")
    return ""


def payload(card: Card) -> Dict[str, Any]:
    target = card.target
    bags = []
    for bag in card.bags:
        bags.append({
            "label": bag.label,
            "total": bag.total,
            "counts": [
                {
                    "bead": row["bead"],
                    "name": c.name(row["bead"]),
                    "count": row["count"],
                    "chance": row["count"] / bag.total,
                }
                for row in bag.counts
            ],
            "beads": bag.beads,
            "target_count": bag.count_of(target) if target else 0,
            "target_chance": bag.chance(target) if target else 0.0,
            "chance_text": ("%d 颗里有 %d 颗%s珠"
                            % (bag.total, bag.count_of(target), c.name(target)))
                           if target else "",
        })
    return {
        "id": card.id,
        "level": card.level,
        "level_name": LEVEL_NAMES.get(card.level, ""),
        "title": card.title,
        "story": card.meta.get("story", ""),
        "kind": card.kind,
        "target": target,
        "target_name": c.name(target) if target else "",
        "question": card.meta.get("question", ""),
        "action": card.meta.get("action", ""),
        "hint": card.meta.get("hint", ""),
        "explain": card.meta.get("explain", ""),
        "bags": bags,
        "prior": [{"bead": bead, "name": c.name(bead)} for bead in card.prior],
        "removed": [{"bead": bead, "name": c.name(bead)} for bead in card.removed],
        "first_draws": card.first_draws,
        "total_draws": card.total_draws,
        "answer_text": answer_text(card),
        "created_by": card.meta.get("created_by", ""),
        "generator": card.meta.get("generator", ""),
        "created_at": card.meta.get("created_at", ""),
    }


def _bag_shape(bag: Bag, target: str) -> str:
    if target:
        others = sorted(int(row["count"]) for row in bag.counts if row["bead"] != target)
        return "T%d/D%s" % (bag.count_of(target), ",".join(str(n) for n in others))
    return "C" + ",".join(str(n) for n in sorted(int(row["count"])
                                                for row in bag.counts))


def shape_key(card: Card) -> str:
    """跟颜色名字无关的结构签名，用来防止同档只是换颜色。"""
    parts = [card.kind, card.meta.get("ask", "")]
    for bag in card.bags:
        parts.append(_bag_shape(bag, card.target))
    if card.prior:
        target = card.target
        parts.append("prior:" + "".join("T" if bead == target else "O"
                                        for bead in card.prior))
    if card.removed:
        target = card.target
        parts.append("removed:" + "".join("T" if bead == target else "O"
                                          for bead in card.removed))
    if card.kind == "convergence":
        parts.append("%d/%d" % (card.first_draws, card.total_draws))
    return "|".join(parts)


def iter_cards(root: Path = PUZZLE_DIR) -> List[Card]:
    root = Path(root)
    return [load_card(path) for path in sorted(root.glob("*/*.txt"))] if root.is_dir() else []


def find_card_path(root: Path = PUZZLE_DIR, card_id: str = "") -> Optional[Path]:
    card_id = (card_id or "").strip()
    if not card_id:
        return None
    for path in Path(root).glob("*/*.txt"):
        if path.stem == card_id:
            return path
    return None


def list_levels(root: Path = PUZZLE_DIR) -> List[Dict[str, int]]:
    counts: Dict[int, int] = {}
    for card in iter_cards(root):
        if not card.problems and card.level in LEVEL_NAMES:
            counts[card.level] = counts.get(card.level, 0) + 1
    return [{"level": level, "count": counts[level]} for level in sorted(counts)]


def check(root: Path = PUZZLE_DIR) -> List[str]:
    problems: List[str] = []
    seen = set()
    root = Path(root)
    for card in iter_cards(root):
        rel = card.path.relative_to(root)
        if not _ID_RE.match(card.id):
            problems.append("%s：id 要写成 <日期>-<时间>-<4位>" % rel)
        if card.path.stem != card.id:
            problems.append("%s：文件名跟 id=%s 对不上" % (rel, card.id))
        if card.path.parent.name.isdigit() and card.path.parent.name != str(card.level):
            problems.append("%s：目录跟 level=%d 对不上" % (rel, card.level))
        for problem in card.problems:
            problems.append("%s：%s" % (rel, problem))
        if card.id in seen:
            problems.append("%s：id 重复了" % rel)
        seen.add(card.id)
    return problems


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="彩珠机会屋题库：检查 / 列表 / 打印")
    parser.add_argument("--dir", default=str(PUZZLE_DIR), help="题库目录")
    parser.add_argument("--list", action="store_true", help="列出每级题数")
    parser.add_argument("--show", metavar="文件", help="打印一张题卡")
    args = parser.parse_args(argv)
    root = Path(args.dir)
    if not root.is_dir():
        print("题库目录不存在：%s" % root, file=sys.stderr)
        return 2

    if args.show:
        card = load_card(Path(args.show))
        if card.problems:
            for problem in card.problems:
                print("× " + problem)
            return 1
        data = payload(card)
        print("id=%s  L%d %s  《%s》"
              % (data["id"], data["level"], data["level_name"], data["title"]))
        for bag in data["bags"]:
            print("%s：%s" % (bag["label"], bag["chance_text"] or bag["total"]))
        print("动手：" + data["action"])
        print("答案：" + data["answer_text"])
        print("解释：" + data["explain"])
        return 0

    cards = iter_cards(root)
    problems = check(root)
    by_rel = {}
    for problem in problems:
        by_rel.setdefault(problem.split("：", 1)[0], []).append(problem)
    for card in cards:
        rel = str(card.path.relative_to(root))
        mark = "×" if rel in by_rel else "√"
        print("%s L%d %-9s %s  《%s》"
              % (mark, card.level, LEVEL_NAMES.get(card.level, "?"), card.id, card.title))
    if args.list:
        print()
        for row in list_levels(root):
            print("  %d 级 %-8s：%d 道"
                  % (row["level"], LEVEL_NAMES.get(row["level"], ""), row["count"]))
    print()
    if problems:
        for problem in problems:
            print("× " + problem)
        print("共 %d 张题卡，%d 个问题" % (len(cards), len(problems)))
        return 1
    print("共 %d 张题卡，全部通过" % len(cards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
