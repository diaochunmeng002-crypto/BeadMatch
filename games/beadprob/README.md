# 彩珠机会屋（BeadProb）

用袋子里的彩珠理解“可能、机会大小、随机波动和不放回”。屏幕负责出题、写出摸珠动作，
孩子在线下用实物摸珠、比较并口头回答，需要时再点「看答案」查看结论和解释。

## 题库

共 **9 个难度，每档 20 道，共 180 道**：

| 难度 | 名称 | 核心理解 | 线下操作 |
| --- | --- | --- | --- |
| 1 | 可能性 | 可能、不可能、一定 | 摸 3 颗，每次放回 |
| 2 | 单袋比较 | 同袋里颜色更多通常更容易摸到 | 摸 5 次，每次放回 |
| 3 | 两袋比较 | 总数相同时，比较目标颜色颗数 | 两袋轮流摸 5 次 |
| 4 | 比例陷阱 | 目标珠更多，不代表占比更大 | 先猜，再各摸 5 次 |
| 5 | 相同机会 | 占比相同就是一样容易，单组结果可能不同 | 各摸 5 次，比较结果 |
| 6 | 三颗赛跑 | 摸珠比赛会受随机结果影响，单轮不决定袋子的机会 | 同色计分珠推进三格，先到 3 颗赢一轮 |
| 7 | 放回与随机 | 放回摇匀后，之前摸到什么不影响下一次 | 照着已有记录再摸一颗 |
| 8 | 多试几次 | 更多累计记录通常更接近袋里的比例 | 先摸 8～12 次，再累计到 24～30 次 |
| 9 | 不放回 | 拿出珠子后，下一次机会会改变 | 依次拿出指定珠子，再摸下一颗 |

所有普通摸珠都遵循同一个动作：

> 摸一颗、看一眼、放回袋子、摇 3 下。

L6 用实际比赛跨过“比较机会”到“看结果”的坎；L7 明确使用已有记录，但仍要求每次放回；
L9 是唯一“不放回”的难度，题面会单独写清。

## 启动

```powershell
python run.py
```

然后打开 <http://127.0.0.1:8000/games/beadprob/>。也可以单独跑：

```powershell
python -m games.beadprob.api    # 8070
```

页面没有可点答案、自动判分或逐次记录。选择题由孩子在线下口头完成，点「看答案」后才显示答案和解释。

## 重新出题

```powershell
python -m games.beadprob.tools.make_puzzles --fresh
```

出题器会重新生成 180 道，生成后立即执行整套题库检查。每档都要求 20 个与颜色名字无关的结构，
不能靠“同一道题换个颜色”凑数。

## 题卡格式

题卡放 `puzzles/<等级>/<id>.txt`，一行一个 `键=值`。例如：

```text
created_at=2026-10-24
created_by=beadprob
generator=make_puzzles@1
id=20261024-132200-0029
level=3
title=红珠去哪只袋子？
story=两只袋子里的珠子总数一样，颜色组成不同。
kind=compare
target=R
question=从哪只袋子更容易摸到红珠？
action=两只袋子轮流摸 5 次，每次放回并摇匀。
bag=左边的袋子|R:1 G:6
bag=右边的袋子|R:3 G:4
answer=right
hint=总数一样时，比一比目标颜色各有几颗。
explain=两只袋子都有 7 颗珠子；左边有 1 颗红珠，右边有 3 颗；右边的袋子目标珠更多，所以机会更大。
```

不同难度使用不同 `kind`：

- L1 `outcome`：`ask=may` / `ask=certain`，答案是 `yes` / `no`
- L2 `most`：答案是一种颜色字母
- L3～L5 `compare`：答案是 `left` / `right` / `same`
- L6 `race`：`ask=majority/even/upset/rounds`；不写固定 `answer=`，赢家由现场摸出来
- L7 `independence`：用 `prior=` 记已有结果，答案是 `same`
- L8 `convergence`：用 `first=` / `total=` 记两个累计节点，答案是 `later`
- L9 `without`：用 `removed=` 记拿出的珠子，答案是 `larger` / `smaller` / `same`

答案不是手写的唯一依据。检查器会根据袋内颗数、已有结果和拿出顺序重新计算并核对。

## 检查

```powershell
python -m games.beadprob.core.cards --list
python -m games.beadprob.core.cards --show <题卡文件>
python -m unittest games.beadprob.tests.test_cards games.beadprob.tests.test_app
```

检查范围包括：字段、文件名与 id、等级目录、答案、每档结构和比例条件、每题是否有摸珠动作，
以及两只袋子同时摆出来时每种颜色合计不超过实物上限 10 颗。
