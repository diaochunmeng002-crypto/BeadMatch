# 启动 / 出题 —— 命令速查

## 1. 启动（广场，所有游戏一起）

```powershell
python run.py
python run.py --port 8001
```

## 2. 启动（带参数：换题库 / 换端口）

```powershell
python run.py --puzzles beadsort=games/beadsort/puzzles_kociemba
python run.py --puzzles beadsort=games/beadsort/puzzles_layershuffle
python run.py --puzzles beadsort=games/beadsort/puzzles_layershuffle_30k
python run.py --puzzles beadsort=games/beadsort/puzzles_layershuffle_30k --port 8001
```

## 3. 打开浏览器

- [广场首页 http://127.0.0.1:8000](http://127.0.0.1:8000)
- [竞技串珠 http://127.0.0.1:8000/games/beadsort/](http://127.0.0.1:8000/games/beadsort/)
- [宝宝串珠 http://127.0.0.1:8000/games/beadmatch/](http://127.0.0.1:8000/games/beadmatch/)
- [推理 http://127.0.0.1:8000/games/logic/](http://127.0.0.1:8000/games/logic/)
- [记忆 http://127.0.0.1:8000/games/memory/](http://127.0.0.1:8000/games/memory/)
- [计算 http://127.0.0.1:8000/games/calc/](http://127.0.0.1:8000/games/calc/)
- [接口文档 http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## 4. 出题

### 4.1 竞技串珠 beadsort（统一入口：三套方法）

```powershell
python -m games.beadsort.tools.make --method walk --n 100000
python -m games.beadsort.tools.make --method walk --n 100000 --per-level 50 --out games/beadsort/puzzles_walk_v2

python -m games.beadsort.tools.make --method kociemba --n 30000
python -m games.beadsort.tools.make --method kociemba --n 30000 --node-limit 2000000 --out games/beadsort/puzzles_kociemba

python -m games.beadsort.tools.make --method layershuffle --n 20
python -m games.beadsort.tools.make --method layershuffle --n 30000 --per-level 200 --out games/beadsort/puzzles_layershuffle_30k
```

### 4.2 宝宝串珠 beadmatch

```powershell
python -m games.beadmatch.tools.make
python -m games.beadmatch.tools.make --n 50 --level 9 --out games/beadmatch/puzzles_new
```

## 5. 检查题库 / 跑测试

```powershell
python -m games.logic.core.puzzles
python -m games.memory.core.cards
python -m games.calc.core.cards
python -m unittest discover -s games/beadsort/tests -t .
python -m unittest games.beadmatch.tests.test_app
```

## 6. 打包 exe

```powershell
python -m pip install pyinstaller pywebview
start\make_exe.bat
python start\launcher.py
```
