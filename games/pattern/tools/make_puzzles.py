"""找规律：批量出题（默认每档 20 道），写完顺手用 `core/cards.py` 验一遍。

    python -m games.pattern.tools.make_puzzles              # 每档补到 20 道（已有的不动）
    python -m games.pattern.tools.make_puzzles --per 10     # 只想每档 10 道
    python -m games.pattern.tools.make_puzzles --seed 7     # 换一批随机
    python -m games.pattern.tools.make_puzzles --dir <目录>  # 写到别处（试玩用）

思路：每一档有固定的"规律模板"，随机挑颜色 / 起点 / 题面长度，再配一句小故事
（假装是小汽车、小皮球、气球……）。**写完立刻读一遍**（`cards.load_card`），
有毛病就删掉重来 —— 所以落盘的一定是过检查命令的题。

已有的题（比如手写的那 10 道）不会动；每档只补到 `--per` 道。
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..core import cards as k
from ..core import colors as c

GAME_DIR = Path(__file__).resolve().parent.parent
PUZZLE_DIR = GAME_DIR / "puzzles"

# (叫什么, 量词, 动词) —— 小故事就从这里挑
THEMES: List[Tuple[str, str, str]] = [
    ("小汽车", "辆", "开过来"),
    ("小皮球", "个", "滚过来"),
    ("气球", "个", "飘过来"),
    ("小鸭子", "只", "游过来"),
    ("糖球", "颗", "排过来"),
    ("小火车", "节", "挂上来"),
    ("积木", "块", "摆过来"),
    ("小蘑菇", "朵", "冒出来"),
    ("小雨滴", "滴", "落下来"),
    ("小星星", "颗", "闪过来"),
    ("小铃铛", "个", "跳过来"),
    ("跳跳球", "个", "弹过来"),
]


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------


def names(beads: Sequence[str]) -> str:
    return "、".join(c.name(ch) for ch in beads)


def repeat_unit(unit: str, n: int) -> List[str]:
    return [unit[i % len(unit)] for i in range(n)]


def _theme(rng: random.Random) -> Tuple[str, str, str]:
    return rng.choice(THEMES)


def _new_id(level: int, n: int, seed: int) -> str:
    """`<日期>-<时间>-<4位>`：时间那一节用「11:档:序号」，4 位用种子算。"""
    stamp = "11%02d%02d" % (level, n)
    tail = "%04x" % ((level * 257 + n * 13 + seed) & 0xFFFF)
    return "20261017-%s-%s" % (stamp, tail)


def _write_card(path: Path, fields: Dict[str, Any]) -> None:
    order = ("created_at", "created_by", "generator", "id", "level", "title", "story",
             "kind", "unit", "counts", "shown", "answer", "fix", "rule")
    lines = ["# colors: " + c.header(), ""]
    for key in order:
        value = fields.get(key)
        if value is None or value == "":
            continue
        lines.append("%s=%s" % (key, value))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _groups_desc(groups: Sequence[Sequence[str]]) -> str:
    """「1颗红色，2颗蓝色…」这种说法（写进小故事用）。"""
    return "，".join("%d颗%s色" % (len(g), c.name(g[0]) if g else "?") for g in groups)


# --------------------------------------------------------------------------
# 十档的模板：每一档只新加一个想法（跟 README 的阶梯表一一对应）
# --------------------------------------------------------------------------


def build_1(rng: random.Random) -> Dict[str, Any]:
    """两色一循环，补下一颗。"""
    noun, word, verb = _theme(rng)
    a, b = rng.sample(c.LETTERS, 2)
    unit = a + b if rng.random() < 0.5 else b + a
    given = rng.choice([5, 6, 7, 8, 9])
    full = repeat_unit(unit, given + 1)
    return {
        "kind": "repeat", "unit": unit,
        "shown": "".join(full[:given]) + "?",
        "answer": full[given],
        "title": "%s排队" % noun,
        "story": "假装这些是%s：%s，一%s接一%s%s。下一%s该是什么颜色？"
                 % (noun, names(full[:given]), word, word, verb, word),
        "rule": "两颗一循环：%s、%s、%s、%s……"
                % (c.name(unit[0]), c.name(unit[1]), c.name(unit[0]), c.name(unit[1])),
    }


def build_2(rng: random.Random) -> Dict[str, Any]:
    """三颗一循环（其中两颗同色），接下三颗。"""
    noun, word, verb = _theme(rng)
    a, b = rng.sample(c.LETTERS, 2)
    unit = a + a + b if rng.random() < 0.5 else a + b + b
    given = rng.choice([7, 8, 9, 10])
    full = repeat_unit(unit, given + 3)
    return {
        "kind": "repeat", "unit": unit,
        "shown": "".join(full[:given]) + "???",
        "answer": "".join(full[given:given + 3]),
        "title": "%s三个一组" % noun,
        "story": "假装这些是%s：%s…… 每三%s一组。接下来三%s该是什么颜色？"
                 % (noun, names(full[:given]), word, word),
        "rule": "三颗一循环：%s、%s、%s。"
                % (c.name(unit[0]), c.name(unit[1]), c.name(unit[2])),
    }


def build_3(rng: random.Random) -> Dict[str, Any]:
    """同样是循环，但空位在中间：补上缺的那一颗。"""
    noun, word, verb = _theme(rng)
    unit = "".join(rng.sample(c.LETTERS, 3))
    n = rng.choice([8, 9, 10])
    full = repeat_unit(unit, n)
    at = rng.randrange(1, n - 1)                 # 不摆在头尾，才是"中间缺一颗"
    shown = full[:at] + ["?"] + full[at + 1:]
    return {
        "kind": "repeat", "unit": unit,
        "shown": "".join(shown),
        "answer": full[at],
        "title": "%s谁的位置空了" % noun,
        "story": "假装这些是%s：%s。队伍中间空了一个位置，空着的那个该是什么颜色？"
                 % (noun, names(full)),
        "rule": "三颗一循环：%s、%s、%s。空着的那一格正好轮到%s。"
                % (c.name(unit[0]), c.name(unit[1]), c.name(unit[2]), c.name(full[at])),
    }


def build_4(rng: random.Random) -> Dict[str, Any]:
    """一组一种颜色，颗数 1、2、3、4（递增），摆下一组。"""
    noun, word, verb = _theme(rng)
    a, b = rng.sample(c.LETTERS, 2)
    unit = a + b if rng.random() < 0.5 else b + a
    counts = [1, 2, 3, 4]
    colors = [unit[i % 2] for i in range(4)]
    groups = [[colors[i]] * counts[i] for i in range(4)]
    shown = groups[:3]
    return {
        "kind": "groups", "unit": unit, "counts": "1,2,3,4",
        "shown": "/".join("".join(g) for g in shown) + "/?",
        "answer": "".join(groups[3]),
        "title": "%s越来越多" % noun,
        "story": "假装这些是%s：%s。下一群该有几%s、什么颜色？"
                 % (noun, _groups_desc(shown), word),
        "rule": "每组比上一组多一颗，颜色%s、%s交替（1、2、3、4）。"
                % (c.name(unit[0]), c.name(unit[1])),
    }


def build_5(rng: random.Random) -> Dict[str, Any]:
    """颗数反过来：5、4、3、2、1，摆后面两群。"""
    noun, word, verb = _theme(rng)
    a, b = rng.sample(c.LETTERS, 2)
    unit = a + b if rng.random() < 0.5 else b + a
    counts = [5, 4, 3, 2, 1]
    colors = [unit[i % 2] for i in range(5)]
    groups = [[colors[i]] * counts[i] for i in range(5)]
    return {
        "kind": "groups", "unit": unit, "counts": "5,4,3,2,1",
        "shown": "/".join("".join(g) for g in groups[:3]) + "/?/?",
        "answer": "".join(groups[3]) + "".join(groups[4]),
        "title": "%s越来越少" % noun,
        "story": "假装这些是%s：%s。这次一群比一群少一%s，后面两群怎么摆？"
                 % (noun, _groups_desc(groups[:3]), word),
        "rule": "这回一组比一组少一颗：5、4、3、2、1，颜色%s、%s交替。"
                % (c.name(unit[0]), c.name(unit[1])),
    }


def build_6(rng: random.Random) -> Dict[str, Any]:
    """每组多取一种新颜色（前缀增长），摆下一组。"""
    noun, word, verb = _theme(rng)
    ncolors = rng.choice([5, 6])
    order = "".join(rng.sample(c.LETTERS, ncolors))
    groups = [list(order[:i]) for i in range(1, ncolors + 1)]
    return {
        "kind": "prefix", "unit": order,
        "counts": ",".join(str(i) for i in range(1, ncolors + 1)),
        "shown": "/".join("".join(g) for g in groups[:-1]) + "/?",
        "answer": "".join(groups[-1]),
        "title": "%s学新颜色" % noun,
        "story": "假装这些是%s：%s…… 每群比前一群多一%s，颜色也一次多用一种。下一群是什么？"
                 % (noun, _groups_desc(groups[:-1]), word),
        "rule": "每组比上一组多一颗，颜色按%s的顺序往后取。"
                % "、".join(c.name(ch) for ch in order),
    }


def build_7(rng: random.Random) -> Dict[str, Any]:
    """找错：循环里有且只有一颗站错了。"""
    noun, word, verb = _theme(rng)
    if rng.random() < 0.5:
        a, b = rng.sample(c.LETTERS, 2)
        unit = a + a + b if rng.random() < 0.5 else a + b + b
    else:
        unit = "".join(rng.sample(c.LETTERS, 3))
    full = repeat_unit(unit, 9)
    at = rng.randrange(9)
    wrong = rng.choice([ch for ch in c.LETTERS if ch != full[at]])
    broken = list(full)
    broken[at] = wrong
    return {
        "kind": "repeat", "unit": unit,
        "shown": "".join(broken),
        "fix": "%d:%s>%s" % (at + 1, wrong, full[at]),
        "title": "%s站错队" % noun,
        "story": "假装这些是%s：%s。队伍里有一%s站错了颜色，第几%s错了？该改成什么颜色？"
                 % (noun, names(broken), word, word),
        "rule": "三颗一循环：%s…… 有一颗站错了队，把它改回来就顺了。"
                % names(full[:len(unit)]),
    }


def build_8(rng: random.Random) -> Dict[str, Any]:
    """每群是上一群的两倍：1、2、4、8。"""
    noun, word, verb = _theme(rng)
    a, b = rng.sample(c.LETTERS, 2)
    unit = a + b if rng.random() < 0.5 else b + a
    counts = [1, 2, 4, 8]
    colors = [unit[i % 2] for i in range(4)]
    groups = [[colors[i]] * counts[i] for i in range(4)]
    return {
        "kind": "groups", "unit": unit, "counts": "1,2,4,8",
        "shown": "/".join("".join(g) for g in groups[:3]) + "/?",
        "answer": "".join(groups[3]),
        "title": "%s翻一倍" % noun,
        "story": "假装这些是%s：%s。每一群都是上一群的两倍，下一群几%s、什么颜色？"
                 % (noun, _groups_desc(groups[:3]), word),
        "rule": "每一组都是上一组的两倍：1、2、4、8，颜色%s、%s交替。"
                % (c.name(unit[0]), c.name(unit[1])),
    }


def build_9(rng: random.Random) -> Dict[str, Any]:
    """镜像单元：走到头就反过来走（红蓝绿绿蓝红）。"""
    noun, word, verb = _theme(rng)
    a, b, d = rng.sample(c.LETTERS, 3)
    unit = a + b + d + d + b + a
    given = len(unit) + rng.choice([1, 2])
    full = repeat_unit(unit, given + 1)
    return {
        "kind": "repeat", "unit": unit,
        "shown": "".join(full[:given]) + "?",
        "answer": full[given],
        "title": "%s照镜子" % noun,
        "story": "假装这些是%s：%s…… 排到最中间就往回走，像照镜子。下一%s是什么颜色？"
                 % (noun, names(full[:given]), word),
        "rule": "六颗一组，走到头就反过来走：%s……" % names(list(unit)),
    }


def build_10(rng: random.Random) -> Dict[str, Any]:
    """复合：一群少一颗（fix），再摆下一群（answer）。"""
    noun, word, verb = _theme(rng)
    a, b = rng.sample(c.LETTERS, 2)
    unit = a + b if rng.random() < 0.5 else b + a
    counts = [1, 2, 3, 4]
    colors = [unit[i % 2] for i in range(4)]
    groups = [[colors[i]] * counts[i] for i in range(4)]
    short = rng.choice([1, 2])                    # 第 2 或第 3 群少一颗
    shown_groups = [list(g) for g in groups[:3]]
    shown_groups[short] = shown_groups[short][:-1]
    pos = sum(len(g) for g in shown_groups[:short + 1])   # 少的那群最后一颗（1 起）
    return {
        "kind": "groups", "unit": unit, "counts": "1,2,3,4",
        "shown": "/".join("".join(g) for g in shown_groups) + "/?",
        "fix": "%d:+%s" % (pos, colors[short]),
        "answer": "".join(groups[3]),
        "title": "%s少了一个" % noun,
        "story": "假装这些是%s：%s…… 有一群少摆了一%s。先找出少的那一%s，再摆出下一群。"
                 % (noun, _groups_desc(shown_groups), word, word),
        "rule": "每组比上一组多一颗，颜色%s、%s交替 —— 有一组少摆了一颗。"
                % (c.name(unit[0]), c.name(unit[1])),
    }


BUILDERS = {i: globals()["build_%d" % i] for i in range(1, 11)}


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------


def _signature(card: k.Card) -> str:
    return "|".join([card.kind, card.unit, card.meta.get("counts", ""),
                     card.meta.get("shown", ""), card.meta.get("fix", "")])


def fill_level(root: Path, level: int, per: int, seed: int, created_at: str) -> int:
    """把某一档补到 `per` 道，返回这次新写了几道。"""
    folder = Path(root) / str(level)
    folder.mkdir(parents=True, exist_ok=True)
    existing = sorted(folder.glob("*.txt"))
    seen = {_signature(k.load_card(p)) for p in existing}
    n = len(existing)
    added = 0
    rng = random.Random(seed * 1000 + level)
    misses = 0
    while n < per:
        fields = BUILDERS[level](rng)
        sig = "|".join([fields["kind"], fields["unit"], fields.get("counts", ""),
                        fields["shown"], fields.get("fix", "")])
        if sig in seen:
            misses += 1
            if misses > 400:
                raise SystemExit("第 %d 档老是撞题，换个 --seed 试试" % level)
            continue
        card_id = _new_id(level, n, seed)
        path = folder / (card_id + ".txt")
        if path.exists():
            n += 1
            continue
        fields.update({
            "created_at": created_at, "created_by": "pattern",
            "generator": "make_puzzles@1", "id": card_id, "level": level,
        })
        _write_card(path, fields)
        card = k.load_card(path)
        if card.problems:
            path.unlink()
            misses += 1
            continue
        seen.add(_signature(card))
        n += 1
        added += 1
    return added


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="找规律：批量出题（默认每档 20 道）")
    parser.add_argument("--dir", default=str(PUZZLE_DIR), help="题库目录（默认 %s）" % PUZZLE_DIR)
    parser.add_argument("--per", type=int, default=20, help="每档补到几道（默认 20）")
    parser.add_argument("--seed", type=int, default=17, help="随机种子（同种子出同一批）")
    args = parser.parse_args(argv)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total = 0
    for level in range(1, 11):
        added = fill_level(Path(args.dir), level, args.per, args.seed, created_at)
        total += added
        print("第 %2d 档：新写 %d 道" % (level, added))
    print("一共新写 %d 道，题库在 %s" % (total, args.dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
