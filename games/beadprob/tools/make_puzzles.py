"""生成彩珠机会屋九档题库，每档 20 道。

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
    return "|".join(parts)


def _text(recipe: Recipe, card_id: str) -> str:
    lines = [
        "# colors: " + c.header(),
        "",
        "created_at=" + DATE,
        "created_by=beadprob",
        "generator=make_puzzles@1",
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
    if recipe.first:
        lines.append("first=" + str(recipe.first))
        lines.append("total=" + str(recipe.total))
    return "\n".join(lines)


def _materialize(recipe: Recipe, serial: int) -> Tuple[str, k.Card]:
    stamp = START + timedelta(minutes=serial * 2)
    card_id = "%s-%04x" % (stamp.strftime("%Y%m%d-%H%M%S"), serial)
    base = _text(recipe, card_id)
    probe = k.parse_card(base, Path("%s.txt" % card_id))
    answer = k.infer_answer(probe)
    if recipe.kind != "race" and not answer:
        raise RuntimeError("算不出答案：L%d《%s》" % (recipe.level, recipe.title))
    answer_line = "" if recipe.kind == "race" else "\nanswer=" + answer
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
                question="闭眼摸 5 次，每次放回摇匀。通常哪种颜色更容易摸到？",
                action="从袋里摸一颗、看一眼、放回、摇 3 下；重复 5 次。",
                hint="两种颜色在同一个袋子里，直接比较颗数。",
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
                    action="两只袋子轮流摸 5 次，每次放回并摇匀。",
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
                    out.append(Recipe(
                        level=4,
                        title="袋子大就更占优吗？",
                        story="两只袋子的总数不同，目标颜色的颗数也不同。",
                        kind="compare",
                        question="从哪只袋子更容易摸到%s珠？" % c.name(target),
                        action="先猜，再从两只袋子各摸 5 次；每次放回并摇匀。",
                        hint="目标珠更多，不一定占的比例更大。",
                        explain="左袋%s，右袋%s。目标珠更多的那只袋子，不一定更容易摸到它。"
                                % (_desc(bags[0][1]), _desc(bags[1][1])),
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
                story="两只袋子的总数不同，但目标颜色所占的比例相同。",
                kind="compare",
                question="从哪只袋子更容易摸到%s珠？" % c.name(target),
                action="先猜，再从两袋各摸 5 次；每次放回并摇匀。",
                hint="别只看总颗数，要比较目标颜色占多少。",
                explain="左袋%s，右袋%s。两只袋子里%s珠所占的比例一样，"
                        "所以机会相同；各摸几次得到的结果不同也很正常。"
                        % (_desc(bags[0][1]), _desc(bags[1][1]), c.name(target)),
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
                    explain="不会。每次放回并摇匀后，袋子都恢复原样，%s珠仍然是 %d 颗中的 %d 颗；"
                            "前面碰巧摸到什么，不会让下一次更容易。"
                            % (c.name(target), total, a),
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
                    title="多摸几次会更清楚吗？",
                    story="小样本会有波动，多记录一些结果通常更有帮助。",
                    kind="convergence",
                    question="先记录 %d 次，再继续累计到 %d 次；哪一份累计记录通常更接近袋里的比例？"
                             % (first, final),
                    action="每次摸完都放回并摇匀。先摸 %d 次记两列，再继续摸到累计 %d 次。"
                           % (first, final),
                    hint="不是保证完全一样，而是通常会更接近。",
                    explain="摸得更多的那一份累计记录通常更接近袋里的真实比例。%s；"
                            "少量试验容易碰巧偏到一边，但不能保证最后一定完全一样。"
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
                before = before_target / before_total
                after = after_target / after_total
                if abs(before - after) < 1e-12:
                    change = "不变"
                    why = "拿出的珠子里，目标颜色所占的比例和袋里原来一样，所以下一次机会不变"
                elif after > before:
                    change = "变大"
                    why = "拿出的珠子里%s珠较少，剩下的%s珠所占比例变大" % (
                        c.name(target), c.name(target))
                else:
                    change = "变小"
                    why = "拿出的珠子里有%s珠，剩下的%s珠所占比例变小" % (
                        c.name(target), c.name(target))
                out.append(Recipe(
                    level=9,
                    title="不放回会怎样？",
                    story="这一次摸出的珠子留在桌上，不再放回袋子。",
                    kind="without",
                    question="已经拿出%s，都不放回。现在再摸一颗，摸到%s珠的机会会怎样变化？"
                             % (chosen, c.name(target)),
                    action="先照题把%s拿出留在桌上，再摸下一颗。" % chosen,
                    hint="先看目标珠少了几颗，再看袋里总数少了几颗。",
                    explain="一开始袋里%s；拿出后剩下 %d 颗，其中%s珠 %d 颗。%s。"
                            % (_desc(counts), after_total, c.name(target),
                               after_target, why),
                    bags=[("神秘袋", counts)],
                    target=target,
                    removed=removed,
                ))
    return out


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
    parser = argparse.ArgumentParser(description="生成彩珠机会屋九档题库")
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
