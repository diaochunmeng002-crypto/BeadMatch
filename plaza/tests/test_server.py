"""广场的访问清单：接口能查、页面能开、首页有入口。"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from plaza import history
from plaza.server import app


class HistoryPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Path(__file__).resolve().parent / ".tmp_history_server.db"
        self._remove()
        os.environ["BEADMATCH_HISTORY_DB"] = str(self.db)
        os.environ.pop("BEADMATCH_HISTORY", None)      # 强制打开，别被别的测试的 off 影响
        self.client = TestClient(app)

    def tearDown(self) -> None:
        os.environ.pop("BEADMATCH_HISTORY_DB", None)
        os.environ.pop("BEADMATCH_HISTORY", None)
        self._remove()

    def _remove(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.db) + suffix)
            if path.exists():
                path.unlink()

    def test_api_is_newest_first(self) -> None:
        history.record(game="calc", puzzle_id="old", level=1,
                       ts=datetime(2026, 9, 20, 1, 0, tzinfo=timezone.utc))
        history.record(game="logic", puzzle_id="new", level=2,
                       ts=datetime(2026, 9, 20, 2, 0, tzinfo=timezone.utc))

        data = self.client.get("/api/history", params={"limit": 200}).json()
        self.assertEqual(data["count"], 2)
        self.assertEqual([e["puzzle_id"] for e in data["events"]], ["new", "old"])
        self.assertEqual(data["events"][0]["game"], "logic")
        self.assertEqual(data["events"][0]["level"], 2)

    def test_api_honours_limit(self) -> None:
        for i in range(5):
            history.record(game="calc", puzzle_id="card-%d" % i)
        data = self.client.get("/api/history?limit=2").json()
        self.assertEqual(data["count"], 2)

    def test_game_endpoints_write_history(self) -> None:
        got = self.client.get("/api/games/calc/random", params={"level": 1})
        self.assertEqual(got.status_code, 200)
        card = got.json()

        rows = history.query(game="calc")
        self.assertEqual([e["source"] for e in rows], ["random"])
        self.assertEqual(rows[0]["puzzle_id"], card["id"])
        self.assertEqual(rows[0]["level"], 1)

        self.client.get("/api/games/calc/puzzles/%s" % card["id"])
        self.assertEqual([e["source"] for e in history.query(game="calc")], ["by_id", "random"])

    def test_kill_switch_stops_automatic_recording(self) -> None:
        os.environ["BEADMATCH_HISTORY"] = "off"
        try:
            self.client.get("/api/games/calc/random", params={"level": 1})
        finally:
            os.environ.pop("BEADMATCH_HISTORY", None)
        self.assertEqual(history.query(game="calc"), [])

    def test_history_page_and_home_link(self) -> None:
        page = self.client.get("/history")
        self.assertEqual(page.status_code, 200)
        self.assertIn("玩过什么", page.text)        # 页面上那行标题（原来写的是"访问清单"）

        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn('href="/history"', home.text)
        # 首页副标题后面并排两个小链接：查看历史 + GitHub（都给自己人看）
        self.assertIn("github.com/diaochunmeng002-crypto/BeadMatch", home.text)

    def test_home_shows_only_the_total(self) -> None:
        """首页每张卡片只报总数（"共 N 题"），不铺每级多少题。"""
        home = self.client.get("/").text
        self.assertIn("共 ", home)
        self.assertNotIn("1 级", home)              # 等级明细只在游戏页的难度下拉里

    def test_history_page_link_points_at_the_puzzle(self) -> None:
        """「打开」得带上题目 id（/games/<游戏>/?p=<id>）—— 光回游戏首页就开成随机一道了。"""
        page = self.client.get("/history").text
        self.assertIn("'/games/' + encodeURIComponent(ev.game) + '/'", page)
        self.assertIn("'?p=' + encodeURIComponent(ev.puzzle_id)", page)

    def test_history_page_shows_the_author_and_the_method(self) -> None:
        """「出题者」那栏要 **created_by + generator** 两个都显示。

        只看 created_by 会以为出题方式只有一种 —— 竞技串珠库里每一道都是
        ``beadsort``，可它们混着 sampler / layershuffle / kociemba / walk 四种
        方法出的，低级和高级还不是同一批；那层信息只在 generator 里。
        """
        history.record_served(game="beadsort",
                              payload={"id": "p1", "level": 1, "created_by": "beadsort",
                                       "generator": "sampler@1"})
        history.record_served(game="beadsort",
                              payload={"id": "p2", "level": 22, "created_by": "beadsort",
                                       "generator": "layershuffle@1"})

        events = self.client.get("/api/history").json()["events"]   # 新的在最前面
        self.assertEqual(events[0]["detail"]["generator"], "layershuffle@1")
        self.assertEqual(events[1]["detail"]["generator"], "sampler@1")

        page = self.client.get("/history").text
        self.assertIn("出题者", page)                  # 表头那一栏
        self.assertIn("ev.detail.created_by", page)    # 前端照着它渲染「谁出的」
        self.assertIn("ev.detail.generator", page)     # 还有「用哪套算法」
        # 算法名尾上的版本号**不显示**（sampler@1 → sampler）：@1 是给自己排错用的，
        # 摆在页面上只是噪音，要看就鼠标停一下（提示里给完整的）
        self.assertIn("full.split('@')[0]", page)

    def test_history_page_literal_keeps_its_backslashes(self) -> None:
        """页面那段 HTML 是**普通**三引号字符串：反斜杠必须成对写。

        2026-10-16 踩过 —— 给 tooltip 写「反斜杠 + n」（想让 JS 见到转义）时，Python
        先把它吃成一个**真换行**，于是那个 JS 字符串从中间被劈开、整段内联脚本报废：
        `load(false)` 根本不会跑，页面永远停在「读取中…」。所以这条盯着页面字面量里
        反斜杠的总数必须是偶数（成对的）。
        """
        path = Path(__file__).resolve().parent.parent / "server.py"
        src = path.read_text(encoding="utf-8")
        start = src.index('_HISTORY_PAGE = """') + len('_HISTORY_PAGE = """')
        body = src[start:src.index('"""', start)]
        self.assertIn("</html>", body)            # 切出来的确实是那一整段页面
        self.assertEqual(body.count("\\") % 2, 0,
                         "页面字面量里有落单的反斜杠 —— Python 会把它吃掉，"
                         "JS 那边就是一段断掉的字符串。要写换行请用「反斜杠 + n」两个字符")

    def test_clear_endpoint_wipes_the_history(self) -> None:
        """「清空」按钮走的就是这条接口：清完一条不剩，还报一句清掉了几条。"""
        history.record_served(game="beadsort", payload={"id": "p1", "level": 1})
        history.record_served(game="beadsort", payload={"id": "p2", "level": 2})
        self.assertEqual(self.client.get("/api/history").json()["count"], 2)

        got = self.client.post("/api/history/clear")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json(), {"ok": True, "deleted": 2})
        self.assertEqual(self.client.get("/api/history").json()["count"], 0)
        self.assertEqual(history.query(game="beadsort"), [])

        page = self.client.get("/history").text
        self.assertIn('id="clear"', page)              # 按钮在
        self.assertIn("/api/history/clear", page)      # 前端打的是这条接口
        self.assertIn("已清空", page)                   # 清完在状态行报一句

    def test_star_api_toggles_one_puzzle(self) -> None:
        """收藏接口：POST /api/star 幂等，GET /api/stars 列出来、能筛。"""
        body = {"game": "logic", "puzzle_id": "p1", "level": 5}
        first = self.client.post("/api/star", json=body)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["starred"])

        self.client.post("/api/star", json=body)      # 再收一次：不该多一条
        data = self.client.get("/api/stars").json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["stars"][0]["level"], 5)
        self.assertEqual(self.client.get("/api/stars", params={"game": "calc"}).json()["count"], 0)

        off = self.client.post("/api/star",
                               json={"game": "logic", "puzzle_id": "p1", "starred": False})
        self.assertEqual(off.status_code, 200)
        self.assertFalse(off.json()["starred"])
        self.assertEqual(self.client.get("/api/stars").json()["count"], 0)

    def test_star_api_rejects_bad_input(self) -> None:
        self.assertEqual(self.client.post("/api/star", json={"game": "nope", "puzzle_id": "p1"})
                         .status_code, 400)
        self.assertEqual(self.client.post("/api/star", json={"game": "logic", "puzzle_id": "  "})
                         .status_code, 400)

    def test_game_page_gets_the_star_widget(self) -> None:
        """每个游戏页面都由广场注入收藏星标；游戏侧只要上报"现在是哪一道"。"""
        page = self.client.get("/games/logic/").text
        self.assertIn('id="plaza-star"', page)       # 星标按钮
        self.assertIn("plaza-star", page)
        self.assertIn('class="glyph"', page)         # ☆ / ★ 单独一个 span，好上色
        self.assertIn("align-items:center;gap:4px", page)  # 星形和文字之间留空格
        self.assertIn("plazaSetPuzzle", page)        # 游戏页面调它上报当前题
        self.assertIn("/api/star", page)             # 点了打这条接口
        self.assertIn("/api/stars", page)            # 初始状态读这条

    def test_stars_page_and_home_link(self) -> None:
        """收藏页：布局照历史页；首页副标题有「收藏 →」入口。"""
        page = self.client.get("/stars")
        self.assertEqual(page.status_code, 200)
        self.assertIn("我收藏的题", page.text)
        self.assertIn("/api/stars", page.text)      # 页面读收藏列表
        self.assertIn("/api/star", page.text)       # 点星取消收藏
        self.assertIn("/games/", page.text)         # 「打开」还是深链接

        home = self.client.get("/").text
        self.assertIn('href="/stars"', home)
        self.assertIn("收藏", home)

    def test_every_game_can_serve_a_puzzle_by_id(self) -> None:
        """深链接靠的是各游戏的 `/puzzles/{id}` —— 所有题库非空的游戏都得能按 id 取题。"""
        games = self.client.get("/api/games").json()["games"]
        self.assertTrue(games)
        for game in games:
            levels = [row["level"] for row in (game.get("levels") or [])]
            if not levels:
                continue                                  # 题库是空的：没得取，跳过
            got = self.client.get("/api/games/%s/random" % game["id"],
                                  params={"level": levels[0]})
            self.assertEqual(got.status_code, 200, game["id"])
            picked = got.json()
            again = self.client.get("/api/games/%s/puzzles/%s" % (game["id"], picked["id"]))
            self.assertEqual(again.status_code, 200, game["id"])
            self.assertEqual(again.json()["id"], picked["id"], game["id"])
            self.assertEqual(again.json()["level"], picked["level"], game["id"])

    def test_beadcipher_is_served_by_the_plaza(self) -> None:
        """新游戏要自动进首页，题目页要挂上广场接口前缀和收藏星标。"""
        games = self.client.get("/api/games").json()["games"]
        game = next((row for row in games if row["id"] == "beadcipher"), None)
        self.assertIsNotNone(game)
        self.assertEqual(game["name"], "彩珠密令")
        self.assertEqual(game["total"], 21)
        self.assertEqual(games[-1]["id"], "beadcipher")   # 新模块固定放在最后

        page = self.client.get("/games/beadcipher/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("彩珠密令", page.text)
        self.assertIn('window.API_BASE="/api/games/beadcipher"', page.text)
        self.assertIn('id="plaza-star"', page.text)

        js = self.client.get("/games/beadcipher/static/app.js")
        self.assertEqual(js.status_code, 200)
        self.assertIn("__beadcipher_loaded", js.text)

    def test_game_url_without_slash_keeps_the_query(self) -> None:
        """/games/<游戏>?p=<id>（少个斜杠）跳过去时，题目 id 不能丢。"""
        got = self.client.get("/games/logic", params={"p": "X"}, follow_redirects=False)
        self.assertEqual(got.status_code, 307)
        self.assertTrue(got.headers["location"].endswith("/games/logic/?p=X"), got.headers)

    def test_frontend_says_no_cache(self) -> None:
        """前端资源要带 `Cache-Control: no-cache`。

        不发这个头，浏览器就按"启发式缓存"把 app.js 存上好几天（问都不问）：
        改了前端、刷新页面还是旧代码 —— 2026-10-16 就是这么被坑的（历史页的
        「打开」已经带上 ?p= 了，点进去却是旧前端的行为）。
        """
        page = self.client.get("/games/beadsort/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers.get("cache-control"), "no-cache")

        js = self.client.get("/games/beadsort/static/app.js")
        self.assertEqual(js.status_code, 200)
        self.assertEqual(js.headers.get("cache-control"), "no-cache")
        self.assertIn("WANT_ID", js.text)      # 顺手确认发出去的确实是新版前端


if __name__ == "__main__":
    unittest.main()
