"""扫 `games/*/game.toml` → 游戏清单（见 ../docs/plaza.md §4.1）。

没有 `game.toml` 的文件夹对广场是隐形的（占位 README 那种就不会被列上首页）。
榜单里每一条会顺手把游戏的 `api.py` 导进来 —— 广场拿它的 `router` 挂接口，
再调它的 `levels()` 问"每级各多少题"。
"""

from __future__ import annotations

import importlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# 游戏都在这儿（跟 games/README.md 一致）
GAMES_DIR = Path(__file__).resolve().parent.parent / "games"

# game.toml 必须写的四样
REQUIRED_KEYS = ("id", "name", "category", "summary")


@dataclass(frozen=True)
class Game:
    """广场眼里的一个游戏。"""

    id: str
    name: str
    category: str          # group / sort / space / plan / logic / memory / pattern / calc
    summary: str           # 一句话（首页上显示）
    folder: Path
    api: object = None     # games.<id>.api 模块（起不来的话是 None）
    error: str = ""        # 起不来的话，错在哪

    @property
    def url(self) -> str:
        """这个游戏的页面地址。"""
        return "/games/%s/" % self.id

    @property
    def api_base(self) -> str:
        """这个游戏的接口基址（页面里由广场注入给前端）。"""
        return "/api/games/%s" % self.id

    @property
    def web_dir(self) -> Path:
        """这个游戏的页面 + 静态资源目录。"""
        return self.folder / "web"


def _load(folder: Path) -> Optional[Game]:
    """读一个游戏文件夹里的 game.toml；没有就不是游戏（返回 None）。"""
    toml_path = folder / "game.toml"
    if not toml_path.is_file():
        return None

    meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_KEYS if not str(meta.get(k, "")).strip()]
    if missing:
        raise ValueError("%s 缺少字段：%s" % (toml_path, " / ".join(missing)))

    gid = str(meta["id"]).strip()
    if gid != folder.name:
        raise ValueError("%s 里的 id=%s 跟文件夹名 %s 对不上" % (toml_path, gid, folder.name))

    api = None
    error = ""
    try:
        api = importlib.import_module("games.%s.api" % gid)
    except Exception as exc:                      # 一个游戏坏了，别连累广场
        error = "%s: %s" % (type(exc).__name__, exc)

    return Game(id=gid, name=str(meta["name"]).strip(), category=str(meta["category"]).strip(),
                summary=str(meta["summary"]).strip(), folder=folder, api=api, error=error)


def list_games(root: Path = GAMES_DIR) -> List[Game]:
    """所有游戏（按 id 排序）。读不动 / 缺字段的游戏也会列出来，带上 error。"""
    out: List[Game] = []
    root = Path(root)
    if not root.is_dir():
        return out
    for folder in sorted(d for d in root.iterdir() if d.is_dir()):
        try:
            game = _load(folder)
        except Exception as exc:
            out.append(Game(id=folder.name, name=folder.name, category="?", summary="",
                            folder=folder, error=str(exc)))
            continue
        if game is not None:
            out.append(game)
    return out


def get(game_id: str, root: Path = GAMES_DIR) -> Optional[Game]:
    """按 id 拿一个游戏。"""
    for game in list_games(root):
        if game.id == game_id:
            return game
    return None


def levels_of(game: Game) -> Dict[str, object]:
    """问一个游戏"每级各多少题" —— 调的是它自己的 `levels()`（广场契约）。"""
    if game.api is None or not hasattr(game.api, "levels"):
        return {"levels": [], "total": 0}
    try:
        data = game.api.levels()
    except Exception as exc:
        return {"levels": [], "total": 0, "error": "%s: %s" % (type(exc).__name__, exc)}
    return {"levels": list(data.get("levels", [])), "total": int(data.get("total", 0))}
