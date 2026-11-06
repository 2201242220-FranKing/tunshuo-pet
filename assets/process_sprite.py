#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说桌宠资源处理：纯白底 -> 去背景 -> 共享裁剪 -> 输出常规帧/眨眼帧。"""

import os
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OPEN_PNG = os.path.join(HERE, "Keep_this_exact_character_desi_2026-11-06T05-00-17.png")
BLINK_PNG = os.path.join(HERE, "Keep_this_exact_blue_plush_wha_2026-11-06T05-00-50.png")
TARGET_W = 240          # 2x 素材，实际显示约 120 逻辑像素


def clean(path):
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    for xy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        if sum(im.getpixel(xy)[:3]) > 720:
            ImageDraw.floodfill(im, xy, (255, 255, 255, 0), thresh=48)
    px = im.load()
    # 逐步削掉贴边的浅白残留，得到干净轮廓（被蓝色包住的脸和肚皮不受影响）
    for _ in range(4):
        kill = []
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if a == 0:
                    continue
                if max(r, g, b) > 240 and (max(r, g, b) - min(r, g, b)) < 12:
                    if ((x > 0 and px[x - 1, y][3] == 0) or
                            (x < w - 1 and px[x + 1, y][3] == 0) or
                            (y > 0 and px[x, y - 1][3] == 0) or
                            (y < h - 1 and px[x, y + 1][3] == 0)):
                        kill.append((x, y))
        for x, y in kill:
            px[x, y] = (0, 0, 0, 0)
        if not kill:
            break
    # 右下角水印兜底清除
    for y in range(int(h * 0.92), h):
        for x in range(int(w * 0.85), w):
            px[x, y] = (0, 0, 0, 0)
    return im


def bleed_colors(im, passes=12):
    """把透明区的 RGB 填成邻近的角色颜色（alpha 仍为 0）。

    纯黑透明的像素在缩放插值时会被混进轮廓，产生一圈黑边；
    先把颜色"渗"出去，任何缩放/旋转都不会再出现黑边。
    """
    rgb = im.convert("RGB")
    alpha = im.getchannel("A")
    transparent = alpha.point(lambda v: 255 if v < 8 else 0)
    for _ in range(passes):
        rgb = Image.composite(rgb.filter(ImageFilter.GaussianBlur(2.0)), rgb, transparent)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def main():
    a, b = clean(OPEN_PNG), clean(BLINK_PNG)
    alpha = a.getchannel("A").point(lambda v: 255 if v > 40 else 0)
    box = alpha.getbbox()
    a2, b2 = bleed_colors(a.crop(box)), bleed_colors(b.crop(box))
    w, h = a2.size
    scale = TARGET_W / w
    size = (TARGET_W, max(1, int(h * scale)))
    bleed_colors(a2.resize(size, Image.LANCZOS), passes=6).save(os.path.join(HERE, "pet.png"))
    bleed_colors(b2.resize(size, Image.LANCZOS), passes=6).save(os.path.join(HERE, "pet_blink.png"))
    print("crop", box, "->", size)


if __name__ == "__main__":
    main()
