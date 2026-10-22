"""彩珠密令的后端：只提供公开题卡，不保存或计算密令。

反馈由出题人对照实体珠子给出，程序只负责显示条件、记录尝试并获得提交的反馈数字。

    python -m games.beadcipher.api          # 单独跑，默认 8060
    python run.py                          # 从游戏广场进入
"""

from __future__ import annotations

import argparse
import os
import random
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from plaza import history
from plaza.nocache import keep_fresh

from .core import cards as k

GAME_DIR = Path(__file__).resolve().parent
PUZZLE_DIR = Path(os.environ.get("BEADCIPHER_PUZZLES") or (GAME_DIR / "puzzles"))
WEB_DIR = Path(os.environ.get("BEADCIPHER_WEB") or (GAME_DIR / "web"))

router = APIRouter(tags=["beadcipher"])


def _load(card_id: str) -> k.Card:
    path = k.find_card_path(PUZZLE_DIR, card_id)
    if path is None:
        raise HTTPException(404, "没有这道题：%s" % card_id)
    card = k.load_card(path)
    if card.problems:
        raise HTTPException(500, "这道题自己有问题，先修一下：" + "；".join(card.problems))
    return card


def _valid_cards(level: Optional[int] = None) -> List[Dict[str, object]]:
    return [row for row in k.list_cards(PUZZLE_DIR, level) if not row["problems"]]


@router.get("/health")
def health() -> Dict[str, object]:
    return {
        "ok": True,
        "game": "beadcipher",
        "puzzles_dir": str(PUZZLE_DIR),
        "exists": PUZZLE_DIR.is_dir(),
    }


@router.get("/levels")
def levels() -> Dict[str, object]:
    rows = k.list_levels(PUZZLE_DIR)
    return {"levels": rows, "total": sum(row["count"] for row in rows)}


@router.get("/puzzles")
def puzzles(level: Optional[int] = Query(None, ge=0)) -> Dict[str, object]:
    rows = [
        {"id": row["id"], "level": row["level"], "title": row["title"]}
        for row in _valid_cards(level)
    ]
    return {"count": len(rows), "puzzles": rows}


@router.get("/puzzles/{card_id}")
def card(card_id: str) -> Dict[str, object]:
    loaded = _load(card_id)
    payload = k.payload(loaded)
    history.record_served(game="beadcipher", payload=payload, source="by_id")
    return payload


@router.get("/random")
def api_random(
    level: int = Query(1, ge=0),
    exclude: Optional[str] = Query(None),
) -> Dict[str, object]:
    pool = [row for row in _valid_cards(level) if row["id"] != exclude]
    if not pool:
        pool = _valid_cards(level)
    if not pool:
        raise HTTPException(404, "题库里没有 %d 级的题" % level)
    pick = random.choice(pool)
    loaded = _load(str(pick["id"]))
    payload = k.payload(loaded)
    payload["pool_size"] = len(pool)
    history.record_served(game="beadcipher", payload=payload, source="random")
    return payload


app = FastAPI(
    title="BeadMatch · 彩珠密令",
    description="双人反馈推理题卡：显示要用的珠子与线索约定。",
    version="0.2.0",
)
app.include_router(router, prefix="/api")


_PLACEHOLDER = """<!doctype html>
<meta charset="utf-8">
<title>彩珠密令（后端）</title>
<body style="font-family:sans-serif;padding:2rem;line-height:1.8">
<h1>彩珠密令后端在跑</h1>
<p><a href="/api/levels">/api/levels</a> · <a href="/api/random?level=1">/api/random?level=1</a></p>
</body>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    page = WEB_DIR / "index.html"
    return page.read_text(encoding="utf-8") if page.exists() else _PLACEHOLDER


WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
keep_fresh(app)


def main(argv: Optional[Sequence[str]] = None) -> int:
    global PUZZLE_DIR
    import uvicorn

    parser = argparse.ArgumentParser(description="单独跑彩珠密令（广场请用 python run.py）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8060)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--puzzles", default=None)
    args = parser.parse_args(argv)
    if args.puzzles:
        PUZZLE_DIR = Path(args.puzzles).resolve()
        os.environ["BEADCIPHER_PUZZLES"] = str(PUZZLE_DIR)
    uvicorn.run("games.beadcipher.api:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
