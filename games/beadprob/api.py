"""彩珠机会屋后端：提供题卡和随机抽取，不记录孩子选了什么。

    python -m games.beadprob.api    # 单独跑，默认 8070
    python run.py                   # 从游戏广场进入
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
PUZZLE_DIR = Path(os.environ.get("BEADPROB_PUZZLES") or (GAME_DIR / "puzzles"))
WEB_DIR = Path(os.environ.get("BEADPROB_WEB") or (GAME_DIR / "web"))

app = FastAPI(
    title="BeadMatch · 彩珠机会屋",
    description="用袋子里的彩珠比较可能性：题卡、提示和概率解释。",
    version="0.4.0",
)
router = APIRouter(tags=["beadprob"])


def _valid(level: Optional[int] = None) -> List[Dict[str, object]]:
    rows = []
    for card in k.iter_cards(PUZZLE_DIR):
        if card.problems or (level is not None and card.level != level):
            continue
        rows.append({"id": card.id, "level": card.level, "title": card.title})
    return rows


def _load(card_id: str) -> k.Card:
    path = k.find_card_path(PUZZLE_DIR, card_id)
    if path is None:
        raise HTTPException(404, "没有这道题：%s" % card_id)
    card = k.load_card(path)
    if card.problems:
        raise HTTPException(500, "这道题自己有问题，先修一下：" + "；".join(card.problems))
    return card


@router.get("/health")
def health() -> Dict[str, object]:
    return {
        "ok": True,
        "game": "beadprob",
        "puzzles_dir": str(PUZZLE_DIR),
        "exists": PUZZLE_DIR.is_dir(),
    }


@router.get("/levels")
def levels() -> Dict[str, object]:
    rows = [dict(row, name=k.LEVEL_NAMES.get(row["level"], ""))
            for row in k.list_levels(PUZZLE_DIR)]
    return {"levels": rows, "total": sum(row["count"] for row in rows)}


@router.get("/puzzles")
def puzzles(level: Optional[int] = Query(None, ge=0)) -> Dict[str, object]:
    rows = _valid(level)
    return {"count": len(rows), "puzzles": rows}


@router.get("/puzzles/{card_id}")
def card(card_id: str) -> Dict[str, object]:
    loaded = _load(card_id)
    data = k.payload(loaded)
    history.record_served(game="beadprob", payload=data, source="by_id")
    return data


@router.get("/random")
def api_random(
    level: int = Query(1, ge=0),
    exclude: Optional[str] = Query(None),
) -> Dict[str, object]:
    pool = [row for row in _valid(level) if row["id"] != exclude]
    if not pool:
        pool = _valid(level)
    if not pool:
        raise HTTPException(404, "题库里没有 %d 级的题" % level)
    picked = random.choice(pool)
    loaded = _load(str(picked["id"]))
    data = k.payload(loaded)
    data["pool_size"] = len(pool)
    history.record_served(game="beadprob", payload=data, source="random")
    return data


_PLACEHOLDER = """<!doctype html>
<meta charset="utf-8">
<title>彩珠机会屋（后端）</title>
<body style="font-family:sans-serif;padding:2rem;line-height:1.8">
<h1>彩珠机会屋后端在跑</h1>
<p><a href="/api/levels">/api/levels</a> ·
   <a href="/api/random?level=1">/api/random?level=1</a></p>
</body>
"""


app.include_router(router, prefix="/api")


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

    parser = argparse.ArgumentParser(description="单独跑彩珠机会屋（广场请用 python run.py）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8070)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--puzzles", default=None)
    args = parser.parse_args(argv)
    if args.puzzles:
        PUZZLE_DIR = Path(args.puzzles).resolve()
        os.environ["BEADPROB_PUZZLES"] = str(PUZZLE_DIR)
    uvicorn.run("games.beadprob.api:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
