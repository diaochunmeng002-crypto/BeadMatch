"""BeadMatch 桌面版启动器（打包成 exe 时用这个当入口）。

做的事：
  1. 确定「数据目录」（题库、日志）和「资源目录」（web/ 前端）；
  2. 找一个**空闲端口**起本地 FastAPI 服务（不写死 8000，避免被占）；
  3. 用 pywebview 开一个**原生窗口**；没有 WebView2 / 没装 pywebview 就退回系统浏览器；
  4. 出错了写日志 + 弹一个消息框（打包后没有控制台，得让用户看得见）。

开发时也可以直接跑：``python launcher.py``
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "BeadMatch"
WINDOW_W, WINDOW_H = 1180, 780


class _NullWriter:
    """占位输出流：打包成 --noconsole 后 sys.stdout/stderr 是 None，
    而不少库（比如 uvicorn 的日志）会调用 .isatty() 之类 → 直接崩。"""

    def write(self, *_args):
        return 0

    def flush(self):
        pass

    def isatty(self):
        return False


def fix_std_streams() -> None:
    for name in ("stdout", "stderr", "__stdout__", "__stderr__"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, _NullWriter())


def data_dir() -> Path:
    """可写目录：打包后 = exe 所在目录；开发时 = 仓库根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def pick_data_dir() -> Path:
    """优先用 exe 旁边；那里写不了（比如装在 C:\\Program Files）就退到用户目录。"""
    primary = data_dir()
    if writable(primary):
        return primary
    fallback = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def resource_dir() -> Path:
    """只读资源目录：打包后 = PyInstaller 的解压目录（_MEIPASS）；开发时 = 仓库根目录。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def free_port() -> int:
    """让系统给我们一个空闲端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def ensure_puzzles(data: Path, res: Path) -> Path:
    """题库目录放在数据目录下；第一次运行（空题库）时把内置题库拷一份过去。"""
    puzzles = data / "puzzles"
    puzzles.mkdir(parents=True, exist_ok=True)
    if not any(puzzles.glob("*/*.txt")):
        builtin = res / "puzzles"
        if builtin.is_dir() and builtin.resolve() != puzzles.resolve():
            shutil.copytree(builtin, puzzles, dirs_exist_ok=True)
    return puzzles


def wait_until_ready(url: str, timeout: float = 15.0) -> bool:
    """等服务起来（轮询 /api/health）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.15)
    return False


def show_error(message: str) -> None:
    """打包后没有控制台，出错用消息框显示（开发时直接打印）。"""
    print(message, file=sys.stderr)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME + " 启动失败", 0x10)
    except Exception:
        pass


def main() -> int:
    fix_std_streams()
    data = pick_data_dir()
    res = resource_dir()

    logging.basicConfig(
        filename=str(data / "BeadMatch.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    puzzles = ensure_puzzles(data, res)
    # 必须在 import server.app 之前设好：静态目录挂载和题库目录都是 import 时确定的
    os.environ["BEADMATCH_PUZZLES"] = str(puzzles)
    os.environ["BEADMATCH_WEB"] = str(res / "web")

    import uvicorn

    import server.app as app_module

    port = free_port()
    url = "http://127.0.0.1:%d" % port
    note = "" if data == data_dir() else "（exe 旁边写不了，改用用户目录）"
    logging.info("data=%s%s res=%s puzzles=%s url=%s", data, note, res, puzzles, url)

    # log_config=None：不用 uvicorn 自带的日志配置（它依赖 stderr，无控制台时会崩）
    config = uvicorn.Config(app_module.app, host="127.0.0.1", port=port,
                            log_config=None, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    if not wait_until_ready(url):
        show_error("本地服务没能启动，请看 %s 里的日志。" % (data / "BeadMatch.log"))
        return 1

    # 只跑服务、不开窗口（自测/无界面环境用）：BEADMATCH_NO_WINDOW=1
    if os.environ.get("BEADMATCH_NO_WINDOW"):
        logging.info("NO_WINDOW 模式：只起服务，不开窗口")
        print("BeadMatch 服务已启动：%s" % url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0

    try:
        import webview  # pywebview：用系统自带的 WebView2，不打包浏览器
    except ImportError:
        webview = None

    if webview is not None:
        try:
            webview.create_window(APP_NAME, url, width=WINDOW_W, height=WINDOW_H,
                                  min_size=(760, 560))
            webview.start()
            return 0
        except Exception as e:  # 没有 WebView2 之类
            logging.exception("pywebview 启动失败，改用浏览器：%s", e)

    # 兜底：用系统默认浏览器打开（关掉窗口就等于结束，用回车退出）
    webbrowser.open(url)
    print("已在浏览器打开：%s\n关掉这个窗口就等于结束程序（或按回车退出）。" % url)
    try:
        input()
    except EOFError:
        while True:
            time.sleep(1)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # 打包后没有控制台，至少让用户看到一句话
        logging.exception("启动失败")
        show_error("启动失败：%s" % exc)
        raise SystemExit(1)
