# BeadMatch

实体玩具（木质底座 + 立柱 + 彩色木珠）的**出题工具**：
家长/老师用它生成一个初始局面，让小孩照着在实物上把珠子摆好，然后开始玩。

软件**不负责解题**——它只负责「出题」和「告诉人怎么摆」。

> 项目正在长成「一个程序装多个游戏的**游戏广场**」，串珠是第一个游戏。
> 那一层的规划（文件怎么组织、以后怎么加游戏）见 [docs/plaza.md](docs/plaza.md)。

## 现在能干什么

- **离线出题**：从已解局面按规则随机乱走 N 步 → **反走即解**（不需要求解器），
  难度 = 解的长度 ÷ 10 向上取整 → 存进题库
  （现在有 **300 道题**：1~10 级各 20 道、11~20 级各 10 道）
- **网页玩**：按等级随机抽一道 → 画成一根根柱子 → **点柱子把颜色由下往上读出来**（语音常开）
  → 「演示解法」一步步把球飞过去（带落珠声）

## 快速开始

```bash
python run.py        # 起服务
```

然后浏览器打开 <http://127.0.0.1:8000>。其它命令（出题、跑测试）见 [docs/how_to_start.md](docs/how_to_start.md)。

## 文档在哪

| 文件 | 内容 |
| --- | --- |
| [docs/plaza.md](docs/plaza.md) | **广场总览**：项目怎么从"一个游戏"长成"多个游戏的广场"，文件怎么组织（尚未动代码） |
| [docs/requirement.md](docs/requirement.md) | **串珠游戏的需求文档**：规则、参数、数据格式、后端接口、前端形态、待确认项 |
| [docs/how_to_start.md](docs/how_to_start.md) | 启动 / 出题 / 跑测试的命令 |
| [docs/discussion-2026-09.md](docs/discussion-2026-09.md) | 9/11–9/14 的讨论流水（**仅作追溯**，结论已并入需求文档） |
| [docs/solver_research.md](docs/solver_research.md) | 外部求解器 / 出题器 / 理论调研（注意：那些求解器都是「旧规则」） |

## 目录结构

```
BeadMatch/
├─ run.py               唯一入口：起服务
├─ games/               游戏都在这儿，一个游戏一个文件夹
│  └─ beadmatch/        串珠（认知分类：规划）
│     ├─ core/          纯逻辑：出题算法 + 题库读写/校验 + 兜底求解器
│     ├─ api.py         FastAPI 后端
│     ├─ web/           前端（原生 JS，三个文件，不用构建）
│     ├─ puzzles/       题库：<level>/<id>.txt
│     ├─ tools/         批量出题等离线工具
│     └─ tests/
├─ start/               怎么跑、怎么发：桌面启动器 / 打包脚本 / 图标
└─ docs/                广场规划 / 需求 / 启动命令 / 讨论流水 / 调研
```

## 只有一套规则

一次挪一颗，**落点只要有空位就能放**（不要求同色）。细节见 [docs/requirement.md](docs/requirement.md) §2。

> 2026-09-14 之前，仓库里还有一个 Kociemba 的 Python 移植（商业球排序那套"只能放空柱或同色柱顶"
> 的规则），当时用来算难度/找短解，现在**已删除**——原因和经过见
> [docs/requirement.md](docs/requirement.md) §8.2 与 [docs/solver_research.md](docs/solver_research.md)。
