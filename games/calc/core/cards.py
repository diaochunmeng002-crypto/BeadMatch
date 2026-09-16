"""calc 的卡片：读写、校验、扫题库。

格式跟 `logic` / `memory` 一样：**注释区 + 元信息区 + 正文区**。

    # colors: Yellow Green Red Purple Blue Orange

    created_at=2026-09-16 10:15:00
    created_by=manual
    id=20260916-101500-a3f1
    title=两红两蓝
    level=1
    task=count
    participants=R R B B
    answer=4

    数一数：一共有几颗珠子？

| 字段 | 说明 |
| --- | --- |
| ``id`` / ``title`` / ``level`` | 文件名就是 id（``20260916-101500-a3f1`` 这种：日期-时间-4 位，跟串珠 / logic 一个叫法）；title 是卡的名字（可选）；level 是难度 |
| ``task`` | 玩法记号：``count`` 数一数 / ``compare`` 比多少 / ``equal`` 一样多 / ``add`` 合起来 / ``subtract`` 拿走 / ``group`` 拆成两组 / ``make`` 凑数 / ``missing`` 缺数 / ``chain`` 连续变化 |
| ``participants`` | **参与者**：这道题用到的珠子 —— 同一颗颜色写几遍就是几颗（``R R B B B`` = 红 2 蓝 3） |
| ``answer`` | **答案**：类型看 task（见下） |
| 正文 | **规则**：一字不改，就是给孩子听/看的那句话 |

答案写什么，按 task 分三种：

- **数字**（``5``）：``count`` / ``add`` / ``subtract`` / ``group`` / ``make`` / ``missing`` / ``chain``；
- **哪边多**（``B``、``蓝`` 都行）或 ``equal``：``compare``；
- 上面两种都行：``equal``（一样多，答案可以是"挪几颗"也可以是哪边）。

读进来就校验，对不上直接报错（不能默默读进来）：颜色认得出、每色不超过实物的 10 颗、
``task`` 是认识的记号、``answer`` 的类型跟 ``task`` 对得上。

用法：

    python -m games.calc.core.cards                  # 检查题库
    python -m games.calc.core.cards --show <文件>     # 打印一张卡
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from . import colors as C

# 元信息区的输出顺序（时间 / 谁出的 固定在前两行）
META_ORDER = ("created_at", "created_by", "id", "title", "level",
              "task", "participants", "answer")
REQUIRED_KEYS = ("id", "level", "task", "participants", "answer")

# 玩法记号（中文名只说给人听，卡里写英文）
TASKS: Dict[str, str] = {
    "count": "数一数",
    "compare": "比多少",
    "equal": "一样多",
    "add": "合起来",
    "subtract": "拿走",
    "group": "拆成两组",
    "make": "凑数",
    "missing": "缺数",
    "chain": "连续变化",
}

# 答案要写数字的玩法 / 要写"哪边多"的玩法
_NUM_TASKS = ("count", "add", "subtract", "group", "make", "missing", "chain")
_SIGN_TASKS = ("compare", "equal")

# "两边一样多"的几种写法
_EQUAL_WORDS = ("equal", "same", "一样", "一样多", "相等", "平", "=")

# 中文数字（孩子说的"五颗"、家长手打的"五"都认）—— 只认到二十，够本游戏用
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# 实物上限：一套串珠每色 10 颗
PER_COLOR_MAX = 10
COLOR_KINDS = len(C.LETTERS)

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_TAG_RE = re.compile(r"^[A-Za-z0-9_@.+-]{1,64}$")

# 题库目录（一卡一文件，文件名 = <id>.txt）
PUZZLE_DIR = Path(__file__).resolve().parent.parent / "puzzles"


@dataclass(frozen=True)
class Card:
    """一张计算卡：珠子 + 玩法 + 规则（正文）+ 答案。"""

    participants: Tuple[str, ...]   # 参与者：哪种颜色各几颗（同一字母重复几次就是几颗）
    task: str                        # 玩法记号
    answer: str                      # 答案（原样存着，判定时再规范化）
    rule: str                        # 正文：给孩子听的那句话

    @property
    def beads(self) -> int:
        """一共几颗珠子。"""
        return len(self.participants)

    @property
    def color_kinds(self) -> int:
        """用了几种颜色。"""
        return len(set(self.participants))


def _cn_number(text: str) -> Optional[int]:
    """中文数字 → 整数；认不出返回 ``None``（只认到二十）。"""
    if text in _CN_DIGITS:
        return _CN_DIGITS[text]
    if len(text) == 2 and text[0] == "十" and text[1] in _CN_DIGITS:
        return 10 + _CN_DIGITS[text[1]]                       # 十一 ~ 十九
    if len(text) == 2 and text[1] == "十" and text[0] in _CN_DIGITS:
        return _CN_DIGITS[text[0]] * 10                       # 二十
    if len(text) == 3 and text[1] == "十" and text[0] in _CN_DIGITS and text[2] in _CN_DIGITS:
        return _CN_DIGITS[text[0]] * 10 + _CN_DIGITS[text[2]]  # 二十一 ~ 九十九
    return None


def normalize_answer(value) -> Union[int, str]:
    """把答案规范成一个好比较的东西：数字 → ``int``；颜色 → 字母；一样多 → ``"equal"``。

    数字认三种写法：``5``、``"5"``、``"五"``（中文数字认到二十）。
    """
    text = str(value).strip()
    if not text:
        raise ValueError("答案是空的")
    if text.lower() in _EQUAL_WORDS:
        return "equal"
    try:
        return int(text)
    except ValueError:
        pass
    cn = _cn_number(text)
    if cn is not None:
        return cn
    try:
        return C.to_letter(text)          # 颜色（"蓝" / "B" / "🔵" 都行）
    except ValueError:
        pass
    for suffix in ("色多", "多"):          # 口语说法："蓝多" / "蓝色多"
        if text.endswith(suffix) and len(text) > len(suffix):
            try:
                return C.to_letter(text[: -len(suffix)])
            except ValueError:
                pass
    raise ValueError("认不出的答案：%r（写数字、颜色、或者 equal）" % value)


def _check_answer_type(task: str, value: Union[int, str]) -> None:
    """答案的类型得跟玩法对得上（数一数的答案不能写成"蓝"）。"""
    if task in _NUM_TASKS and not isinstance(value, int):
        raise ValueError("%s 的答案得是个数，现在写的是 %r" % (TASKS[task], value))
    if task == "compare" and isinstance(value, int):
        raise ValueError("比多少的答案要写哪边多（颜色），或者 equal —— 现在写的是数字 %r" % value)


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
                lines.append("%s=%s" % (key, meta[key]))
        lines.append("")
    if card.rule:
        lines.extend(card.rule.splitlines())
    return "\n".join(lines)


def parse_card(text: str) -> Tuple[Card, Dict[str, object]]:
    """解析一张卡，返回 ``(卡, 元信息)``。读进来就校验，对不上直接报错。"""
    raw: Dict[str, str] = {}
    rule_lines: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _KEY_RE.match(s)
        if m:
            raw[m.group(1)] = m.group(2).strip()
        else:
            rule_lines.append(s)

    for key in REQUIRED_KEYS:
        if key not in raw:
            raise ValueError("卡里缺少必需字段 %s=" % key)

    try:
        level = int(raw["level"])
    except ValueError:
        raise ValueError("level 不是整数：%r" % raw["level"])
    if level < 0:
        raise ValueError("level 不能是负数：%s" % level)

    task = raw["task"].strip().lower()
    if task not in TASKS:
        raise ValueError("认不出的 task：%r（能用的是 %s）"
                         % (raw["task"], " / ".join(TASKS)))

    # ---- 参与者：哪些颜色、各几颗 ----
    try:
        participants = C.to_letters(raw["participants"])
    except ValueError as exc:
        raise ValueError("participants 读不了：%s" % exc)
    if not participants:
        raise ValueError("participants 是空的 —— 这道题用几颗珠子？")
    for row in C.counts_of(participants):
        if int(row["count"]) > PER_COLOR_MAX:
            raise ValueError("%s 有 %d 颗，超过实物的 %d 颗"
                             % (row["name"], row["count"], PER_COLOR_MAX))
    if len(set(participants)) > COLOR_KINDS:
        raise ValueError("一条题里出现了 %d 种颜色，超过了 %d 种"
                         % (len(set(participants)), COLOR_KINDS))

    # ---- 答案：类型要跟玩法对得上 ----
    try:
        answer_value = normalize_answer(raw["answer"])
    except ValueError as exc:
        raise ValueError("answer 读不了：%s" % exc)
    _check_answer_type(task, answer_value)

    # ---- 出身 ----
    if "created_by" in raw and not _TAG_RE.match(str(raw["created_by"])):
        raise ValueError("created_by 的格式不对：%r" % raw["created_by"])
    if "created_at" in raw and not _STAMP_RE.match(str(raw["created_at"])):
        raise ValueError("created_at 的格式不对：%r（要写成 2026-09-16 10:00:00）"
                         % raw["created_at"])

    meta: Dict[str, object] = {}
    for key, value in raw.items():
        meta[key] = int(value) if key == "level" else value
    meta["task"] = task

    card = Card(participants=participants, task=task, answer=raw["answer"].strip(),
                rule="\n".join(rule_lines))
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


# --------------------------------------------------------------------------
# 题库索引（目录就是索引：等级看目录名、id 看文件名）
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
                "task": head.get("task", ""),
                "task_cn": TASKS.get(head.get("task", ""), head.get("task", "")),
                "beads": len(C.to_letters(head.get("participants", ""))),
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
        raise LookupError("题库里没有 %s 级的卡" % level)
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
    """一行摘要：``数一数  L1 数一数 珠子=5 颜色=2 答案=5``。"""
    meta = meta or {}
    title = str(meta.get("title") or "").strip()
    head = "%s  " % title if title else ""
    return "%s L%s %s 珠子=%d 颜色=%d 答案=%s" % (
        head, meta.get("level", "?"), TASKS.get(card.task, card.task),
        card.beads, card.color_kinds, card.answer)


# --------------------------------------------------------------------------
# 检查题库
# --------------------------------------------------------------------------


def check_dir(root=PUZZLE_DIR, *, stream=sys.stdout) -> int:
    """扫一遍题库：报「读得进来吗 / 是什么玩法 / 答案写得对不对」。

    只有**读不进来**才算问题（返回值就是问题数）。答案对不对只能靠人 ——
    程序不知道"红色的有几颗"这句问的是什么，所以这里不自动判答案。
    """
    root = Path(root)
    files = sorted(root.glob("*/*.txt"))
    if not files:
        print("题库是空的：%s" % root, file=stream)
        return 0

    problems = 0
    for path in files:
        rel = "%s/%s" % (path.parent.name, path.name)
        try:
            card, meta = load_card(path)
        except ValueError as exc:
            problems += 1
            print("× %s —— %s" % (rel, exc), file=stream)
            continue

        print("√ %s  %s" % (rel, describe(card, meta)), file=stream)
        print("     材料 %s" % C.format_materials(card.participants), file=stream)
        if card.rule:
            print("     规则 %s" % card.rule.splitlines()[0], file=stream)
        else:
            print("     ！这张卡没有写规则（正文是空的）", file=stream)

    print("", file=stream)
    print("共 %d 张卡：读不进来 %d 张。" % (len(files), problems), file=stream)
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
    p = argparse.ArgumentParser(description="calc 题库：检查 / 打印")
    p.add_argument("--dir", default=str(PUZZLE_DIR), help="题库根目录（默认本游戏的 puzzles/）")
    p.add_argument("--show", metavar="FILE", help="打印一张卡（附带程序读到的字段）")
    args = p.parse_args(argv)

    if args.show:
        card, meta = load_card(args.show)
        print(render_card(card, meta))
        print("")
        print("# 程序读到的是：%s" % describe(card, meta))
        print("# 材料：%s（%s）" % (C.format_materials(card.participants),
                                   C.format_letters(card.participants)))
        print("# 答案规范化之后：%r" % normalize_answer(card.answer))
        return 0

    return 1 if check_dir(Path(args.dir)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
