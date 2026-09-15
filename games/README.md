# games —— 游戏都放这儿

一个游戏一个文件夹，文件夹名 = **游戏 id**（小写英文，比如 `beadmatch`）。每个游戏自带：
`core/`（纯逻辑）、`api.py`（后端接口）、`web/`（页面）、`puzzles/`（题库）、`tests/`。

- 广场靠 **`game.toml`** 发现游戏：没有这个文件的文件夹**对广场是隐形的**（不会被列到首页）。
- `group/ sort/ space/ plan/ logic/ memory/` 是**按认知分类先建的占位**
  （README 用英文，一两行说明这类游戏是什么）。真做某个游戏时，建 `games/<游戏英文名>/`，
  把分类写进它的 `game.toml`（例如 `category = "memory"`）。
- 广场的整体规划见 [../docs/plaza.md](../docs/plaza.md)。
