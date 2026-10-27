"""本地保存「哪些难度不在游戏菜单里显示」。

配置只记隐藏的等级。这样游戏以后新增的等级会默认显示，不需要迁移配置。
文件跟历史记录放在同一个可写数据目录，开发时就是仓库根目录。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, Iterable, Mapping, List

from . import history

log = logging.getLogger(__name__)

SETTINGS_NAME = "difficulty-settings.json"
_write_lock = threading.Lock()


def settings_path() -> Path:
    """配置文件位置；测试可用环境变量直接指定。"""
    explicit = (os.environ.get("BEADMATCH_DIFFICULTY_SETTINGS") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return history.data_dir() / SETTINGS_NAME


def load_hidden() -> Dict[str, List[int]]:
    """读隐藏等级。文件不存在或损坏时按「全部显示」处理。"""
    path = settings_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("hidden", {}) if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            raise ValueError("hidden 不是对象")
        out: Dict[str, List[int]] = {}
        for game_id, values in raw.items():
            if not isinstance(game_id, str) or not isinstance(values, list):
                continue
            levels = sorted({
                int(value) for value in values
                if isinstance(value, int) and not isinstance(value, bool) and value > 0
            })
            if levels:
                out[game_id] = levels
        return out
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        log.warning("难度配置读不了，先按全部显示：%s", exc)
        return {}


def save_hidden(hidden: Mapping[str, Iterable[int]]) -> Dict[str, List[int]]:
    """原子写入隐藏等级，返回实际保存的规范化内容。"""
    normalized: Dict[str, List[int]] = {}
    for game_id, values in hidden.items():
        levels = sorted({
            int(value) for value in values
            if isinstance(value, int) and not isinstance(value, bool) and value > 0
        })
        if levels:
            normalized[str(game_id)] = levels

    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "hidden": normalized}
    temp = path.with_name(path.name + ".tmp")
    with _write_lock:
        try:
            temp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temp, path)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass
    return normalized
