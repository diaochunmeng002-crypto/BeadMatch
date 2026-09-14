# solver —— 本项目自己的求解器

| 文件 | 说明 |
| --- | --- |
| `free_solver.py` | 按**本项目规则**（落点只要有空位就能放）求解：DFS + 启发式。**只保证能解开、不保证步数最少** |
| `test_free_solver.py` | 它的测试（规则判定、格式不变量、与独立重写的暴力搜索对拍） |

规则、参数、数据格式一律看 [../docs/requirement.md](../docs/requirement.md)。

## 怎么用

```python
import sys; sys.path.insert(0, "solver")
from free_solver import solve_any, verify, format_moves

moves = solve_any(state)        # state = 矩阵[柱子][位置]，位置 0 = 最顶端那一格
print(format_moves(moves))      # "3-7 1-2 …"（柱子编号从 1 起）
print(verify(state, moves))     # True = 这条解确实能解开
```

```bash
python -m unittest solver.test_free_solver -v
```

## 它在本项目里的定位（重要）

- **出题不依赖它**：[../walk_gen.py](../walk_gen.py) 的引导式走法「反走即解」，不需要求解器 ——
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

原版 Pascal 源码仍在本机 `../vendor/kociemba/`（**不随仓库分发**）；
这段调研的经过和结论留在 [../docs/solver_research.md](../docs/solver_research.md)。
