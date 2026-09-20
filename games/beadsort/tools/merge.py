"""把几个题库**临时拼成一个**（拼出来的那份是产物，随时可以再拼一次）。

```bash
# 把 games/beadsort/puzzles_* 全拼进 games/beadsort/puzzles
python -m games.beadsort.tools.merge games/beadsort/puzzles games/beadsort/puzzles_*

# 源不写就用「目标旁边的 puzzles_*」当源
python -m games.beadsort.tools.merge games/beadsort/puzzles
```

规矩（2026-09-20 跟需求方对齐的）：

* 目标库先**清空**（里面所有东西全删）——它是拼出来的，不是原始数据；
* 源库**只读**：只 copy 不搬，源目录一个字不动；
* **按原来的档拼**：源的 `1/` 进目标的 `1/`，档不重算、文件名照抄
  （题目 id 就在文件名里，重算会把它弄丢）；
* 同档**同名**的题只留先到的那一道（id 是「时间戳 + seed」，正常撞不上）；
* 源参数支持通配 —— PowerShell **不会**替你展开 `puzzles_*`，所以这里自己展；
* 只 print：每个源几道、每档几道、合计几道（不写台账，题目文件本身就是记录）。
"""

from __future__ import annotations

import argparse
import glob
import shutil
from collections import Counter
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]      # <仓库根>/games/beadsort/tools/merge.py
GAME_DIR = Path(__file__).resolve().parent.parent    # <仓库根>/games/beadsort

DEFAULT_SOURCE_GLOB = "puzzles_*"                    # 不写源的时候就按这个找


def expand_sources(patterns: Sequence[str], target: Path) -> List[Path]:
    """把源参数展开成目录列表：通配自己展开、跳过目标自己、同一个目录只算一次。"""
    out: List[Path] = []
    seen = set()
    for pat in patterns:
        hits = sorted(glob.glob(pat)) if glob.has_magic(pat) else [pat]
        if not hits:
            print("源没找到（跳过）：%s" % pat)
        for hit in hits:
            p = Path(hit)
            if p.resolve() == target:
                print("跳过目标自己：%s" % p)
                continue
            if not p.is_dir() or p.resolve() in seen:
                continue
            seen.add(p.resolve())
            out.append(p)
    return out


def check_target(target: Path, sources: Sequence[Path]) -> Optional[str]:
    """清空是不可恢复的，先拦住明显不该清的目标。返回错误话术 / None。"""
    r = target.resolve()
    if r == Path(r.anchor):                                   # 盘根，比如 C:\
        return "目标是盘根目录，不干：%s" % r
    if r in (REPO_ROOT.resolve(), GAME_DIR.resolve(), Path.home().resolve()):
        return "目标是仓库根 / 游戏目录 / 用户主目录，不干：%s" % r
    for s in sources:
        sr = s.resolve()
        if sr == r:
            return "目标就是源（等于自己清自己）：%s" % r
        if r in sr.parents:
            return "目标是源的上级目录（会把那个源一起删掉）：%s" % r
    return None


def wipe(root: Path) -> int:
    """清空题库目录：里面的文件和子目录**全删**，目录本身留着。返回删了几个文件。"""
    if not root.is_dir():
        return 0
    removed = 0
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            removed += sum(1 for f in entry.rglob("*") if f.is_file())
            shutil.rmtree(entry)
        else:
            entry.unlink()
            removed += 1
    return removed


def copy_levels(sources: Sequence[Path], target: Path) -> Tuple[Counter, Counter, int]:
    """按原来的档把题 copy 进目标库。

    返回（每个源贡献几道, 每档几道, 同档同名跳过几道）。
    """
    per_source: Counter = Counter()
    per_level: Counter = Counter()
    skipped = 0
    for src in sources:
        for lvl_dir in sorted(src.iterdir()):
            if not (lvl_dir.is_dir() and lvl_dir.name.isdigit()):
                continue                                     # 题库只认数字档目录
            for f in sorted(lvl_dir.glob("*.txt")):
                dest_dir = target / lvl_dir.name
                dest = dest_dir / f.name
                if dest.exists():                            # 同档同名：留先到的那一道
                    skipped += 1
                    continue
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                per_level[int(lvl_dir.name)] += 1
                per_source[src.name] += 1
    return per_source, per_level, skipped


def report(target: Path, sources: Sequence[Path], per_source: Counter,
           per_level: Counter, skipped: int) -> None:
    """打完收工：每个源几道 / 每档几道 / 合计几道。"""
    print("源 %d 个：%s" % (len(sources),
                            " / ".join("%s %d" % (s.name, per_source[s.name]) for s in sources)
                            or "（一个都没有）"))
    for level in sorted(per_level):
        print("%4d 级  %5d" % (level, per_level[level]))
    if skipped:
        print("同档同名跳过了 %d 道（只留先到的）" % skipped)
    print("合计 %d 道 → %s" % (sum(per_level.values()), target))


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="把几个题库拼成一个（目标先清空）")
    p.add_argument("target", metavar="目标库", help="拼到哪个目录（先清空；不存在就新建）")
    p.add_argument("sources", nargs="*", metavar="源库",
                   help="源目录，可以给通配（默认：目标旁边的 %s）" % DEFAULT_SOURCE_GLOB)
    args = p.parse_args(argv)

    target = Path(args.target)
    patterns = list(args.sources) or [str(target.parent / DEFAULT_SOURCE_GLOB)]
    sources = expand_sources(patterns, target.resolve())
    if not sources:
        print("一个源目录都没找到，什么都不做。")
        return 2

    bad = check_target(target, sources)
    if bad:
        print(bad)
        return 2

    removed = wipe(target)
    target.mkdir(parents=True, exist_ok=True)
    print("先把 %s 清空：删了 %d 个文件" % (target, removed))
    per_source, per_level, skipped = copy_levels(sources, target)
    report(target, sources, per_source, per_level, skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
