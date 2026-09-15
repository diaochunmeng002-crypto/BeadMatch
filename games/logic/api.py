"""logic 的后端接口（FastAPI）。

现在**能独立跑**（广场外壳还没做，见 docs/plaza.md 第 2 步）：

    python -m games.logic.api              # 默认 127.0.0.1:8010
    python -m games.logic.api --port 8020

然后 http://127.0.0.1:8010/docs 就能点着试。
等广场做好了，它会 import 这里的 ``router``（前缀 ``/api/logic``）挂到
``/api/games/logic`` 底下 —— 接口名不用改。

| 接口 | 作用 |
| --- | --- |
| ``GET /api/logic/health`` | 活着没 + 题库目录 |
| ``GET /api/logic/levels`` | 每个等级各多少道题 |
| ``GET /api/logic/puzzles?level=1`` | 列出题目 |
| ``GET /api/logic/puzzles/{id}`` | 取一道题：**参与者 + 题目 + 答案** |
| ``GET /api/logic/random?level=1`` | 从某个等级里随机抽一道 |
| ``POST /api/logic/check`` | 交一个排法，看它对不对（哪几条线索没满足） |
"""

from __future__ import annotations

import argparse
import os
import random
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .core import puzzles as p
from .core.chinese import to_letter, to_letters
from .core.clues import holds, notation

# 题库目录可以用环境变量覆盖（打包/广场那边会设），默认就是本游戏的 puzzles/
PUZZLE_DIR = Path(os.environ.get("BEADMATCH_LOGIC_PUZZLES") or p.PUZZLE_DIR)
# 前端目录同理（web/ 由这个服务顺手托管，前端不用单独起）
WEB_DIR = Path(os.environ.get("BEADMATCH_LOGIC_WEB")
               or (Path(__file__).resolve().parent / "web"))

PREFIX = "/api/logic"

router = APIRouter(prefix=PREFIX, tags=["logic"])


# --------------------------------------------------------------------------
# 入参
# --------------------------------------------------------------------------


class CheckRequest(BaseModel):
    id: str = Field(..., description="题目 id（用哪道题的线索判定）")
    order: Union[str, List[str]] = Field(
        ..., description="排好的顺序，从左到右；字母或中文都行，例如 \"R B G Y P O\""
    )


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------


def _clue_payload(clue) -> Dict[str, object]:
    """一条线索：原文（给孩子看）+ 记号（给程序/调试看）。"""
    return {"text": clue.text.strip(), "notation": notation(clue)}


def _clue_lines(puzzle: p.Puzzle) -> List[Dict[str, object]]:
    """题目按**原句**分组返回：一句话可能对应多条判定。

    比如「绿色紧挨着蓝色，站在蓝色前面。」= ``G~B`` + ``G<B`` 两条。
    """
    lines: List[Dict[str, object]] = []
    for clue in puzzle.clues:
        text = clue.text.strip()
        if lines and lines[-1]["text"] == text:
            lines[-1]["notations"].append(notation(clue))       # type: ignore[union-attr]
        else:
            lines.append({"text": text, "notations": [notation(clue)]})
    return lines


def _puzzle_payload(puzzle: p.Puzzle, meta: Dict[str, object]) -> Dict[str, object]:
    """一道题的**核心信息**：参与者、题目（线索原文）、答案，外加出身信息。"""
    return {
        "id": meta.get("id", ""),
        "title": meta.get("title", ""),      # 题目的名字（有没有都行）
        "level": meta.get("level", 0),
        "participants": list(puzzle.participants),
        "answer": list(puzzle.answer),
        "clues": _clue_lines(puzzle),
        "created_at": meta.get("created_at", ""),
        "created_by": meta.get("created_by", ""),
        "solution_by": meta.get("solution_by", ""),
    }


def _load(puzzle_id: str) -> Tuple[p.Puzzle, Dict[str, object]]:
    path = p.find_puzzle_path(PUZZLE_DIR, puzzle_id)
    if path is None:
        raise HTTPException(404, "没有这道题：%s" % puzzle_id)
    try:
        return p.load_puzzle(path)
    except ValueError as exc:
        raise HTTPException(500, "这道题的 txt 有问题：%s" % exc)


def _tokens(order: Union[str, Sequence[str]]) -> Tuple[str, ...]:
    """把前端传来的顺序（``"R B G"`` / ``"红 蓝 绿"`` / ``["R","B","G"]``）变成字母。"""
    try:
        if isinstance(order, str):
            return to_letters(order)
        return tuple(to_letter(token) for token in order)
    except ValueError as exc:
        raise HTTPException(400, "顺序读不了：%s" % exc)


# --------------------------------------------------------------------------
# 接口
# --------------------------------------------------------------------------


@router.get("/health")
def health() -> Dict[str, object]:
    """活着没 + 题库在哪。"""
    return {"ok": True, "game": "logic",
            "puzzles_dir": str(PUZZLE_DIR), "exists": PUZZLE_DIR.is_dir()}


@router.get("/levels")
def levels() -> Dict[str, object]:
    """题库里每个等级各有多少道题。"""
    data = p.list_levels(PUZZLE_DIR)
    return {"levels": data, "total": sum(row["count"] for row in data)}


@router.get("/puzzles")
def puzzles(level: Optional[int] = Query(None, ge=0, description="只看某个等级")) -> Dict[str, object]:
    """列出题目（只读文件头，比较快）。"""
    rows = p.list_puzzles(PUZZLE_DIR, level)
    return {"count": len(rows), "puzzles": rows}


@router.get("/puzzles/{puzzle_id}")
def puzzle(puzzle_id: str) -> Dict[str, object]:
    """取一道题：参与者 + 题目（线索原文）+ 答案。"""
    puzzle_obj, meta = _load(puzzle_id)
    return _puzzle_payload(puzzle_obj, meta)


@router.get("/random")
def api_random(
    level: int = Query(1, ge=0, description="从哪个等级里随机抽，例如 1"),
) -> Dict[str, object]:
    """从某个等级里随机抽一道题。"""
    pool = p.list_puzzles(PUZZLE_DIR, level)
    if not pool:
        raise HTTPException(404, "题库里没有 %d 级的题" % level)

    pick = random.choice(pool)
    puzzle_obj, meta = _load(str(pick["id"]))
    payload = _puzzle_payload(puzzle_obj, meta)
    payload["pool_size"] = len(pool)
    return payload


@router.post("/check")
def check(req: CheckRequest) -> Dict[str, object]:
    """检查一个排法：对不对？不对的话是哪几条线索没满足。

    这是给以后"孩子排完点确认"用的；对错都返回 200，用 ``ok`` 字段区分。
    """
    puzzle_obj, _meta = _load(req.id)
    order = _tokens(req.order)

    if sorted(order) != sorted(puzzle_obj.participants):
        raise HTTPException(400, "这个顺序不是这道题的参与者：%s vs %s"
                            % (" ".join(order), " ".join(puzzle_obj.participants)))

    broken = [_clue_payload(clue) for clue in puzzle_obj.clues if not holds(clue, order)]
    return {
        "ok": not broken,
        "broken": broken,
        "total_clues": len(puzzle_obj.clues),
        "order": list(order),
    }


# --------------------------------------------------------------------------
# 独立跑（广场做好之前先这么用）
# --------------------------------------------------------------------------


app = FastAPI(
    title="BeadMatch · logic",
    description="推理游戏的题库接口：参与者 + 题目 + 答案。",
    version="0.1.0",
)
app.include_router(router)


# --------------------------------------------------------------------------
# 前端（web/）：起服务时顺手托管，打开 / 就是页面
# --------------------------------------------------------------------------

_PLACEHOLDER = """<!doctype html>
<meta charset="utf-8">
<title>BeadMatch · 推理（后端）</title>
<body style="font-family: sans-serif; padding: 2rem; line-height: 1.8; max-width: 46rem">
<h1>推理游戏的后端在跑</h1>
<p>前端还没做（<code>web/index.html</code> 不存在）。接口可以点着看，或者去
  <a href="/docs">/docs</a> 交互式试（POST 的接口只能在那边试）。</p>
<h3>题库</h3>
<ul>
  <li><a href="/api/logic/levels">/api/logic/levels</a> —— 每个等级各多少道题</li>
  <li><a href="/api/logic/puzzles?level=1">/api/logic/puzzles?level=1</a> —— 列出题目</li>
  <li><a href="/api/logic/random?level=1">/api/logic/random?level=1</a> —— 随机抽一道</li>
  <li>/api/logic/puzzles/{id} —— 取一道题（参与者 + 题目 + 答案）</li>
</ul>
<h3>其他</h3>
<ul>
  <li><a href="/api/logic/health">/api/logic/health</a> —— 活着没</li>
  <li><a href="/openapi.json">/openapi.json</a> —— 接口原始定义</li>
</ul>
</body>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    page = WEB_DIR / "index.html"
    if page.exists():
        return page.read_text(encoding="utf-8")
    return _PLACEHOLDER


# 静态目录先建出来再挂载 —— 免得"启动时 web/ 还不存在 → 没挂上"这种坑
WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def main(argv: Optional[Sequence[str]] = None) -> int:
    import uvicorn

    parser = argparse.ArgumentParser(description="跑 logic 后端")
    parser.add_argument("--host", default="127.0.0.1", help="想让平板/手机连就写 0.0.0.0")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--reload", action="store_true", help="改代码自动重启（开发用）")
    args = parser.parse_args(argv)
    uvicorn.run("games.logic.api:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
