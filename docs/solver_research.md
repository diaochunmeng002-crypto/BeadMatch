# 外部求解器与理论调研

> 日期：2026-09-11（2026-09-14 精简）
> 本文只回答一件事：**外面有什么现成的东西可以参考**。
> 本项目的规则、参数、数据格式看 [requirement.md](requirement.md)；讨论过程看
> [discussion-2026-09.md](discussion-2026-09.md)。
>
> ⚠️ **注意**：下面这些求解器（包括我们移植的 `solver/kociemba_solver.py`）实现的是
> **旧规则**——只能把珠子放到空柱或顶色相同的柱子上。
> 本项目**没有这条限制**（见 [requirement.md](requirement.md) §2.2），
> 所以它们的「有解比例」「最优步数」不等于本项目的结论，只在「借它求一条短解」时有用（§8）。

## 结论速览

| 问题 | 结论 |
| --- | --- |
| 有没有现成的**求解器**？ | 有，而且有权威实现（§1），但都是旧规则 |
| 有没有现成的**出题器**？ | 基本没有，得自己写（§2） |
| 「最少挪动步数」能不能直接算？ | 我们的规则下没有现成算法；实测 BFS 也搜不动（见 [requirement.md](requirement.md) §4.4） |
| 理论难度？ | 球排序 / 水排序都是 **NP-完全**（§3） |

---

## 1. 求解器（现成，可参考）

| 仓库 | 语言 | 星 | 方法 / 备注 |
| --- | --- | --- | --- |
| [hkociemba/WaterBallSortPuzzleOptimalSolver](https://github.com/hkociemba/WaterBallSortPuzzleOptimalSolver) | Pascal | 41 | **最权威**。作者是 Kociemba 算法的作者。算法介于 A* 和广度优先之间，用 2³² 位的数组存哈希。支持随机生成局面、编辑、撤销。有 Windows exe |
| [kuking/WaterSortPuzzleSolver](https://github.com/kuking/WaterSortPuzzleSolver) | Go | 24 | 水排序求解 |
| [cemasma/water-sort-puzzle-solver](https://github.com/cemasma/water-sort-puzzle-solver) | Go | 21 | 水排序求解 |
| [pkositsyn/water-sort-puzzle-solver](https://github.com/pkositsyn/water-sort-puzzle-solver) | Go | 18 | 水排序求解 |
| [tanjuntao/water-sort-puzzle](https://github.com/tanjuntao/water-sort-puzzle) | Python | 17 | 中文项目（「水排序」），DFS + BFS |
| [erhosen/ball-sort-puzzle-bot](https://github.com/erhosen/ball-sort-puzzle-bot) | Python | 16 | Telegram 机器人 |
| [tjwood100/ball-sort-puzzle-solver](https://github.com/tjwood100/ball-sort-puzzle-solver) | Python | 14 | 递归 DFS 回溯 + 已访问去重；附随机出题脚本（其 README 注明：随机出的题不保证有解） |
| [teo3fl/WaterSortPuzzleSolver](https://github.com/teo3fl/WaterSortPuzzleSolver) | C# | 12 | 生成并展示解法 |
| [MurielPinho/Ball-Sort-Game-Solver](https://github.com/MurielPinho/Ball-Sort-Game-Solver) | Python | 2 | 同时实现 A\*、BFS、DFS、贪心、一致代价、迭代加深，适合做算法对比 |
| [AntounWagdy/Ball-Sort-Puzzle-Solver](https://github.com/AntounWagdy/Ball-Sort-Puzzle-Solver) | C++ | 6 | 带分析功能 |
| [akcio/ball_sort_puzzle_solver](https://github.com/akcio/ball_sort_puzzle_solver) | JS | 5 | 网页版 |

**Kociemba 的算法说明**（两页，值得读）：

- https://kociemba.org/themen/waterball/algorithm.html
- https://kociemba.org/themen/waterball/algorithm2.html

核心思路：

1. 把局面按「颜色块（block）」计数，已解局面固定是 C 个块。
2. 对**一次倒尽可能多**的玩法（水排序），任何移动都不会让块数增加 →
   可以做二维 BFS：`states[块数减少次数][不减少的步数]`，先填满 `x = B − C` 那一列就是最优解。
3. 对**一次只挪一颗**的玩法（球排序），移动可能让块数增加，算法要做修正（把空柱也当成一个块），
   这样得到的**只是近似最优**。

工程细节：同一局面内的柱子按字典序排序做归一化（消除空柱位置不同导致的重复）；用 2³² 位的哈希表去重。

> 我们的移植版在 [../solver/kociemba_solver.py](../solver/kociemba_solver.py)，
> 用法和在项目里的定位见 [requirement.md](requirement.md) §8。

## 2. 关卡生成器（基本没有现成的）

用「water sort level generator」「sort puzzle level generation」在 GitHub 上搜，命中极少：

| 仓库 | 语言 | 星 | 备注 |
| --- | --- | --- | --- |
| [MeoBeoSiTinh/WaterSortLevelGenerator](https://github.com/MeoBeoSiTinh/WaterSortLevelGenerator) | JS | 0 | 唯一直接命中的生成器，无说明 |
| [oanhere33-maker/water-sort-game-editor](https://github.com/oanhere33-maker/water-sort-game-editor) | TS | 11 | Cocos Creator 关卡**编辑器**，手工编辑 + JSON 导出，不是自动出题 |

**结论：出题这块得自己实现**（我们现在的做法见 [requirement.md](requirement.md) §4）。

---

## 3. 理论背景

**arXiv:2202.09495 — Sorting Balls and Water: Equivalence and Computational Complexity**（Ito、Uehara 等，2022）

https://arxiv.org/abs/2202.09495

摘要要点：

- 球排序与水排序在**可解性上等价**：一个局面能用球式移动解开，当且仅当能用倒水式移动解开。
- 可解的局面，解的长度是**多项式级**的，因此问题属于 **NP**。
- 这两个问题是 **NP-完全**的：判断「能不能解」和求「最短解」都是难问题。
- 论文还给出了「需要多少根空柱才能保证任意局面都可解」的上界和下界。

对我们的意义：**别指望有"最优步数"的现成精确算法**；难度用近似值/上界是合理的选择
（我们现在就是这么做的，见 [requirement.md](requirement.md) §8）。

---

## 4. 参考链接

- Kociemba 算法总览：https://kociemba.org/themen/waterball/colorsort.html
- Kociemba 算法说明（一次倒尽可能多）：https://kociemba.org/themen/waterball/algorithm.html
- Kociemba 算法说明（一次挪一颗）：https://kociemba.org/themen/waterball/algorithm2.html
- 最优求解器源码：https://github.com/hkociemba/WaterBallSortPuzzleOptimalSolver
- NP-完全性论文：https://arxiv.org/abs/2202.09495
