"""calc 的后端接口（FastAPI）。

现在**能独立跑**（广场外壳还没做，见 docs/plaza.md 第 2 步）：

    python -m games.calc.api             # 默认 127.0.0.1:8030
    python -m games.calc.api --port 8040

然后 http://127.0.0.1:8030/docs 就能点着试。
等广场做好了，它会 import 这里的 ``router``（前缀 ``/api/calc``）挂到
``/api/games/calc`` 底下 —— 接口名不用改。

| 接口 | 作用 |
| --- | --- |
| ``GET /api/calc/health`` | 活着没 + 题库目录 |
| ``GET /api/calc/levels`` | 每个等级各多少张卡 |
| ``GET /api/calc/puzzles?level=1`` | 列出卡片 |
| ``GET /api/calc/puzzles/{id}`` | 取一张卡：**参与者 + 玩法 + 规则 + 答案** |
| ``GET /api/calc/random?level=1`` | 从某个等级随机抽一张（「出题」） |
| ``POST /api/calc/check`` | 交一个答案，看对不对 |

跟 `memory` 不一样的地方：**这儿有 ``/check``** —— 计算题的答案是一个数（或哪边多），
孩子说完就能判。
"""

from __future__ import annotations

import argparse
import os
import random
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .core import colors as C
from .core import cards as c

# 题库目录可以用环境变量覆盖（打包/广场那边会设），默认就是本游戏的 puzzles/
PUZZLE_DIR = Path(os.environ.get("BEADMATCH_CALC_PUZZLES") or c.PUZZLE_DIR)
# 前端目录同理（web/ 由这个服务顺手托管，前端不用单独起）
WEB_DIR = Path(os.environ.get("BEADMATCH_CALC_WEB")
               or (Path(__file__).resolve().parent / "web"))

PREFIX = "/api/calc"

router = APIRouter(prefix=PREFIX, tags=["calc"])


# --------------------------------------------------------------------------
# 入参
# --------------------------------------------------------------------------


class CheckRequest(BaseModel):
    id: str = Field(..., description="题目 id")
    answer: Union[str, int] = Field(
        ..., description="孩子说的答案：数字（5）、颜色（蓝 / B / 🔵），或者 equal（一样多）"
    )


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------


def _card_payload(card: c.Card, meta: Dict[str, object]) -> Dict[str, object]:
    """一张卡的**核心信息**：参与者（哪些颜色各几颗）+ 玩法 + 规则 + 答案。"""
    return {
        "id": meta.get("id", ""),
        "title": meta.get("title", ""),
        "level": int(meta.get("level", 0)),
        "task": card.task,
        "task_cn": c.TASKS.get(card.task, card.task),
        "participants": C.counts_of(card.participants),   # [{color,name,cn,en,emoji,count}]
        "beads": card.beads,                              # 一共几颗
        "colors": card.color_kinds,                       # 用了几种颜色
        "rule": card.rule,                                # 规则：给孩子听的那句话
        "answer": card.answer,                            # 原样（给人看）
        "answer_value": c.normalize_answer(card.answer),   # 规范化（数字 / 颜色字母 / equal）
        "created_at": meta.get("created_at", ""),
        "created_by": meta.get("created_by", ""),
    }


def _load(card_id: str):
    try:
        return c.load(card_id, PUZZLE_DIR)
    except LookupError:
        raise HTTPException(404, "没有这张卡：%s" % card_id)
    except ValueError as exc:
        raise HTTPException(500, "这张卡的 txt 有问题：%s" % exc)


# --------------------------------------------------------------------------
# 接口
# --------------------------------------------------------------------------


@router.get("/health")
def health() -> Dict[str, object]:
    """活着没 + 题库在哪。"""
    return {"ok": True, "game": "calc",
            "puzzles_dir": str(PUZZLE_DIR), "exists": PUZZLE_DIR.is_dir()}


@router.get("/levels")
def levels() -> Dict[str, object]:
    """题库里每个等级各有多少张卡。"""
    data = c.list_levels(PUZZLE_DIR)
    return {"levels": data, "total": sum(row["count"] for row in data)}


@router.get("/puzzles")
def puzzles(level: Optional[int] = Query(None, ge=0, description="只看某个等级")) -> Dict[str, object]:
    """列出卡片（只读文件头，比较快）。"""
    rows = c.list_cards(PUZZLE_DIR, level)
    return {"count": len(rows), "puzzles": rows}


@router.get("/puzzles/{card_id}")
def card(card_id: str) -> Dict[str, object]:
    """取一张卡：参与者 + 玩法 + 规则 + 答案。"""
    card_obj, meta = _load(card_id)
    return _card_payload(card_obj, meta)


@router.get("/random")
def api_random(
    level: int = Query(1, ge=0, description="从哪个等级里随机抽，例如 1"),
) -> Dict[str, object]:
    """从某个等级里随机抽一张卡 —— 界面上那个「出题」按钮就是它。"""
    pool = c.list_cards(PUZZLE_DIR, level)
    if not pool:
        raise HTTPException(404, "题库里没有 %d 级的卡" % level)

    pick = random.choice(pool)
    card_obj, meta = _load(str(pick["id"]))
    payload = _card_payload(card_obj, meta)
    payload["pool_size"] = len(pool)
    return payload


@router.post("/check")
def check(req: CheckRequest) -> Dict[str, object]:
    """检查一个答案：对不对？答案是"数字 / 颜色 / equal"哪种写法都行。

    对错都返回 200，用 ``ok`` 字段区分（跟 `logic` 的 ``/check`` 一个路子）。
    """
    card_obj, _meta = _load(req.id)
    try:
        given = c.normalize_answer(req.answer)
    except ValueError as exc:
        raise HTTPException(400, "答案读不了：%s" % exc)
    expected = c.normalize_answer(card_obj.answer)
    return {
        "ok": given == expected,
        "given": given,
        "expected": expected,
        "expected_answer": card_obj.answer,     # 原样（给人看）
        "task": card_obj.task,
        "task_cn": c.TASKS.get(card_obj.task, card_obj.task),
    }


# --------------------------------------------------------------------------
# 独立跑（广场做好之前先这么用）
# --------------------------------------------------------------------------


app = FastAPI(
    title="BeadMatch · calc",
    description="计算游戏的题库接口：参与者（哪些颜色各几颗）+ 玩法 + 规则 + 答案。",
    version="0.1.0",
)
app.include_router(router)


# --------------------------------------------------------------------------
# 前端（web/）：起服务时顺手托管，打开 / 就是页面
# --------------------------------------------------------------------------

_PLACEHOLDER = """<!doctype html>
<meta charset="utf-8">
<title>BeadMatch · 计算（后端）</title>
<body style="font-family: sans-serif; padding: 2rem; line-height: 1.8; max-width: 46rem">
<h1>计算游戏的后端在跑</h1>
<p>前端还没做（<code>web/index.html</code> 不存在）。接口可以点着看，或者去
  <a href="/docs">/docs</a> 交互式试（POST 的接口只能在那边试）。</p>
<h3>题目</h3>
<ul>
  <li><a href="/api/calc/levels">/api/calc/levels</a> —— 每个等级各多少张卡</li>
  <li><a href="/api/calc/puzzles?level=1">/api/calc/puzzles?level=1</a> —— 列出卡片</li>
  <li><a href="/api/calc/random?level=1">/api/calc/random?level=1</a> —— 随机抽一张（出题）</li>
  <li>/api/calc/puzzles/{id} —— 取一张卡（参与者 + 玩法 + 规则 + 答案）</li>
</ul>
<h3>其他</h3>
<ul>
  <li><a href="/api/calc/health">/api/calc/health</a> —— 活着没</li>
  <li><code>POST /api/calc/check</code> —— 交一个答案看对不对（在 /docs 里试）</li>
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

    parser = argparse.ArgumentParser(description="跑 calc 后端")
    parser.add_argument("--host", default="127.0.0.1", help="想让平板/手机连就写 0.0.0.0")
    parser.add_argument("--port", type=int, default=8030)
    parser.add_argument("--reload", action="store_true", help="改代码自动重启（开发用）")
    args = parser.parse_args(argv)
    uvicorn.run("games.calc.api:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
