"""BeadMatch 的访问日志（最简单版）。

这一层只管两件事：**写一条**、**查出来**。哪里调用它（游戏的 /random、
/puzzles/{id}，还是别的地方）以后再说 —— 这个文件不碰任何游戏代码。

存哪（从高到低）：

* ``BEADMATCH_HISTORY_DB``：直接给一个数据库文件路径（测试用）；
* ``BEADMATCH_DATA_DIR``：给一个目录，库里就叫 ``history.db``
  （启动器以后把"打包后能写的目录"设成这个就行）；
* 打包后：exe 旁边；写不了（比如装在 ``C:\\Program Files``）就退到
  ``%LOCALAPPDATA%\\BeadMatch``；
* 开发时：仓库根目录。

库是 Python 自带的 SQLite，不用装任何东西；整个"数据库"就是一个文件。

命令行（开发时自查用）：

    python -m plaza.history path
    python -m plaza.history init
    python -m plaza.history add calc 20260916-110119-7848 --level 9 --source random
    python -m plaza.history list --game calc --limit 20
    python -m plaza.history summary --game calc --level 9
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

log = logging.getLogger(__name__)

APP_NAME = "BeadMatch"
DB_NAME = "history.db"
REPO_ROOT = Path(__file__).resolve().parent.parent

# 一条访问记录一张表。字段只存"信封"信息（谁、哪道题、什么时候），
# 不碰题目内容；detail 里以后可以放 {"ok": true} 这种附加信息。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS access_event (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc_ms INTEGER NOT NULL,
  day       TEXT    NOT NULL,
  game      TEXT    NOT NULL,
  puzzle_id TEXT    NOT NULL,
  level     INTEGER,
  event     TEXT    NOT NULL DEFAULT 'served',
  source    TEXT    NOT NULL DEFAULT '',
  player    TEXT    NOT NULL DEFAULT 'default',
  detail    TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_access_puzzle
  ON access_event(game, puzzle_id, ts_utc_ms);
CREATE INDEX IF NOT EXISTS ix_access_day
  ON access_event(day, game);
"""


# --------------------------------------------------------------------------
# 数据库放哪
# --------------------------------------------------------------------------


def _writable(folder: Path) -> bool:
    """这个目录能不能写（跟 launcher 一个做法）。"""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / (".write-test-%d" % os.getpid())   # 带 pid，免得两个进程抢同一个文件名
        probe.write_text("x", encoding="utf-8")
        try:
            probe.unlink()
        except OSError:
            pass
        return True
    except OSError:
        return False


@lru_cache(maxsize=1)
def data_dir() -> Path:
    """放历史数据的目录。"""
    explicit = (os.environ.get("BEADMATCH_DATA_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser()

    if getattr(sys, "frozen", False):                 # PyInstaller 打出来的 exe
        base = Path(sys.executable).resolve().parent
    else:                                              # 开发时：仓库根目录
        base = REPO_ROOT
    if _writable(base):
        return base

    fallback = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def db_path() -> Path:
    """数据库文件在哪。环境变量优先（测试 / 特殊部署用）。"""
    explicit = (os.environ.get("BEADMATCH_HISTORY_DB") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return data_dir() / DB_NAME


# --------------------------------------------------------------------------
# 底层
# --------------------------------------------------------------------------


def _connect(path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """开一个短连接并把表建好。调用方负责 close()。"""
    target = Path(path) if path is not None else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(target), timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")      # 读写不互相卡
    con.execute("PRAGMA busy_timeout=5000")
    con.executescript(_SCHEMA)
    con.commit()
    return con


def init_db(path: Optional[Union[str, Path]] = None) -> Path:
    """建库 / 建表。已经在了就什么也不改。返回数据库文件路径。"""
    target = Path(path) if path is not None else db_path()
    con = _connect(target)
    con.close()
    return target


def _to_ms(ts: Optional[datetime]) -> int:
    """datetime → 毫秒时间戳（UTC）。naive 的按本机时区算。"""
    if ts is None:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    if ts.tzinfo is None:
        ts = ts.astimezone()
    return int(ts.timestamp() * 1000)


def _local_day(ms: int) -> str:
    """毫秒时间戳 → 本机日期 'YYYY-MM-DD'（按天查 / 统计用）。"""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


def _local_iso(ms: int) -> str:
    """毫秒时间戳 → 本机时间，带时区：'2026-09-20T21:30:05+08:00'。"""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _row(row: sqlite3.Row) -> Dict[str, Any]:
    """数据库一行 → 给人/给接口用的 dict。"""
    ms = int(row["ts_utc_ms"])
    try:
        detail = json.loads(row["detail"] or "{}")
    except ValueError:
        detail = {}
    return {
        "id": int(row["id"]),
        "ts": _local_iso(ms),
        "ts_utc_ms": ms,
        "day": row["day"],
        "game": row["game"],
        "puzzle_id": row["puzzle_id"],
        "level": row["level"],
        "event": row["event"],
        "source": row["source"],
        "player": row["player"],
        "detail": detail,
    }


# --------------------------------------------------------------------------
# 写
# --------------------------------------------------------------------------


def record(
    *,
    game: str,
    puzzle_id: str,
    level: Optional[int] = None,
    event: str = "served",
    source: str = "",
    player: str = "default",
    detail: Optional[Mapping[str, Any]] = None,
    ts: Optional[datetime] = None,
) -> int:
    """插一条访问记录，返回它在本库里的 id。

    写不进去会**抛异常**。以后把日志挂到游戏接口上时，用下面的
    ``record_safe()``，别让磁盘满 / 只读把出题也带崩。
    """
    game = str(game or "").strip()
    puzzle_id = str(puzzle_id or "").strip()
    if not game or not puzzle_id:
        raise ValueError("game 和 puzzle_id 都得有内容")

    ms = _to_ms(ts)
    payload = json.dumps(dict(detail or {}), ensure_ascii=False, sort_keys=True)
    level = None if level is None else int(level)
    con = _connect()
    try:
        cur = con.execute(
            "INSERT INTO access_event"
            " (ts_utc_ms, day, game, puzzle_id, level, event, source, player, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ms, _local_day(ms), game, puzzle_id, level,
             str(event or "served"), str(source or ""), str(player or "default"), payload),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def enabled() -> bool:
    """``BEADMATCH_HISTORY=off`` 时关掉自动记录（测试 / 不想记的时候用）。

    只影响 ``record_safe()`` 这条自动路径；显式调 ``record()`` 照样写。
    """
    return (os.environ.get("BEADMATCH_HISTORY") or "").strip().lower() not in (
        "off", "0", "false", "no", "none",
    )


def record_safe(**kwargs: Any) -> Optional[int]:
    """跟 ``record()`` 一样，但出错只记日志、返回 None —— 给游戏接口用。"""
    if not enabled():
        return None
    try:
        return record(**kwargs)
    except Exception:
        log.exception("访问日志写不进去：%r", {k: v for k, v in kwargs.items() if k != "detail"})
        return None


def record_served(*, game: str, payload: Mapping[str, Any],
                  source: str = "") -> Optional[int]:
    """游戏接口把一道题发给前端时调这个 —— 从 payload 里取 id / level。"""
    puzzle_id = str(payload.get("id") or "").strip()
    if not puzzle_id:
        return None
    return record_safe(game=game, puzzle_id=puzzle_id, level=payload.get("level"),
                       event="served", source=source)


# --------------------------------------------------------------------------
# 查
# --------------------------------------------------------------------------


def query(
    *,
    game: Optional[str] = None,
    puzzle_id: Optional[str] = None,
    level: Optional[int] = None,
    event: Optional[str] = None,
    player: Optional[str] = None,
    day: Optional[str] = None,
    since_day: Optional[str] = None,
    until_day: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    newest_first: bool = True,
) -> List[Dict[str, Any]]:
    """按条件查记录，新的在前（``newest_first=False`` 就旧的在前面）。"""
    where: List[str] = []
    params: List[Any] = []

    def eq(column: str, value: Any) -> None:
        if value is not None and str(value) != "":
            where.append("%s = ?" % column)
            params.append(value)

    eq("game", game)
    eq("puzzle_id", puzzle_id)
    eq("event", event)
    eq("player", player)
    eq("day", day)
    if level is not None:
        eq("level", int(level))
    if since_day:
        where.append("day >= ?")
        params.append(str(since_day))
    if until_day:
        where.append("day <= ?")
        params.append(str(until_day))

    sql = "SELECT * FROM access_event"
    if where:
        sql += " WHERE " + " AND ".join(where)
    direction = "DESC" if newest_first else "ASC"
    sql += " ORDER BY ts_utc_ms %s, id %s LIMIT ? OFFSET ?" % (direction, direction)
    params += [max(1, int(limit)), max(0, int(offset))]

    con = _connect()
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_row(row) for row in rows]


def summary(
    *,
    game: Optional[str] = None,
    level: Optional[int] = None,
    event: Optional[str] = "served",
    player: Optional[str] = None,
    since_day: Optional[str] = None,
    until_day: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """每道题一行：做过几次、第一次/最后一次什么时候。

    **最久没碰过的排最前面** —— 以后"不重复出题"直接拿这个顺序就行。
    """
    where: List[str] = []
    params: List[Any] = []
    if game:
        where.append("game = ?")
        params.append(str(game))
    if level is not None:
        where.append("level = ?")
        params.append(int(level))
    if event:
        where.append("event = ?")
        params.append(str(event))
    if player:
        where.append("player = ?")
        params.append(str(player))
    if since_day:
        where.append("day >= ?")
        params.append(str(since_day))
    if until_day:
        where.append("day <= ?")
        params.append(str(until_day))

    sql = (
        "SELECT game, puzzle_id, MAX(level) AS level, COUNT(*) AS times,"
        " MIN(ts_utc_ms) AS first_ms, MAX(ts_utc_ms) AS last_ms"
        " FROM access_event"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY game, puzzle_id ORDER BY last_ms ASC, game, puzzle_id"

    con = _connect()
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()

    out: List[Dict[str, Any]] = []
    for row in rows:
        first_ms, last_ms = int(row["first_ms"]), int(row["last_ms"])
        out.append({
            "game": row["game"],
            "puzzle_id": row["puzzle_id"],
            "level": row["level"],
            "times": int(row["times"]),
            "first": _local_iso(first_ms),
            "first_utc_ms": first_ms,
            "last": _local_iso(last_ms),
            "last_utc_ms": last_ms,
        })
    return out


# --------------------------------------------------------------------------
# 命令行：开发时自查
# --------------------------------------------------------------------------


def _add_filters(p: argparse.ArgumentParser) -> None:
    p.add_argument("--game", help="只看某个游戏，例如 calc")
    p.add_argument("--level", type=int, help="只看某个等级")
    p.add_argument("--event", help="只看某种事件，例如 served")
    p.add_argument("--player", help="只看某个人")
    p.add_argument("--since-day", help="从哪天起（含），YYYY-MM-DD")
    p.add_argument("--until-day", help="到哪天止（含），YYYY-MM-DD")


def _print_json(data: Any) -> None:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BeadMatch 访问日志（最简单版）")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("path", help="数据库文件在哪")
    sub.add_parser("init", help="建库 / 建表")

    add = sub.add_parser("add", help="插一条记录")
    add.add_argument("game")
    add.add_argument("puzzle_id")
    add.add_argument("--level", type=int)
    add.add_argument("--event", default="served")
    add.add_argument("--source", default="")
    add.add_argument("--player", default="default")
    add.add_argument("--detail", help='附加信息，JSON，例如 \'{"ok": true}\'')
    add.add_argument("--json", action="store_true", help="打印刚插入的那条")

    show = sub.add_parser("list", help="查记录")
    _add_filters(show)
    show.add_argument("--day", help="只看某一天，YYYY-MM-DD")
    show.add_argument("--puzzle", dest="puzzle_id", help="只看某道题")
    show.add_argument("--limit", type=int, default=20)
    show.add_argument("--offset", type=int, default=0)
    show.add_argument("--oldest", action="store_true", help="旧的在前面")
    show.add_argument("--json", action="store_true")

    stat = sub.add_parser("summary", help="每道题做过几次、什么时候")
    _add_filters(stat)
    stat.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0

    if args.cmd == "path":
        path = db_path()
        print(path)
        print("（%s）" % ("已存在" if path.exists() else "还没建"))
        return 0

    if args.cmd == "init":
        print("建好了：%s" % init_db())
        return 0

    if args.cmd == "add":
        detail = None
        if args.detail:
            try:
                detail = json.loads(args.detail)
            except ValueError as exc:
                parser.error("--detail 不是合法 JSON：%s" % exc)
        new_id = record_safe(game=args.game, puzzle_id=args.puzzle_id, level=args.level,
                             event=args.event, source=args.source, player=args.player,
                             detail=detail)
        if new_id is None:
            return 1
        if args.json:
            rows = query(game=args.game.strip(), puzzle_id=args.puzzle_id.strip(), limit=1)
            _print_json(rows[0] if rows else {"id": new_id})
        else:
            print("插入成功，id=%d" % new_id)
        return 0

    if args.cmd == "list":
        rows = query(game=args.game, level=args.level, event=args.event, player=args.player,
                     day=args.day, since_day=args.since_day, until_day=args.until_day,
                     puzzle_id=args.puzzle_id, limit=args.limit, offset=args.offset,
                     newest_first=not args.oldest)
        if args.json:
            _print_json(rows)
        else:
            for row in rows:
                level = "" if row["level"] is None else "%s级 " % row["level"]
                print("[%d] %s  %s%s  %s  %s  %s"
                      % (row["id"], row["ts"], level, row["puzzle_id"],
                         row["game"], row["event"], row["source"]))
            if not rows:
                print("（没有记录）")
        return 0

    if args.cmd == "summary":
        rows = summary(game=args.game, level=args.level, event=args.event or "served",
                       player=args.player, since_day=args.since_day, until_day=args.until_day)
        if args.json:
            _print_json(rows)
        else:
            for row in rows:
                level = "" if row["level"] is None else "%s级 " % row["level"]
                print("%s  %s%s  %d 次  上次 %s"
                      % (row["game"], level, row["puzzle_id"], row["times"], row["last"]))
            if not rows:
                print("（没有记录）")
        return 0

    parser.error("不认识这个子命令：%s" % args.cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
