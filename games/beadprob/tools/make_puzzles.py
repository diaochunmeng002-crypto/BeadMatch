"""生成彩珠机会屋十档题库，每档 20 道。

    python -m games.beadprob.tools.make_puzzles --fresh

生成器只负责写 ``games/beadprob/puzzles/`` 下的 ``.txt``；写完会把整个题库
重新读一遍，任何一道不过校验就整体报错，不会留下半套题库。
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from games.beadprob.core import cards as k
from games.beadprob.core import colors as c

PER_LEVEL = 20
DATE = "2026-10-24"
START = datetime(2026, 10, 24, 12, 0, 0)
PALETTE = list(c.LETTERS)
GENERATOR = "make_puzzles@2"


@dataclass
class Recipe:
    level: int
    title: str
    story: str
    kind: str
    question: str
    action: str
    hint: str
    explain: str
    bags: List[Tuple[str, List[Tuple[str, int]]]]
    target: str = ""
    ask: str = ""
    prior: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    conclusion: str = ""
    answer_code: str = ""
    first: int = 0
    total: int = 0


def _parts(total: int, count: int) -> Iterable[Tuple[int, ...]]:
    if count == 1:
        if total >= 1:
            yield (total,)
        return
    for first in range(1, total - count + 2):
        for rest in _parts(total - first, count - 1):
            yield (first,) + rest


def _bag_counts(counts: Sequence[Tuple[str, int]]) -> Dict[str, int]:
    return {bead: n for bead, n in counts}


def _desc(counts: Sequence[Tuple[str, int]]) -> str:
    return "、".join("%s珠 %d 颗" % (c.name(bead), n) for bead, n in counts)


def _sequence_text(seq: Sequence[str]) -> str:
    return "、".join(c.name(bead) + "珠" for bead in seq)


def _shape(recipe: Recipe) -> str:
    parts = [recipe.kind, recipe.ask]
    for _, counts in recipe.bags:
        data = _bag_counts(counts)
        if recipe.target:
            others = sorted(n for bead, n in data.items() if bead != recipe.target)
            parts.append("T%d/D%s" % (data.get(recipe.target, 0),
                                      ",".join(str(n) for n in others)))
        else:
            parts.append("C" + ",".join(str(n) for n in sorted(data.values())))
    if recipe.prior:
        parts.append("prior:" + "".join("T" if bead == recipe.target else "O"
                                        for bead in recipe.prior))
    if recipe.removed:
        parts.append("removed:" + "".join("T" if bead == recipe.target else "O"
                                          for bead in recipe.removed))
    if recipe.first:
        parts.append("%d/%d" % (recipe.first, recipe.total))
    if recipe.kind == "evidence":
        parts.append(recipe.question)
    return "|".join(parts)


def _text(recipe: Recipe, card_id: str) -> str:
    lines = [
        "# colors: " + c.header(),
        "",
        "created_at=" + DATE,
        "created_by=beadprob",
        "generator=" + GENERATOR,
        "id=" + card_id,
        "level=" + str(recipe.level),
        "title=" + recipe.title,
        "story=" + recipe.story,
        "kind=" + recipe.kind,
    ]
    if recipe.target:
        lines.append("target=" + recipe.target)
    if recipe.ask:
        lines.append("ask=" + recipe.ask)
    lines.extend([
        "question=" + recipe.question,
        "action=" + recipe.action,
    ])
    for label, counts in recipe.bags:
        lines.append("bag=%s|%s" % (
            label, " ".join("%s:%d" % (bead, n) for bead, n in counts)))
    if recipe.prior:
        lines.append("prior=" + "".join(recipe.prior))
    if recipe.removed:
        lines.append("removed=" + "".join(recipe.removed))
    for line in recipe.evidence:
        lines.append("evidence=" + line)
    if recipe.first:
        lines.append("first=" + str(recipe.first))
        lines.append("total=" + str(recipe.total))
    return "\n".join(lines)


def _materialize(recipe: Recipe, serial: int) -> Tuple[str, k.Card]:
    stamp = START + timedelta(minutes=serial * 2)
    card_id = "%s-%04x" % (stamp.strftime("%Y%m%d-%H%M%S"), serial)
    base = _text(recipe, card_id)
    probe = k.parse_card(base, Path("%s.txt" % card_id))
    answer = recipe.answer_code if recipe.kind == "evidence" else k.infer_answer(probe)
    if recipe.kind != "race" and not answer:
        raise RuntimeError("算不出答案：L%d《%s》" % (recipe.level, recipe.title))
    answer_line = "" if recipe.kind == "race" else "\nanswer=" + answer
    if recipe.conclusion:
        answer_line += "\nconclusion=" + recipe.conclusion
    text = base + answer_line + "\nhint=" + recipe.hint + "\nexplain=" + recipe.explain
    card = k.parse_card(text, Path(str(recipe.level), "%s.txt" % card_id))
    if card.problems:
        raise RuntimeError("L%d《%s》生成失败：%s"
                           % (recipe.level, recipe.title, "；".join(card.problems)))
    return text, card


def _choose(recipes: List[Recipe], rng: random.Random,
            count: int = PER_LEVEL) -> List[Recipe]:
    rng.shuffle(recipes)
    seen = set()
    out: List[Recipe] = []
    for recipe in recipes:
        try:
            _materialize(recipe, 0)       # 先在内存里过一遍完整规则
        except RuntimeError:
            continue
        shape = _shape(recipe)
        if shape in seen:
            continue
        seen.add(shape)
        out.append(recipe)
        if len(out) == count:
            return out
    raise RuntimeError("只能凑出 %d 道，需要 %d 道" % (len(out), count))


def _choose_outcome(recipes: List[Recipe], rng: random.Random) -> List[Recipe]:
    """L1 四类各取 5 道，不能整套碰巧全是“不一定”。"""
    buckets: Dict[str, List[Recipe]] = {
        "may_yes": [], "may_no": [], "certain_yes": [], "certain_no": [],
    }
    for recipe in recipes:
        data = dict(recipe.bags[0][1])
        target_count = data.get(recipe.target, 0)
        total = sum(data.values())
        if recipe.ask == "may":
            key = "may_yes" if target_count else "may_no"
        else:
            key = "certain_yes" if target_count == total else "certain_no"
        buckets[key].append(recipe)

    out: List[Recipe] = []
    seen = set()
    for key in ("may_yes", "may_no", "certain_yes", "certain_no"):
        rng.shuffle(buckets[key])
        picked = 0
        for recipe in buckets[key]:
            try:
                _materialize(recipe, 0)
            except RuntimeError:
                continue
            shape = _shape(recipe)
            if shape in seen:
                continue
            seen.add(shape)
            out.append(recipe)
            picked += 1
            if picked == 5:
                break
        if picked != 5:
            raise RuntimeError("L1 的 %s 只凑出 %d 道" % (key, picked))
    rng.shuffle(out)
    return out


def _outcome_recipes() -> List[Recipe]:
    out: List[Recipe] = []
    for total in range(4, 10):
        for ncolor in (1, 2, 3):
            for counts in _parts(total, ncolor):
                bag_colors = PALETTE[:ncolor]
                for target in PALETTE[:4]:
                    for ask in ("may", "certain"):
                        data = list(zip(bag_colors, counts))
                        target_count = dict(data).get(target, 0)
                        if ask == "certain" and target_count < total // 2:
                            # “一定”题也保留反例，但别让反例全挤在极端袋里。
                            pass
                        if ask == "may":
                            question = "闭眼摸一颗，可能摸到%s珠吗？" % c.name(target)
                        else:
                            question = "闭眼摸一颗，一定会摸到%s珠吗？" % c.name(target)
                        if ask == "may":
                            explain = ("袋里有 %d 颗%s珠，所以可能摸到。" % (target_count, c.name(target))
                                       if target_count else
                                       "袋里一颗%s珠也没有，所以不可能摸到。" % c.name(target))
                            hint = "先看看袋里有没有%s珠。" % c.name(target)
                        elif target_count == total:
                            explain = "袋里的每一颗都是%s珠，所以一定摸到它。" % c.name(target)
                            hint = "看看有没有别的颜色。"
                        else:
                            explain = "袋里还有别的颜色，所以不一定摸到%s珠。" % c.name(target)
                            hint = "可能发生，不等于每次都会发生。"
                        out.append(Recipe(
                            level=1,
                            title="可能还是一定？",
                            story="袋子里的珠子形状一样，只能看见颜色。",
                            kind="outcome",
                            question=question,
                            action="从袋里摸 3 颗，每次放回并摇匀。",
                            hint=hint,
                            explain=explain,
                            bags=[("神秘袋", data)],
                            target=target,
                            ask=ask,
                        ))
    return out


def _most_recipes(rng: random.Random) -> List[Recipe]:
    out: List[Recipe] = []
    for total in range(4, 13):
        for a in range(1, total):
            b = total - a
            if b <= 0 or a == b:
                continue
            pair = tuple(sorted((a, b), reverse=True))
            colors = rng.sample(PALETTE, 2)
            counts = [(colors[0], pair[0]), (colors[1], pair[1])]
            rng.shuffle(counts)
            majority = counts[0][0] if counts[0][1] > counts[1][1] else counts[1][0]
            out.append(Recipe(
                level=2,
                title="哪种颜色更常见？",
                story="袋里只有两种颜色的珠子，形状都一样。",
                kind="most",
                question="闭眼摸 10 次，每次放回摇匀。通常哪种颜色更容易摸到？",
                action="从袋里摸一颗、看一眼、放回、摇 3 下；重复 10 次。次数少时结果可能碰巧偏到一边。",
                hint="两种颜色在同一个袋子里，直接比较颗数，不靠几次结果猜。",
                explain="%s；%s珠更多，所以通常更容易摸到%s珠。"
                        % (_desc(counts), c.name(majority), c.name(majority)),
                bags=[("神秘袋", counts)],
            ))
    return out


def _compare_same_total_recipes(rng: random.Random) -> List[Recipe]:
    out: List[Recipe] = []
    for total in range(6, 10):
        for left_target in range(1, total):
            for right_target in range(1, total):
                if left_target == right_target:
                    continue
                if left_target + right_target > 10:
                    continue
                left_other = total - left_target
                right_other = total - right_target
                if left_other + right_other > 10:
                    continue
                target, other = rng.sample(PALETTE, 2)
                left_counts = [(target, left_target), (other, left_other)]
                right_counts = [(target, right_target), (other, right_other)]
                if rng.random() < 0.5:
                    bags = [("左边的袋子", left_counts), ("右边的袋子", right_counts)]
                else:
                    bags = [("左边的袋子", right_counts), ("右边的袋子", left_counts)]
                left_n = bags[0][1][0][1] if bags[0][1][0][0] == target else bags[0][1][1][1]
                right_n = bags[1][1][0][1] if bags[1][1][0][0] == target else bags[1][1][1][1]
                better = "左边的袋子" if left_n > right_n else "右边的袋子"
                out.append(Recipe(
                    level=3,
                    title="%s珠去哪只袋子？" % c.name(target),
                    story="两只袋子里的珠子总数一样，颜色组成不同。",
                    kind="compare",
                    question="从哪只袋子更容易摸到%s珠？" % c.name(target),
                    action="两只袋子轮流摸 10 次，每次放回并摇匀。结果不同也正常，结论看两只袋子的组成。",
                    hint="总数一样时，比一比目标颜色各有几颗。",
                    explain="两只袋子都有 %d 颗珠子；左边有 %d 颗%s珠，右边有 %d 颗。"
                            "%s目标珠更多，所以机会更大。"
                            % (total, left_n, c.name(target), right_n, better),
                    bags=bags,
                    target=target,
                ))
    return out


def _proportion_trap_recipes(rng: random.Random) -> List[Recipe]:
    out: List[Recipe] = []
    for small_total in range(5, 10):
        for big_total in range(small_total + 1, 13):
            for small_target in range(1, small_total):
                for big_target in range(small_target + 1, big_total):
                    if small_target + big_target > 10:
                        continue
                    small_other = small_total - small_target
                    big_other = big_total - big_target
                    if small_other + big_other > 10:
                        continue
                    if small_target / small_total <= big_target / big_total:
                        continue
                    target, other = rng.sample(PALETTE, 2)
                    rare = (small_total, small_target, small_other)
                    many = (big_total, big_target, big_other)
                    if rng.random() < 0.5:
                        bags = [
                            ("左边的袋子", [(target, rare[1]), (other, rare[2])]),
                            ("右边的袋子", [(target, many[1]), (other, many[2])]),
                        ]
                    else:
                        bags = [
                            ("左边的袋子", [(target, many[1]), (other, many[2])]),
                            ("右边的袋子", [(target, rare[1]), (other, rare[2])]),
                        ]
                    left_n = dict(bags[0][1]).get(target, 0)
                    right_n = dict(bags[1][1]).get(target, 0)
                    left_total = sum(n for _, n in bags[0][1])
                    right_total = sum(n for _, n in bags[1][1])
                    more_label = "左边的袋子" if left_n > right_n else "右边的袋子"
                    better_label = (
                        "左边的袋子"
                        if left_n / left_total > right_n / right_total
                        else "右边的袋子"
                    )
                    out.append(Recipe(
                        level=4,
                        title="袋子大就更占优吗？",
                        story="两只袋子的珠子总数不同，目标珠的颗数也不同；先看其他颜色的珠子多了多少。",
                        kind="compare",
                        question="从哪只袋子更容易摸到%s珠？" % c.name(target),
                        action="先猜，再从两只袋子各摸 10 次；每次放回并摇匀。结果不同也正常，结论看袋里的组成。",
                        hint="目标珠更多，不代表更容易；其他颜色的珠子也可能增加得更多。",
                        explain=(
                            "左袋%s，右袋%s。%s中%s珠更多，但它的其他颜色也更多，"
                            "把目标珠的机会冲淡了，所以%s更容易。"
                            % (_desc(bags[0][1]), _desc(bags[1][1]), more_label,
                               c.name(target), better_label)
                        ),
                        bags=bags,
                        target=target,
                    ))
    return out


def _equal_chance_recipes(rng: random.Random) -> List[Recipe]:
    fractions = ((1, 2), (1, 3), (2, 3), (1, 4), (2, 5), (3, 5))
    options: List[Tuple[Tuple[int, int], int, int, Tuple[int, ...]]] = []
    for numerator, denominator in fractions:
        for total in range(4, 13):
            if total * numerator % denominator:
                continue
            target = total * numerator // denominator
            rest = total - target
            if target <= 0 or rest <= 0:
                continue
            options.append(((numerator, denominator), total, target, (rest,)))
            if rest >= 2:
                for split in range(1, rest):
                    options.append(((numerator, denominator), total, target,
                                    (split, rest - split)))

    out: List[Recipe] = []
    for i, left in enumerate(options):
        for right in options[i + 1:]:
            if left[0] != right[0] or left[1] == right[1]:
                continue
            ratio_numerator, ratio_denominator = left[0]
            target, = rng.sample(PALETTE, 1)
            distractors = [x for x in PALETTE if x != target]
            rng.shuffle(distractors)
            left_counts = [(target, left[2])] + list(zip(distractors, left[3]))
            right_counts = [(target, right[2])] + list(zip(distractors, right[3]))
            if rng.random() < 0.5:
                bags = [("左边的袋子", left_counts), ("右边的袋子", right_counts)]
            else:
                bags = [("左边的袋子", right_counts), ("右边的袋子", left_counts)]
            out.append(Recipe(
                level=5,
                title="真的不一样吗？",
                story="两只袋子的总数不同，目标珠的颗数也不同。先看看它们能不能按同样的小组摆开。",
                kind="compare",
                question="从哪只袋子更容易摸到%s珠？" % c.name(target),
                action="先猜，再从两袋各摸 10 次；每次放回并摇匀。结果不同也正常，结论看分组方式。",
                hint="把珠子每 %d 颗看成一个小组，比较每个小组里有几颗%s珠。"
                     % (ratio_denominator, c.name(target)),
                explain="左袋%s，右袋%s。两只袋子都按每 %d 颗一组，每组有 %d 颗%s珠。"
                        "小组的组成一样，所以机会相同；摸到的结果不同也很正常。"
                        % (_desc(bags[0][1]), _desc(bags[1][1]),
                           ratio_denominator, ratio_numerator, c.name(target)),
                bags=bags,
                target=target,
            ))
    return out


def _race_recipes(rng: random.Random) -> List[Recipe]:
    """L6：三颗赛跑。孩子实际推进计分珠，不预设本轮赢家。"""
    plans = {
        "majority": ((7, 3), (7, 2), (7, 1), (6, 2), (6, 1)),
        "even": ((4, 4), (5, 5), (5, 4), (6, 5), (6, 6)),
        "upset": ((7, 3), (6, 4), (6, 3), (5, 3), (7, 4)),
        "rounds": ((5, 3, 2), (4, 4, 2), (6, 2, 2), (5, 4, 1), (4, 3, 3)),
    }
    out: List[Recipe] = []
    for ask, count_plan in plans.items():
        for counts_tuple in count_plan:
            colors = rng.sample(PALETTE, len(counts_tuple))
            counts = list(zip(colors, counts_tuple))
            ordered = sorted(counts, key=lambda row: row[1])
            words = "、".join("%s珠 %d 颗" % (c.name(bead), n) for bead, n in ordered)
            if ask == "majority":
                question = "先猜哪一种颜色更可能先到 3 颗，再开始摸珠。"
                explain = ("袋里%s。数量更多的颜色通常更容易先到 3 颗，但某一轮被少数颜色抢先，"
                           "也完全可能；袋子的组成并没有因此改变。" % words)
            elif ask == "even":
                question = "这些颜色看起来机会接近。先猜谁先到 3 颗，再连玩三局。"
                explain = ("袋里%s。颜色组成接近时，每种颜色的机会也接近；连玩几局可能出现同一个赢家，"
                           "也可能轮换，单轮结果不会固定成某种顺序。" % words)
            elif ask == "upset":
                question = "少数颜色也可能先到 3 颗。先猜会不会出现反超，再玩三轮。"
                explain = ("袋里%s。多数颜色通常更容易先到 3 颗，但少数颜色也可能抢先完成一轮；"
                           "这正是随机结果，不能因为一次反超就说袋里的组成变了。" % words)
            else:
                question = "同一袋连玩三轮。每轮赢家会一样吗？先猜，再看实际结果。"
                explain = ("袋里%s。每次摸完都放回并摇匀，上一轮谁赢不会改变下一轮的机会；"
                           "三轮的赢家可能相同，也可能不同。" % words)
            out.append(Recipe(
                level=6,
                title="三颗赛跑",
                story="用袋外剩下的同色珠做计分珠，每种颜色准备 3 颗。",
                kind="race",
                question=question,
                action="摸一颗、看一眼、放回、摇 3 下；摸到哪色就推该色一颗计分珠，先到 3 颗赢一轮。",
                hint="不用算数，只看哪一种颜色的珠子先排满三格。",
                explain=explain,
                bags=[("神秘袋", counts)],
                ask=ask,
            ))
    return out


def _choose_race(recipes: List[Recipe], rng: random.Random) -> List[Recipe]:
    """四类三颗赛跑各 5 道，总共 20 道。"""
    out: List[Recipe] = []
    seen = set()
    for ask in ("majority", "even", "upset", "rounds"):
        bucket = [recipe for recipe in recipes if recipe.ask == ask]
        rng.shuffle(bucket)
        picked = 0
        for recipe in bucket:
            try:
                _materialize(recipe, 0)
            except RuntimeError:
                continue
            shape = _shape(recipe)
            if shape in seen:
                continue
            seen.add(shape)
            out.append(recipe)
            picked += 1
            if picked == 5:
                break
        if picked != 5:
            raise RuntimeError("L6 的 %s 只凑出 %d 道" % (ask, picked))
    rng.shuffle(out)
    return out


def _independence_recipes(rng: random.Random) -> List[Recipe]:
    patterns = ("TTTT", "OOOO", "TOTOT", "OTOTO", "TTOT", "OOTOO",
                "TTOOTT", "OOTTO", "TTTTT", "OOOOO")
    out: List[Recipe] = []
    for total in range(5, 11):
        for a in range(1, total):
            b = total - a
            if b <= 0:
                continue
            target, other = rng.sample(PALETTE, 2)
            counts = [(target, a), (other, b)]
            for pattern in patterns:
                prior = [target if ch == "T" else other for ch in pattern]
                seq = _sequence_text(prior)
                out.append(Recipe(
                    level=7,
                    title="前面摸过，后面会变吗？",
                    story="下面记录的是刚才已经摸到的结果，每次摸完都放回去并摇匀了。",
                    kind="independence",
                    question="前面依次摸到%s。现在再摸一颗，摸到%s珠的机会会变大吗？"
                             % (seq, c.name(target)),
                    action="照着上面的记录再摸一颗；之前每次都已经放回并摇匀。",
                    hint="先想一想：袋子里的颜色组成有没有变？",
                    explain="不会。前面每次都已经放回并摇匀，袋里还是原来的 %d 颗珠子，"
                            "%s珠也还是 %d 颗；刚才碰巧摸到什么，不会让下一次更容易。"
                            % (total, c.name(target), a),
                    bags=[("神秘袋", counts)],
                    target=target,
                    prior=prior,
                ))
    return out


def _convergence_recipes(rng: random.Random) -> List[Recipe]:
    milestones = ((8, 24), (10, 30), (12, 30))
    out: List[Recipe] = []
    for total in range(5, 13):
        for a in range(1, total):
            b = total - a
            if b <= 0 or a == b:
                continue
            target = PALETTE[0] if a > b else PALETTE[1]
            other = next(bead for bead in PALETTE if bead != target)
            counts = [(target, max(a, b)), (other, min(a, b))]
            for first, final in milestones:
                out.append(Recipe(
                    level=8,
                    title="多摸几次更清楚吗？",
                    story="记录次数少时，结果容易碰巧偏到一边；多记一些通常更容易看出袋里的情况。",
                    kind="convergence",
                    question="先记录 %d 次，再继续累计到 %d 次；哪一份记录更容易看出哪种颜色更常见？"
                             % (first, final),
                    action="每次摸完都放回并摇匀。先摸 %d 次记两列，再继续摸到累计 %d 次。"
                           % (first, final),
                    hint="次数少，结果容易碰巧偏到一边；多记一些更有帮助。",
                    explain="摸得更多的那一份记录通常更容易看出哪种颜色更常见。%s；"
                            "少量试验可能碰巧偏到一边，多摸也不能保证每次都完全一样。"
                            % _desc(counts),
                    bags=[("神秘袋", counts)],
                    target=target,
                    first=first,
                    total=final,
                ))
    return out


def _without_replacement_recipes(rng: random.Random) -> List[Recipe]:
    patterns = ("T", "O", "TT", "OO", "TO", "OT", "TTO", "OOT", "OTO", "TOT")
    out: List[Recipe] = []
    for total in range(5, 11):
        for a in range(1, total):
            b = total - a
            if b <= 0:
                continue
            target, other = rng.sample(PALETTE, 2)
            counts = [(target, a), (other, b)]
            for pattern in patterns:
                removed = [target if ch == "T" else other for ch in pattern]
                if len(removed) >= total:
                    continue
                chosen = _sequence_text(removed)
                before_target = a
                before_total = total
                removed_target = removed.count(target)
                after_target = before_target - removed_target
                after_total = before_total - len(removed)
                before_other = before_total - before_target
                after_other = after_total - after_target
                before = before_target / before_total
                after = after_target / after_total
                if abs(before - after) < 1e-12:
                    change = "不变"
                    why = "目标珠和其他珠按同样的方式减少，分组关系没变，所以机会不变"
                elif after > before:
                    change = "变大"
                    why = "拿出的其他颜色更多，袋里剩下的珠子变少，目标珠更容易被摸到"
                else:
                    change = "变小"
                    why = "拿出的珠子里有%s珠，目标珠变少，所以机会变小" % c.name(target)
                out.append(Recipe(
                    level=9,
                    title="不放回会怎样？",
                    story="这一次摸出的珠子留在桌上，不再放回袋子。",
                    kind="without",
                    question="已经拿出%s，都不放回。现在再摸一颗，摸到%s珠的机会会怎样变化？"
                             % (chosen, c.name(target)),
                    action="先照题把%s拿出留在桌上，再摸下一颗。" % chosen,
                    hint="先看目标珠少了没有，再看其他颜色少了多少。",
                    explain="一开始袋里目标珠 %d 颗、其他珠 %d 颗；拿出后目标珠 %d 颗、其他珠 %d 颗。%s。"
                            % (before_target, before_other, after_target, after_other, why),
                    bags=[("神秘袋", counts)],
                    target=target,
                    removed=removed,
                ))
    return out


def _evidence_recipes() -> List[Recipe]:
    """L10：不计算，判断样本、随机波动、新信息和因果关系。"""
    rows = [
        {
            "ask": "missing",
            "title": "飞回来的飞机",
            "story": "统计员只能看到安全返航的飞机，并在机身上记录弹孔。",
            "evidence": [
                "返航飞机：机翼 8 处弹孔，机身 5 处，驾驶舱 0 处",
                "没有返航的飞机：没有任何记录",
            ],
            "question": "只凭这些返航飞机的弹孔，能直接说驾驶舱最安全吗？",
            "action": "用彩珠在纸飞机图上摆出弹孔，再讨论哪些飞机没有进入这张统计图。",
            "answer": "no",
            "conclusion": "不能，因为没有返航的飞机没有进入统计。",
            "hint": "先问：哪些飞机没有出现在记录里？",
            "explain": "驾驶舱没有弹孔，可能是因为真的安全，也可能是因为那里中弹的飞机没有飞回来。缺少未返航数据，不能直接下结论。",
        },
        {
            "ask": "missing",
            "title": "完成游戏的人",
            "story": "一个游戏只向完成全部十关的玩家发了问卷。",
            "evidence": [
                "收到 50 份问卷，其中 40 人说游戏很简单",
                "没有完成十关的玩家没有收到问卷",
            ],
            "question": "这些回答能代表第一次来玩的玩家吗？",
            "action": "把完成者的珠子放在左边，再想想哪些玩家没有珠子代表。",
            "answer": "no",
            "conclusion": "不能，问卷只看到了已经完成游戏的人。",
            "hint": "谁会更容易完成全部十关？",
            "explain": "愿意坚持到第十关的人可能本来就喜欢游戏或更熟练；没完成的玩家没有回答，样本已经经过筛选。",
        },
        {
            "ask": "missing",
            "title": "精彩集锦",
            "story": "一段篮球集锦剪进了十次投篮，每一次都命中。",
            "evidence": [
                "集锦里：10 次投篮，10 次命中",
                "没有投中的镜头全部被剪掉",
            ],
            "question": "能用这段集锦判断球员的真实命中率吗？",
            "action": "用 10 颗彩珠代表集锦，再挑出另一种颜色代表被剪掉的投篮。",
            "answer": "no",
            "conclusion": "不能，集锦只保留了成功结果。",
            "hint": "失败投篮去哪里了？",
            "explain": "集锦展示的是被挑出来的成功片段，不等于全部投篮记录。要估计命中率，需要把命中和没命中的次数都记下来。",
        },
        {
            "ask": "missing",
            "title": "只剩五星的评价",
            "story": "一家商店删除了所有一星到三星的评价，只留下五星。",
            "evidence": [
                "页面显示：80 条五星评价",
                "被删除的差评没有显示数量",
            ],
            "question": "看到全是五星，能说所有买过的人都满意吗？",
            "action": "用彩珠表示看到的五星，再用不透明的杯子盖住可能消失的评价。",
            "answer": "no",
            "conclusion": "不能，被删掉的评价也是买家体验的一部分。",
            "hint": "页面为什么一条低分都没有？",
            "explain": "低分评价被删除后，剩下的记录已经不代表全部买家。评价分布要先看数据是否完整。",
        },
        {
            "ask": "selection",
            "title": "游泳馆调查",
            "story": "有人在游泳馆调查了 50 个孩子：喜不喜欢游泳？",
            "evidence": [
                "48 个孩子回答喜欢",
                "调查地点只有正在游泳馆活动的孩子",
            ],
            "question": "48 个孩子喜欢，能说明所有孩子都喜欢游泳吗？",
            "action": "用彩珠代表 48 个“喜欢”，再想想不在这里的孩子要不要代表。",
            "answer": "no",
            "conclusion": "不能，在游泳馆调查会更容易遇到本来就喜欢游泳的孩子。",
            "hint": "谁最可能出现在游泳馆？",
            "explain": "调查地点先筛选了一遍人群。要了解所有孩子，需要从不同地点、不同兴趣的孩子中取样。",
        },
        {
            "ask": "selection",
            "title": "只问观众",
            "story": "老师在比赛结束后，只调查了坐在第一排的观众。",
            "evidence": [
                "第一排 10 人都说比赛很精彩",
                "后排观众和没来看比赛的人没有被调查",
            ],
            "question": "能用这 10 个人判断所有人对比赛的评价吗？",
            "action": "把 10 颗珠子放在展示区，再留一个空盒代表没有接受调查的人。",
            "answer": "no",
            "conclusion": "不能，样本只包含坐在第一排的人。",
            "hint": "还有哪些人没有接受调查？",
            "explain": "第一排观众可能和后排、没来的人有不同想法。样本范围太窄，就不能代表全部人。",
        },
        {
            "ask": "selection",
            "title": "大鱼网",
            "story": "有人用网眼很大的渔网调查池塘里的鱼。",
            "evidence": [
                "抓到 10 条鱼，每条都很大",
                "小鱼可能从大网眼里游走",
            ],
            "question": "能根据这 10 条大鱼说池塘里没有小鱼吗？",
            "action": "用大珠和小珠当鱼，检查这个“网”会把哪一种留下。",
            "answer": "no",
            "conclusion": "不能，捕鱼工具先把小鱼筛掉了。",
            "hint": "捉不到是因为不存在，还是因为工具抓不住？",
            "explain": "样本受到工具筛选。看到鱼都大，可能只是小鱼没有被网留下，不能说明池塘里没有小鱼。",
        },
        {
            "ask": "selection",
            "title": "爱好者论坛",
            "story": "一个游戏论坛里，大家讨论这个游戏时都很积极。",
            "evidence": [
                "论坛调查中，90% 的人说很喜欢这个游戏",
                "调查对象只是主动登录论坛的用户",
            ],
            "question": "能说所有玩过游戏的人都喜欢它吗？",
            "action": "把论坛用户放一堆，再想想删除游戏、没登录的人放在哪里。",
            "answer": "no",
            "conclusion": "不能，论坛用户只是玩过的人中很特别的一部分。",
            "hint": "不喜欢的人会不会更容易离开论坛？",
            "explain": "愿意长期参与论坛的人通常更感兴趣；不喜欢的用户可能早就离开了。调查结果只代表留下来发言的人。",
        },
        {
            "ask": "streak",
            "title": "连续五颗红珠",
            "story": "袋子的组成没有变化，每次摸完都放回并摇匀。",
            "evidence": [
                "刚才连续摸到 5 颗红珠",
                "每次摸完都放回并摇匀",
            ],
            "question": "连续出现红珠后，下一次蓝珠会变得更容易吗？",
            "action": "用彩珠做一次有放回的摸珠，发现连续结果后停下来讨论。",
            "answer": "same",
            "conclusion": "不会，袋里的组成没变，下一次机会仍然和原来一样。",
            "hint": "先问袋子有没有改变。",
            "explain": "连续红珠可以让结果看起来很特别，但只要每次都放回并摇匀，袋子就没有记住刚才的结果。",
        },
        {
            "ask": "streak",
            "title": "连续五次正面",
            "story": "一枚硬币连续掷出五次正面，硬币没有被改变。",
            "evidence": [
                "前五次结果：正、正、正、正、正",
                "硬币是同一枚普通硬币",
            ],
            "question": "第六次一定更可能是反面吗？",
            "action": "用彩珠代表正反面，记录几次连续结果，但不要按“该轮到反面”猜。",
            "answer": "no",
            "conclusion": "不一定，前面的结果不会让硬币自动更想出现反面。",
            "hint": "硬币会记得前面掷过什么吗？",
            "explain": "如果硬币每次掷出的条件相同，前面出现正面并不会改变下一次；连续正面只是可能发生的随机序列。",
        },
        {
            "ask": "streak",
            "title": "三个红点连成线",
            "story": "一张随机点阵图上，正好有三个红点挨在一起。",
            "evidence": [
                "点阵里很多位置随机放了红点和蓝点",
                "其中三个红点形成一条直线",
            ],
            "question": "看到三个红点排成线，就一定是有人故意设计吗？",
            "action": "撒一把彩珠，看看随机摆放时会不会偶尔出现成串、成堆的样子。",
            "answer": "no",
            "conclusion": "不一定，随机结果里偶尔也会出现看起来有规律的小团块。",
            "hint": "随机是不是意味着每次都必须东一个、西一个？",
            "explain": "随机会产生局部聚集。只凭一小处看起来整齐，不足以证明背后有设计；要比较整体数量和重复实验的结果。",
        },
        {
            "ask": "streak",
            "title": "四投全中",
            "story": "一个孩子连续投进四球，大家说他今天进入了“手感状态”。",
            "evidence": [
                "最近四次投篮全部命中",
                "之前和之后的投篮没有完整记录",
            ],
            "question": "只凭四次全中，能确定他的真实能力突然提高了吗？",
            "action": "用四种颜色的珠子记录命中与未命中，继续多投几轮再比较。",
            "answer": "no",
            "conclusion": "不能，四投全中可能只是短时间内的巧合。",
            "hint": "四次的样本够不够？",
            "explain": "短时间连续成功很引人注意，但需要更多次记录才能判断能力是否真的改变。不能只看最精彩的一小段。",
        },
        {
            "ask": "update",
            "title": "三只盒子",
            "story": "三只盒子中只有一只藏着星星，孩子先选中了左边。",
            "evidence": [
                "朋友打开中间盒子，里面是空的",
                "三只盒子中仍然只有一只藏星星",
            ],
            "question": "知道中间是空的以后，需要重新判断另外两只盒子吗？",
            "action": "用三颗不同颜色的珠子代表盒子，拿走已经确认没有星星的那一颗。",
            "answer": "change",
            "conclusion": "需要重新判断，因为一个可能的位置已经被排除。",
            "hint": "新信息减少了哪些可能？",
            "explain": "知道中间是空的以后，星星只剩两个可能位置。现在还不能确定在哪只盒子里，但对盒子的判断已经改变。",
        },
        {
            "ask": "update",
            "title": "拿走一颗蓝珠",
            "story": "袋里原来有 3 颗橙珠和 3 颗蓝珠。",
            "evidence": [
                "已经摸出 1 颗蓝珠",
                "这颗蓝珠不放回",
            ],
            "question": "现在再摸一颗，摸到橙珠的机会有变化吗？",
            "action": "用彩珠还原袋子，拿走一颗蓝珠，再比较剩下的橙珠和蓝珠数量。",
            "answer": "change",
            "conclusion": "有变化，蓝珠少了一颗，剩下橙珠的数量相对更多。",
            "hint": "橙珠少了吗？蓝珠少了吗？",
            "explain": "拿走的是一颗蓝珠，橙珠仍然是 3 颗，但袋里的其他珠子少了一颗，所以橙珠在下一次摸珠中更突出了。",
        },
        {
            "ask": "update",
            "title": "朋友确认过",
            "story": "一个朋友隔着袋子猜里面有黄珠，另一个朋友打开看了一眼，说确实有。",
            "evidence": [
                "第一个朋友只是猜",
                "第二个朋友现场看过并确认",
            ],
            "question": "两个说法都出现后，你更应该相信哪一个？",
            "action": "用彩珠和挡板模拟“猜”和“亲眼看”两种信息来源。",
            "answer": "yes",
            "conclusion": "更应该相信亲自看过的朋友，因为信息来源经过了确认。",
            "hint": "一个消息是猜的，另一个经过了什么？",
            "explain": "新信息不仅要有内容，还要看来源是否可靠。已经实际检查过的信息，比没有依据的猜测更值得相信。",
        },
        {
            "ask": "update",
            "title": "换了一个说法",
            "story": "小盒里有一颗奖品，朋友只说“不在第一盒”。",
            "evidence": [
                "奖品原本可能在三个盒子里",
                "新的确定信息说明：第一盒没有",
            ],
            "question": "听到这个确定信息后，三个盒子仍然完全一样吗？",
            "action": "摆三颗彩珠代表盒子，把已经被排除的颜色拿走。",
            "answer": "change",
            "conclusion": "不一样了，第一盒已经被排除，判断范围变小了。",
            "hint": "新的确定信息排除了什么？",
            "explain": "得到可靠的新信息后，原来的可能结果会减少。即使还不能确定答案，也不应该继续把已排除的选项当成同等可能。",
        },
        {
            "ask": "cause",
            "title": "雨伞和湿地",
            "story": "统计发现，雨天街上雨伞多，地面也更容易湿。",
            "evidence": [
                "雨伞多的日子，地面经常是湿的",
                "雨伞和湿地面常常一起出现",
            ],
            "question": "能说雨伞把地面弄湿了吗？",
            "action": "用蓝色珠子代表雨、黄色代表雨伞、灰色代表湿地，看看谁可能同时带来前两样。",
            "answer": "not-cause",
            "conclusion": "不能，下雨可能同时造成大家带伞和地面变湿。",
            "hint": "有没有第三个原因同时影响两件事？",
            "explain": "两件事经常一起出现，不代表一件造成另一件。雨可能同时解释了雨伞和湿地面。",
        },
        {
            "ask": "cause",
            "title": "冰淇淋和晒伤",
            "story": "统计发现，冰淇淋卖得多的日子，晒伤的人也更多。",
            "evidence": [
                "晴天时冰淇淋销量较高",
                "晴天时户外活动更多，晒伤也更常见",
            ],
            "question": "能说吃冰淇淋会导致晒伤吗？",
            "action": "用同一种颜色的珠子标记晴天，分别用它连接冰淇淋和晒伤记录。",
            "answer": "not-cause",
            "conclusion": "不能，晴天可能是两件事背后共同的原因。",
            "hint": "两件事共同受什么条件影响？",
            "explain": "晴天既能让人更想买冰淇淋，也会让更多人在户外活动。只有共同出现的记录，不足以说明其中一件造成另一件。",
        },
        {
            "ask": "cause",
            "title": "幸运袜",
            "story": "一支球队换了红袜子后连赢三场，队员说袜子带来了好运。",
            "evidence": [
                "穿红袜子的三场都赢了",
                "穿其他袜子时的比赛结果没有被完整比较",
            ],
            "question": "能确定是红袜子让球队获胜吗？",
            "action": "用彩珠分别记录不同袜子和胜负，先确认两种条件下的全部比赛。",
            "answer": "not-cause",
            "conclusion": "不能，还需要比较穿和不穿红袜子时的全部结果。",
            "hint": "是否缺少另一种情况的记录？",
            "explain": "只挑出连胜的三场，不能看出袜子是否真的影响结果。要比较两种情况的完整记录，还要考虑对手、队员状态等其他因素。",
        },
        {
            "ask": "cause",
            "title": "个子高和鞋码大",
            "story": "统计发现，个子高的孩子通常鞋码也更大。",
            "evidence": [
                "身高较大的孩子，鞋码通常也较大",
                "观察结果来自不同年龄、不同成长阶段的孩子",
            ],
            "question": "能说鞋码大让孩子长得更高吗？",
            "action": "用彩珠给不同年龄的孩子分组，观察年龄是不是同时影响身高和鞋码。",
            "answer": "not-cause",
            "conclusion": "不能，年龄或成长会同时影响身高和鞋码。",
            "hint": "孩子的年龄有没有同时影响两件事？",
            "explain": "身高和鞋码一起变大，可能是因为孩子一起长大。相关记录能提示共同变化，但不能直接证明其中一项造成另一项。",
        },
    ]
    return [
        Recipe(
            level=10,
            title=row["title"],
            story=row["story"],
            kind="evidence",
            question=row["question"],
            action=row["action"],
            hint=row["hint"],
            explain=row["explain"],
            bags=[],
            ask=row["ask"],
            evidence=row["evidence"],
            conclusion=row["conclusion"],
            answer_code=row["answer"],
        )
        for row in rows
    ]


def build_all() -> List[Tuple[str, k.Card]]:
    rng = random.Random(20261024)
    groups: List[List[Recipe]] = [
        _choose_outcome(_outcome_recipes(), rng),
        _choose(_most_recipes(rng), rng),
        _choose(_compare_same_total_recipes(rng), rng),
        _choose(_proportion_trap_recipes(rng), rng),
        _choose(_equal_chance_recipes(rng), rng),
        _choose_race(_race_recipes(rng), rng),
        _choose(_independence_recipes(rng), rng),
        _choose(_convergence_recipes(rng), rng),
        _choose(_without_replacement_recipes(rng), rng),
        _choose(_evidence_recipes(), rng),
    ]
    selected = [recipe for group in groups for recipe in group]
    rng.shuffle(selected)
    selected.sort(key=lambda recipe: recipe.level)
    out: List[Tuple[str, k.Card]] = []
    for serial, recipe in enumerate(selected, 1):
        out.append(_materialize(recipe, serial))
    return out


def write_all(items: List[Tuple[str, k.Card]], root: Path, fresh: bool) -> None:
    root = root.resolve()
    expected = (k.GAME_DIR / "puzzles").resolve()
    if root != expected:
        raise RuntimeError("为了安全，只写 %s；收到 %s" % (expected, root))
    if fresh and root.exists():
        for path in root.glob("*/*.txt"):
            path.unlink()
    for text, card in items:
        path = root / str(card.level) / ("%s.txt" % card.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="生成彩珠机会屋十档题库")
    parser.add_argument("--out", default=str(k.PUZZLE_DIR), help="题库目录")
    parser.add_argument("--fresh", action="store_true",
                        help="先删掉目标目录里的旧 .txt，再生成整套")
    args = parser.parse_args(argv)
    try:
        items = build_all()
        write_all(items, Path(args.out), args.fresh)
    except Exception as exc:
        print("× 生成失败：%s" % exc, file=sys.stderr)
        return 1
    print("已生成 %d 道题卡：%s" % (len(items), args.out))
    for row in k.list_levels(Path(args.out)):
        print("  L%d %-9s %d 道"
              % (row["level"], k.LEVEL_NAMES.get(row["level"], ""), row["count"]))
    problems = k.check(Path(args.out))
    if problems:
        for problem in problems:
            print("× " + problem)
        return 1
    print("题库检查全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
