"""别让浏览器"自己猜"前端能缓存多久 —— 广场和每个游戏的单独入口共用这一条。

Starlette 的静态托管只发 `ETag` / `Last-Modified`，不发 `Cache-Control`。浏览器于是
按"启发式缓存"给它们一个有效期（≈ 上次修改距今的 10%，动辄好几天），而且**问都不问**。
很难查的那种"bug"就是这么来的：改了 `web/app.js`、刷新页面，看到的还是旧前端
（2026-10-16 踩过一次：历史页的「打开」明明带上了 `?p=`，点进去却是旧前端的行为 ——
随机一道 1 级的题）。

`no-cache` 不是"不缓存"：它只是要求**每次回来问一句**。带着 `ETag` 一问就 304，
本地这点开销可以忽略。挂一次，以后改前端"刷新即见效"，不用教人按 Ctrl+F5。
"""

from __future__ import annotations

from typing import Sequence, Tuple

from fastapi import FastAPI, Request


def keep_fresh(app: FastAPI, prefixes: Sequence[str] = ("/static/",)) -> None:
    """给 `app` 装一条中间件：`prefixes` 开头的请求，响应都带 `Cache-Control: no-cache`。

    广场传 `("/static/", "/games/")` —— 连游戏页面本身一起（页面里的导航和接口基址
    是广场注入的，改了就希望立刻看到）；单个游戏自己跑时，`web/` 那三件套都在
    `/static/` 底下，用默认值就够。
    """
    roots: Tuple[str, ...] = tuple(prefixes)

    @app.middleware("http")
    async def _keep_fresh(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(roots):
            response.headers.setdefault("Cache-Control", "no-cache")
        return response
