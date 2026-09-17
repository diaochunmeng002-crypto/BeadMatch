# 怎么启动

所有命令都在**仓库根目录**（`C:\Code\BeadMatch`）下敲。

## 起广场（推荐）：一个程序装所有游戏

```bash
python run.py
```

然后浏览器打开：

```
http://127.0.0.1:8000                ← 广场首页（宝宝串珠 / 推理 / 记忆 / 计算）
http://127.0.0.1:8000/games/calc/    ← 某个游戏的页面
http://127.0.0.1:8000/api/games      ← 有哪些游戏（JSON）
http://127.0.0.1:8000/docs           ← 所有游戏的接口文档（都在一个页面里）
```

| 页面 | 是哪个游戏 |
| --- | --- |
| `/` | 广场首页（列出所有游戏） |
| `/games/beadmatch/` | 宝宝串珠（规划） |
| `/games/logic/` | 推理 |
| `/games/memory/` | 记忆 |
| `/games/calc/` | 计算 |

每个游戏的接口在 `/api/games/<游戏>/...`（例：`/api/games/calc/random?level=1`）。
前端不用单独起服务，后端顺手托管了每个游戏的 `web/`。

端口被占了换一个：`python run.py --port 8001`；想让平板/手机连：`--host 0.0.0.0`；
改代码自动重启（开发用）：`--reload`。

## 只想调某一个游戏

四个游戏都能单独跑，端口互不打扰（平时用不到，改某个游戏时方便）：

| 游戏 | 命令 | 端口 |
| --- | --- | --- |
| 宝宝串珠 | `python -m games.beadmatch.api` | 8000 |
| 推理 | `python -m games.logic.api` | 8010 |
| 记忆 | `python -m games.memory.api` | 8020 |
| 计算 | `python -m games.calc.api` | 8030 |

单独跑时页面在 `/`、接口在 `/api/<游戏>/...`（跟以前一模一样）——
游戏里的前端代码两种跑法共用，广场会往页面里注入接口基址，不用改。

## 出题

出 1 道：

```bash
python -m games.beadmatch.core.generator
```

批量出（默认走 85 步出 10 道，也就是 9 级 10 道）：

```bash
python -m games.beadmatch.tools.make_puzzles
```

## 跑测试

```bash
python -m unittest games.beadmatch.tests.test_generator
python -m unittest games.beadmatch.tests.test_walk_gen
python -m unittest games.beadmatch.tests.test_app
python -m unittest games.beadmatch.tests.test_free_solver
```

## 检查 logic 题库

```bash
python -m games.logic.core.puzzles
```

每道题报一次「解有几个」—— **多解就是题目有问题**（线索不够）。详细说明见
[games/logic/README.md](../games/logic/README.md)。

## 起 logic 的后端（第二个游戏，暂时是独立的一个服务）

```bash
python -m games.logic.api
```

然后浏览器打开：

```
http://127.0.0.1:8010          ← 玩的页面（前端）
http://127.0.0.1:8010/docs     ← 接口文档
```

（换端口：`--port 8020`。前端不用单独起，后端顺手托管了 `web/`。）

## 检查 memory 卡片库

```bash
python -m games.memory.core.cards
```

每张规则卡报一行「读得进来吗 / 什么难度 / demo 跟材料对不对」—— **只有"读不进来"算问题**
（材料认不出、形状记号不认识、id 跟文件名对不上这种）。demo 跟材料对不上只提示一句。
详细说明见 [games/memory/README.md](../games/memory/README.md)。

想看某一张卡（附带程序读到的字段）：

```bash
python -m games.memory.core.cards --show games/memory/puzzles/1/1-01.txt
```

## 起 memory 的后端（第三个游戏，暂时也是独立的一个服务）

```bash
python -m games.memory.api
```

然后浏览器打开：

```
http://127.0.0.1:8020          ← 玩的页面（前端）
http://127.0.0.1:8020/docs     ← 接口文档
```

（换端口：`--port 8030`。接口只有 5 个，**没有 `/check`** —— 记忆游戏的排列是出题人当场摆的，
程序手里没有答案。）

## 检查 calc 题库

```bash
python -m games.calc.core.cards
```

每张计算卡报一行「读得进来吗 / 什么玩法 / 答案写得对不对（类型）」—— **只有"读不进来"算问题**
（颜色认不出、`task` 不认识、答案类型跟玩法对不上这种）。详细说明见
[games/calc/README.md](../games/calc/README.md)。

想看某一张卡（附带程序读到的字段）：

```bash
python -m games.calc.core.cards --show games/calc/puzzles/1/20260916-101500-a3f1.txt
```

## 起 calc 的后端（第四个游戏，暂时也是独立的一个服务）

```bash
python -m games.calc.api
```

然后浏览器打开：

```
http://127.0.0.1:8030          ← 玩的页面（前端）
http://127.0.0.1:8030/docs     ← 接口文档
```

（换端口：`--port 8040`。跟别的游戏不一样的是**有 `POST /api/calc/check`** ——
交一个答案（`5` / `"五"` / `"蓝"` / `"equal"` 都行）就能判对错。）

## 打包成 exe（Windows 桌面版）

先装一次打包工具：

```bash
python -m pip install pyinstaller pywebview
```

然后双击 `start\make_exe.bat`（或者在仓库根目录敲）：

```bat
start\make_exe.bat
```

产出：`dist\BeadMatch\BeadMatch.exe`（双击即用）。

不想打包、只想看看桌面窗口长什么样：

```bash
python start\launcher.py
```

打包完会在仓库里留下 `build\`（PyInstaller 的工作目录，`BeadMatch.spec` 也在里面）
和 `dist\`（成品）。这两个目录都不进仓库（`.gitignore` 已排除），想清理可以直接删。

几个要点：

- **不用打包浏览器**：窗口用系统自带的 WebView2（Windows 10/11 都有）；万一机器上没有，
  启动器会自动退回「用默认浏览器打开」，不会打不开。
- **数据放在 exe 旁边**：`games\beadmatch\puzzles\`（首次运行会把内置题库拷过去）和
  `BeadMatch.log`（出问题看它）。
- **放在哪**：放在有写权限的地方（桌面、文档、D 盘随便建个文件夹都行）。
  如果放在 `C:\Program Files` 这类需要管理员权限的目录，程序会**自动改用**
  `%LOCALAPPDATA%\BeadMatch` 存数据，并在日志里写明。
- 给别人用：把整个 `dist\BeadMatch\` 文件夹（或压成 zip）发过去即可。
- ⚠️ **必须整个文件夹一起给**：`BeadMatch.exe` 旁边的 `_internal\` 不能少，单独发 exe 是跑不起来的。
- 体积：约 35 MB；压成 zip 约 12~15 MB。

### 在哪些 Windows 上能用

| 系统 | 结果 |
| --- | --- |
| Windows 11（64 位） | ✅ 直接双击就能用（WebView2 系统预装） |
| Windows 10 1803+（64 位） | ✅ 直接能用（WebView2 一般随 Edge 装好了） |
| Windows 10 早期版本（没 WebView2） | ✅ 程序能跑，但窗口起不来时会**自动退回默认浏览器** |
| Windows 8.1 / 8 / 7 | ❌ 打不开（捆绑的 Python 3.13 与 WebView2 都不支持这些系统） |
| 32 位 Windows | ❌ 打不开（打的是 64 位包） |
| 装了杀毒 / 公司管控的电脑 | ⚠️ 可能被拦（PyInstaller 常见误报），需要加白名单 |
- **图标**：`start\beadmatch.ico` 已经有了（打包脚本里用 `--icon start\beadmatch.ico` 接上）。
  想改样子就编辑 `start\make_icon.py` 顶部的配色/颗数，然后 `python start\make_icon.py` 重新生成
  （会同时刷新 `start\beadmatch.png` 预览图）。
