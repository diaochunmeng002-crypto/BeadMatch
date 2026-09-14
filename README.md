# BeadMatch

实体玩具（木质底座 + 立柱 + 彩色木珠）的**出题工具**：
家长/老师用它生成一个初始局面，让小孩照着在实物上把珠子摆好，然后开始玩。

软件**不负责解题**——它只负责「出题」和「告诉人怎么摆」。

## 现在能干什么

- **离线出题**：从已解局面随机乱走 N 步，交给求解器算步数 → 定难度等级 → 存进题库
  （已经有 **409 道题**：2 级 54、3 级 245、4 级 92、5 级 18）
- **网页玩**：按等级随机抽一道 → 画成一根根柱子 → **点柱子把颜色读出来**（可选语音）
  → 「演示解法」一步步把球飞过去（带落珠声）

## 快速开始

```bash
python -m server.app        # 起服务
```

然后浏览器打开 <http://127.0.0.1:8000>。其它命令（出题、跑测试）见 [docs/how_to_start.md](docs/how_to_start.md)。

## 文档在哪

| 文件 | 内容 |
| --- | --- |
| [docs/requirement.md](docs/requirement.md) | **唯一的需求文档**：规则、参数、数据格式、后端接口、前端形态、待确认项 |
| [docs/how_to_start.md](docs/how_to_start.md) | 启动 / 出题 / 跑测试的命令 |
| [docs/discussion-2026-09.md](docs/discussion-2026-09.md) | 9/11–9/14 的讨论流水（**仅作追溯**，结论已并入需求文档） |
| [docs/solver_research.md](docs/solver_research.md) | 外部求解器 / 出题器 / 理论调研（注意：那些求解器都是「旧规则」） |

## 目录结构

```
BeadMatch/
├─ generator.py         出题器：generate / render_board / parse_board / load_board / save_board
├─ make_puzzles.py      批量出题，写进题库 + index.csv
├─ test_generator.py
├─ docs/                需求 / 启动命令 / 讨论流水 / 调研
├─ puzzles/             题库：<level>/<id>.txt + index.csv
├─ server/              FastAPI 后端（app.py + test_app.py）
├─ solver/
│  ├─ free_solver.py      按本项目规则写的求解器（DFS + 启发式）
│  ├─ free_solver.py      按本项目规则求解（DFS + 启发式），只作兜底
│  └─ test_*.py
├─ walk_gen.py          出题算法：引导式走法 + 反走即解（不需要求解器）
├─ web/                 前端（原生 JS，三个文件，不用构建）
└─ vendor/kociemba/     已删除的旧求解器的原版源码存档（**不随仓库分发**，只作本机对照）
```

## 只有一套规则

一次挪一颗，**落点只要有空位就能放**（不要求同色）。细节见 [docs/requirement.md](docs/requirement.md) §2。

> 2026-09-14 之前，仓库里还有一个 Kociemba 的 Python 移植（商业球排序那套"只能放空柱或同色柱顶"
> 的规则），当时用来算难度/找短解，现在**已删除**——原因和经过见
> [docs/requirement.md](docs/requirement.md) §8.2 与 [docs/solver_research.md](docs/solver_research.md)。
