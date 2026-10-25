#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成程序图标 app.ico（多分辨率：16/24/32/48/64/128/256）。

设计：蓝色渐变圆角方块底 + 白色勾选框和勾，表示“选择题已选中”。
重新生成：python make_icon.py
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ICO_PATH = os.path.join(HERE, "app.ico")
PREVIEW_PATH = os.path.join(HERE, "icon_preview.png")

MASTER = 1024          # 先在大画布上绘制，再缩小抗锯齿
ICO_SIZES = [256, 128, 64, 48, 32, 24, 16]

# 渐变色（上 -> 下）
GRAD_TOP = (47, 168, 248)
GRAD_BOTTOM = (13, 82, 200)
WHITE = (255, 255, 255, 255)


def rounded_gradient_bg(size: int) -> Image.Image:
    """带圆角的垂直渐变背景。"""
    # 1. 先画渐变矩形
    grad = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / (size - 1)
        c = tuple(int(GRAD_TOP[i] + (GRAD_BOTTOM[i] - GRAD_TOP[i]) * t) for i in range(3))
        d.line([(0, y), (size, y)], fill=c)
    # 2. 圆角蒙版
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    radius = int(size * 0.22)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out


def draw_round_line(d: ImageDraw.ImageDraw, points, width: int, fill=WHITE) -> None:
    """带圆头的折线。"""
    d.line(points, fill=fill, width=width, joint="curve")
    r = width / 2
    for x, y in (points[0], points[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def make_master() -> Image.Image:
    img = rounded_gradient_bg(MASTER)
    d = ImageDraw.Draw(img)
    s = MASTER

    # 白色圆角勾选框（描边）
    box_l, box_t, box_r, box_b = int(s * 0.24), int(s * 0.24), int(s * 0.76), int(s * 0.76)
    stroke = int(s * 0.062)
    d.rounded_rectangle(
        [box_l, box_t, box_r, box_b], radius=int(s * 0.115),
        outline=WHITE, width=stroke,
    )

    # 框内大勾
    check_w = int(s * 0.062)
    draw_round_line(
        d,
        [(int(s * 0.345), int(s * 0.515)), (int(s * 0.465), int(s * 0.635)),
         (int(s * 0.675), int(s * 0.375))],
        check_w,
    )
    return img


def main() -> None:
    master = make_master().resize((ICO_SIZES[0], ICO_SIZES[0]), Image.Resampling.LANCZOS)
    master.save(ICO_PATH, format="ICO", sizes=[(x, x) for x in ICO_SIZES])
    master.save(PREVIEW_PATH, format="PNG")
    print("已生成：%s" % ICO_PATH)
    print("预览图：%s" % PREVIEW_PATH)


if __name__ == "__main__":
    main()
