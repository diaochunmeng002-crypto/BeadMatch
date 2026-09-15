"""BeadMatch 的唯一入口 —— 开发和打包都从这儿走。

    python run.py                    # 起服务，默认 127.0.0.1:8000
    python run.py --port 8001        # 端口被占了换一个
    python run.py --host 0.0.0.0     # 想让平板/手机连
    python run.py --reload           # 改代码自动重启（开发用）

打包成 exe 时用的是 start/launcher.py（它自己找空闲端口 + 开窗口），不走这里，
但它读的是同一个 app 对象（``games.beadmatch.api:app``）。
"""

from __future__ import annotations

import argparse

import uvicorn

from games.beadmatch.api import app


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="跑 BeadMatch 后端")
    p.add_argument("--host", default="127.0.0.1", help="想给平板/手机连就写 0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true", help="改代码自动重启（开发用）")
    args = p.parse_args(argv)
    uvicorn.run("games.beadmatch.api:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
