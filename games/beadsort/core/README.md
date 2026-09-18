# core —— 串珠的纯逻辑层

| 文件 | 说明 |
| --- | --- |
| `methods/` | **出题方法**：一个方法一个模块（`walk.py` / `kociemba.py` + 注册表）。加第三种方法 = 加一个文件 |
| `walk_gen.py` | 反走的零件（拿得起/放得下、合并同球连搬、乱度指标），`methods/walk.py` 用它 |
| `sampler.py` | 约束采样器：纯随机反走 + 禁重复局面 + 停滞截断；出题和"量天花板"都用它 |
| `kociemba_solver.py` | Kociemba 水排序解算器的 Python 移植（`single` 模式 = 我们的规则）。**2026-09-18 从 git 历史捞回来的**，现在给 `methods/kociemba.py` 当求解器 |
| `generator.py` | 出题 / 题库读写与校验（题目文件的渲染、解析、存读、索引） |
| `free_solver.py` | 规则（**只能放空柱或同色柱顶**）+ 求解（DFS + 启发式）。**只保证能解开、不保证步数最少** |

这一层不碰网络、不碰端口；测试在 [../tests/](../tests/)。

规则看 [free_solver.py](free_solver.py) 的模块说明（跟宝宝串珠那套不一样）、玩法和出题方式看
[../README.md](../README.md)；参数和数据格式跟宝宝串珠同一套（`docs/requirement.md`）；
广场（多游戏）那层的规划看 [../../../docs/plaza.md](../../../docs/plaza.md)。

## 怎么用

```python
from games.beadsort.core.free_solver import solve_any, verify, format_moves

moves = solve_any(state)        # state = 矩阵[柱子][位置]，位置 0 = 最顶端那一格
print(format_moves(moves))      # "3-7 1-2 …"（柱子编号从 1 起）
print(verify(state, moves))     # True = 这条解确实能解开
```

```bash
python -m unittest games.beadsort.tests.test_free_solver -v
```

## 它在本项目里的定位（重要）

- **出题不依赖它**：[walk_gen.py](walk_gen.py) 的「施工式反走」，不需要求解器 ——
  所以出题 100% 成功、毫秒级；
- 它只当**兜底**：手工摆的题、外部来的题，用它判断"有没有解"、给一条参考解；
- 能力有限：实测 100 步的题 5/5 能解出，但会给 129 / 170 步这种绕远路的解；200 步的题只有 3/5。

## 历史：Kociemba 的 Python 移植（删过，又捞回来了）

2026-09-11 移植过 hkociemba 的 WaterBallSortPuzzleOptimalSolver（Pascal → Python）。
它实现的是**商业球排序那套规则**（只能放空柱或顶色相同的柱子），而且很快（0.03~0.08 秒出解），
当时的用途是"帮我们算难度 / 找短解"。

2026-09-14 删除，原因两条：

1. **规则不一样**：它的「最少步数」在本项目的规则下只是**上界**，它报「无解」也不代表我们解不开；
2. **用不上了**：改用 `walk_gen` 出题后，解是白送的；拿它去解那些新题，10 道里 **0 道**能解出
   （唯一"解出"的那道给了 101 步，比我们白送的 100 步还长）。

**2026-09-18 又捞回来了**（`git show 1ce96a1^:solver/kociemba_solver.py`，字节没变），放进 beadsort
当**第二种出题方法**：随机摆一个局面，让它解，解出来才留（`methods/kociemba.py`）。
当年那两条删除理由对 beadsort 都不成立 —— ①它的规则**就是** beadsort 的规则；
②现在不是"拿它解反走出来的题"，而是"拿它筛随机摆出来的题"，正是它的强项。
它自带的测试（含一份独立写的暴力 BFS 对拍）也一起回来了：`tests/test_kociemba_solver.py`。

原版 Pascal 源码当年存在本机 `../../../vendor/kociemba/`，**2026-09-15 已删除**（规则不同、代码里没有任何引用）；
这段调研的经过和结论留在 [../../../docs/solver_research.md](../../../docs/solver_research.md)。
