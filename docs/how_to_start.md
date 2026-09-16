# 怎么启动

所有命令都在**仓库根目录**（`C:\Code\BeadMatch`）下敲。

## 起后端

```bash
python run.py
```

然后浏览器打开：

```
http://127.0.0.1:8000          ← 玩的页面（前端）
http://127.0.0.1:8000/docs     ← 接口文档（想直接试接口时用）
```

前端不用单独起服务，后端顺手托管了 `web/`。

端口被占了就换一个：

```bash
python run.py --port 8001
```

想让平板/手机连：

```bash
python run.py --host 0.0.0.0
```

改代码自动重启（开发用）：

```bash
python run.py --reload
```

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
