# 怎么启动

（所有命令都在仓库根目录下敲。）

都在仓库根目录（`C:\Code\BeadMatch`）下敲。

## 起后端

```bash
python -m server.app
```

然后浏览器打开：

```
http://127.0.0.1:8000          ← 玩的页面（前端）
http://127.0.0.1:8000/docs     ← 接口文档（想直接试接口时用）
```

前端不用单独起服务，后端顺手托管了 `web/`。

端口被占了就换一个：

```bash
python -m server.app --port 8001
```

想让平板/手机连：

```bash
python -m server.app --host 0.0.0.0
```

改代码自动重启（开发用）：

```bash
uvicorn server.app:app --reload
```

## 出题

出 1 道：

```bash
python generator.py
```

批量出（默认 100 步 ×500 道 + 200 步 ×100 道）：

```bash
python make_puzzles.py
```

## 跑测试

```bash
python -m unittest test_generator
python -m unittest test_walk_gen
python -m unittest server.test_app
python -m unittest solver.test_free_solver
```

## 打包成 exe（Windows 桌面版）

先装一次打包工具：

```bash
python -m pip install pyinstaller pywebview
```

然后在 **仓库根目录**执行：

```bat
make_exe.bat
```

产出：`dist\BeadMatch\BeadMatch.exe`（双击即用）。

几个要点：

- **不用打包浏览器**：窗口用系统自带的 WebView2（Windows 10/11 都有）；万一机器上没有，
  启动器会自动退回「用默认浏览器打开」，不会打不开。
- **数据放在 exe 旁边**：`puzzles\`（首次运行会把内置题库拷过去）和 `BeadMatch.log`（出问题看它）。
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
- **图标**：仓库里已经有 `beadmatch.ico`（打包脚本里已经用 `--icon beadmatch.ico` 接上了）。
  想改样子就编辑 `make_icon.py` 顶部的配色/颗数，然后 `python make_icon.py` 重新生成
  （会同时刷新 `beadmatch.png` 预览图）。
