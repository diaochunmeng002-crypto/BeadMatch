"""收藏：哪几道题"觉得好"（以后想再看 / 再给孩子做）。

跟访问日志用**同一个本地库**（见 `history.db_path()`），但**单独一张表**：

* `access_event` 是**事件流** —— 每看一次一条；
* `star` 是**状态** —— 一道题（游戏 + 题目 id）最多一条，有就是收藏了。

所以收藏是幂等的：连着收藏两次还是一条；取消两次也不报错。

命令行（开发时自查用）：

    python -m plaza.stars                     # 列出所有收藏
    python -m plaza.stars --game logic        # 只看推理
    python -m plaza.stars --add logic 20260915-220118-a0fa --level 5
    python -m plaza.stars --remove logic 20260915-220118-a0fa
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import history

_SCHEMA = """
CREATE TABLE IF NOT EXISTS star (
  game          TEXT    NOT NULL,
  puzzle_id     TEXT    NOT NULL,
  level         INTEGER,
  created_at_ms INTEGER NOT NULL,
  PRIMARY KEY (game, puzzle_id)
);
CREATE INDEX IF NOT EXISTS ix_star_level ON star(game, level);
"""


def _connect():
    """跟访问日志同一个库、同一套连接设置；顺手把收藏表建好。"""
    con = history.connect()
    con.executescript(_SCHEMA)
    con.commit()
    return con


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone().isoformat(
        timespec="seconds")


def _row(row) -> Dict[str, Any]:
    return {
        "game": row["game"],
        "puzzle_id": row["puzzle_id"],
        "level": row["level"],
        "starred": True,
        "created_at_ms": int(row["created_at_ms"]),
        "created_at": _iso(int(row["created_at_ms"])),
    }


def init_db() -> Path:
    """建表（已经在了就什么也不改），返回数据库文件路径。"""
    con = _connect()
    con.close()
    return history.db_path()


def get(game: str, puzzle_id: str) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        row = con.execute("SELECT * FROM star WHERE game = ? AND puzzle_id = ?",
                          (game, puzzle_id)).fetchone()
    finally:
        con.close()
    return _row(row) if row else None


def is_starred(game: str, puzzle_id: str) -> bool:
    return get(game, puzzle_id) is not None


def list_stars(game: Optional[str] = None,
               level: Optional[int] = None) -> List[Dict[str, Any]]:
    """收藏列表，新的在前（可按游戏 / 等级筛）。"""
    where: List[str] = []
    params: List[Any] = []
    if game:
        where.append("game = ?")
        params.append(str(game))
    if level is not None:
        where.append("level = ?")
        params.append(int(level))
    sql = "SELECT * FROM star"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at_ms DESC, game, puzzle_id"

    con = _connect()
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_row(row) for row in rows]


def set_starred(game: str, puzzle_id: str, level: Optional[int] = None,
                starred: bool = True) -> Dict[str, Any]:
    """收藏（`starred=True`）或取消（`False`）—— **幂等**，返回这道题现在的状态。"""
    game = str(game or "").strip()
    puzzle_id = str(puzzle_id or "").strip()
    if not game or not puzzle_id:
        raise ValueError("game 和 puzzle_id 都得有内容")

    con = _connect()
    try:
        row = con.execute("SELECT * FROM star WHERE game = ? AND puzzle_id = ?",
                          (game, puzzle_id)).fetchone()
        if starred:
            if row is None:
                con.execute("INSERT INTO star(game, puzzle_id, level, created_at_ms)"
                            " VALUES(?, ?, ?, ?)",
                            (game, puzzle_id, None if level is None else int(level),
                             int(time.time() * 1000)))
            elif row["level"] is None and level is not None:
                con.execute("UPDATE star SET level = ? WHERE game = ? AND puzzle_id = ?",
                            (int(level), game, puzzle_id))
        elif row is not None:
            con.execute("DELETE FROM star WHERE game = ? AND puzzle_id = ?",
                        (game, puzzle_id))
        con.commit()
        row = con.execute("SELECT * FROM star WHERE game = ? AND puzzle_id = ?",
                          (game, puzzle_id)).fetchone()
    finally:
        con.close()
    if row is None:
        return {"game": game, "puzzle_id": puzzle_id, "starred": False, "level": None}
    state = _row(row)
    state["starred"] = True
    return state


def clear() -> int:
    """把收藏全删掉（测试 / 重来用）。返回删了几条。"""
    con = _connect()
    try:
        n = con.execute("DELETE FROM star").rowcount
        con.commit()
        return int(n or 0)
    finally:
        con.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="收藏（跟访问日志同一个本地库）")
    parser.add_argument("--game", help="只看某个游戏，例如 logic")
    parser.add_argument("--level", type=int, help="只看某个等级")
    parser.add_argument("--add", nargs=2, metavar=("游戏", "题目id"), help="收藏一道题")
    parser.add_argument("--remove", nargs=2, metavar=("游戏", "题目id"), help="取消收藏")
    args = parser.parse_args(argv)

    if args.add:
        state = set_starred(args.add[0], args.add[1], args.level, True)
        print("收藏了：%s %s" % (state["game"], state["puzzle_id"])
              if state["starred"] else "没收藏上")
        return 0
    if args.remove:
        state = set_starred(args.remove[0], args.remove[1], args.level, False)
        print("取消了：%s %s" % (state["game"], state["puzzle_id"]))
        return 0

    rows = list_stars(args.game, args.level)
    for row in rows:
        level = "" if row["level"] is None else "%s 级 " % row["level"]
        print("★ %-10s %s%-28s %s" % (row["game"], level, row["puzzle_id"],
                                      row["created_at"]))
    if not rows:
        print("（还没有收藏）")
    else:
        print()
        print("共 %d 道收藏" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
