"""找规律的后端接口（FastAPI）。

职责很小：把题库读出来给前端。**判定不在后端** —— 孩子在实物珠子上摆，
页面负责给题面、给任务说明，点「完成」之后亮出标准答案和规律解释，再由孩子/家长自评。

起服务别直接跑这个文件 —— 用仓库根目录的入口：

    python run.py                  # 默认 127.0.0.1:8000（广场里就有这个游戏）
    python -m games.pattern.api    # 单跑这个游戏（8040）
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

# 目录可以用环境变量覆盖 —— 打包成 exe 后，数据要放 exe 旁边、只读资源在解压目录，
# 由 launcher.py 在 import 之前设好这两个变量（不设就用本游戏文件夹里的 puzzles/ 和 web/）。
GAME_DIR = Path(__file__).resolve().parent
PUZZLE_DIR = Path(os.environ.get("PATTERN_PUZZLES") or (GAME_DIR / "puzzles"))
WEB_DIR = Path(os.environ.get("PATTERN_WEB") or (GAME_DIR / "web"))

app = FastAPI(
    title="Pattern · 找规律",
    description="看出一串珠子在按什么变，接着往下摆的后端：题库浏览 + 随机抽题",
    version="0.1.0",
)

# 接口都挂在这个 router 上（**不带前缀**）：单独跑时 app 给它加上 `/api`，
# 广场里则由广场挂到 `/api/games/pattern` 底下 —— 同一个 router，两处都能用。
router = APIRouter(tags=["pattern"])


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------


def _one_level(level: Optional[int]) -> List[Dict[str, object]]:
    """某一档里**读得进来**的题（有毛病的题不往外发）。"""
    rows = [row for row in k.list_cards(PUZZLE_DIR, level) if not row["problems"]]
    return rows


def _payload(card: k.Card) -> Dict[str, object]:
    return k.payload(card)


# --------------------------------------------------------------------------
# 接口
# --------------------------------------------------------------------------


@router.get("/health")
def health() -> Dict[str, object]:
    return {"ok": True, "game": "pattern",
            "puzzles_dir": str(PUZZLE_DIR), "exists": PUZZLE_DIR.is_dir()}


@router.get("/levels")
def levels() -> Dict[str, object]:
    """每个等级各有多少道题。"""
    data = k.list_levels(PUZZLE_DIR)
    return {"levels": data, "total": sum(row["count"] for row in data)}


@router.get("/puzzles")
def puzzles(level: Optional[int] = Query(None, ge=0, description="只看某个等级")) -> Dict[str, object]:
    """列出题目（只读文件头，比较快）。"""
    rows = [{"id": r["id"], "level": r["level"], "title": r["title"], "kind": r["kind"]}
            for r in _one_level(level)]
    return {"count": len(rows), "puzzles": rows}


@router.get("/puzzles/{card_id}")
def card(card_id: str) -> Dict[str, object]:
    """按 id 取一道题（含答案和规律解释）。"""
    path = k.find_card_path(PUZZLE_DIR, card_id)
    if path is None:
        raise HTTPException(404, "没有这道题：%s" % card_id)
    loaded = k.load_card(path)
    if loaded.problems:
        raise HTTPException(500, "这道题自己有问题，先修一下：" + "；".join(loaded.problems))
    payload = _payload(loaded)
    history.record_served(game="pattern", payload=payload, source="by_id")
    return payload


@router.get("/random")
def api_random(
    level: int = Query(..., ge=0, description="从哪个等级里随机抽，例如 1"),
    exclude: Optional[str] = Query(None, description="别再抽到这一道（「换一题」用）"),
) -> Dict[str, object]:
    """从某一档里随机抽一道题；`exclude` 给了就先把那道剔掉（换一题别原地打转）。"""
    pool = [row for row in _one_level(level) if row["id"] != exclude]
    if not pool:
        pool = _one_level(level)               # 这一档只有一道：那就还是它
    if not pool:
        raise HTTPException(404, "题库里没有 %d 级的题" % level)
    pick = random.choice(pool)
    loaded = k.load_card(Path(pick["path"]))
    payload = _payload(loaded)
    payload["pool_size"] = len(pool)
    history.record_served(game="pattern", payload=payload, source="random")
    return payload


# --------------------------------------------------------------------------
# 静态前端（还没有前端时给个说明页）
# --------------------------------------------------------------------------


_PLACEHOLDER = """<!doctype html>
<meta charset="utf-8">
<title>找规律 后端</title>
<body style="font-family: sans-serif; padding: 2rem; line-height: 1.8; max-width: 46rem">
<h1>找规律 后端在跑</h1>
<p>前端还没做。接口可以点着看，或者去 <a href="/docs">/docs</a> 交互式试。</p>
<ul>
  <li><a href="/api/levels">/api/levels</a> —— 每个等级各多少道题</li>
  <li><a href="/api/puzzles?level=1">/api/puzzles?level=1</a> —— 列出某等级的题</li>
  <li><a href="/api/random?level=1">/api/random?level=1</a> —— 随机抽一道，直接返回题目</li>
  <li>/api/puzzles/{id} —— 按 id 取一道题</li>
  <li><a href="/api/health">/api/health</a> —— 活着没</li>
</ul>
</body>
"""


# 单独跑的时候接口挂在 /api/... 底下；广场里由广场挂到 /api/games/pattern。
app.include_router(router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    page = WEB_DIR / "index.html"
    if page.exists():
        return page.read_text(encoding="utf-8")
    return _PLACEHOLDER


# 静态目录先建出来再挂载 —— 免得"启动时 web/ 还不存在 → 没挂上"这种坑
WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
keep_fresh(app)               # 前端别被浏览器的"启发式缓存"存住（见 plaza/nocache.py）


# --------------------------------------------------------------------------
# 单独跑（平时用 python run.py 起广场，这条只在单调试这个游戏时用）
# --------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    global PUZZLE_DIR
    import uvicorn

    parser = argparse.ArgumentParser(description="单独跑找规律（广场请用 python run.py）")
    parser.add_argument("--host", default="127.0.0.1", help="想让平板/手机连就写 0.0.0.0")
    parser.add_argument("--port", type=int, default=8040)
    parser.add_argument("--reload", action="store_true", help="改代码自动重启（开发用）")
    parser.add_argument("--puzzles", metavar="目录", default=None,
                        help="换一个题库目录（默认 %s）" % PUZZLE_DIR)
    args = parser.parse_args(argv)
    if args.puzzles:
        PUZZLE_DIR = Path(args.puzzles).resolve()
        os.environ["PATTERN_PUZZLES"] = str(PUZZLE_DIR)
        print("题库目录换成：%s（存在：%s）" % (PUZZLE_DIR, PUZZLE_DIR.exists()))
    uvicorn.run("games.pattern.api:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
