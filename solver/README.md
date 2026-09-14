# solver —— Kociemba 解算器的 Python 移植

把 [hkociemba/WaterBallSortPuzzleOptimalSolver](https://github.com/hkociemba/WaterBallSortPuzzleOptimalSolver)
的 Pascal 源码（`water.pas`）移植成了 Python。

原始源码留档在 `../vendor/kociemba/`（**只在本机，不随仓库分发**）。

> **2026-09-12 注意**：本求解器（以及原版 Kociemba 程序）实现的是「一次挪一颗，
> **只能**放到空柱或顶色相同的柱子上」这套**模型**。需求方已确认**本项目的游戏没有这条限制**
> （见 [../docs/requirement.md](../docs/requirement.md) §2.2，落点只要有空位就能放）。
> 所以本求解器报的「有无解」「最优步数」只对那套模型成立，不能直接当成本项目的判据。

| 文件 | 说明 |
| --- | --- |
| `kociemba_solver.py` | 移植后的解算器 + 命令行 |
| `test_kociemba_solver.py` | 正确性验证（用独立实现的暴力搜索对拍） |
| `free_solver.py` | **2026-09-12 新增**：按本项目规则（落点只要有空位）的求解器，DFS + 启发式；`solve_any()` 会先借上面的 Kociemba，它给不出解再退回来 |
| `test_free_solver.py` | `free_solver` 的测试（规则判定、格式不变量、对拍） |

> **术语提醒**：本目录的 `kociemba_solver.py` 是**旧规则**（商业球排序）的实现，
> 我们只在 `free_solver.solve_any()` 里**借它求一条短解**——它的走法在本项目规则下同样合法。
> 本项目自己的规则、参数、数据格式一律看 [../docs/requirement.md](../docs/requirement.md)。

## 快速开始

```bash
# 6 色、容量 10、2 根空柱，一次挪一颗（球排序）：不传 --puzzle 就是随机出一个局面并求解
python kociemba_solver.py --colors 6 --volume 10 --empty 2 --single --seed 1

# 4 色、容量 5、2 根空柱，一次倒尽可能多（水排序），求最优解
python kociemba_solver.py --colors 4 --volume 5 --empty 2 --multi

# 从 JSON 文件读局面
python kociemba_solver.py --puzzle puzzle.json --single
```

（**没有 `--random` 这个参数**：不传 `--puzzle` 时默认就是随机出一个局面。）

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--colors` | 颜色数 C |
| `--volume` | 每根柱子的容量 N |
| `--empty` | 空柱数量 K（默认 2） |
| `--single` | 一次挪一颗（球排序）。**本项目的玩法** |
| `--multi` | 一次倒尽可能多（水排序） |
| `--node-limit` | 生成节点上限，超过就中止 |
| `--save` | 把随机生成的局面存成 JSON |
| `--quiet` | 只输出解 |

## 作为库调用

```python
from kociemba_solver import ColorSortSolver, make_vial, render

# 容量 3 的两根柱子：一根 2 红，一根 2 蓝，外加一根空柱
vials = [
    make_vial([2, 2], 3),   # 从下到上：红 红
    make_vial([1, 1], 3),   # 从下到上：蓝 蓝
    make_vial([], 3),       # 空柱
]

solver = ColorSortSolver(n_colors=2, n_volume=3, n_empty_vials=1, single_mode=True)
result = solver.solve(vials)

print(result.status)              # optimal / near-optimal / solved / unsolved / aborted
print(result.moves)               # [(源柱, 目标柱), ...]，0 起的初始柱子编号
print(result.total_move_count)    # 总步数
print(result.moves_text)          # 人类可读，柱子编号从 1 起
print(render(vials, 3))           # 把局面画出来
```

### 数据格式

一根柱子是长度 `n_volume` 的整数列表，**下标 0 是最顶上那颗珠子，下标 `n_volume-1`
是最底下那颗**，`0` 表示空位。用 `make_vial()` 可以从「从下到上」的写法转过来。

```
容量 5 的柱子，从下到上是 红、蓝、绿  ->  [0, 0, 绿, 蓝, 红]
空柱                                  ->  [0, 0, 0, 0, 0]
```

颜色编号沿用原版枚举：`0` 空、`1` 蓝、`2` 红、`3` 柠黄、`4` 黄、`5` 紫、`6` 青……

## 验证情况

`test_kociemba_solver.py` 用一个**独立重写**的暴力广度优先搜索做对照，
覆盖 8 种参数组合、各 12 个随机局面：

- **`--multi` 玩法**：移植版给出的步数与暴力搜索的**最优步数完全一致**。
- **`--single` 玩法**：有解 / 无解的判断与暴力搜索**完全一致**；
  给出的走法套到盘面上能真的走成已解状态。
  在这些小规模样本上，步数**也完全等于最优**（184~200 个样本全部相等）。
  但请注意：原作者明确说过 single 玩法**不保证最优**，这只是小规模下的实测结果。
- 另外验证了「确实存在无解局面」且移植版能判出来。

```bash
cd solver
python -m unittest test_kociemba_solver -v
```

## 与原版的差异

| 项目 | 原版 Pascal | 本移植 |
| --- | --- | --- |
| 去重用的哈希表 | 2³² 位的位图，固定占 **512 MB** | Python `set` |
| 界面 | Lazarus 图形界面（出题、手动试玩、撤销） | 命令行 + 库 |
| 输出 | 单块模式只报告主体步数 | 主体与收尾步数分开报，并给出总数 |

哈希表这一项：两者都是按 32 位哈希值去重，**语义完全等价**，
只是 `set` 明显更省内存（几百万节点大约几百 MB，而不是一上来就占 512 MB）。
如果将来发现内存或速度不够，可以按原版思路换回位图。

## 已知限制

- **性能**：纯 Python，实测大约 **每秒 2 万节点**。
  用原版的 200 万节点上限换算过来，跑满一次大概要 100 秒。规模一大就偏慢，
  适合出题时后台跑，不适合界面上即时响应。
- **single 玩法不是最优**：这是原算法本身的限制，不是移植引入的。

## 实测结论（重要）

用本移植版扫了一遍参数，结果对出题器的设计影响很大。
测试条件：容量 10，每种颜色 10 颗，`single` 玩法，随机生成局面。

| 配置 | 结果 | 生成节点 | 用时 |
| --- | --- | --- | --- |
| 4 色 + 7 根柱子（1 空柱） | 30 个局面里只有 2 个有解 | 平均 127 | 0.1s |
| 5 色 + 7 根柱子（1 空柱） | 30 个局面里只有 2 个有解 | 平均 160 | 0.1s |
| 6 色 + 7 根柱子（1 空柱） | **30 个局面里 0 个有解** | 平均 116 | 0.1s |
| 4 色 + 8 根柱子（2 空柱） | 有解 | 54,832 | 1.9s |
| 5 色 + 8 根柱子（2 空柱） | 有解 | 245,746 | 9.9s |
| 6 色 + 8 根柱子（2 空柱） | 有解 | 436,121 | 23.5s |

原因：当柱子容量**正好等于**每种颜色的颗数时，开局每种颜色都装满一根柱子，
所有柱子都是满的。这时唯一能放珠子的地方只有那根空柱，
第二步之后几乎每一步都要求「顶色刚好匹配」，路很快就被堵死。

所以：**空柱只有 1 根时，题目基本出不出来。**
柱子容量等于每色颗数时，空柱至少要有 2 根。
