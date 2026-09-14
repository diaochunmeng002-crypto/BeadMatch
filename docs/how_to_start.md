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
python -m unittest server.test_app
python -m unittest solver.test_free_solver
python -m unittest solver.test_kociemba_solver
```
