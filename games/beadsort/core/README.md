# core —— 串珠的纯逻辑层

| 文件 | 说明 |
| --- | --- |
| `walk_gen.py` | 出题算法：**施工式反走**（把一条合法解倒着演一遍 → 题面；见模块开头） |
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

## 历史：Kociemba 的 Python 移植（2026-09-14 已删除）

2026-09-11 移植过 hkociemba 的 WaterBallSortPuzzleOptimalSolver（Pascal → Python）。
它实现的是**商业球排序那套规则**（只能放空柱或顶色相同的柱子），而且很快（0.03~0.08 秒出解），
当时的用途是"帮我们算难度 / 找短解"。

2026-09-14 删除，原因两条：

1. **规则不一样**：它的「最少步数」在本项目的规则下只是**上界**，它报「无解」也不代表我们解不开；
2. **用不上了**：改用 `walk_gen` 出题后，解是白送的；拿它去解那些新题，10 道里 **0 道**能解出
   （唯一"解出"的那道给了 101 步，比我们白送的 100 步还长）。

原版 Pascal 源码当年存在本机 `../../../vendor/kociemba/`，**2026-09-15 已删除**（规则不同、代码里没有任何引用）；
这段调研的经过和结论留在 [../../../docs/solver_research.md](../../../docs/solver_research.md)。
