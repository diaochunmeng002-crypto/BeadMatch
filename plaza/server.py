"""广场外壳：一个程序装所有游戏（见 ../docs/plaza.md §4）。

    python run.py                 # 默认 127.0.0.1:8000（推荐，唯一入口）
    python -m plaza.server        # 一样，调试时方便

页面（广场占根路径，每个游戏在自己的前缀下，谁也不挡谁）：

    /                             广场首页：列出所有游戏
    /games/<id>/                  某个游戏的页面（广场顺手往页面里注入接口基址）
    /games/<id>/static/...        那个游戏的静态资源
    /static/...                   广场公共的前端（首页样式等）

接口：

    GET  /api/games                        有哪些游戏
    GET  /api/games/<id>/levels            那个游戏每级各多少题
    GET  /api/games/<id>/random?level=N    随机抽一道
    GET  /api/games/<id>/puzzles/{pid}     按 id 取一道
    POST /api/games/<id>/check             判定（有这条游戏的才有）
    GET  /api/games/<id>/health            那个游戏活着没
    GET  /api/health                       广场活着没
    GET  /api/history?limit=200            最近访问记录（新的在前）

**广场自己不知道任何游戏规则**，它只是把每个游戏 `api.py` 里的 `router` 换个前缀挂上，
再把它的 `web/` 托管出去（见 registry.py）。

页面 `/history` 是那条访问清单：默认拉最近 200 条，只看"时间 / 游戏 / id"。
首页页脚有一个不显眼的入口 —— 这是给自己人看的，不往游戏页面上放。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import history, registry
from .registry import Game

WEB_DIR = Path(__file__).resolve().parent / "web"

app = FastAPI(
    title="BeadMatch 游戏广场",
    description="一个程序装多个游戏：串珠（规划）、推理、记忆、计算……"
                "每个游戏的规则和题库都是它自己的，广场只负责「有哪些游戏、怎么开」。",
    version="0.1.0",
)


# --------------------------------------------------------------------------
# 每个游戏：挂接口 + 挂静态 + 挂页面
# --------------------------------------------------------------------------


# 广场给每个游戏页面加的"换个游戏"小条：放在**页面最上面（游戏标题之前）**，
# 字小、颜色淡、用各游戏自己的主题变量，所以看着像游戏自带的。
# 能点的写成带下划线的链接，"你正在看的这个"是加粗、没有下划线 —— 一眼分得开。
# **游戏自己不用改代码**；单独跑某个游戏时不会出现外链。
_NAV_CSS = """<style>
.plaza-nav{width:100%;max-width:46rem;margin:0 0 10px;font-size:.82rem;line-height:1.8;
  color:var(--muted,#8a857f);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.plaza-nav a{color:inherit;text-decoration:underline;text-underline-offset:3px;
  text-decoration-thickness:1px;text-decoration-color:rgba(128,128,128,.45)}
.plaza-nav a:hover{color:var(--ink,#333);text-decoration-color:currentColor}
.plaza-nav .sep{opacity:.35}
.plaza-nav .here{color:var(--ink,#333);font-weight:600}
</style>"""


def _nav_html(current: Game) -> str:
    parts = ['<a class="home" href="/">游戏广场</a>']
    for game in GAMES:
        parts.append('<span class="sep">·</span>')
        if game.id == current.id:
            parts.append('<span class="here">%s</span>' % game.name)
        else:
            parts.append('<a href="%s">%s</a>' % (game.url, game.name))
    return '<nav class="plaza-nav" aria-label="换个游戏">' + "".join(parts) + "</nav>"


def _game_page(game: Game) -> str:
    """游戏的页面 —— 顺手注入两样东西：接口基址（前端两种跑法共用一套代码）
    ＋ 顶部那条"换个游戏"（游戏自己不用管）。"""
    index = game.web_dir / "index.html"
    if not index.is_file():
        return ("<!doctype html><meta charset='utf-8'><title>%s</title>"
                "<body style='font-family:sans-serif;padding:2rem'>"
                "<p>这个游戏还没有页面（<code>web/index.html</code> 不存在）。</p>"
                "<p><a href='/'>← 回广场</a></p>" % game.name)

    html = index.read_text(encoding="utf-8")
    # 接口基址 + 导航的样式都塞进 head（样式早一步到，就不会先闪一个没样式的导航）
    inject = "<script>window.API_BASE=%s;</script>" % json.dumps(game.api_base)
    inject += "\n" + _NAV_CSS
    if "</head>" in html:
        html = html.replace("</head>", inject + "\n</head>", 1)
    else:
        html = inject + html

    nav = _nav_html(game)
    body = re.search(r"<body[^>]*>", html)
    if body:                                 # 导航在**最上面**，游戏标题在它下面
        return html[: body.end()] + "\n" + nav + html[body.end():]
    return nav + html


def _page_route(game: Game):
    def page() -> HTMLResponse:
        return HTMLResponse(_game_page(game))
    page.__name__ = "page_%s" % game.id.replace("-", "_")
    return page


def _slash_route(game: Game):
    def go() -> RedirectResponse:
        return RedirectResponse(game.url, status_code=307)
    go.__name__ = "slash_%s" % game.id.replace("-", "_")
    return go


GAMES = registry.list_games()

for _game in GAMES:
    if _game.api is not None and hasattr(_game.api, "router"):
        app.include_router(_game.api.router, prefix=_game.api_base)
    app.get(_game.url, response_class=HTMLResponse)(_page_route(_game))
    app.get(_game.url.rstrip("/"))(_slash_route(_game))       # 少个斜杠 → 跳过去
    if _game.web_dir.is_dir():
        app.mount("/games/%s/static" % _game.id, StaticFiles(directory=_game.web_dir),
                  name="%s-static" % _game.id)


# --------------------------------------------------------------------------
# 广场自己的接口
# --------------------------------------------------------------------------


@app.get("/api/health")
def health() -> Dict[str, object]:
    """广场活着没。"""
    games = registry.list_games()
    return {"ok": True, "plaza": True, "games": len(games),
            "broken": [g.id for g in games if g.error]}


@app.get("/api/games")
def api_games() -> Dict[str, object]:
    """有哪些游戏（首页和外面的程序都用这条）。"""
    rows: List[Dict[str, object]] = []
    for game in registry.list_games():
        info = registry.levels_of(game)
        row: Dict[str, object] = {
            "id": game.id,
            "name": game.name,
            "category": game.category,
            "summary": game.summary,
            "url": game.url,
            "api_base": game.api_base,
            "levels": info["levels"],
            "total": info["total"],
        }
        if game.error:
            row["error"] = game.error
        if info.get("error"):
            row["levels_error"] = info["error"]
        rows.append(row)
    return {"count": len(rows), "games": rows}


@app.get("/api/history")
def api_history(
    limit: int = Query(200, ge=1, le=1000, description="要几条，默认 200"),
) -> Dict[str, object]:
    """最近访问记录，新的在前。数据来源见 plaza/history.py。"""
    try:
        rows = history.query(limit=limit)
    except Exception as exc:
        raise HTTPException(500, "访问日志读不了：%s" % exc)
    return {"count": len(rows), "events": rows}


# --------------------------------------------------------------------------
# 首页
# --------------------------------------------------------------------------

_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BeadMatch · 游戏广场</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<header>
  <h1>游戏广场</h1>
  <p class="lead">实体串珠 + 一个小程序：家长出题，孩子在实物上动手。</p>
</header>
<main>
%s
</main>
<footer>
  <p>共 %d 个游戏 · 接口清单在 <a href="/api/games">/api/games</a> ·
     每个游戏的接口文档在 <a href="/docs">/docs</a>
     <a class="access" href="/history" title="最近 200 条访问记录">访问清单</a></p>
</footer>
</body>
</html>
"""


_HISTORY_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>访问清单 · BeadMatch</title>
<link rel="stylesheet" href="/static/style.css">
<style>
.bar{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:.85rem}
.bar button{font:inherit;color:inherit;background:var(--card);border:1px solid var(--border);
  border-radius:999px;padding:3px 12px;cursor:pointer}
.bar button:hover{border-color:var(--ink);color:var(--ink)}
.wrap{overflow-x:auto;border:1px solid var(--border);border-radius:14px;background:var(--card)}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--border);white-space:nowrap}
th{font-size:.78rem;color:var(--muted);font-weight:600}
tbody tr:last-child td{border-bottom:0}
td.time{color:var(--muted);font-variant-numeric:tabular-nums}
td.game{font-weight:600}
td .muted{color:var(--muted);font-weight:400}
td.id{font-family:ui-monospace,Consolas,monospace;font-size:.85rem}
.none{color:var(--muted)}
</style>
</head>
<body>
<header>
  <h1>访问清单</h1>
  <p class="lead">最近 200 条，新的在最上面 · <a href="/">← 回广场</a></p>
</header>
<main>
  <div class="bar"><span id="status">读取中…</span><button id="reload">刷新</button></div>
  <div class="wrap" id="wrap" hidden>
    <table>
      <thead><tr><th>时间</th><th>游戏</th><th>id</th></tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </div>
  <p class="none" id="empty" hidden>还没有记录。</p>
</main>
<script>
const rowsEl = document.getElementById('rows');
const wrapEl = document.getElementById('wrap');
const emptyEl = document.getElementById('empty');
const statusEl = document.getElementById('status');

function stamp(text) {
  const d = new Date(text);
  if (isNaN(d.getTime())) return text || '';
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} `
       + `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function line(ev) {
  const tr = document.createElement('tr');

  const time = document.createElement('td');
  time.className = 'time';
  time.textContent = stamp(ev.ts);

  const game = document.createElement('td');
  game.className = 'game';
  game.textContent = ev.game || '';
  if (ev.level !== null && ev.level !== undefined) {
    const lv = document.createElement('span');
    lv.className = 'muted';
    lv.textContent = ` · ${ev.level} 级`;
    game.appendChild(lv);
  }

  const id = document.createElement('td');
  id.className = 'id';
  id.textContent = ev.puzzle_id || '';

  tr.append(time, game, id);
  return tr;
}

async function load() {
  statusEl.textContent = '读取中…';
  try {
    const r = await fetch('/api/history?limit=200');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    const events = data.events || [];
    rowsEl.replaceChildren(...events.map(line));
    wrapEl.hidden = events.length === 0;
    emptyEl.hidden = events.length !== 0;
    statusEl.textContent = `共 ${events.length} 条`;
  } catch (e) {
    wrapEl.hidden = true;
    emptyEl.hidden = true;
    statusEl.textContent = '读取失败：' + e.message;
  }
}

document.getElementById('reload').addEventListener('click', load);
load();
</script>
</body>
</html>
"""


def _home_html() -> str:
    cards: List[str] = []
    for game in registry.list_games():
        info = registry.levels_of(game)
        levels = info["levels"]
        if levels:
            detail = "、".join("%s 级 %d 题" % (row["level"], row["count"]) for row in levels)
            detail = "共 %d 题（%s）" % (info["total"], detail)
        else:
            detail = "还没有题目"
        warn = ""
        if game.error:
            warn = '<p class="warn">起不来：%s</p>' % game.error
            detail = "——"
        cards.append(
            '<a class="game" href="%s">'
            '<span class="name">%s</span>'
            '<span class="tag">%s</span>'
            '<span class="summary">%s</span>'
            '<span class="count">%s</span>%s'
            "</a>" % (game.url, game.name, game.category, game.summary, detail, warn)
        )
    if not cards:
        cards.append('<p class="empty">还没发现任何游戏 —— 游戏文件夹里要有 <code>game.toml</code>。</p>')
    return _PAGE % ("\n".join(cards), len(cards))


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _home_html()


@app.get("/history", response_class=HTMLResponse)
def history_page() -> str:
    """访问清单 —— 首页页脚那个不显眼的入口。"""
    return _HISTORY_PAGE


# 静态目录先建出来再挂载 —— 免得"启动时 web/ 还不存在 → 没挂上"这种坑
WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="plaza-static")


# --------------------------------------------------------------------------
# 单独跑广场（run.py 也是起这个 app）
# --------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    import uvicorn

    parser = argparse.ArgumentParser(description="跑 BeadMatch 游戏广场")
    parser.add_argument("--host", default="127.0.0.1", help="想让平板/手机连就写 0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="改代码自动重启（开发用）")
    args = parser.parse_args(argv)
    uvicorn.run("plaza.server:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
