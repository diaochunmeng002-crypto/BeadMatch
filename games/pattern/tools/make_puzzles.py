"""找规律：批量出题（默认每档 20 道），写完顺手用 `core/cards.py` 验一遍。

**每道题的形状都不一样。** 同一档里 20 道题的形状签名（`cards.shape_key`：单元长度/
组成、给了几颗、空位在哪、组数怎么变、镜像几颗……**不含颜色**）不能重复 —— 所以不是
"一道题换个颜色说 20 遍"。档和档之间才是难度差别：L1 补下一颗、L2 接三颗、L3 补中间……

    python -m games.pattern.tools.make_puzzles              # 每档补到 20 道（手写题不动）
    python -m games.pattern.tools.make_puzzles --fresh      # 先删掉"以前生成的"，再重新出一版
    python -m games.pattern.tools.make_puzzles --per 10     # 只想每档 10 道
    python -m games.pattern.tools.make_puzzles --seed 7     # 换一批随机

`--fresh` 只删 **生成出来的**（文件里有 `generator=make_puzzles@…`）；手写题
（`created_by=manual`）会留着。
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..core import cards as k
from ..core import colors as c

GAME_DIR = Path(__file__).resolve().parent.parent
PUZZLE_DIR = GAME_DIR / "puzzles"

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


def _unit(pattern: str, rng: random.Random) -> str:
    """`"aab"` → 把 a/b 换成两种不同的随机颜色（颜色不复用）。"""
    pool = rng.sample(c.LETTERS, len(set(pattern)))
    letters: Dict[str, str] = {}
    out: List[str] = []
    for ch in pattern:
        if ch not in letters:
            letters[ch] = pool[len(letters)]
        out.append(letters[ch])
    return "".join(out)


def _groups(counts: Sequence[int], unit: str) -> List[List[str]]:
    return [[unit[i % len(unit)]] * n for i, n in enumerate(counts)]


def _groups_desc(groups: Sequence[Sequence[str]]) -> str:
    return "，".join("%d颗%s色" % (len(g), c.name(g[0]) if g else "?") for g in groups)


def _card(kind: str, unit: str, counts: str, shown: str, answer: str,
          title: str, story: str, rule: str, fix: str = "") -> Dict[str, Any]:
    return {"kind": kind, "unit": unit, "counts": counts, "shown": shown,
            "answer": answer, "title": title, "story": story, "rule": rule,
            "fix": fix}


def _new_id(level: int, n: int, seed: int) -> str:
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


# --------------------------------------------------------------------------
# 每一档：抽一个"形状"再长成一道题（形状跟颜色无关）
# --------------------------------------------------------------------------


def make_1(rng: random.Random) -> Optional[Dict[str, Any]]:
    """L1·重复单元（2~4 颗、颜色都不一样），补下一颗。"""
    noun, word, verb = _theme(rng)
    size = rng.randint(2, 4)
    unit = "".join(rng.sample(c.LETTERS, size))
    given = rng.randint(size + 2, 12)
    full = repeat_unit(unit, given + 1)
    tail = {2: "排队", 3: "轮着排", 4: "四个一伙"}[size]
    how = {2: "一颗接一颗", 3: "三种颜色轮着来", 4: "四颗一组、颜色都不一样"}[size]
    return _card(
        "repeat", unit, "", "".join(full[:given]) + "?", full[given],
        noun + tail,
        "假装这些是%s：%s…… %s。下一%s该是什么颜色？"
        % (noun, names(full[:given]), how, word),
        "%d颗一循环：%s。" % (size, "、".join(c.name(ch) for ch in unit)),
    )


def make_2(rng: random.Random) -> Optional[Dict[str, Any]]:
    """L2·单元三/四颗、里面有一对同色，接下三颗。"""
    noun, word, verb = _theme(rng)
    pattern = rng.choice(["aab", "abb", "aaab", "abbb", "aabb"])
    unit = _unit(pattern, rng)
    given = rng.randint(len(unit) + 3, 12)
    full = repeat_unit(unit, given + 3)
    title = {"aab": "两个一样的", "abb": "后面两个", "aaab": "三个一样的",
             "abbb": "一串三个", "aabb": "两个两个换"}[pattern]
    return _card(
        "repeat", unit, "", "".join(full[:given]) + "???",
        "".join(full[given:given + 3]),
        "%s%s" % (noun, title),
        "假装这些是%s：%s…… 这一小段里有相同的颜色。接下来三%s是什么颜色？"
        % (noun, names(full[:given]), word),
        "%d颗一循环：%s。" % (len(unit), "、".join(c.name(ch) for ch in unit)),
    )


def make_3(rng: random.Random) -> Optional[Dict[str, Any]]:
    """L3·同一串循环，中间挖掉一颗。"""
    noun, word, verb = _theme(rng)
    pattern = rng.choice(["ab", "abc", "aab", "abb", "abcd"])
    unit = _unit(pattern, rng)
    n = rng.randint(max(8, len(unit) + 4), 12)
    full = repeat_unit(unit, n)
    at = rng.randrange(1, n - 1)
    return _card(
        "repeat", unit, "", "".join(full[:at] + ["?"] + full[at + 1:]), full[at],
        "%s谁的位置空了" % noun,
        "假装这些是%s：%s。中间空了一个位置，空着的那个该是什么颜色？"
        % (noun, names(full)),
        "%d颗一循环：%s。空着的那一格正好轮到%s。"
        % (len(unit), "、".join(c.name(ch) for ch in unit), c.name(full[at])),
    )


def make_4(rng: random.Random) -> Optional[Dict[str, Any]]:
    """L4·一组比一组多（起点 1~4、步长 1~2），摆下一组。"""
    noun, word, verb = _theme(rng)
    start = rng.randint(1, 4)
    step = rng.randint(1, 2)
    total = rng.randint(3, 4)
    unit = "".join(rng.sample(c.LETTERS, rng.randint(2, 3)))
    counts = [start + step * i for i in range(total)]
    if max(counts) > 10:
        return None
    groups = _groups(counts, unit)
    return _card(
        "groups", unit, ",".join(map(str, counts)),
        "/".join("".join(g) for g in groups[:-1]) + "/?", "".join(groups[-1]),
        "%s越来越多" % noun,
        "假装这些是%s：%s。下一群该有几%s、什么颜色？"
        % (noun, _groups_desc(groups[:-1]), word),
        "每组比上一组多%d颗（%s），颜色按%s循环。"
        % (step, "、".join(map(str, counts)), "、".join(c.name(ch) for ch in unit)),
    )


def make_5(rng: random.Random) -> Optional[Dict[str, Any]]:
    """L5·一组比一组少（步长 1~2），摆最后两组。"""
    noun, word, verb = _theme(rng)
    step = rng.randint(1, 2)
    total = rng.randint(3, 5)
    top = rng.randint(3, 7)
    unit = "".join(rng.sample(c.LETTERS, rng.randint(2, 3)))
    counts = [top - step * i for i in range(total)]
    if counts[-1] < 1:
        return None
    groups = _groups(counts, unit)
    blanks = min(2, total - 1)
    shown = groups[:total - blanks]
    return _card(
        "groups", unit, ",".join(map(str, counts)),
        "/".join("".join(g) for g in shown) + "/?" * blanks,
        "".join("".join(g) for g in groups[total - blanks:]),
        "%s越来越少" % noun,
        "假装这些是%s：%s。这次一群比一群少%d%s，后面%s怎么摆？"
        % (noun, _groups_desc(shown), step,
           "颗", "两群" if blanks == 2 else "一群"),
        "一组比一组少%d颗（%s），颜色按%s循环。"
        % (step, "、".join(map(str, counts)), "、".join(c.name(ch) for ch in unit)),
    )


def make_6(rng: random.Random) -> Optional[Dict[str, Any]]:
    """L6·每组多取几种新颜色（前缀增长，起点/步长/取到第几组都可变）。"""
    noun, word, verb = _theme(rng)
    ncolors = rng.randint(3, 6)
    start = rng.randint(1, 2)
    step = rng.randint(1, 2)
    if start + step > ncolors:
        return None
    limit = rng.randint(start + step, ncolors)
    counts = list(range(start, limit + 1, step))
    if len(counts) < 2:
        return None
    order = "".join(rng.sample(c.LETTERS, ncolors))
    groups = [list(order[:n]) for n in counts]
    return _card(
        "prefix", order, ",".join(map(str, counts)),
        "/".join("".join(g) for g in groups[:-1]) + "/?", "".join(groups[-1]),
        "%s学新颜色" % noun,
        "假装这些是%s：%s…… 每群比前一群多%s，颜色也一次多用一种。下一群是什么？"
        % (noun, _groups_desc(groups[:-1]),
           "一颗" if step == 1 else "两颗"),
        "每组比上一组多取%d种颜色，顺序是%s。"
        % (step, "、".join(c.name(ch) for ch in order)),
    )


def make_7(rng: random.Random) -> Optional[Dict[str, Any]]:
    """L7·循环里放错一颗（单元 2~4 颗，错的在哪一颗随机）。"""
    noun, word, verb = _theme(rng)
    pattern = rng.choice(["ab", "abc", "aab", "abb", "aabb"])
    unit = _unit(pattern, rng)
    n = rng.randint(8, 10)
    full = repeat_unit(unit, n)
    at = rng.randrange(n)
    wrong = rng.choice([ch for ch in c.LETTERS if ch != full[at]])
    broken = list(full)
    broken[at] = wrong
    return _card(
        "repeat", unit, "", "".join(broken), "",
        "%s站错队" % noun,
        "假装这些是%s：%s。队伍里有一%s站错了颜色，第几%s错了？该改成什么颜色？"
        % (noun, names(broken), word, word),
        "%d颗一循环：%s。有一颗站错了队，把它改回来就顺了。"
        % (len(unit), "、".join(c.name(ch) for ch in unit)),
        fix="%d:%s>%s" % (at + 1, wrong, full[at]),
    )


def make_8(rng: random.Random) -> Optional[Dict[str, Any]]:
    """L8·每群是上一群的几倍（2 或 3 倍，起点/给了几群都可变）。"""
    noun, word, verb = _theme(rng)
    mult = rng.choice([2, 3])
    start = rng.randint(1, 3)
    shown = rng.randint(1, 3)
    unit = "".join(rng.sample(c.LETTERS, rng.randint(2, 3)))
    counts = [start * mult ** i for i in range(shown + 1)]
    if max(counts) > 10:
        return None
    groups = _groups(counts, unit)
    return _card(
        "groups", unit, ",".join(map(str, counts)),
        "/".join("".join(g) for g in groups[:-1]) + "/?", "".join(groups[-1]),
        "%s翻%d倍" % (noun, mult),
        "假装这些是%s：%s。每一群都是上一群的%d倍，下一群几%s、什么颜色？"
        % (noun, _groups_desc(groups[:-1]), mult, word),
        "每一组都是上一组的%d倍（%s），颜色按%s循环。"
        % (mult, "、".join(map(str, counts)), "、".join(c.name(ch) for ch in unit)),
    )


def make_9(rng: random.Random) -> Optional[Dict[str, Any]]:
    """L9·镜像单元（走到头往回走），镜像几颗、多给几颗都可变。"""
    noun, word, verb = _theme(rng)
    size = rng.randint(2, 6)
    extra = rng.randint(0, 3)
    colors = rng.sample(c.LETTERS, size)
    unit = "".join(colors) + "".join(reversed(colors))
    given = len(unit) + extra
    full = repeat_unit(unit, given + 1)
    return _card(
        "repeat", unit, "", "".join(full[:given]) + "?", full[given],
        "%s照镜子" % noun,
        "假装这些是%s：%s…… 排到最中间就往回走，像照镜子。下一%s是什么颜色？"
        % (noun, names(full[:given]), word),
        "%d颗一组，走到头就反过来走：%s……" % (len(unit), names(list(unit))),
    )


def make_10(rng: random.Random) -> Optional[Dict[str, Any]]:
    """L10·复合：一群少一颗（fix）+ 摆下一群（answer）。"""
    noun, word, verb = _theme(rng)
    start = rng.randint(1, 3)
    step = rng.randint(1, 2)
    total = rng.randint(3, 5)          # 3~5 组，形状空间才够 20 个
    counts = [start + step * i for i in range(total)]
    if max(counts) > 10:
        return None
    unit = "".join(rng.sample(c.LETTERS, rng.randint(2, 3)))
    groups = _groups(counts, unit)
    short = rng.randrange(1, total - 1)
    shown = [list(g) for g in groups[:-1]]
    shown[short] = shown[short][:-1]
    pos = sum(len(g) for g in shown[:short + 1])
    return _card(
        "groups", unit, ",".join(map(str, counts)),
        "/".join("".join(g) for g in shown) + "/?", "".join(groups[-1]),
        "%s少了一个" % noun,
        "假装这些是%s：%s…… 有一群少摆了一%s。先找出少的那一%s，再摆出下一群。"
        % (noun, _groups_desc(shown), word, word),
        "每组比上一组多%d颗（%s），颜色按%s循环 —— 有一组少摆了一颗。"
        % (step, "、".join(map(str, counts)), "、".join(c.name(ch) for ch in unit)),
        fix="%d:+%s" % (pos, unit[short % len(unit)]),
    )


MAKERS: Dict[int, Callable[[random.Random], Optional[Dict[str, Any]]]] = {
    1: make_1, 2: make_2, 3: make_3, 4: make_4, 5: make_5,
    6: make_6, 7: make_7, 8: make_8, 9: make_9, 10: make_10,
}


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------


def _is_generated(path: Path) -> bool:
    try:
        return "generator=make_puzzles@" in path.read_text(encoding="utf-8")
    except OSError:
        return False


def fill_level(root: Path, level: int, per: int, seed: int, created_at: str,
               fresh: bool = False) -> Tuple[int, int]:
    """把某一档补到 `per` 道（**形状不重复**），返回 (新写几道, 删掉几道)。"""
    folder = Path(root) / str(level)
    folder.mkdir(parents=True, exist_ok=True)
    removed = 0
    if fresh:
        for path in sorted(folder.glob("*.txt")):
            if _is_generated(path):
                path.unlink()
                removed += 1

    existing = sorted(folder.glob("*.txt"))
    seen = {k.shape_key(k.load_card(p)) for p in existing}
    n = len(existing)
    added = 0
    rng = random.Random(seed * 1000 + level)
    misses = 0
    while n < per:
        fields = MAKERS[level](rng)
        if not fields:
            misses += 1
            if misses > 3000:
                raise SystemExit("第 %d 档凑不出 %d 个不同形状了（形状空间不够）" % (level, per))
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
            if misses > 3000:
                raise SystemExit("第 %d 档凑不出 %d 个不同形状了（形状空间不够）" % (level, per))
            continue
        sig = k.shape_key(card)
        if sig in seen:                       # 同一档里"形状"不能重复
            path.unlink()
            misses += 1
            if misses > 3000:
                raise SystemExit("第 %d 档凑不出 %d 个不同形状了（形状空间不够）" % (level, per))
            continue
        seen.add(sig)
        n += 1
        added += 1
    return added, removed


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="找规律：批量出题（默认每档 20 道）")
    parser.add_argument("--dir", default=str(PUZZLE_DIR), help="题库目录（默认 %s）" % PUZZLE_DIR)
    parser.add_argument("--per", type=int, default=20, help="每档补到几道（默认 20）")
    parser.add_argument("--seed", type=int, default=17, help="随机种子（同种子出同一批）")
    parser.add_argument("--fresh", action="store_true",
                        help="先删掉以前生成的（手写题留着），重新出一版")
    args = parser.parse_args(argv)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total_added = total_removed = 0
    for level in range(1, 11):
        added, removed = fill_level(Path(args.dir), level, args.per, args.seed,
                                    created_at, args.fresh)
        total_added += added
        total_removed += removed
        cards = [k.load_card(p) for p in sorted((Path(args.dir) / str(level)).glob("*.txt"))]
        shapes = {k.shape_key(card) for card in cards if not card.problems}
        print("第 %2d 档：新写 %d 道，形状 %d 种 / %d 道%s"
              % (level, added, len(shapes), len(cards),
                 ("，删掉旧的 %d 道" % removed) if removed else ""))
    print("一共新写 %d 道%s，题库在 %s"
          % (total_added, ("（删掉旧的 %d 道）" % total_removed) if total_removed else "",
             args.dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
