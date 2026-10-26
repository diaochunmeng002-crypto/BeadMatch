"""数学实验室的后端接口（FastAPI）。

职责很小：把演示清单给前端。判定不在后端 —— 孩子拿实物珠子做实验，
页面给题目、玩法提示，点「看答案」亮出性质、示例摆法和一句为什么。

起服务别直接跑这个文件 —— 用仓库根目录的入口：

    python run.py                  # 默认 127.0.0.1:8000（广场里就有这个模块）
    python -m games.mathlab.api    # 单跑这个模块（8050）
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Dict, Optional, Sequence

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from plaza import history
from plaza.nocache import keep_fresh

from .core import demos as d

GAME_DIR = Path(__file__).resolve().parent
WEB_DIR = GAME_DIR / "web"

app = FastAPI(
    title="MathLab · 数学实验室",
    description="用珠子做实验：数量守恒、拆分、均分、位值……",
    version="0.1.0",
)

router = APIRouter(tags=["mathlab"])


# --------------------------------------------------------------------------
# 接口
# --------------------------------------------------------------------------


@router.get("/health")
def health() -> Dict[str, object]:
    return {"ok": True, "game": "mathlab", "demos": len(d.list_demos())}


@router.get("/levels")
def levels() -> Dict[str, object]:
    """每档几个演示（广场首页那张卡片靠它）。"""
    return d.levels()


@router.get("/puzzles")
def puzzles(level: Optional[int] = Query(None, ge=1, description="只看某一档")) -> Dict[str, object]:
    """列出演示（接口路径跟别的游戏统一叫 `/puzzles`，页面里还是叫"演示"）。"""
    rows = [{"id": demo.id, "level": demo.level, "theme": demo.theme, "title": demo.title}
            for demo in d.list_demos(level) if not demo.problems]
    return {"count": len(rows), "demos": rows}


@router.get("/puzzles/{demo_id}")
def puzzle(demo_id: str) -> Dict[str, object]:
    """按 id 取一个演示（含玩法提示、答案、示例摆法和为什么）。"""
    found = d.get(demo_id)
    if found is None:
        raise HTTPException(404, "没有这个演示：%s" % demo_id)
    if found.problems:
        raise HTTPException(500, "这个演示自己有问题，先修一下：" + "；".join(found.problems))
    payload = d.payload(found)
    history.record_served(game="mathlab", payload=payload, source="by_id")
    return payload


@router.get("/random")
def api_random(
    level: int = Query(..., ge=1, description="从哪一档里抽，例如 1"),
    exclude: Optional[str] = Query(None, description="别再抽到这一个（「换一个」用）"),
) -> Dict[str, object]:
    pool = [demo for demo in d.list_demos(level)
            if not demo.problems and demo.id != exclude]
    if not pool:
        pool = [demo for demo in d.list_demos(level) if not demo.problems]
    if not pool:
        raise HTTPException(404, "这一档还没有演示")
    pick = random.choice(pool)
    payload = d.payload(pick)
    payload["pool_size"] = len(pool)
    history.record_served(game="mathlab", payload=payload, source="random")
    return payload


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------


# 单独跑的时候接口挂在 /api/... 底下；广场里由广场挂到 /api/games/mathlab。
app.include_router(router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    page = WEB_DIR / "index.html"
    if page.exists():
        return page.read_text(encoding="utf-8")
    return "<!doctype html><meta charset='utf-8'><p>数学实验室：web/index.html 还没做。"


WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
keep_fresh(app)               # 前端别被浏览器的"启发式缓存"存住（见 plaza/nocache.py）


# --------------------------------------------------------------------------
# 单独跑
# --------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    import uvicorn

    parser = argparse.ArgumentParser(description="单独跑数学实验室（广场请用 python run.py）")
    parser.add_argument("--host", default="127.0.0.1", help="想让平板/手机连就写 0.0.0.0")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--reload", action="store_true", help="改代码自动重启（开发用）")
    args = parser.parse_args(argv)
    uvicorn.run("games.mathlab.api:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
