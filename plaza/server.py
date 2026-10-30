"""广场外壳：一个程序装所有游戏（见 ../docs/plaza.md §4）。

    python run.py                 # 默认 127.0.0.1:8000（推荐，唯一入口）
    python -m plaza.server        # 一样，调试时方便

页面（广场占根路径，每个游戏在自己的前缀下，谁也不挡谁）：

    /                             广场首页：列出所有游戏
    /difficulties                 难度管理：逐游戏选择游戏页里显示哪些等级
    /games/<id>/                  某个游戏的页面（广场顺手往页面里注入接口基址）
    /games/<id>/static/...        那个游戏的静态资源
    /static/...                   广场公共的前端（首页样式等）

接口：

    GET  /api/games                        有哪些游戏
    GET  /api/difficulty-settings          每个游戏的难度和显示开关
    PUT  /api/difficulty-settings          保存哪些难度不在菜单里显示
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
import tomllib
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import difficulty_settings, history, registry, stars
from .nocache import keep_fresh
from .registry import Game

WEB_DIR = Path(__file__).resolve().parent / "web"
EXTRA_DIR = Path(__file__).resolve().parent.parent / "extras"

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
  color:var(--muted,#8a857f);display:flex;align-items:center;gap:5px;flex-wrap:nowrap}
.plaza-nav a{color:inherit;text-decoration:underline;text-underline-offset:3px;
  text-decoration-thickness:1px;text-decoration-color:rgba(128,128,128,.45);
  white-space:nowrap}
.plaza-nav a:hover{color:var(--ink,#333);text-decoration-color:currentColor}
.plaza-nav .sep{opacity:.35}
.plaza-nav .here{color:var(--ink,#333);font-weight:600;white-space:nowrap}
.plaza-nav .plaza-tools{margin-left:auto;display:inline-flex;align-items:center;gap:8px;
  flex-shrink:0}
.plaza-nav .plaza-star{font:inherit;font-size:.8rem;color:inherit;
  background:none;border:1px solid rgba(128,128,128,.35);border-radius:999px;
  padding:1px 10px;cursor:pointer;white-space:nowrap;line-height:1.4;
  display:inline-flex;flex-direction:row;align-items:center;justify-content:center;
  gap:4px;flex:0 0 auto}
.plaza-nav .plaza-star:hover{border-color:var(--ink,#333);color:var(--ink,#333)}
.plaza-nav .plaza-star .glyph{font-size:1.05em;line-height:1;opacity:.8;flex:0 0 auto}
.plaza-nav .plaza-star .star-label{font:inherit;line-height:1;letter-spacing:normal;
  margin:0;padding:0;color:inherit;flex:0 0 auto}
.plaza-nav .plaza-star.on .glyph{color:#f2c231;opacity:1}   /* 已收藏 = 黄色五角星 */
.plaza-nav .plaza-star.on{border-color:rgba(226,181,44,.65)}
.plaza-nav .plaza-star[hidden]{display:none}
</style>"""


# 其他菜单：入口跟游戏链接排在左边，「收藏」仍在最右边。当前正在看的
# 其他玩法保留在下拉里并加粗，菜单本身仍跟普通游戏页共用同一套结构。
_EXTRA_LINKS = (
    ("kendama", "剑玉", "/extras/kendama"),
    ("slingshot", "弹弓", "/extras/slingshot"),
    ("pitchpot", "投壶", "/extras/pitchpot"),
    ("pickleball", "匹克球", "/extras/pickleball"),
)


def _extras_menu_html(current_id: Optional[str] = None) -> str:
    links: List[str] = []
    for extra_id, label, url in _EXTRA_LINKS:
        if extra_id == current_id:
            links.append('<span class="here" aria-current="page">%s</span>' % label)
        else:
            links.append('<a href="%s">%s</a>' % (url, label))
    return ('<div class="plaza-extra">'
            '<button type="button" class="plaza-extra-toggle" aria-expanded="false"'
            ' aria-haspopup="true">其他<span class="caret" aria-hidden="true">⌄</span></button>'
            '<div class="plaza-extra-menu" role="group" aria-label="其他玩法" hidden>'
            + "".join(links) + "</div></div>")


_EXTRAS_CSS = """<style>
.plaza-extra{position:relative}
.plaza-extra-toggle{font:inherit;color:inherit;background:none;border:0;padding:0 2px;
  display:inline-flex;align-items:center;gap:3px;cursor:pointer;white-space:nowrap}
.plaza-extra-toggle:hover,.plaza-extra.open .plaza-extra-toggle{color:var(--ink,#333)}
.plaza-extra .caret{font-size:.85em;opacity:.65;transition:transform .12s ease}
.plaza-extra.open .caret{transform:rotate(180deg)}
.plaza-extra-menu{position:absolute;z-index:30;top:calc(100% + 7px);right:0;min-width:8.5rem;
  padding:5px;color:var(--ink,#333);
  background:var(--panel,var(--card,var(--bg,#fff)));
  border:1px solid var(--border,#d9d5d0);border-radius:10px;
  box-shadow:0 8px 24px rgba(0,0,0,.22)}
.plaza-extra-menu[hidden]{display:none}
.plaza-extra-menu a{display:block;padding:6px 9px;border-radius:6px;color:var(--ink,#333);
  opacity:1;text-decoration:none;white-space:nowrap}
.plaza-extra-menu a[hidden]{display:none}
.plaza-extra-menu .here{display:block;padding:6px 9px;white-space:nowrap}
.plaza-extra-menu a:hover{background:rgba(128,128,128,.12)}
.plaza-nav .plaza-extra-menu{left:0;right:auto}
</style>"""


_EXTRAS_JS = """<script>
(function () {
  function setOpen(root, open) {
    var toggle = root.querySelector('.plaza-extra-toggle');
    var menu = root.querySelector('.plaza-extra-menu');
    if (!toggle || !menu) return;
    root.classList.toggle('open', open);
    menu.hidden = !open;
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function closeAll() {
    var roots = Array.prototype.slice.call(document.querySelectorAll('.plaza-extra'));
    roots.forEach(function (root) { setOpen(root, false); });
  }

  function init() {
    var roots = Array.prototype.slice.call(document.querySelectorAll('.plaza-extra'));

    roots.forEach(function (root) {
      var toggle = root.querySelector('.plaza-extra-toggle');
      var menu = root.querySelector('.plaza-extra-menu');
      if (!toggle || !menu) return;

      toggle.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        var open = !root.classList.contains('open');
        closeAll();
        setOpen(root, open);
      });

      menu.addEventListener('click', function (event) {
        var link = event.target.closest('a');
        if (!link) return;
        if ((link.getAttribute('href') || '') === '#') event.preventDefault();
        setOpen(root, false);
      });
    });

  }

  document.addEventListener('click', closeAll);
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closeAll();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
</script>"""


# 游戏自己的 /levels 响应在浏览器里过滤一次。这样不用改九套游戏前端，
# 游戏仍从自己的接口动态读难度，广场只负责去掉管理页里关掉的项。
_LEVEL_FILTER_JS = """<script>
(function () {
  var hidden = Array.isArray(window.PLAZA_HIDDEN_LEVELS)
    ? window.PLAZA_HIDDEN_LEVELS.map(Number)
    : [];
  var requested = NaN;
  try {
    requested = Number(new URLSearchParams(window.location.search).get('level'));
  } catch (error) { /* 参数读不到就按普通游戏页处理 */ }
  var hasRequested = Number.isFinite(requested) && requested > 0;
  if (!hidden.length && !hasRequested) return;

  var nativeFetch = window.fetch;
  if (typeof nativeFetch !== 'function') return;

  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : ((input && input.url) || '');
    var pending = nativeFetch.apply(this, arguments);
    if (!/\\/levels(?:\\?.*)?$/.test(url)) return pending;

    return pending.then(function (response) {
      if (!response || !response.ok) return response;
      if (typeof Response !== 'function' || typeof Headers !== 'function') return response;
      return response.clone().json().then(function (data) {
        if (!data || !Array.isArray(data.levels)) return response;
        var visible = data.levels.filter(function (row) {
          var level = Number(row && row.level);
          return hidden.indexOf(level) < 0 || level === requested;
        });
        // 题库变动或手工改配置后也不让游戏页变成空菜单。
        if (!visible.length) return response;
        // 各游戏默认都取下拉框第一项；把链接指定的等级放第一项即可统一直达。
        var target = visible.findIndex(function (row) {
          return Number(row && row.level) === requested;
        });
        if (target >= 0) visible.unshift(visible.splice(target, 1)[0]);
        data.levels = visible;
        var headers = new Headers(response.headers);
        headers.set('Content-Type', 'application/json');
        headers.delete('Content-Length');
        return new Response(JSON.stringify(data), {
          status: response.status,
          statusText: response.statusText,
          headers: headers,
        });
      }).catch(function () {
        return response;
      });
    });
  };
})();
</script>"""


def _game_names() -> Dict[str, str]:
    """id → 中文名。历史 / 收藏页也认识“其他玩法”的名字。"""
    names = {game.id: game.name for game in GAMES}
    names.update({extra_id: label for extra_id, label, _ in _EXTRA_LINKS})
    return names


def _extra_routes() -> Dict[str, str]:
    """已挂好页面的其他玩法：id → URL。空占位链接不会被当成可打开项。"""
    return {extra_id: url for extra_id, _, url in _EXTRA_LINKS if url != "#"}


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
    el.querySelector('.star-label').textContent = starred ? '已收藏' : '收藏';
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


def _nav_html(current: Optional[Game], extra_current: Optional[str] = None) -> str:
    parts = ['<a class="home" href="/">游戏广场</a>']
    for game in GAMES:
        parts.append('<span class="sep">·</span>')
        if current is not None and game.id == current.id:
            parts.append('<span class="here">%s</span>' % game.name)
        else:
            parts.append('<a href="%s">%s</a>' % (game.url, game.name))
    parts.append('<span class="sep">·</span>')
    parts.append(_extras_menu_html(extra_current))
    parts.append('<span class="plaza-tools">')
    parts.append('<button type="button" class="plaza-star" id="plaza-star" hidden'
                 ' title="收藏这道题（以后好找）">'
                 '<span class="glyph" aria-hidden="true">☆</span>'
                 '<span class="star-label">收藏</span></button>')
    parts.append('</span>')
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
    hidden_levels = difficulty_settings.load_hidden().get(game.id, [])
    inject += "\n<script>window.PLAZA_HIDDEN_LEVELS=%s;</script>" % json.dumps(hidden_levels)
    inject += "\n" + _LEVEL_FILTER_JS
    inject += "\n" + _NAV_CSS + "\n" + _EXTRAS_CSS
    inject += "\n" + _STAR_JS.replace("__GAME_ID__", json.dumps(game.id))
    inject += "\n" + _EXTRAS_JS
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


def _difficulty_rows() -> List[Dict[str, object]]:
    """当前所有游戏及难度；开关状态从本地配置合并出来。"""
    hidden = difficulty_settings.load_hidden()
    rows: List[Dict[str, object]] = []
    for game in GAMES:
        info = registry.levels_of(game)
        hidden_levels = set(hidden.get(game.id, []))
        levels: List[Dict[str, object]] = []
        for row in info["levels"]:
            if not isinstance(row, dict):
                continue
            try:
                number = int(row["level"])
            except (KeyError, TypeError, ValueError):
                continue
            name = str(row.get("name") or "").strip()
            levels.append({
                "level": number,
                "count": int(row.get("count", 0) or 0),
                "name": name,
                "enabled": number not in hidden_levels,
                "url": "%s?level=%d" % (game.url, number),
            })
        if levels and not any(row["enabled"] for row in levels):
            for row in levels:
                row["enabled"] = True
        item: Dict[str, object] = {
            "id": game.id,
            "name": game.name,
            "url": game.url,
            "levels": levels,
        }
        if game.error:
            item["error"] = game.error
        if info.get("error"):
            item["levels_error"] = info["error"]
        rows.append(item)
    return rows


def _difficulty_payload() -> Dict[str, object]:
    rows = _difficulty_rows()
    return {"count": len(rows), "games": rows}


class DifficultySettingsRequest(BaseModel):
    """`PUT /api/difficulty-settings` 的入参；只传需要隐藏的等级。"""

    hidden: Dict[str, List[int]]


@app.get("/api/difficulty-settings")
def api_difficulty_settings() -> Dict[str, object]:
    """管理页的数据：每个游戏的难度、题量和当前开关状态。"""
    return _difficulty_payload()


@app.put("/api/difficulty-settings")
def api_difficulty_settings_save(req: DifficultySettingsRequest) -> Dict[str, object]:
    """保存隐藏等级。每个游戏至少留一个可见难度，免得游戏页没有入口。"""
    games = _difficulty_rows()
    by_id = {str(game["id"]): game for game in games}
    normalized: Dict[str, List[int]] = {}

    for game_id, values in req.hidden.items():
        game = by_id.get(game_id)
        if game is None:
            raise HTTPException(400, "没有这个游戏：%s" % game_id)
        valid = {int(row["level"]) for row in game["levels"]}
        requested = set(values)
        invalid = sorted(requested - valid)
        if invalid:
            raise HTTPException(
                400,
                "%s 没有这些难度：%s" % (game_id, "、".join(map(str, invalid))),
            )
        if valid and requested >= valid:
            raise HTTPException(400, "%s 至少要保留一个难度" % game_id)
        if requested:
            normalized[game_id] = sorted(requested)

    difficulty_settings.save_hidden(normalized)
    return _difficulty_payload()


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


class ExtraViewRequest(BaseModel):
    """`POST /api/extras/{id}/view` 的入参。"""

    level: int


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
    if game not in {g.id for g in GAMES} and game not in set(_extra_routes()):
        raise HTTPException(400, "没有这个游戏：%s" % game)
    if not puzzle_id:
        raise HTTPException(400, "puzzle_id 是空的")
    try:
        state = stars.set_starred(game, puzzle_id, req.level, req.starred)
    except Exception as exc:
        raise HTTPException(500, "收藏写不进去：%s" % exc)
    return {"ok": True, **state}


@app.post("/api/extras/{extra_id}/view")
def api_extra_view(extra_id: str, req: ExtraViewRequest) -> Dict[str, object]:
    """记录当前展示的其他玩法级别；历史页靠它认出物理玩法。"""
    data = _load_extra(extra_id)
    levels = data["levels"]
    assert isinstance(levels, list)
    if req.level < 1 or req.level > len(levels):
        raise HTTPException(400, "没有这个难度：%s" % req.level)
    level = levels[req.level - 1]
    if not isinstance(level, dict):
        raise HTTPException(500, "这个难度读不了")
    level_name = str(level.get("name") or "").strip()
    if not level_name:
        raise HTTPException(500, "这个难度没有名称")
    history.record_served(
        game=extra_id,
        payload={"id": level_name, "level": req.level, "created_by": "其他玩法"},
        source="extra",
    )
    return {"ok": True, "game": extra_id, "puzzle_id": level_name, "level": req.level}


# --------------------------------------------------------------------------
# 首页
# --------------------------------------------------------------------------

_EXTRA_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ · 其他玩法 · BeadMatch</title>
<link rel="stylesheet" href="/static/style.css">
__NAV_CSS__
__STAR_JS__
<style>
.extra-top{width:100%;max-width:46rem;display:flex;align-items:center;justify-content:space-between;
  gap:16px;flex-wrap:wrap}
.extra-top h1{margin:0}
.extra-controls{display:flex;align-items:center;gap:8px;font-size:.9rem}
.extra-controls select{font:inherit;padding:6px 30px 6px 12px;border:1px solid var(--border);
  border-radius:10px;background:var(--card);color:var(--ink);cursor:pointer}
.extra-main{width:100%;max-width:46rem;display:block;margin-top:12px}
.extra-summary{margin:0 0 14px;color:var(--muted);font-size:.88rem;line-height:1.7}
.safety{display:flex;gap:12px;padding:12px 15px;border:1px solid var(--border);
  border-radius:11px;color:var(--muted);font-size:.84rem;line-height:1.7}
.safety strong{flex:0 0 auto;color:var(--ink)}
.level-panels{margin-top:16px}
.level-card{margin:0;padding:20px;background:var(--card);border:1px solid var(--border);
  border-radius:14px}
.level-card[hidden]{display:none}
.level-kicker{margin:0 0 5px;color:var(--muted);font-size:.78rem;letter-spacing:.05em}
.level-card h2{margin:0;font-size:1.25rem}
.goal{margin:7px 0 20px;color:var(--muted);line-height:1.7}
.level-card h3{margin:18px 0 8px;color:var(--muted);font-size:.78rem;letter-spacing:.06em}
.steps{margin:0;padding-left:1.5rem;line-height:1.9}
.steps.plain-steps{list-style:none;padding-left:0}
.pass{margin-top:18px;padding:11px 13px;border-radius:9px;background:rgba(128,128,128,.09);
  line-height:1.65}
.pass span{display:block;color:var(--muted);font-size:.75rem;margin-bottom:2px}
.tip{margin:14px 0 0;color:var(--muted);line-height:1.7;font-size:.86rem}
.tip strong{color:var(--ink)}
</style>
</head>
<body>
__NAV__
<header class="extra-top">
  <h1>__NAME__</h1>
  <div class="extra-controls">
    <label for="level">难度</label>
    <select id="level" aria-label="难度">__OPTIONS__</select>
  </div>
</header>
<main class="extra-main">
  <p class="extra-summary">__SUMMARY__</p>
  <section class="safety"><strong>开始前</strong><span>__SAFETY__</span></section>
  <section class="level-panels" aria-live="polite">__PANELS__</section>
</main>
<script>
(function () {
  var select = document.getElementById('level');
  var panels = Array.prototype.slice.call(document.querySelectorAll('.level-card'));
  var viewUrl = __VIEW_URL__;
  var recordedLevel = null;

  function recordView(panel) {
    var level = Number(panel.dataset.levelNumber);
    if (level === recordedLevel) return;
    recordedLevel = level;
    fetch(viewUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level: level }),
    }).catch(function () {
      recordedLevel = null;
    });
  }

  function show(index, updateUrl) {
    if (!panels[index]) return;
    select.value = String(index);
    panels.forEach(function (panel, i) {
      panel.hidden = i !== index;
    });
    var panel = panels[index];
    if (typeof window.plazaSetPuzzle === 'function') {
      window.plazaSetPuzzle({
        id: panel.dataset.puzzleId,
        level: Number(panel.dataset.levelNumber),
      });
    }
    recordView(panel);
    if (updateUrl && window.history && window.history.replaceState) {
      var url = new URL(window.location.href);
      url.searchParams.set('level', String(index + 1));
      window.history.replaceState(null, '', url);
    }
  }

  select.addEventListener('change', function () { show(Number(select.value), true); });
  var wanted = Number(new URLSearchParams(window.location.search).get('level') || 1) - 1;
  show(wanted >= 0 && wanted < panels.length ? wanted : 0, false);
})();
</script>
__EXTRAS_JS__
</body>
</html>
"""


def _load_extra(extra_id: str) -> Dict[str, object]:
    """读 `extras/<id>.toml`。其他玩法共用一个最小内容格式，不进入游戏注册表。"""
    if not re.fullmatch(r"[a-z0-9-]+", extra_id):
        raise HTTPException(404, "没有这个其他玩法")
    path = EXTRA_DIR / ("%s.toml" % extra_id)
    if not path.is_file():
        raise HTTPException(404, "没有这个其他玩法")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise HTTPException(500, "其他玩法读不了：%s" % exc)
    if data.get("id") != extra_id:
        raise HTTPException(500, "%s 的 id 跟文件名对不上" % path)
    levels = data.get("levels")
    if not isinstance(levels, list) or not levels:
        raise HTTPException(500, "%s 没有难度" % path)
    return data


def _extra_page(extra_id: str) -> str:
    data = _load_extra(extra_id)
    name = escape(str(data["name"]))
    summary = escape(str(data["summary"]))
    safety = escape(str(data["safety"]))
    levels = data["levels"]
    assert isinstance(levels, list)

    options: List[str] = []
    panels: List[str] = []
    for index, level in enumerate(levels):
        if not isinstance(level, dict):
            continue
        level_name = escape(str(level["name"]))
        short = escape(str(level["short"]))
        steps_title = escape(str(level.get("steps_title", "怎么玩"))).strip()
        goal_html = escape(str(level["goal"]))
        goal_details = level.get("goal_details")
        if isinstance(goal_details, list):
            goal_html += "".join("<br>%s" % escape(str(line))
                                 for line in goal_details if str(line).strip())
        selected = " selected" if index == 0 else ""
        options.append(
            '<option value="%d"%s>%d 级（%s）</option>'
            % (index, selected, index + 1, short)
        )
        steps_plain = bool(level.get("steps_plain"))
        steps_tag = "ul" if steps_plain else "ol"
        steps_class = "steps plain-steps" if steps_plain else "steps"
        steps_items = "".join("<li>%s</li>" % escape(str(step)) for step in level["steps"])
        steps_html = '<%s class="%s">%s</%s>' % (
            steps_tag, steps_class, steps_items, steps_tag,
        )
        hidden = "" if index == 0 else " hidden"
        panels.append(
            '<article class="level-card" data-level="%d" data-level-number="%d"'
            ' data-puzzle-id="%s"%s>'
            '<p class="level-kicker">第 %d 级 · %s</p>'
            '<h2>%s</h2><p class="goal">%s</p>%s%s'
            '<div class="pass"><span>过关</span>%s</div>'
            '<p class="tip"><strong>提示：</strong>%s</p>'
            "</article>"
            % (index, index + 1, level_name, hidden, index + 1, short,
               level_name, goal_html,
               ("<h3>%s</h3>" % steps_title) if steps_title else "",
               steps_html, escape(str(level["pass_condition"])), escape(str(level["tip"])))
        )
    if not options:
        raise HTTPException(500, "%s 没有可显示的难度" % extra_id)

    return (_EXTRA_PAGE.replace("__NAV_CSS__", _NAV_CSS + "\n" + _EXTRAS_CSS)
                      .replace("__STAR_JS__",
                               _STAR_JS.replace("__GAME_ID__", json.dumps(extra_id)))
                      .replace("__VIEW_URL__",
                               json.dumps("/api/extras/%s/view" % extra_id))
                      .replace("__NAV__", _nav_html(None, extra_current=extra_id))
                      .replace("__EXTRAS_JS__", _EXTRAS_JS)
                      .replace("__NAME__", name)
                      .replace("__SUMMARY__", summary)
                      .replace("__SAFETY__", safety)
                      .replace("__OPTIONS__", "".join(options))
                      .replace("__PANELS__", "".join(panels)))


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
  <div class="home-head">
    <h1>游戏广场</h1>
    <nav class="home-tools" aria-label="广场工具">
      <a class="home-action" href="/difficulties">难度管理</a>
      <a class="home-action" href="/history">历史</a>
      <a class="home-action" href="/stars"><span aria-hidden="true">☆</span> 收藏</a>
    </nav>
  </div>
  <p class="lead">实体串珠 + 一个小程序：家长出题，孩子在实物上动手。</p>
</header>
<main>
%s
__EXTRA_HOME_CARDS__
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


# 难度管理：开关只改本地配置；游戏页下次打开时按配置加载自己的 /levels。
_DIFFICULTIES_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>难度管理 · BeadMatch</title>
<link rel="stylesheet" href="/static/style.css">
<style>
.bar{color:var(--muted);font-size:.85rem;min-height:1.6em}
.game-card{padding:16px 18px;background:var(--card);border:1px solid var(--border);
  border-radius:14px}
.game-head{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}
.game-head h2{margin:0;font-size:1.08rem}
.game-head h2 a{color:inherit;text-decoration:none}
.game-head h2 a:hover{text-decoration:underline}
.game-head .count,.game-error{color:var(--muted);font-size:.8rem}
.game-error{line-height:1.7}
.level-list{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.level-item{display:flex;align-items:center;gap:8px;min-width:0;padding:9px 10px;
  border:1px solid var(--border);border-radius:10px}
.level-item:hover{border-color:var(--muted)}
.level-copy{display:flex;flex-direction:column;gap:2px;min-width:0}
.level-name{display:block;font-size:.92rem;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;color:inherit;text-decoration:none}
.level-name:hover{text-decoration:underline}
.level-count{color:var(--muted);font-size:.76rem}
.level-item input{position:absolute;opacity:0;pointer-events:none}
.switch-label{display:flex;margin-left:auto;cursor:pointer}
.switch-track{position:relative;width:42px;height:24px;flex:0 0 auto;
  border-radius:999px;background:var(--border);transition:background .14s ease}
.switch-track::after{content:"";position:absolute;top:3px;left:3px;width:18px;height:18px;
  border-radius:50%;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.28);
  transition:transform .14s ease}
.level-item input:checked + .switch-track{background:#43a047}
.level-item input:checked + .switch-track::after{transform:translateX(18px)}
.level-item input:focus-visible + .switch-track{outline:2px solid var(--ink);
  outline-offset:2px}
.level-item input:disabled + .switch-track{opacity:.45}
@media (max-width:560px){
  .level-list{grid-template-columns:repeat(2,minmax(0,1fr))}
}
</style>
</head>
<body>
<header>
  <div class="home-head">
    <h1>难度管理</h1>
    <nav class="home-tools" aria-label="难度管理导航">
      <a class="home-action" href="/history">历史</a>
      <a class="home-action" href="/stars"><span aria-hidden="true">☆</span> 收藏</a>
      <a class="home-action" href="/">← 游戏广场</a>
    </nav>
  </div>
  <p class="lead">关掉的难度不会出现在游戏菜单里。每个游戏至少保留一个。</p>
</header>
<main>
  <div class="bar">
    <span id="status">读取中…</span>
  </div>
  <div id="list"></div>
</main>
<script>
const listEl = document.getElementById('list');
const statusEl = document.getElementById('status');
let games = [];
let saveQueue = Promise.resolve();
let pendingSaves = 0;

function setStatus(text) { statusEl.textContent = text; }

function levelRow(level, game) {
  const item = document.createElement('div');
  item.className = 'level-item';

  const copy = document.createElement('span');
  copy.className = 'level-copy';
  const name = document.createElement('a');
  name.className = 'level-name';
  name.href = level.url || ('/games/' + encodeURIComponent(game.id)
    + '/?level=' + encodeURIComponent(level.level));
  name.textContent = level.level + ' 级' + (level.name ? ' · ' + level.name : '');
  const count = document.createElement('span');
  count.className = 'level-count';
  count.textContent = level.count + ' 道';
  copy.append(name, count);

  const toggle = document.createElement('input');
  toggle.type = 'checkbox';
  toggle.checked = !!level.enabled;
  toggle.disabled = level.single;
  toggle.setAttribute('aria-label', (level.enabled ? '隐藏 ' : '显示 ') + level.level + ' 级');
  toggle.addEventListener('change', () => {
    const wouldRemain = games
      .find((game) => game.levels.includes(level)).levels
      .filter((row) => row === level ? toggle.checked : row.enabled).length;
    if (!wouldRemain) {
      toggle.checked = true;
      setStatus('每个游戏至少要保留一个难度');
      return;
    }
    level.enabled = toggle.checked;
    toggle.setAttribute('aria-label',
      (level.enabled ? '隐藏 ' : '显示 ') + level.level + ' 级');
    queueSave();
  });

  const switchLabel = document.createElement('label');
  switchLabel.className = 'switch-label';
  if (level.single) switchLabel.title = '每个游戏至少要保留一个难度';

  const track = document.createElement('span');
  track.className = 'switch-track';
  track.setAttribute('aria-hidden', 'true');
  switchLabel.append(toggle, track);
  item.append(copy, switchLabel);
  return item;
}

function gameCard(game) {
  const card = document.createElement('section');
  card.className = 'game-card';
  const head = document.createElement('div');
  head.className = 'game-head';
  const title = document.createElement('h2');
  const titleLink = document.createElement('a');
  titleLink.href = game.url;
  titleLink.textContent = game.name;
  title.appendChild(titleLink);
  const count = document.createElement('span');
  count.className = 'count';
  count.textContent = game.levels.length + ' 个难度';
  head.append(title, count);
  card.appendChild(head);

  if (game.error || game.levels_error) {
    const error = document.createElement('p');
    error.className = 'game-error';
    error.textContent = game.error || game.levels_error;
    card.appendChild(error);
    return card;
  }

  if (!game.levels.length) {
    const empty = document.createElement('p');
    empty.className = 'game-error';
    empty.textContent = '还没有可管理的难度。';
    card.appendChild(empty);
    return card;
  }

  const list = document.createElement('div');
  list.className = 'level-list';
  game.levels.forEach((level) => {
    level.single = game.levels.length === 1;
    list.appendChild(levelRow(level, game));
  });
  card.appendChild(list);
  return card;
}

function render() {
  listEl.replaceChildren(...games.map(gameCard));
}

async function load() {
  setStatus('读取中…');
  try {
    const response = await fetch('/api/difficulty-settings', { cache: 'no-store' });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const data = await response.json();
    games = data.games || [];
    render();
    setStatus('共 ' + games.length + ' 个游戏');
  } catch (error) {
    setStatus('读取失败：' + error.message);
  }
}

function hiddenSnapshot() {
  const hidden = {};
  games.forEach((game) => {
    const levels = game.levels.filter((level) => !level.enabled).map((level) => level.level);
    if (levels.length) hidden[game.id] = levels;
  });
  return hidden;
}

function queueSave() {
  const hidden = hiddenSnapshot();
  pendingSaves += 1;
  setStatus('保存中…');
  // 顺序保存：快速连点多个开关时，后一个完整快照一定最后落盘。
  saveQueue = saveQueue.then(async () => {
    const response = await fetch('/api/difficulty-settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hidden }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || ('HTTP ' + response.status));
  }).then(() => {
    pendingSaves -= 1;
    if (!pendingSaves) setStatus('已保存，下次打开游戏按这个配置加载');
  }).catch((error) => {
    pendingSaves -= 1;
    setStatus('保存失败：' + error.message);
  });
}

load();
</script>
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
  <div class="home-head">
    <h1>玩过什么</h1>
    <nav class="home-tools" aria-label="历史页导航">
      <a class="home-action" href="/difficulties">难度管理</a>
      <a class="home-action" href="/stars"><span aria-hidden="true">☆</span> 收藏</a>
      <a class="home-action" href="/">← 游戏广场</a>
    </nav>
  </div>
  <p class="lead">按天分组，新的在最上面。</p>
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
const EXTRA_LINKS = __EXTRA_LINKS__;        // 其他玩法 id → 页面路径
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
  const extraUrl = EXTRA_LINKS[ev.game];
  if (extraUrl) {
    a.href = extraUrl + '?level=' + encodeURIComponent(ev.level || 1);
    a.title = '打开' + (GAME_NAMES[ev.game] || '') + '第 ' + (ev.level || 1) + ' 级';
  } else {
    // 直接开**这**一道题：/games/<游戏>/?p=<题目 id>；万一条目里没有 id，就退回游戏首页
    a.href = '/games/' + encodeURIComponent(ev.game) + '/'
           + (ev.puzzle_id ? '?p=' + encodeURIComponent(ev.puzzle_id) : '');
    a.title = ev.puzzle_id ? '打开 ' + ev.puzzle_id : '打开这个游戏';
  }
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
  <div class="home-head">
    <h1>我收藏的题</h1>
    <nav class="home-tools" aria-label="收藏页导航">
      <a class="home-action" href="/difficulties">难度管理</a>
      <a class="home-action" href="/history">历史</a>
      <a class="home-action" href="/">← 游戏广场</a>
    </nav>
  </div>
  <p class="lead">觉得好的题都在这儿。</p>
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
const EXTRA_LINKS = __EXTRA_LINKS__;        // 其他玩法 id → 页面路径
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
  const extraUrl = EXTRA_LINKS[s.game];
  if (extraUrl) {
    a.href = extraUrl + '?level=' + encodeURIComponent(s.level || 1);
    a.title = '打开' + (GAME_NAMES[s.game] || '') + '第 ' + (s.level || 1) + ' 级';
  } else {
    // 跟历史页一样是深链接：直接开这道题
    a.href = '/games/' + encodeURIComponent(s.game) + '/'
           + (s.puzzle_id ? '?p=' + encodeURIComponent(s.puzzle_id) : '');
    a.title = s.puzzle_id ? '打开 ' + s.puzzle_id : '打开这个游戏';
  }
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


def _extra_home_cards_html() -> str:
    cards: List[str] = []
    for extra_id, name, url in _EXTRA_LINKS:
        try:
            data = _load_extra(extra_id)
            levels = data["levels"]
            assert isinstance(levels, list)
            summary = str(data.get("card_summary") or data.get("summary") or "")
            count = "共 %d 级" % len(levels)
        except Exception:
            summary = "这个玩法暂时打不开。"
            count = "内容读取失败"
        cards.append(
            '<a class="extra-game" href="%s">'
            '<span class="extra-name">%s</span>'
            '<span class="extra-summary">%s</span>'
            '<span class="extra-count">%s</span>'
            "</a>" % (url, escape(name), escape(summary), count)
        )
    return ('<section class="extra-games" aria-labelledby="extra-title">'
            '<h2 id="extra-title">其他玩法</h2><div class="extra-grid">'
            + "".join(cards) + "</div></section>")


def _home_html() -> str:
    cards: List[str] = []
    for game in registry.list_games():
        info = registry.levels_of(game)
        levels = info["levels"]
        # 首页只报总数 —— 等级明细太长（竞技串珠 20 档、找规律 10 档），要细看进游戏里选难度
        detail = ("共 %d 题" % info["total"]) if levels else "还没有题目"
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
    page = _PAGE % ("\n".join(cards), len(cards))
    return page.replace("__EXTRA_HOME_CARDS__", _extra_home_cards_html())


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _home_html()


@app.get("/difficulties", response_class=HTMLResponse)
def difficulties_page() -> str:
    """难度管理页；数据和开关都走 `/api/difficulty-settings`。"""
    return _DIFFICULTIES_PAGE


@app.get("/extras/{extra_id}", response_class=HTMLResponse)
def extra_page(extra_id: str) -> str:
    """其他玩法的说明页；内容来自 `extras/<id>.toml`。"""
    return _extra_page(extra_id)


@app.get("/history", response_class=HTMLResponse)
def history_page() -> str:
    """玩过什么 —— 首页右侧导航「历史」进来的。"""
    return (_HISTORY_PAGE
            .replace("__GAME_NAMES__", json.dumps(_game_names(), ensure_ascii=False))
            .replace("__EXTRA_LINKS__", json.dumps(_extra_routes(), ensure_ascii=False)))


@app.get("/stars", response_class=HTMLResponse)
def stars_page() -> str:
    """我收藏的题 —— 首页副标题的「收藏 →」进来的。"""
    return (_STARS_PAGE
            .replace("__GAME_NAMES__", json.dumps(_game_names(), ensure_ascii=False))
            .replace("__EXTRA_LINKS__", json.dumps(_extra_routes(), ensure_ascii=False)))


# 静态目录先建出来再挂载 —— 免得"启动时 web/ 还不存在 → 没挂上"这种坑
WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="plaza-static")

# 前端（游戏页面 + 各家 web/ 里的三件套）每次都回来问一句，别被浏览器的"启发式缓存"存住 ——
# 不然改了 app.js、刷新还是旧页面（详见 plaza/nocache.py）
keep_fresh(app, ("/static/", "/games/", "/extras/"))


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
