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
    POST /api/history/clear                把访问记录全清掉（历史页那个「清空」按钮）
    GET  /api/stars?game=&level=           收藏列表（新的在前）
    POST /api/star                         收藏 / 取消（幂等：{"game","puzzle_id","level","starred"}）

**广场自己不知道任何游戏规则**，它只是把每个游戏 `api.py` 里的 `router` 换个前缀挂上，
再把它的 `web/` 托管出去（见 registry.py）。

页面 `/history` 是那条访问清单：默认拉最近 200 条，看"时间 / 游戏 / 等级 / 题目 / 出题者"，
上头有「刷新」和「清空」。入口在首页副标题后面（「历史」）；「GitHub」在页脚
（跟接口清单 / 接口文档一排）—— 都是给自己人看的，不往游戏页面上放。
页面 `/stars` 是我收藏的题：布局照历史页，一颗黄星点一下取消、行尾「打开」是深链接。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import history, registry, stars
from .nocache import keep_fresh
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
.plaza-nav .plaza-star{margin-left:auto;font:inherit;font-size:.8rem;color:inherit;
  background:none;border:1px solid rgba(128,128,128,.35);border-radius:999px;
  padding:1px 10px;cursor:pointer;white-space:nowrap}
.plaza-nav .plaza-star:hover{border-color:var(--ink,#333);color:var(--ink,#333)}
.plaza-nav .plaza-star .glyph{font-size:1.05em;line-height:1;opacity:.8}
.plaza-nav .plaza-star.on .glyph{color:#f2c231;opacity:1}   /* 已收藏 = 黄色五角星 */
.plaza-nav .plaza-star.on{border-color:rgba(226,181,44,.65)}
.plaza-nav .plaza-star[hidden]{display:none}
</style>"""


def _game_names() -> Dict[str, str]:
    """id → 中文名。历史页把 ``calc`` 这种 id 显示成「计算」用。"""
    return {game.id: game.name for game in GAMES}


# 收藏星标：广场给每个游戏页面注入同一份脚本，游戏只要在"拿到一道题"时调
# `window.plazaSetPuzzle({id, level})` 告诉它现在是哪一道（单独跑时不注入，调不到也没事）。
# 单独的 `__GAME_ID__` 由广场替换成这个游戏 id。
_STAR_JS = """<script>
(function () {
  var GAME_ID = __GAME_ID__;
  var current = null;      // 现在是哪一道：{id, level}
  var starred = false;
  var busy = false;

  function button() { return document.getElementById('plaza-star'); }

  function paint() {
    var el = button();
    if (!el) return;
    if (!current) { el.hidden = true; return; }
    el.hidden = false;
    // 未收藏 = 空心五角星（不填色）；已收藏 = 黄色实心五角星（颜色写在 CSS 里）
    el.querySelector('.glyph').textContent = starred ? '★' : '☆';
    el.querySelector('.label').textContent = starred ? '已收藏' : '收藏';
    el.title = starred ? '点一下取消收藏' : '收藏这道题（以后好找）';
    el.classList.toggle('on', starred);
    el.setAttribute('aria-pressed', starred ? 'true' : 'false');
  }

  function refresh() {
    if (!current) return;
    fetch('/api/stars?game=' + encodeURIComponent(GAME_ID))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !current) return;
        starred = (data.stars || []).some(function (s) { return s.puzzle_id === current.id; });
        paint();
      })
      .catch(function () { /* 读不到就先显示 ☆，点了再说 */ });
  }

  /** 游戏页面拿到一道题就调这个：`{id, level}` */
  window.plazaSetPuzzle = function (p) {
    if (!p || !p.id) { current = null; starred = false; paint(); return; }
    current = { id: String(p.id), level: (p.level === undefined || p.level === null) ? null : Number(p.level) };
    paint();
    refresh();
  };

  function toggle() {
    if (!current || busy) return;
    busy = true;
    fetch('/api/star', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ game: GAME_ID, puzzle_id: current.id,
                             level: current.level, starred: !starred }),
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data) { starred = !!data.starred; paint(); }
        busy = false;
      })
      .catch(function () { busy = false; });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var el = button();
    if (el) {
      el.addEventListener('click', toggle);
      el.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
      });
    }
    paint();
  });
})();
</script>"""


def _nav_html(current: Game) -> str:
    parts = ['<a class="home" href="/">游戏广场</a>']
    for game in GAMES:
        parts.append('<span class="sep">·</span>')
        if game.id == current.id:
            parts.append('<span class="here">%s</span>' % game.name)
        else:
            parts.append('<a href="%s">%s</a>' % (game.url, game.name))
    parts.append('<button type="button" class="plaza-star" id="plaza-star" hidden'
                 ' title="收藏这道题（以后好找）">'
                 '<span class="glyph" aria-hidden="true">☆</span>'
                 '<span class="label">收藏</span></button>')
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
    inject += "\n" + _STAR_JS.replace("__GAME_ID__", json.dumps(game.id))
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
    def go(request: Request) -> RedirectResponse:
        # 查询串要带上：`/games/beadsort?p=<id>` 少个斜杠也得还是那一道题
        tail = "?" + request.url.query if request.url.query else ""
        return RedirectResponse(game.url + tail, status_code=307)
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
    offset: int = Query(0, ge=0, description="跳过几条（分页用）"),
) -> Dict[str, object]:
    """最近访问记录，新的在前。数据来源见 plaza/history.py。"""
    try:
        rows = history.query(limit=limit, offset=offset)
    except Exception as exc:
        raise HTTPException(500, "访问日志读不了：%s" % exc)
    return {"count": len(rows), "offset": offset, "events": rows}


@app.post("/api/history/clear")
def api_history_clear() -> Dict[str, object]:
    """把访问记录**全清掉** —— 历史页右上角那个「清空」按钮走的就是这条。

    为什么是 POST 而不是 DELETE：这是"动一下就没了"的动作，写成 POST 就不必担心
    被浏览器的预取 / 某个 GET 顺手带走。清的就是记录本身，不碰任何游戏数据；
    删多少返回多少，方便页面上报一句"已清空 N 条"。
    """
    try:
        deleted = history.clear()
    except Exception as exc:
        raise HTTPException(500, "清不掉：%s" % exc)
    return {"ok": True, "deleted": deleted}


class StarRequest(BaseModel):
    """`POST /api/star` 的入参。"""

    game: str
    puzzle_id: str
    level: Optional[int] = None
    starred: bool = True          # false = 取消收藏


@app.get("/api/stars")
def api_stars(
    game: Optional[str] = Query(None, description="只看某个游戏，例如 logic"),
    level: Optional[int] = Query(None, ge=0, description="只看某个等级"),
) -> Dict[str, object]:
    """收藏列表，新的在前（可按游戏 / 等级筛）。数据来源见 plaza/stars.py。"""
    try:
        rows = stars.list_stars(game, level)
    except Exception as exc:
        raise HTTPException(500, "收藏读不了：%s" % exc)
    return {"count": len(rows), "stars": rows}


@app.post("/api/star")
def api_star(req: StarRequest) -> Dict[str, object]:
    """收藏 / 取消收藏一道题 —— **幂等**：连着发两次结果一样。

    收藏是"状态"不是"事件"：一道题（游戏 + 题目 id）最多一条，跟访问日志分开存。
    `starred=false` 就是取消；`level` 只有第一次收藏时用得着（以后不会来回改）。
    """
    game = (req.game or "").strip()
    puzzle_id = (req.puzzle_id or "").strip()
    if game not in {g.id for g in GAMES}:
        raise HTTPException(400, "没有这个游戏：%s" % game)
    if not puzzle_id:
        raise HTTPException(400, "puzzle_id 是空的")
    try:
        state = stars.set_starred(game, puzzle_id, req.level, req.starred)
    except Exception as exc:
        raise HTTPException(500, "收藏写不进去：%s" % exc)
    return {"ok": True, **state}


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
  <p class="lead">实体串珠 + 一个小程序：家长出题，孩子在实物上动手。
     <a class="sidelink" href="/history">历史 →</a>
     <a class="sidelink" href="/stars">收藏 →</a></p>
</header>
<main>
%s
</main>
<footer>
  <p>共 %d 个游戏 · 接口清单在 <a href="/api/games">/api/games</a> ·
     每个游戏的接口文档在 <a href="/docs">/docs</a> ·
     源码在 <a href="https://github.com/diaochunmeng002-crypto/BeadMatch/commits/master"
              target="_blank" rel="noreferrer">GitHub</a></p>
</footer>
</body>
</html>
"""


# 访问清单：按天分组，每行「时间 / 游戏(中文) / 等级 / 题目 id / 出题者 / 打开」。
# 「出题者」读的是记录 detail 里的两栏（写进去的见 history.record_served）：
# **created_by**（谁出的：`manual` / `beadmatch` / `beadsort`）+ **generator**
# （用哪套算法出的：`layershuffle@1` / `sampler@1` / `walk_guided@4` …），
# 拼成「beadsort · sampler」这样。**两栏都得显示**：竞技串珠那 1900+ 道题
# created_by 全是 `beadsort`，只看它这栏是死的（低级和高级看着一模一样），
# 而库里其实混着四种出题方法。
# 算法名尾上的**版本号不显示**（`sampler@1` → `sampler`）：它是给自己排错用的，
# 摆在页面上只是噪音，要的时候鼠标停一下（title 里有完整的）。
# 老记录 / 没这两栏的游戏空着就是。
# 「打开」直接开**那一道题**：/games/<游戏>/?p=<题目 id>（题目 id 由游戏页面自己认，
# 见各游戏 web/app.js 里的 WANT_ID）。认不出这个参数 / 那道题不在题库里，
# 游戏页面会退回"随机抽一道"，所以老页面照旧能打开，只是回到从前那种行为。
# 每次加载 100 条，底部「加载更多」翻页（后端 /api/history 支持 limit/offset 的思路，
# 这里先用 limit 累计）。
_HISTORY_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>玩过什么 · BeadMatch</title>
<link rel="stylesheet" href="/static/style.css">
<style>
.bar{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:.85rem;flex-wrap:wrap}
.bar button{font:inherit;color:inherit;background:var(--card);border:1px solid var(--border);
  border-radius:999px;padding:3px 12px;cursor:pointer}
.bar button:hover:not(:disabled){border-color:var(--ink);color:var(--ink)}
.bar button:disabled{opacity:.5;cursor:default}
.day{margin:22px 0 8px;font-size:.8rem;font-weight:600;color:var(--muted);letter-spacing:.03em}
.day:first-child{margin-top:0}
.wrap{overflow:hidden;border:1px solid var(--border);border-radius:14px;background:var(--card)}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--border);white-space:nowrap}
th{font-size:.78rem;color:var(--muted);font-weight:600}
tbody tr:last-child td{border-bottom:0}
td.time{color:var(--muted);font-variant-numeric:tabular-nums}
td.game{font-weight:600}
td .muted{color:var(--muted);font-weight:400}
td.id{font-family:ui-monospace,Consolas,monospace;font-size:.85rem}
td.open a{color:inherit;text-decoration:underline;text-underline-offset:3px;
  text-decoration-color:rgba(128,128,128,.45)}
td.open a:hover{text-decoration-color:currentColor}
.none{color:var(--muted)}
</style>
</head>
<body>
<header>
  <h1>玩过什么</h1>
  <p class="lead">按天分组，新的在最上面 · <a href="/stars">收藏 →</a> · <a href="/">← 回广场</a></p>
</header>
<main>
  <div class="bar">
    <span id="status">读取中…</span>
    <button id="reload">刷新</button>
    <button id="clear">清空</button>
  </div>
  <div id="list"></div>
  <p class="none" id="empty" hidden>还没有记录。</p>
  <div class="bar" style="justify-content:center;margin-top:14px">
    <button id="more" hidden>加载更多</button>
  </div>
</main>
<script>
const GAME_NAMES = __GAME_NAMES__;          // id → 中文名（后端注入）
const PAGE = 100;                          // 每次加载几条
const listEl = document.getElementById('list');
const emptyEl = document.getElementById('empty');
const statusEl = document.getElementById('status');
const moreBtn = document.getElementById('more');

let loaded = 0;                            // 已经拉了几条

function pad(n) { return String(n).padStart(2, '0'); }

function hm(text) {                        // "2026-10-15T07:43:46+08:00" → "07:43:46"
  const d = new Date(text);
  if (isNaN(d.getTime())) return text || '';
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function dayKey(text) {                    // 本机日期 "2026-10-15"（分组用）
  const d = new Date(text);
  if (isNaN(d.getTime())) return '';
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function dayLabel(day) {                   // 今天 / 昨天 / 具体日期
  const t = new Date();
  const today = `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}`;
  const y = new Date(t.getTime() - 86400000);
  const yest = `${y.getFullYear()}-${pad(y.getMonth() + 1)}-${pad(y.getDate())}`;
  if (day === today) return '今天 · ' + day;
  if (day === yest) return '昨天 · ' + day;
  return day;
}

function row(ev) {
  const tr = document.createElement('tr');

  const time = document.createElement('td');
  time.className = 'time';
  time.textContent = hm(ev.ts);

  const game = document.createElement('td');
  game.className = 'game';
  game.textContent = GAME_NAMES[ev.game] || ev.game || '';

  const level = document.createElement('td');
  level.className = 'muted';
  level.textContent = (ev.level === null || ev.level === undefined) ? '' : ev.level + ' 级';

  const id = document.createElement('td');
  id.className = 'id';
  id.textContent = ev.puzzle_id || '';

  // 出题者：从记录 detail 里取 —— created_by（谁出的）+ generator（用哪套算法出的）。
  // 两栏都显示，中间用「·」连：「beadsort · sampler」。只显示 created_by 的话
  // 竞技串珠每一行都是同一个 `beadsort`，低级和高级看着一模一样（点不出区别）。
  // 算法名尾上的版本号不显示（`sampler@1` → `sampler`）—— 那是给自己排错看的，
  // 摆在页面上只是噪音；鼠标停在上面时，提示里给完整的。
  const by = document.createElement('td');
  by.className = 'muted';
  const author = (ev.detail && ev.detail.created_by) || '';
  const full = (ev.detail && ev.detail.generator) || '';     // 完整：sampler@1
  const method = full.split('@')[0].trim();                  // 显示用：sampler
  by.textContent = (author && method) ? author + ' · ' + method : (author || method);
  by.title = (author || full) ? '谁出的：' + (author || '—') + '\\n用哪套算法：' + (full || '—') : '';

  const open = document.createElement('td');
  open.className = 'open';
  const a = document.createElement('a');
  // 直接开**这**一道题：/games/<游戏>/?p=<题目 id>；万一条目里没有 id，就退回游戏首页
  a.href = '/games/' + encodeURIComponent(ev.game) + '/'
         + (ev.puzzle_id ? '?p=' + encodeURIComponent(ev.puzzle_id) : '');
  a.title = ev.puzzle_id ? '打开 ' + ev.puzzle_id : '打开这个游戏';
  a.textContent = '打开';
  open.appendChild(a);

  tr.append(time, game, level, id, by, open);
  return tr;
}

// 建一组「日期标题 + 表格」，返回可往里塞行的 tbody
function dayBlock(day) {
  const head = document.createElement('div');
  head.className = 'day';
  head.textContent = dayLabel(day);

  const wrap = document.createElement('div');
  wrap.className = 'wrap';
  const table = document.createElement('table');
  table.innerHTML = '<thead><tr><th>时间</th><th>游戏</th><th>等级</th>'
                  + '<th>题目</th><th>出题者</th><th></th></tr></thead><tbody></tbody>';
  wrap.appendChild(table);

  listEl.append(head, wrap);
  return table.querySelector('tbody');
}

// 把新拿到的记录按天分组渲染（同一天合并到一个标题下）
function render(events, append) {
  if (!append) listEl.replaceChildren();
  if (!events.length) return;

  let lastDay = append ? (listEl.dataset.lastDay || '') : '';
  let tbody = null;
  if (append && lastDay) {                       // 续上最后一天的那个 tbody
    const lastWrap = listEl.lastElementChild;
    tbody = lastWrap ? lastWrap.querySelector('tbody') : null;
  }

  for (const ev of events) {
    const day = dayKey(ev.ts);
    if (day !== lastDay || !tbody) {
      tbody = dayBlock(day);
      lastDay = day;
    }
    tbody.appendChild(row(ev));
  }
  listEl.dataset.lastDay = lastDay;
}

async function load(append) {
  const offset = append ? loaded : 0;
  statusEl.textContent = append ? '加载中…' : '读取中…';
  moreBtn.disabled = true;
  try {
    const r = await fetch(`/api/history?limit=${PAGE}&offset=${offset}`);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    const events = data.events || [];
    render(events, append);
    loaded = offset + events.length;
    // 还没有记录
    if (loaded === 0) { emptyEl.hidden = false; statusEl.textContent = '还没有记录'; }
    else { emptyEl.hidden = true; statusEl.textContent = `已显示 ${loaded} 条`; }
    // 一次没拿满 PAGE 条 → 到底了
    moreBtn.hidden = events.length < PAGE;
  } catch (e) {
    statusEl.textContent = '读取失败：' + e.message;
  } finally {
    moreBtn.disabled = false;
  }
}

// 清空全部记录：先问一句（删了不给撤回），成了就把列表和分页一起归零
async function clearAll() {
  if (!confirm('把「玩过什么」里的记录全清掉？删了就没了，不能撤回。')) return;
  statusEl.textContent = '清空中…';
  try {
    const r = await fetch('/api/history/clear', { method: 'POST' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    listEl.replaceChildren();
    listEl.dataset.lastDay = '';
    loaded = 0;
    emptyEl.hidden = false;
    moreBtn.hidden = true;
    statusEl.textContent = `已清空 ${data.deleted} 条`;
  } catch (e) {
    statusEl.textContent = '清空失败：' + e.message;
  }
}

document.getElementById('reload').addEventListener('click', () => load(false));
moreBtn.addEventListener('click', () => load(true));
document.getElementById('clear').addEventListener('click', clearAll);
load(false);
</script>
</body>
</html>
"""


# 收藏清单：布局照历史页（标题 + 状态栏 + 一张表），但**不按天分组**（收藏一般没几条），
# 每行末尾的「打开」跟历史页一样是深链接 `/games/<游戏>/?p=<题目 id>`；
# 最左边那颗黄星点一下就取消收藏。
_STARS_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>收藏 · BeadMatch</title>
<link rel="stylesheet" href="/static/style.css">
<style>
.bar{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:.85rem;flex-wrap:wrap}
.bar button{font:inherit;color:inherit;background:var(--card);border:1px solid var(--border);
  border-radius:999px;padding:3px 12px;cursor:pointer}
.bar button:hover:not(:disabled){border-color:var(--ink);color:var(--ink)}
.wrap{overflow:hidden;border:1px solid var(--border);border-radius:14px;background:var(--card)}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--border);white-space:nowrap}
th{font-size:.78rem;color:var(--muted);font-weight:600}
tbody tr:last-child td{border-bottom:0}
td.time{color:var(--muted);font-variant-numeric:tabular-nums}
td.game{font-weight:600}
td .muted{color:var(--muted);font-weight:400}
td.id{font-family:ui-monospace,Consolas,monospace;font-size:.85rem}
td.open a{color:inherit;text-decoration:underline;text-underline-offset:3px;
  text-decoration-color:rgba(128,128,128,.45)}
td.open a:hover{text-decoration-color:currentColor}
td.star button{font:inherit;font-size:1.15rem;line-height:1;background:none;border:0;
  color:#f2c231;cursor:pointer;padding:0 2px}
td.star button:hover{filter:brightness(1.15)}
.none{color:var(--muted);line-height:1.9}
</style>
</head>
<body>
<header>
  <h1>我收藏的题</h1>
  <p class="lead">觉得好的题都在这儿 · <a href="/history">历史 →</a> · <a href="/">← 回广场</a></p>
</header>
<main>
  <div class="bar">
    <span id="status">读取中…</span>
    <button id="reload">刷新</button>
  </div>
  <div id="list"></div>
  <p class="none" id="empty" hidden>还没有收藏 —— 玩到喜欢的题，点页面右上角的 ☆ 收藏。</p>
</main>
<script>
const GAME_NAMES = __GAME_NAMES__;          // id → 中文名（后端注入）
const listEl = document.getElementById('list');
const emptyEl = document.getElementById('empty');
const statusEl = document.getElementById('status');

function pad(n) { return String(n).padStart(2, '0'); }

// "2026-10-21T08:12:30+08:00" → "2026-10-21 08:12"
function when(text) {
  const d = new Date(text);
  if (isNaN(d.getTime())) return text || '';
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
       + `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function tableBody() {
  const wrap = document.createElement('div');
  wrap.className = 'wrap';
  const table = document.createElement('table');
  table.innerHTML = '<thead><tr><th>收藏</th><th>游戏</th><th>等级</th>'
                  + '<th>题目</th><th>收藏时间</th><th></th></tr></thead><tbody></tbody>';
  wrap.appendChild(table);
  listEl.appendChild(wrap);
  return table.querySelector('tbody');
}

function row(s) {
  const tr = document.createElement('tr');

  const star = document.createElement('td');
  star.className = 'star';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = '★';
  btn.title = '取消收藏';
  btn.setAttribute('aria-label', '取消收藏 ' + s.puzzle_id);
  btn.addEventListener('click', () => unstar(s));
  star.appendChild(btn);

  const game = document.createElement('td');
  game.className = 'game';
  game.textContent = GAME_NAMES[s.game] || s.game || '';

  const level = document.createElement('td');
  level.className = 'muted';
  level.textContent = (s.level === null || s.level === undefined) ? '' : s.level + ' 级';

  const id = document.createElement('td');
  id.className = 'id';
  id.textContent = s.puzzle_id || '';

  const time = document.createElement('td');
  time.className = 'time';
  time.textContent = when(s.created_at);

  const open = document.createElement('td');
  open.className = 'open';
  const a = document.createElement('a');
  // 跟历史页一样是深链接：直接开这道题
  a.href = '/games/' + encodeURIComponent(s.game) + '/'
         + (s.puzzle_id ? '?p=' + encodeURIComponent(s.puzzle_id) : '');
  a.title = s.puzzle_id ? '打开 ' + s.puzzle_id : '打开这个游戏';
  a.textContent = '打开';
  open.appendChild(a);

  tr.append(star, game, level, id, time, open);
  return tr;
}

async function unstar(s) {
  statusEl.textContent = '取消收藏…';
  try {
    const r = await fetch('/api/star', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ game: s.game, puzzle_id: s.puzzle_id, starred: false }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    await load();
  } catch (e) {
    statusEl.textContent = '取消收藏失败：' + e.message;
  }
}

async function load() {
  statusEl.textContent = '读取中…';
  try {
    const r = await fetch('/api/stars');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    const rows = data.stars || [];
    listEl.replaceChildren();
    if (!rows.length) {
      emptyEl.hidden = false;
      statusEl.textContent = '还没有收藏';
      return;
    }
    emptyEl.hidden = true;
    statusEl.textContent = `共收藏 ${rows.length} 道`;
    const tbody = tableBody();
    rows.forEach((s) => tbody.appendChild(row(s)));
  } catch (e) {
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
    """玩过什么 —— 首页右侧导航「历史」进来的。"""
    return _HISTORY_PAGE.replace(
        "__GAME_NAMES__", json.dumps(_game_names(), ensure_ascii=False))


@app.get("/stars", response_class=HTMLResponse)
def stars_page() -> str:
    """我收藏的题 —— 首页副标题的「收藏 →」进来的。"""
    return _STARS_PAGE.replace(
        "__GAME_NAMES__", json.dumps(_game_names(), ensure_ascii=False))


# 静态目录先建出来再挂载 —— 免得"启动时 web/ 还不存在 → 没挂上"这种坑
WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="plaza-static")

# 前端（游戏页面 + 各家 web/ 里的三件套）每次都回来问一句，别被浏览器的"启发式缓存"存住 ——
# 不然改了 app.js、刷新还是旧页面（详见 plaza/nocache.py）
keep_fresh(app, ("/static/", "/games/"))


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
