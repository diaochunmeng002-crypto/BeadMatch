"""找规律的题库：读、列、校验。

## 题目文件长这样（注释区 + 元信息区，照其他四个游戏的写法）

    # colors: Yellow Green Red Purple Blue Orange

    created_at=2026-10-17 10:01:01
    created_by=manual
    id=20261017-100101-1a01
    level=1
    title=红蓝排队
    kind=repeat
    unit=RB
    shown=RBRBR?
    answer=B
    rule=两颗一循环：红、蓝、红、蓝……

## 字段

* 通用：`id` / `level` / `title` / `kind` / `shown` / `rule`
  （`created_at` / `created_by` 给历史页的「出题者」那栏用，手写题写 `manual`）
* `story=` —— 可选：一句情境（"假装是小汽车一辆辆开过来……"），页面显示在题目名下面
* `kind` 说的是**形状 + 规律类型**（三种）：
  * `repeat` —— 一条直线上的循环：要 `unit=<重复单元>`（`RB` / `RRB` / `RBGGBR`）
  * `groups` —— 一组一种颜色、每组的颗数在变：要 `unit=<颜色循环>` + `counts=1,2,3,4`
  * `prefix` —— 每组把颜色顺序再往后多取一种：要 `unit=<颜色顺序>` + `counts=1,2,3,4,5`
* `fix=` **可选，跟 kind 正交**：题面里有一颗放错了（或少了一颗）→ `fix=<位置>:<改法>`
  （`8:B>R` = 第 8 颗该是红；`5:+R` = 第 5 颗后面补一颗红 —— `+` 只用在分组题上）
  带 `fix` 的题，"唯一解"检查会额外把「只动一颗」的改法全试一遍。
* `shown`  —— 题面：珠子紧挨着写，**分组用 `/`**，空位写 `?`
  （分组题里一个 `?` 占一整行 = "这一组空着"；直线题里一个 `?` 就是一颗）
* `answer` —— 空位里该是什么（按顺序写；`fix` 类不用写）

## 检查命令盯的三件事

1. **字段齐、id 跟文件名一致、level 跟所在目录一致**；
2. **题面 + 答案跟写明的那条规律完全对得上**（拿 `unit` / `counts` 算一遍完整序列，逐位比）；
3. **答案唯一**：
   * `repeat` / `fix`：整条序列（含答案）的**最短周期**必须正好是 `len(unit)`
     —— 有更短的周期，说明这题还能用另一种更简单的规律解释，得改；
   * `fix`：把「只动一颗」的所有改法都试一遍（换色 + 补一颗），**恰好一种**能修好；
   * `groups` / `prefix`：唯一性由 `unit + counts` 直接决定，检查的是"题面与答案跟它一致"。

再加一条**物理上限**：实物珠子每种颜色只有 10 颗（一共 60 颗），
题面 + 答案加起来不能超 —— 超了孩子就摆不出来。

命令行（开发时自查用）：

    python -m games.pattern.core.cards              # 把题库整个检查一遍
    python -m games.pattern.core.cards --list       # 列出来
    python -m games.pattern.core.cards --show <题目文件>
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import colors as c

GAME_DIR = Path(__file__).resolve().parent.parent
PUZZLE_DIR = GAME_DIR / "puzzles"

KINDS = ("repeat", "groups", "prefix")
LINE_KINDS = ("repeat",)                # 一条直线（题面只有一行）
GROUP_KINDS = ("groups", "prefix")      # 分组（一行 = 一组）
REQUIRED = ("id", "level", "title", "kind", "shown", "rule")

_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
_FIX_RE = re.compile(r"^\s*(\d+)\s*:\s*(?:([A-Za-z])\s*>\s*([A-Za-z])|\+\s*([A-Za-z]))\s*$")


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------


@dataclass
class Card:
    """一道题（读进来 + 算好之后的样子）。"""

    path: Path
    meta: Dict[str, str] = field(default_factory=dict)
    rows: List[List[Optional[str]]] = field(default_factory=list)   # 题面：一行一组，None = 空位
    blank_groups: List[int] = field(default_factory=list)           # 哪几行是"整组空着"
    full: List[str] = field(default_factory=list)                   # 规律算出来的完整珠子序列
    answer: List[str] = field(default_factory=list)                 # 空位按顺序该是什么
    fix: Optional[Dict[str, Any]] = None                            # {'pos','kind','from','to'|'bead'}
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
    def rule(self) -> str:
        return self.meta.get("rule", "")

    @property
    def unit(self) -> str:
        return _unit(self.meta)

    @property
    def counts(self) -> List[int]:
        return _counts(self.meta)

    @property
    def blank_count(self) -> int:
        """空位一共有几颗（分组题里一整组空着，按 counts 展开数）。"""
        n = 0
        for i, row in enumerate(self.rows):
            if i in self.blank_groups:
                n += self.counts[i] if i < len(self.counts) else 0
            else:
                n += sum(1 for x in row if x is None)
        return n

    @property
    def blank_at_end(self) -> bool:
        """空位是不是全在最后（分组题整组空着都算"在最后"）。"""
        seen_blank = False
        for i, row in enumerate(self.rows):
            if i in self.blank_groups or any(x is None for x in row):
                seen_blank = True
            elif seen_blank:
                return False
        return True

    @property
    def task(self) -> str:
        """页面上那句任务说明 —— 由题目的形状算出来，前端不用自己判断。"""
        extra = ""
        if self.fix:
            extra = "先找出放错的那一颗：说出是第几颗、该是什么颜色，再改正"
        n = self.blank_count
        if not n:
            return extra
        if self.kind in GROUP_KINDS:
            main = "说说下一组该有几颗、什么颜色，再用实物珠子摆出来"
        elif not self.blank_at_end:
            main = "补上缺了的那一颗"
        elif n == 1:
            main = "补上下一颗"
        else:
            main = "摆出接下来的 %d 颗" % n
        return (extra + "；再" + main) if extra else main


# --------------------------------------------------------------------------
# 读
# --------------------------------------------------------------------------


def _parse_meta(text: str) -> Tuple[Dict[str, str], List[str]]:
    """`键=值` 一行一条（`#` 开头是注释）→ (meta, 问题)。"""
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
        meta[key.strip()] = value.strip()
    return meta, problems


def _parse_shown(text: str) -> List[List[Optional[str]]]:
    """`RBRBR?` → [[R,B,R,B,R,None]]；`R/BB/RR?` → [[R],[B,B],[R,R,None]]"""
    rows: List[List[Optional[str]]] = []
    for seg in (text or "").split("/"):
        seg = seg.replace(" ", "").replace("　", "")
        if not seg:
            continue
        row: List[Optional[str]] = []
        for ch in seg:
            if ch == "?":
                row.append(None)
            elif c.is_color(ch):
                row.append(ch.upper())
            else:
                raise ValueError("题面里有不认识的字符：%r" % ch)
        rows.append(row)
    return rows


def _unit(meta: Dict[str, str]) -> str:
    return re.sub(r"[\s,]+", "", (meta.get("unit") or "")).upper()


def _counts(meta: Dict[str, str]) -> List[int]:
    raw = (meta.get("counts") or "").strip()
    if not raw:
        return []
    return [int(x) for x in re.split(r"[\s,]+", raw) if x]


def parse_fix(text: str) -> Dict[str, Any]:
    """`8:B>R` / `5:+R` → dict。"""
    m = _FIX_RE.match(text or "")
    if not m:
        raise ValueError("fix 写法不对：%r（要 `8:B>R` 或 `5:+R`）" % text)
    pos = int(m.group(1))
    if m.group(2):
        return {"pos": pos, "kind": "swap", "from": m.group(2).upper(), "to": m.group(3).upper()}
    return {"pos": pos, "kind": "add", "bead": m.group(4).upper()}


def apply_fix(beads: Sequence[str], fix: Dict[str, Any]) -> List[str]:
    """把 fix 用上去：`swap` = 把第 pos 颗换成 to；`add` = 第 pos 颗**后面**补一颗。

    位置从 1 起，按**题面里已经给的珠子**数（空位不算）。
    """
    out = [str(x) for x in beads]
    pos = int(fix["pos"])
    if fix["kind"] == "swap":
        if pos < 1 or pos > len(out):
            raise ValueError("fix 里说第 %d 颗，可题面只有 %d 颗" % (pos, len(out)))
        if out[pos - 1] != fix["from"]:
            raise ValueError("fix 里说第 %d 颗是 %s，可题面上那颗是 %s"
                             % (pos, c.name(fix["from"]), c.name(out[pos - 1])))
        out[pos - 1] = fix["to"]
        return out
    if pos < 0 or pos > len(out):
        raise ValueError("fix 里说在第 %d 颗后面补，可题面只有 %d 颗" % (pos, len(out)))
    out.insert(pos, fix["bead"])
    return out


def apply_fix_to_tokens(tokens: List[Optional[str]], fix: Dict[str, Any]) -> List[Optional[str]]:
    """把 fix 用到"展开成格子"的题面上：位置按**已给的珠子**数（从 1 起），空位不算。

    （`apply_fix` 只认珠子串；这里要保留空位的位置，好跟完整序列逐格比。）
    """
    idxs = [i for i, tok in enumerate(tokens) if tok is not None]
    pos = int(fix["pos"])
    if fix["kind"] == "swap":
        if pos < 1 or pos > len(idxs):
            raise ValueError("fix 里说第 %d 颗，可题面只给了 %d 颗" % (pos, len(idxs)))
        at = idxs[pos - 1]
        if tokens[at] != fix["from"]:
            raise ValueError("fix 里说第 %d 颗是 %s，可题面上那颗是 %s"
                             % (pos, c.name(fix["from"]), c.name(tokens[at] or "")))
        tokens[at] = fix["to"]
        return tokens
    if pos < 0 or pos > len(idxs):
        raise ValueError("fix 里说在第 %d 颗后面补，可题面只给了 %d 颗" % (pos, len(idxs)))
    tokens.insert(idxs[pos - 1] + 1 if pos else 0, fix["bead"])
    return tokens


def _matches(tokens: Sequence[Optional[str]], full: Sequence[str]) -> bool:
    """题面（空位跳过）跟完整序列对得上吗。"""
    if len(tokens) != len(full):
        return False
    return all(tok is None or tok == want for tok, want in zip(tokens, full))


def expected_sequence(meta: Dict[str, str], rows: List[List[Optional[str]]]) -> List[str]:
    """按写明的那条规律，把**完整序列**（含答案）算出来。"""
    kind = (meta.get("kind") or "").strip()
    unit = _unit(meta)
    counts = _counts(meta)
    if kind in GROUP_KINDS:
        out: List[str] = []
        for i, n in enumerate(counts):
            color = unit[i % len(unit)]
            out.extend(list(unit[:n]) if kind == "prefix" else [color] * n)
        return out
    length = sum(len(row) for row in rows)      # 直线：一个位置一颗（空位也算一格）
    return [unit[i % len(unit)] for i in range(length)]


def _shown_beads(card: Card) -> List[str]:
    """题面里**已经给的**珠子（按顺序，空位不算）。"""
    return [x for row in card.rows for x in row if x is not None]


def shortest_unit(seq: Sequence[str]) -> int:
    """最短单元：最小的 p，让整条序列都等于"某个 p 颗的单元无限重复"的前 len 颗。

    注意 p 允许比一半长：9 颗的 `RBGGBR RBG`（6 颗一循环）最短单元就是 6。
    找不到更短的（哪怕等于全长）就返回 len —— 那意味着"单元 = 整条"。
    """
    n = len(seq)
    for p in range(1, n + 1):
        if all(seq[i] == seq[i % p] for i in range(n)):
            return p
    return n


def load_card(path: Path) -> Card:
    """读一道题，顺手把「这道题自己有没有毛病」都收进 `card.problems`。"""
    path = Path(path)
    card = Card(path=path)
    text = path.read_text(encoding="utf-8")
    meta, problems = _parse_meta(text)
    card.meta = meta
    card.problems.extend(problems)

    for key in REQUIRED:
        if key not in meta:
            card.problems.append("少了 `%s=`" % key)
    if card.problems:
        return card

    if card.kind not in KINDS:
        card.problems.append("kind=%s 不认识（只能是 %s）" % (card.kind, " / ".join(KINDS)))
        return card

    # 题面
    try:
        card.rows = _parse_shown(meta.get("shown", ""))
    except ValueError as exc:
        card.problems.append(str(exc))
        return card
    if not card.rows:
        card.problems.append("shown 是空的")
        return card
    card.blank_groups = [i for i, row in enumerate(card.rows) if row == [None]]

    # 规律
    unit = card.unit
    counts = card.counts
    if not unit:
        card.problems.append("少了 `unit=`（重复单元 / 颜色顺序）")
    for ch in unit:
        if not c.is_color(ch):
            card.problems.append("unit=%s 里有不是颜色的字符：%r" % (unit, ch))
    if len(set(unit)) != len(unit) and card.kind == "prefix":
        card.problems.append("prefix 的 unit=%s 有重复颜色 —— 每组要「每次多一种新颜色」" % unit)
    if card.kind in GROUP_KINDS:
        if not counts:
            card.problems.append("分组题要 `counts=`（每组的颗数，例：1,2,3,4）")
        elif len(counts) != len(card.rows):
            card.problems.append("有 %d 组，可 counts 写了 %d 个" % (len(card.rows), len(counts)))
        if card.kind == "prefix":
            if counts != sorted(counts) or len(set(counts)) != len(counts):
                card.problems.append("prefix 的 counts=%s 得是递增的（每组多取一种颜色）" % counts)
            if counts and counts[-1] > len(unit):
                card.problems.append("counts 里有 %d，可 unit 只有 %d 种颜色" % (counts[-1], len(unit)))
    elif len(card.rows) != 1:
        card.problems.append("%s 是「一条直线」的题型，题面不能分组（别写 `/`）" % card.kind)

    # fix（可选，跟 kind 正交）
    if (meta.get("fix") or "").strip():
        try:
            card.fix = parse_fix(meta["fix"])
        except ValueError as exc:
            card.problems.append(str(exc))
        if card.fix and card.fix["kind"] == "add" and card.kind in LINE_KINDS:
            card.problems.append("`+X`（补一颗）只能用在分组题上：直线题补一颗会把后面全挪位")
    if card.problems:
        return card

    # 完整序列 + 空位
    card.full = expected_sequence(meta, card.rows)
    tokens = _tokens(card)          # 题面展开：None 分开数着（分组整组空 → 展开成 counts 个 None）
    raw = list(tokens)
    if card.fix:
        if not card.blank_at_end:
            card.problems.append("带 fix 的题，空位得排在最后（fix 的位置是按「已给的珠子」数的）")
        try:
            apply_fix_to_tokens(tokens, card.fix)
        except ValueError as exc:
            card.problems.append(str(exc))
            return card
        if _matches(raw, card.full):
            card.problems.append("题面上说「有一颗放错了」，可它本来就对 —— fix 白写了")
    if len(tokens) != len(card.full):
        card.problems.append("题面（%d 格，含空位）跟规律算出来的 %d 颗对不上"
                             % (len(tokens), len(card.full)))
        return card
    for i, (tok, want) in enumerate(zip(tokens, card.full)):
        if tok is not None and tok != want:
            card.problems.append("第 %d 格是 %s，可按规律该是 %s（这颗是不是该用 fix= 标出来？）"
                                 % (i + 1, c.name(tok), c.name(want)))
    card.answer = [card.full[i] for i, tok in enumerate(tokens) if tok is None]
    written = re.sub(r"[\s,]+", "", (meta.get("answer") or "")).upper()
    if written and written != "".join(card.answer):
        card.problems.append("answer 写的是 %s，可按规律空位该是 %s"
                             % (written, "".join(card.answer)))
    if card.answer and not written:
        card.problems.append("少了 `answer=`（空位里该是什么颜色）")
    if written and not card.answer:
        card.problems.append("题面里没有空位，可写了 `answer=%s`" % written)

    _check_limits(card)
    _check_unique(card)
    return card


def _tokens(card: Card) -> List[Optional[str]]:
    """题面展开成一格一格：分组题里"整组空着"按 counts 展开成那么多个 None。"""
    out: List[Optional[str]] = []
    for i, row in enumerate(card.rows):
        if i in card.blank_groups:
            out.extend([None] * (card.counts[i] if i < len(card.counts) else 1))
        else:
            out.extend(row)
    return out


def _check_limits(card: Card) -> None:
    """物理上限：每种颜色手上有 10 颗。"""
    for ch in c.LETTERS:
        n = card.full.count(ch)
        if n > c.PER_COLOR:
            card.problems.append("%s色要 %d 颗，可手上一共只有 %d 颗"
                                 % (c.name(ch), n, c.PER_COLOR))


def _check_unique(card: Card) -> None:
    """答案唯不唯一。"""
    unit = card.unit
    if card.kind == "repeat":
        if len(card.full) < len(unit):
            card.problems.append("整道题（含答案）只有 %d 颗，摆不满一个 %r 的单元 —— 看不出来"
                                 % (len(card.full), unit))
        p = shortest_unit(card.full)
        if p < len(unit):
            card.problems.append("这条序列还有更短的周期 %d 颗（%s）—— 说明它也能用另一种更简单的规律解释，"
                                 "答案就不唯一了" % (p, "".join(card.full[:p])))
        elif p > len(unit):
            card.problems.append("按 unit=%s 排出来，最短周期却是 %d 颗 —— 单元写错了吧"
                                 % (unit, p))
    if card.fix:
        given = _shown_beads(card)
        # 注意：同一份结果可能有好几种说法（"第 3 颗后面补红" 和 "第 4 颗后面补红" 摆出来一模一样），
        # 所以按**结果序列**去重 —— 唯一解指的是"只能摆出一种样子"，不是"只能说一种话"。
        results: Dict[str, List[str]] = {}
        for i in range(len(given)):                       # 换一颗
            for ch in c.LETTERS:
                if ch == given[i]:
                    continue
                cand = list(given)
                cand[i] = ch
                if _is_prefix(cand, card.full):
                    results.setdefault("".join(cand), []).append(
                        "第%d颗%s→%s" % (i + 1, c.name(given[i]), c.name(ch)))
        for pos in range(len(given) + 1):                 # 补一颗
            for ch in c.LETTERS:
                cand = list(given)
                cand.insert(pos, ch)
                if _is_prefix(cand, card.full):
                    results.setdefault("".join(cand), []).append("第%d颗后面补%s" % (pos, c.name(ch)))
        written = ("第%d颗%s→%s" % (card.fix["pos"], c.name(card.fix["from"]),
                                    c.name(card.fix["to"]))) if card.fix["kind"] == "swap" \
            else "第%d颗后面补%s" % (card.fix["pos"], c.name(card.fix["bead"]))
        if len(results) != 1:
            ways = " / ".join(sorted(" ".join(v) for v in results.values())) or "没有"
            card.problems.append("「只动一颗」能摆出 %d 种结果（%s：%s），可题里写的是 %s —— 答案必须唯一"
                                 % (len(results), ways, " ".join(results.keys()), written))
        elif written not in results[list(results)[0]]:
            card.problems.append("题里写的 %s 摆不出唯一的那个结果（%s）"
                                 % (written, " ".join(results[list(results)[0]])))


def _is_prefix(candidate: Sequence[str], expected: Sequence[str]) -> bool:
    """候选珠子串是不是完整序列的开头（补完/换完就能接着往下排）。"""
    return len(candidate) <= len(expected) and list(candidate) == list(expected[:len(candidate)])


# --------------------------------------------------------------------------
# 题库（目录）
# --------------------------------------------------------------------------


def list_cards(root: Path = PUZZLE_DIR, level: Optional[int] = None) -> List[Dict[str, Any]]:
    """列出题目（可按等级筛）—— 每道一行摘要。"""
    out: List[Dict[str, Any]] = []
    root = Path(root)
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*/*.txt")):
        if level is not None and path.parent.name != str(level):
            continue
        card = load_card(path)
        out.append({
            "id": card.id, "level": card.level, "title": card.title, "kind": card.kind,
            "path": path, "problems": card.problems,
        })
    return out


def list_levels(root: Path = PUZZLE_DIR) -> List[Dict[str, int]]:
    """每个等级各有多少道题（只有真的读得进来的才算）。"""
    counts: Dict[int, int] = {}
    for row in list_cards(root):
        if row["problems"]:
            continue
        counts[row["level"]] = counts.get(row["level"], 0) + 1
    return [{"level": lv, "count": counts[lv]} for lv in sorted(counts)]


def find_card_path(root: Path = PUZZLE_DIR, card_id: str = "") -> Optional[Path]:
    """按 id 找题目文件（id 必须跟文件名一致）。"""
    card_id = (card_id or "").strip()
    if not card_id:
        return None
    root = Path(root)
    for path in root.glob("*/*.txt"):
        if path.stem == card_id:
            return path
    return None


def payload(card: Card) -> Dict[str, Any]:
    """给页面/接口的题目结构（前端不用自己解析题面）。"""
    return {
        "id": card.id,
        "level": card.level,
        "title": card.title,
        "story": card.meta.get("story", ""),   # 一句情境（"假装是小汽车…"），可空
        "kind": card.kind,
        "rule": card.rule,
        "task": card.task,
        "rows": display_rows(card),           # 题面（空位、整组空着都标出来了）
        "reveal_rows": reveal_rows(card),     # 揭晓用：空位填上答案、fix 用上
        "answer": card.answer,
        "answer_text": answer_text(card),     # "蓝、红、红（3 颗）"
        "fix": card.fix,
        "fix_text": fix_text(card),           # "第 8 颗：原来是蓝，该改成红"
        "created_by": card.meta.get("created_by", ""),
        "generator": card.meta.get("generator", ""),
        "created_at": card.meta.get("created_at", ""),
    }


def display_rows(card: Card) -> List[List[Dict[str, Any]]]:
    """题面（给页面看的）：一格要么 `{'bead': 'R'}`，要么 `{'blank': True}`；
    "整组空着"的行就一个 `{'blank_group': True}` —— 该摆几颗，正是要孩子想的。"""
    out: List[List[Dict[str, Any]]] = []
    for i, row in enumerate(card.rows):
        if i in card.blank_groups:
            out.append([{"blank_group": True}])
        else:
            out.append([{"bead": x} if x is not None else {"blank": True} for x in row])
    return out


def reveal_rows(card: Card) -> List[List[Dict[str, Any]]]:
    """揭晓用的题面：空位填上答案、fix 用上；每格带个标记
    （`answer` = 空位填进去的，`fix` = 改过 / 补上的那颗）。"""
    tokens = _tokens(card)
    marks = ["answer" if t is None else "" for t in tokens]
    if card.fix:
        before = list(tokens)
        apply_fix_to_tokens(tokens, card.fix)
        given = [i for i, t in enumerate(before) if t is not None]
        if card.fix["kind"] == "swap":
            for i, (a, b) in enumerate(zip(before, tokens)):
                if a != b:
                    marks[i] = "fix"
        else:
            at = (given[card.fix["pos"] - 1] + 1) if card.fix["pos"] else 0
            marks.insert(at, "fix")
    cells = [{"bead": t if t is not None else card.full[i], "mark": m}
             for i, (t, m) in enumerate(zip(tokens, marks))]
    if card.kind in GROUP_KINDS and card.counts and len(cells) == sum(card.counts):
        out: List[List[Dict[str, Any]]] = []
        i = 0
        for n in card.counts:
            out.append(cells[i:i + n])
            i += n
        return out
    return [cells]


def answer_text(card: Card) -> str:
    """答案怎么写给人看：`蓝、红、红（3 颗）`。"""
    if not card.answer:
        return ""
    return "、".join(c.name(x) for x in card.answer) + "（%d 颗）" % len(card.answer)


def fix_text(card: Card) -> str:
    """错在哪儿、怎么改 —— 说人话。"""
    if not card.fix:
        return ""
    f = card.fix
    if f["kind"] == "swap":
        return "第 %d 颗：原来是%s，该改成%s" % (f["pos"], c.name(f["from"]), c.name(f["to"]))
    return "第 %d 颗后面补一颗%s" % (f["pos"], c.name(f["bead"]))


# --------------------------------------------------------------------------
# 检查题库（命令行）
# --------------------------------------------------------------------------


def _check_relative(card: Card, root: Path) -> List[str]:
    """跟"文件放在哪儿 / 叫什么"有关的检查。"""
    problems: List[str] = []
    if not _ID_RE.match(card.id):
        problems.append("id=%s 不像 `<日期>-<时间>-<4位>`（例：20261017-100101-1a01）" % card.id)
    if card.path.stem != card.id:
        problems.append("文件名（%s）跟 id（%s）对不上" % (card.path.stem, card.id))
    want = card.path.parent.name
    if want.isdigit() and want != str(card.level):
        problems.append("放在 %s/ 里，可 level=%s" % (want, card.level))
    return problems


def iter_cards(root: Path = PUZZLE_DIR) -> List[Card]:
    root = Path(root)
    return [load_card(p) for p in sorted(root.glob("*/*.txt"))] if root.is_dir() else []


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="找规律题库：检查 / 列表 / 打印")
    parser.add_argument("--dir", default=str(PUZZLE_DIR), help="题库目录（默认 %s）" % PUZZLE_DIR)
    parser.add_argument("--list", action="store_true", help="列出来（每级几道）")
    parser.add_argument("--show", metavar="文件", help="打印一道题（并把它检查一遍）")
    args = parser.parse_args(argv)

    root = Path(args.dir)
    if not root.is_dir():
        print("题库目录不存在：%s" % root, file=sys.stderr)
        return 2

    if args.show:
        card = load_card(Path(args.show))
        if card.problems:
            for p in card.problems:
                print("× %s" % p)
            return 1
        print("id=%s  等级 %d  《%s》" % (card.id, card.level, card.title))
        print("kind=%s  unit=%s%s" % (card.kind, card.unit,
                                      ("  counts=%s" % card.counts) if card.counts else ""))
        print("题面：" + "/".join("".join(x or "?" for x in row) for row in card.rows))
        if card.fix:
            print("fix：%s" % card.meta.get("fix"))
        print("完整：" + "".join(card.full))
        print("答案：" + "".join(card.answer or []) + "（空位 %d 颗）" % card.blank_count)
        print("任务：" + card.task)
        print("规律：" + card.rule)
        return 0

    cards = iter_cards(root)
    bad = 0
    for card in cards:
        problems = _check_relative(card, root) + card.problems
        rel = card.path.relative_to(root)
        if problems:
            bad += 1
            print("× %s  《%s》" % (rel, card.title or "?"))
            for p in problems:
                print("    - %s" % p)
        else:
            print("√ %s  L%s  《%s》  %s%s  %s"
                  % (rel, card.level, card.title, card.kind,
                     ("+" + card.meta.get("fix", "")) if card.fix else "",
                     card.task))
    if args.list:
        print()
        for row in list_levels(root):
            print("  %d 级：%d 道" % (row["level"], row["count"]))
    print()
    print("共 %d 道，%s" % (len(cards), "全部通过" if not bad else "%d 道有问题" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
