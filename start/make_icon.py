"""生成程序图标 beadmatch.ico（顺带存一张 PNG 预览）。

画法：深色圆角方块 + 一根白色立柱 + 串在柱子上的 4 颗彩珠 —— 就是游戏里的一根珠子柱。
配色跟网页里的一致（Y/G/R/P/B/O 六个球色，这里取前四个保证在小尺寸下也看得清）。

想改配色/颗数就改下面的常量，然后重跑：python start/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent     # start\
OUT_ICO = HERE / "beadmatch.ico"
OUT_PNG = HERE / "beadmatch.png"
SIZE = 256          # 最终图标尺寸
SS = 4              # 超采样倍数（先画大再缩小，边缘更顺滑）

INK = (51, 49, 46, 255)          # 底色：跟网页的 --ink 一致
PEG = (250, 249, 247, 255)       # 立柱：跟网页背景色一致
BALLS = [                        # 从下往上
    (242, 194, 49, 255),         # 黄 Y
    (76, 175, 80, 255),          # 绿 G
    (229, 72, 77, 255),          # 红 R
    (59, 130, 246, 255),         # 蓝 B
]


def draw() -> Image.Image:
    w = SIZE * SS
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角方底
    d.rounded_rectangle([0, 0, w - 1, w - 1], radius=int(w * 0.22), fill=INK)

    # 立柱（细长白棒）
    peg_w = int(w * 0.085)
    peg_x = w // 2 - peg_w // 2
    d.rounded_rectangle(
        [peg_x, int(w * 0.13), peg_x + peg_w, int(w * 0.87)],
        radius=peg_w // 2, fill=PEG,
    )

    # 珠子：自下而上串上去，稍微压住立柱
    n = len(BALLS)
    gap = int(w * 0.012)
    bead = int((w * 0.74 - gap * (n - 1)) / n)
    top = int(w * 0.13)
    for i, color in enumerate(BALLS):
        y = top + i * (bead + gap)
        x = w // 2 - bead // 2
        d.ellipse([x, y, x + bead, y + bead], fill=color)
        # 一点高光，看起来像球
        hl = int(bead * 0.26)
        d.ellipse(
            [x + int(bead * 0.22), y + int(bead * 0.18),
             x + int(bead * 0.22) + hl, y + int(bead * 0.18) + hl],
            fill=(255, 255, 255, 90),
        )

    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> int:
    icon = draw()
    icon.save(OUT_PNG)
    icon.save(OUT_ICO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                              (64, 64), (128, 128), (256, 256)])
    print("已生成 %s 和 %s" % (OUT_ICO, OUT_PNG))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
