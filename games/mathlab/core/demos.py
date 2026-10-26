"""数学实验室的演示：**一个演示一个文件**（跟别的游戏一样）。

文件放 `puzzles/<等级>/<id>.txt`，格式照其他游戏：注释区 + 元信息区 + 正文区。

    # colors: Yellow Green Red Purple Blue Orange

    created_at=2026-10-17
    created_by=manual
    id=l1-match
    level=1
    title=一样多吗？
    thing=小皮球
    unit=个
    materials=R:3 B:3
    example=红串：3 个|RRR|3 个|
    example=蓝串拉开：还是 3 个|BBB|3 个（看着更长）|wide
    answer=看起来更长的那串不一定更多 —— 一颗对一颗地对齐，两串都是 3 个，一样多。
    why=长度会被间距骗人。比多少要看个数：一颗配一颗，配得上的就一样多。

    摆两串小皮球：一串 3 个红、一串 3 个蓝。
    把蓝的那串拉开一点，让它看起来更长。
    先猜一猜：看起来长的那串更多吗？
    一颗对一颗地对齐，数一数：两串各有几个？

字段：

* `thing` / `unit` —— 这些珠子假装是什么（小球 / 气球 / 豆腐…）、量词（颗 / 个 / 块）
* `materials` —— **参与者**：`R:3 B:3`（颜色:颗数，空格分开）
* `example` —— 示例摆法：`标签|珠子组|说明|标记`
  （珠子组用空格分开，如 `RRR RR`；说明可空；标记现在只有 `wide` = 拉开间距）
* 正文（元信息后面那些行）—— **题目**：一行一步，最后一步就是那句"问"

检查（`python -m games.mathlab.core.demos`）盯：
字段齐不齐、id 跟文件名一致、level 跟目录一致、颜色认不认得出、
每种颜色 ≤10 颗（参与者和每张示例都算）、示例标记认不认识。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

LEVEL_NAMES = {1: "感知", 2: "组合", 3: "结构", 4: "探索"}
COLORS = "YGRPBO"
PER_COLOR = 10                       # 手上一共 6 色、每种 10 颗

GAME_DIR = Path(__file__).resolve().parent.parent
PUZZLE_DIR = GAME_DIR / "puzzles"

# 认得的元信息键（不在这儿的 `键=值` 行，就当正文）
META_KEYS = ("created_at", "created_by", "id", "level", "theme", "title", "thing", "unit",
             "materials", "example", "answer", "why")
REQUIRED = ("id", "level", "theme", "title", "thing", "unit", "answer", "why")
EXAMPLE_FLAGS = ("wide",)


@dataclass
class Demo:
    path: Path
    meta: Dict[str, str] = field(default_factory=dict)
    materials: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    example: List[Dict[str, Any]] = field(default_factory=list)
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
    def theme(self) -> str:
        return self.meta.get("theme", "")

    @property
    def thing(self) -> str:
        return self.meta.get("thing", "")

    @property
    def unit(self) -> str:
        return self.meta.get("unit", "")

    @property
    def answer(self) -> str:
        return self.meta.get("answer", "")

    @property
    def why(self) -> str:
        return self.meta.get("why", "")


# --------------------------------------------------------------------------
# 读
# --------------------------------------------------------------------------


def _parse_materials(text: str, problems: List[str]) -> List[Dict[str, Any]]:
    """`R:3 B:3` → [{'bead': 'R', 'count': 3}, …]"""
    out: List[Dict[str, Any]] = []
    for tok in (text or "").split():
        bead, sep, count = tok.partition(":")
        bead = bead.strip().upper()
        if not sep or bead not in COLORS:
            problems.append("materials 里的 %r 要写成「颜色:颗数」（例：R:7）" % tok)
            continue
        try:
            n = int(count)
        except ValueError:
            problems.append("materials 里的 %r 颗数不是整数" % tok)
            continue
        if n <= 0:
            problems.append("materials 里的 %r 颗数要大于 0" % tok)
            continue
        out.append({"bead": bead, "count": n})
    return out


def _parse_example(text: str, problems: List[str]) -> Dict[str, Any]:
    """`标签|RRR RR|说明|wide` → {'label':…, 'groups':[…], 'note':…, 'wide': True}"""
    parts = text.split("|")
    while len(parts) < 4:
        parts.append("")
    label, groups, note, flags = (p.strip() for p in parts[:4])
    row: Dict[str, Any] = {"label": label,
                           "groups": [g for g in groups.split() if g],
                           "note": note}
    if not row["groups"]:
        problems.append("example「%s」没有珠子组" % (label or "?"))
    for group in row["groups"]:
        for ch in group:
            if ch not in COLORS:
                problems.append("example「%s」里有不是颜色的字符：%r" % (label or "?", ch))
    for flag in flags.split():
        if flag in EXAMPLE_FLAGS:
            row[flag] = True
        else:
            problems.append("example「%s」的标记 %r 不认识（只有 %s）"
                            % (label or "?", flag, " / ".join(EXAMPLE_FLAGS)))
    return row


def load_demo(path: Path) -> Demo:
    """读一个演示，顺手把「它自己有没有毛病」都收进 `demo.problems`。"""
    path = Path(path)
    demo = Demo(path=path)
    body: List[str] = []
    in_body = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not in_body:
            key, sep, value = line.partition("=")
            key = key.strip()
            if sep and key in META_KEYS:
                value = value.strip()
                if key == "example":
                    demo.example.append(_parse_example(value, demo.problems))
                else:
                    demo.meta[key] = value
                continue
            in_body = True
        body.append(line)
    demo.steps = body
    demo.materials = _parse_materials(demo.meta.get("materials", ""), demo.problems)
    _check(demo)
    return demo


def _check(demo: Demo) -> None:
    """字段齐不齐、id / level 跟文件位置对不对、物理上限。"""
    for key in REQUIRED:
        if not str(demo.meta.get(key, "") or "").strip():
            demo.problems.append("少了 %s=" % key)
    if demo.level not in LEVEL_NAMES:
        demo.problems.append("level=%r 不认识（只能是 1 / 2 / 3 / 4）" % demo.meta.get("level"))
    if demo.path.stem != demo.id:
        demo.problems.append("文件名（%s）跟 id（%s）对不上" % (demo.path.stem, demo.id))
    folder = demo.path.parent.name
    if folder.isdigit() and folder != str(demo.level):
        demo.problems.append("放在 %s/ 里，可 level=%s" % (folder, demo.level))
    if not demo.materials:
        demo.problems.append("materials 是空的（参与者总得有点东西）")
    if len(demo.steps) < 2:
        demo.problems.append("题目至少要两步（正文一行一步）")
    if not demo.example:
        demo.problems.append("一条 example 都没有（答案里要画示例）")
    # 物理上限：参与者每种颜色 ≤10 颗；每张示例也一样
    used: Dict[str, int] = {}
    for row in demo.materials:
        used[row["bead"]] = used.get(row["bead"], 0) + row["count"]
    for ch, n in used.items():
        if n > PER_COLOR:
            demo.problems.append("参与者里 %s色 %d 颗，可手上只有 %d 颗" % (ch, n, PER_COLOR))
    for row in demo.example:
        per: Dict[str, int] = {}
        for group in row["groups"]:
            for ch in group:
                per[ch] = per.get(ch, 0) + 1
        for ch, n in per.items():
            if n > PER_COLOR:
                demo.problems.append("示例「%s」里 %s色 %d 颗，超出手上的 %d 颗"
                                     % (row["label"] or "?", ch, n, PER_COLOR))


# --------------------------------------------------------------------------
# 查
# --------------------------------------------------------------------------


def iter_demos(root: Path = PUZZLE_DIR) -> List[Demo]:
    root = Path(root)
    if not root.is_dir():
        return []
    return [load_demo(path) for path in sorted(root.glob("*/*.txt"))]


def list_demos(level: Optional[int] = None, root: Path = PUZZLE_DIR) -> List[Demo]:
    return [demo for demo in iter_demos(root)
            if level is None or demo.level == level]


def get(demo_id: str, root: Path = PUZZLE_DIR) -> Optional[Demo]:
    demo_id = (demo_id or "").strip()
    if not demo_id:
        return None
    for path in sorted(Path(root).glob("*/*.txt")):
        if path.stem == demo_id:
            return load_demo(path)
    return None


def levels(root: Path = PUZZLE_DIR) -> Dict[str, object]:
    """每档几个演示（只有真的读得进来的才算）。"""
    counts: Dict[int, int] = {}
    for demo in iter_demos(root):
        if demo.problems:
            continue
        counts[demo.level] = counts.get(demo.level, 0) + 1
    return {"levels": [{"level": lv, "count": counts[lv]} for lv in sorted(counts)],
            "total": sum(counts.values())}


def payload(demo: Demo) -> Dict[str, Any]:
    """给页面的演示结构（前端不用自己拼）。"""
    return {
        "id": demo.id,
        "level": demo.level,
        "level_name": LEVEL_NAMES.get(demo.level, ""),
        "theme": demo.theme,
        "title": demo.title,
        "thing": demo.thing,
        "unit": demo.unit,
        "materials": demo.materials,
        "steps": demo.steps,
        "answer": demo.answer,
        "why": demo.why,
        "example": demo.example,
        "created_by": demo.meta.get("created_by", ""),
        "generator": demo.meta.get("generator", ""),
        "created_at": demo.meta.get("created_at", ""),
    }


def check(root: Path = PUZZLE_DIR) -> List[str]:
    """整个题库的问题（每个文件自己的问题都在 load_demo 里攒好了）。"""
    problems: List[str] = []
    seen: set = set()
    for demo in iter_demos(root):
        problems.extend("%s：%s" % (demo.path.name, p) for p in demo.problems)
        if demo.id in seen:
            problems.append("%s：id 重复了" % demo.path.name)
        seen.add(demo.id)
    return problems


def main(argv: Optional[Sequence[str]] = None) -> int:
    demos = iter_demos()
    for demo in demos:
        mark = "√" if not demo.problems else "×"
        print("%s L%d %-4s %s  《%s》" % (mark, demo.level,
                                         LEVEL_NAMES.get(demo.level, ""),
                                         demo.id, demo.title))
    problems = check()
    print()
    if problems:
        for p in problems:
            print("× " + p)
        return 1
    print("共 %d 个演示，全部通过" % len(demos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
