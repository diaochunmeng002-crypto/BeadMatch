"""串珠的后端接口（FastAPI）。

职责很小：把题库读出来给前端、算「下一步怎么走」、需要时现出一题。
出题和求解都在 Python 里（`core/generator.py` / `core/free_solver.py`），这里只做包装。

起服务别直接跑这个文件 —— 用仓库根目录的入口：

    python run.py                    # 默认 127.0.0.1:8000
    python run.py --reload           # 开发用，改代码自动重启
    python run.py --host 0.0.0.0     # 想让平板/手机连就用这个

接口文档：起服务后打开 http://127.0.0.1:8000/docs
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
from pydantic import BaseModel, Field

from plaza import history

from .core import generator as g
from .core.free_solver import format_moves, is_finished, solve_any

# 目录可以用环境变量覆盖 —— 打包成 exe 后，数据要放 exe 旁边、只读资源在解压目录，
# 由 launcher.py 在 import 之前设好这两个变量（不设就用本游戏文件夹里的 puzzles/ 和 web/）。
GAME_DIR = Path(__file__).resolve().parent
PUZZLE_DIR = Path(os.environ.get("BEADSORT_PUZZLES") or (GAME_DIR / "puzzles"))
WEB_DIR = Path(os.environ.get("BEADSORT_WEB") or (GAME_DIR / "web"))

app = FastAPI(
    title="BeadSort · 竞技串珠",
    description="出题器的后端：题库浏览 + 下一步提示 + 现场出题",
    version="0.1.0",
)

# 接口都挂在这个 router 上（**不带前缀**）：单独跑时 app 给它加上 `/api`，
# 广场里则由广场挂到 `/api/games/beadsort` 底下 —— 同一个 router，两处都能用。
router = APIRouter(tags=["beadsort"])


# --------------------------------------------------------------------------
# 入参
# --------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    difficulty: int = Field(5, ge=0, description="想要的等级（目前不筛选，只记录）")
    walk_steps: Optional[int] = Field(None, ge=1, le=2000, description="出题时随机乱走多少步")
    seed: Optional[int] = Field(None, description="随机种子；给了就能复现")
    save: bool = Field(False, description="是否把这题存进题库")


class NextRequest(BaseModel):
    matrix: List[List[int]] = Field(
        ..., description="矩阵[柱子][位置]；位置 0 = 最顶端那一格，0 表示空位"
    )
    id: Optional[str] = Field(
        None, description="题目 id。给了就用题目文件里的标准解法（又快又准），不用现算"
    )


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------


def _check_matrix(matrix: List[List[int]]) -> None:
    """校验局面：形状、取值、空位在顶端、每色颗数。对不上抛 400。"""
    if not matrix or not matrix[0]:
        raise HTTPException(400, "矩阵是空的")
    tubes, capacity = len(matrix), len(matrix[0])
    colors = set()
    for t, tube in enumerate(matrix):
        if len(tube) != capacity:
            raise HTTPException(400, "第 %d 根柱子的格子数是 %d，!= %d" % (t + 1, len(tube), capacity))
        seen_ball = False
        for v in tube:
            if v < 0 or v > g.COLORS:
                raise HTTPException(400, "第 %d 根柱子出现越界颜色 %r" % (t + 1, v))
            if v:
                seen_ball = True
                colors.add(v)
            elif seen_ball:
                raise HTTPException(400, "第 %d 根柱子的空位不在顶端" % (t + 1))
    for c in range(1, g.COLORS + 1):
        n = sum(tube.count(c) for tube in matrix)
        if c in colors and n != g.BALLS_PER_COLOR:
            raise HTTPException(400, "颜色 %d 有 %d 颗，!= %d" % (c, n, g.BALLS_PER_COLOR))


def _puzzle_payload(matrix, meta: Dict[str, object]) -> Dict[str, object]:
    return {
        "id": meta.get("id", ""),
        "level": meta.get("level", 0),
        "moves": meta.get("moves", 0),
        "steps": meta.get("steps", 0),
        "seed": meta.get("seed", 0),
        "tubes": meta.get("tubes", len(matrix)),
        "capacity": meta.get("capacity", len(matrix[0]) if matrix else 0),
        "colors": meta.get("colors", g.COLOR_LETTERS[: g.COLORS]),
        "color_names": list(g.COLOR_NAMES[: g.COLORS]),
        "generator": meta.get("generator", ""),
        "created_by": meta.get("created_by", ""),
        "created_at": meta.get("created_at", ""),
        "solution_by": meta.get("solution_by", ""),
        "solution": meta.get("solution", ""),
        "matrix": [list(t) for t in matrix],
    }


# --------------------------------------------------------------------------
# 接口
# --------------------------------------------------------------------------


@router.get("/health")
def health() -> Dict[str, object]:
    return {"ok": True, "puzzles_dir": str(PUZZLE_DIR), "exists": PUZZLE_DIR.exists()}


@router.get("/levels")
def levels() -> Dict[str, object]:
    """题库里每个等级各有多少道题。"""
    data = g.list_levels(PUZZLE_DIR)
    return {"levels": data, "total": sum(x["count"] for x in data)}


@router.get("/puzzles")
def puzzles(level: Optional[int] = None) -> Dict[str, object]:
    """列出题目（可按等级筛），只返回收下的。"""
    data = g.list_puzzles(PUZZLE_DIR, level)
    return {"count": len(data), "puzzles": data}


@router.get("/puzzles/{puzzle_id}")
def puzzle(puzzle_id: str) -> Dict[str, object]:
    """按 id 取一道题（含标准解法）。"""
    path = g.find_puzzle_path(PUZZLE_DIR, puzzle_id)
    if path is None:
        raise HTTPException(404, "没有这道题：%s" % puzzle_id)
    matrix, meta = g.load_board(path)
    payload = _puzzle_payload(matrix, meta)
    history.record_served(game="beadsort", payload=payload, source="by_id")
    return payload


@router.get("/random")
def api_random(
    level: int = Query(..., ge=0, description="从哪个等级里随机抽，例如 3"),
) -> Dict[str, object]:
    """从**某一个等级**里随机抽一道题，直接返回完整题目（含标准解法）。"""
    pool = g.list_puzzles(PUZZLE_DIR, level)
    if not pool:
        raise HTTPException(404, "题库里没有 %d 级的题" % level)

    pick = random.choice(pool)
    path = g.find_puzzle_path(PUZZLE_DIR, str(pick["id"]))
    if path is None:
        raise HTTPException(500, "题库索引里有这道题但文件找不到：%s" % pick["id"])
    matrix, meta = g.load_board(path)
    payload = _puzzle_payload(matrix, meta)
    payload["pool_size"] = len(pool)
    history.record_served(game="beadsort", payload=payload, source="random")
    return payload


@router.post("/next")
def api_next(req: NextRequest) -> Dict[str, object]:
    """提示下一步怎么走。

    ⚠️ **暂定接口**（docs/requirement.md §9 第 3 条还没定稿）。

    两种用法：
    * 带 `id`（推荐）：直接用题目文件里的标准解法 —— 又快又准，还不用求解器；
      前提是 `matrix` 还是这题的初始局面（孩子还没动过）。
    * 不带 `id`：拿矩阵现算一条解（用我们自己的 DFS，**可能算不出来**，那就 504）。
    """
    _check_matrix(req.matrix)
    if is_finished(req.matrix):
        return {"finished": True, "move": None, "move_text": "", "remaining": 0}

    if req.id:
        path = g.find_puzzle_path(PUZZLE_DIR, req.id)
        if path is not None:
            start, meta = g.load_board(path)
            if [list(t) for t in start] == req.matrix:
                moves = g.parse_moves(str(meta["solution"]))
                first = moves[0]
                return {
                    "finished": False,
                    "source": "puzzle",
                    "move": {"from": first[0], "to": first[1]},
                    "move_text": format_moves([first]),
                    "remaining": len(moves),
                    "solution": format_moves(moves),
                }

    moves = solve_any(req.matrix, time_limit=5.0)
    if not moves:
        raise HTTPException(504, "这一步没算出来（超预算），可以再试一次")
    first = moves[0]
    return {
        "finished": False,
        "source": "solver",
        "move": {"from": first[0], "to": first[1]},          # 0 起
        "move_text": format_moves([first]),                  # 1 起，跟文件格式一致
        "remaining": len(moves),
        "solution": format_moves(moves),
    }


@router.post("/generate")
def api_generate(req: GenerateRequest) -> Dict[str, object]:
    """现场出一题（默认不落盘）。题库里已经有几百道，这个接口是留给"想现出"的场景。"""
    matrix, meta = g.generate(req.difficulty, seed=req.seed, walk_steps=req.walk_steps)
    if req.save:
        g.save_board(PUZZLE_DIR, matrix, meta)
    return _puzzle_payload(matrix, meta)


@router.post("/play")
def api_play(req: NextRequest) -> Dict[str, object]:
    """把整条解给出来（给前端做"演示解法"动画用）。带 `id` 就直接读题目文件。"""
    _check_matrix(req.matrix)
    if req.id:
        path = g.find_puzzle_path(PUZZLE_DIR, req.id)
        if path is not None:
            start, meta = g.load_board(path)
            if [list(t) for t in start] == req.matrix:
                moves = g.parse_moves(str(meta["solution"]))
                return {"moves": format_moves(moves), "count": len(moves),
                        "source": "puzzle"}
    moves = solve_any(req.matrix, time_limit=5.0)
    if moves is None:
        raise HTTPException(504, "没算出来（超预算）")
    return {"moves": format_moves(moves), "count": len(moves), "source": "solver"}


# --------------------------------------------------------------------------
# 静态前端（还没有前端时给个说明页）
# --------------------------------------------------------------------------


_PLACEHOLDER = """<!doctype html>
<meta charset="utf-8">
<title>竞技串珠 后端</title>
<body style="font-family: sans-serif; padding: 2rem; line-height: 1.8; max-width: 46rem">
<h1>竞技串珠 后端在跑</h1>
<p>前端还没做。接口可以点着看，或者去 <a href="/docs">/docs</a> 交互式试（POST 的接口只能在那边试）。</p>

<h3>题库</h3>
<ul>
  <li><a href="/api/levels">/api/levels</a> —— 每个等级各多少道题</li>
  <li><a href="/api/puzzles?level=3">/api/puzzles?level=3</a> —— 列出某等级的题（可换等级）</li>
  <li><a href="/api/random?level=3">/api/random?level=3</a> —— <b>随机抽一道</b>，直接返回题目（含标准解法）</li>
  <li>/api/puzzles/{id} —— 按 id 取一道题，得把 {id} 换成真实编号（先从上面那个列表里拿）</li>
</ul>

<h3>玩的时候</h3>
<ul>
  <li>POST /api/next —— 提示下一步（<a href="/docs">去 /docs 试</a>）</li>
  <li>POST /api/play —— 算出整条解，给"演示解法"动画用（<a href="/docs">去 /docs 试</a>）</li>
</ul>

<h3>出题</h3>
<ul>
  <li>POST /api/generate —— 现场出一题，可选存进题库（<a href="/docs">去 /docs 试</a>）</li>
</ul>

<h3>其他</h3>
<ul>
  <li><a href="/api/health">/api/health</a> —— 活着没</li>
  <li><a href="/openapi.json">/openapi.json</a> —— 接口原始定义</li>
</ul>
</body>
"""


# 单独跑的时候接口挂在 /api/... 底下（跟以前一模一样）；广场里由广场挂到
# /api/games/beadsort —— 同一个 router，前缀不一样而已。
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


# --------------------------------------------------------------------------
# 单独跑（平时用 python run.py 起广场，这条只在单调试这个游戏时用）
# --------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    global PUZZLE_DIR
    import uvicorn

    parser = argparse.ArgumentParser(description="单独跑竞技串珠（广场请用 python run.py）")
    parser.add_argument("--host", default="127.0.0.1", help="想让平板/手机连就写 0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="改代码自动重启（开发用）")
    parser.add_argument("--puzzles", metavar="目录", default=None,
                        help="换一个题库目录（默认 %s）。例：--puzzles games/beadsort/puzzles_kociemba"
                             % PUZZLE_DIR)
    args = parser.parse_args(argv)
    if args.puzzles:                     # 2026-09-18：以前只能靠环境变量 BEADSORT_PUZZLES
        PUZZLE_DIR = Path(args.puzzles).resolve()
        os.environ["BEADSORT_PUZZLES"] = str(PUZZLE_DIR)   # --reload 会另起进程，得靠环境变量传下去
        print("题库目录换成：%s（存在：%s）" % (PUZZLE_DIR, PUZZLE_DIR.exists()))
    uvicorn.run("games.beadsort.api:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
