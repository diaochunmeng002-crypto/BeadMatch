"""BeadMatch 的唯一入口（游戏广场）—— 开发和打包都从这儿走。

    python run.py                    # 起广场，默认 127.0.0.1:8000
    python run.py --port 8001        # 端口被占了换一个
    python run.py --host 0.0.0.0     # 想让平板/手机连
    python run.py --reload           # 改代码自动重启（开发用）

打开 <http://127.0.0.1:8000> 是广场首页：串珠 / 推理 / 记忆 / 计算都从那儿进。
每个游戏也还能单独跑（`python -m games.calc.api` → 8030，等等），两边互不影响。

打包成 exe 时用的是 start/launcher.py（它自己找空闲端口 + 开窗口），不走这里，
但它读的是同一个 app 对象（``plaza.server:app``）。
"""

from __future__ import annotations

import argparse

import uvicorn

from plaza.server import app


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="跑 BeadMatch 游戏广场")
    p.add_argument("--host", default="127.0.0.1", help="想给平板/手机连就写 0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true", help="改代码自动重启（开发用）")
    args = p.parse_args(argv)
    uvicorn.run("plaza.server:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
