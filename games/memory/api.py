"""memory 的后端接口（FastAPI）。

现在**能独立跑**（广场外壳还没做，见 docs/plaza.md 第 2 步）：

    python -m games.memory.api             # 默认 127.0.0.1:8020
    python -m games.memory.api --port 8030

然后 http://127.0.0.1:8020/docs 就能点着试。
等广场做好了，它会 import 这里的 ``router``（前缀 ``/api/memory``）挂到
``/api/games/memory`` 底下 —— 接口名不用改。

| 接口 | 作用 |
| --- | --- |
| ``GET /api/memory/health`` | 活着没 + 卡片库目录 |
| ``GET /api/memory/levels`` | 每个等级各多少张卡 |
| ``GET /api/memory/puzzles?level=1`` | 列出规则卡 |
| ``GET /api/memory/puzzles/{id}`` | 取一张卡：**材料 + 形式 + 观察时间 + 还原什么** |
| ``GET /api/memory/random?level=1`` | 从某个等级随机抽一张（**这才是「出题」**） |

⚠️ **没有 ``/check``。** memory 的排列是出题人当场摆的，程序手里没有答案，
判定由出题人做（见 README §2）—— 所以这套接口只给规则，不给答案。
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

from .core import colors as C
from .core import cards as c

# 卡片库目录可以用环境变量覆盖（打包/广场那边会设），默认就是本游戏的 puzzles/
PUZZLE_DIR = Path(os.environ.get("BEADMATCH_MEMORY_PUZZLES") or c.PUZZLE_DIR)
# 前端目录同理（web/ 由这个服务顺手托管，前端不用单独起）
WEB_DIR = Path(os.environ.get("BEADMATCH_MEMORY_WEB")
               or (Path(__file__).resolve().parent / "web"))

# 单独跑的时候接口挂在 /api/memory 底下；广场里由广场挂到 /api/games/memory
PREFIX = "/api/memory"

router = APIRouter(tags=["memory"])


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------


def _card_payload(card: c.Card, meta: Dict[str, object]) -> Dict[str, object]:
    """一张卡的**核心信息**：材料清单 + 摆法形式 + 观察时间 + 还原什么。

    ⚠️ 没有"答案"这一栏 —— 这游戏压根没有标准排列（README §2）。
    """
    return {
        "id": meta.get("id", ""),
        "title": meta.get("title", ""),
        "noun": card.noun_cn,                      # 这些珠子扮演谁（没写就是"珠子"）
        "unit": card.unit_cn,                      # 数它的量词（没写就是"颗"）
        "level": int(meta.get("level", 0)),
        "materials": C.counts_of(card.materials),   # [{color, name, cn, en, emoji, count}]
        "beads": card.beads,                        # 一共几颗
        "colors": card.color_kinds,                 # 用了几种颜色
        "shape": card.shape,
        "shape_cn": c.SHAPES.get(card.shape, card.shape),
        "observe": card.observe,                    # 观察几秒
        "restore": card.restore,
        "restore_cn": c.RESTS.get(card.restore, card.restore),
        "delay": card.delay,
        "reverse": card.reverse,
        "demo": list(card.demo),                    # 只示意，不是答案
        "note": card.note,                          # 给出题人看的一句说明
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
    """活着没 + 卡片库在哪。"""
    return {"ok": True, "game": "memory",
            "puzzles_dir": str(PUZZLE_DIR), "exists": PUZZLE_DIR.is_dir()}


@router.get("/levels")
def levels() -> Dict[str, object]:
    """卡片库里每个等级各有多少张卡。"""
    data = c.list_levels(PUZZLE_DIR)
    return {"levels": data, "total": sum(row["count"] for row in data)}


@router.get("/puzzles")
def puzzles(level: Optional[int] = Query(None, ge=0, description="只看某个等级")) -> Dict[str, object]:
    """列出规则卡（只读文件头，比较快）。"""
    rows = c.list_cards(PUZZLE_DIR, level)
    return {"count": len(rows), "puzzles": rows}


@router.get("/puzzles/{card_id}")
def card(card_id: str) -> Dict[str, object]:
    """取一张卡：材料 + 形式 + 观察时间 + 还原什么。"""
    card_obj, meta = _load(card_id)
    return _card_payload(card_obj, meta)


@router.get("/random")
def api_random(
    level: int = Query(1, ge=0, description="从哪个等级里随机抽，例如 1"),
) -> Dict[str, object]:
    """从某个等级里随机抽一张卡 —— 界面上那个「出题」按钮就是它。"""
    pool = c.list_cards(PUZZLE_DIR, level)
    if not pool:
        raise HTTPException(404, "卡片库里没有 %d 级的卡" % level)

    pick = random.choice(pool)
    card_obj, meta = _load(str(pick["id"]))
    payload = _card_payload(card_obj, meta)
    payload["pool_size"] = len(pool)
    return payload


# --------------------------------------------------------------------------
# 独立跑（广场做好之前先这么用）
# --------------------------------------------------------------------------


app = FastAPI(
    title="BeadMatch · memory",
    description="记忆游戏的规则卡接口：材料 + 形式 + 观察时间 + 还原什么。"
                "**没有答案** —— 排列由出题人当场摆。",
    version="0.1.0",
)
app.include_router(router, prefix=PREFIX)


# --------------------------------------------------------------------------
# 前端（web/）：起服务时顺手托管，打开 / 就是页面
# --------------------------------------------------------------------------

_PLACEHOLDER = """<!doctype html>
<meta charset="utf-8">
<title>BeadMatch · 记忆（后端）</title>
<body style="font-family: sans-serif; padding: 2rem; line-height: 1.8; max-width: 46rem">
<h1>记忆游戏的后端在跑</h1>
<p>前端还没做（<code>web/index.html</code> 不存在）。接口可以点着看，或者去
  <a href="/docs">/docs</a> 交互式试。</p>
<h3>规则卡</h3>
<ul>
  <li><a href="/api/memory/levels">/api/memory/levels</a> —— 每个等级各多少张卡</li>
  <li><a href="/api/memory/puzzles?level=1">/api/memory/puzzles?level=1</a> —— 列出卡片</li>
  <li><a href="/api/memory/random?level=1">/api/memory/random?level=1</a> —— 随机抽一张（出题）</li>
  <li>/api/memory/puzzles/{id} —— 取一张卡（材料 + 形式 + 观察时间 + 还原什么）</li>
</ul>
<h3>其他</h3>
<ul>
  <li><a href="/api/memory/health">/api/memory/health</a> —— 活着没</li>
  <li><a href="/openapi.json">/openapi.json</a> —— 接口原始定义</li>
</ul>
<p>⚠️ 没有 <code>/check</code>：判定由出题人做，程序手里没有答案。</p>
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

    parser = argparse.ArgumentParser(description="跑 memory 后端")
    parser.add_argument("--host", default="127.0.0.1", help="想让平板/手机连就写 0.0.0.0")
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--reload", action="store_true", help="改代码自动重启（开发用）")
    args = parser.parse_args(argv)
    uvicorn.run("games.memory.api:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
