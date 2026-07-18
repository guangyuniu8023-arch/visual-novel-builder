#!/usr/bin/env python3
"""生成标题页动态封面的粒子飘落 tile（透明 PNG，1440×2560，垂直无缝循环）。

粒子类型按题材配方选：
  petals  花瓣（恋爱/治愈，粉色椭圆）
  rain    雨滴（悬疑/黑暗，细长斜线，配快速下落动画）
  motes   光尘（奇幻/科幻，发光小圆点，配缓慢上浮动画）
  snow    雪（冬日/治愈，白色小圆点）
  fog     雾气（黑暗/悬疑，大片低透明椭圆，配超慢横移动画）

用法:
  python3 gen_particles.py --out game/background/title_particles.png \\
      --type rain --color "#A8C8E8" [--count 26]
"""
import argparse
import random

from PIL import Image, ImageDraw, ImageFilter

W, H = 1440, 2560


def hex_rgb(hx):
    hx = hx.lstrip('#')
    return (int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16))


def petal(tile, x, y, size, angle, alpha, rgb):
    p = Image.new('RGBA', (size * 2, size * 2), (0, 0, 0, 0))
    pd = ImageDraw.Draw(p)
    pd.ellipse([size * 0.3, size * 0.6, size * 1.7, size * 1.5], fill=(*rgb, alpha))
    pd.ellipse([size * 0.5, size * 0.75, size * 1.3, size * 1.25],
               fill=(min(255, rgb[0] + 25), min(255, rgb[1] + 25), min(255, rgb[2] + 25), min(255, alpha + 30)))
    p = p.rotate(angle, expand=True, resample=Image.BICUBIC)
    tile.paste(p, (x, y), p)


def rain(tile, x, y, size, angle, alpha, rgb):
    """细长斜线雨滴：size 为长度"""
    w = max(3, size // 14)
    p = Image.new('RGBA', (w * 4, size), (0, 0, 0, 0))
    pd = ImageDraw.Draw(p)
    pd.line([(w * 2, 0), (w * 2, size)], fill=(*rgb, alpha), width=w)
    p = p.rotate(angle, expand=True, resample=Image.BICUBIC)
    tile.paste(p, (x, y), p)


def motes(tile, x, y, size, angle, alpha, rgb):
    """发光圆点：实心核 + 光晕"""
    p = Image.new('RGBA', (size * 4, size * 4), (0, 0, 0, 0))
    pd = ImageDraw.Draw(p)
    pd.ellipse([size, size, size * 3, size * 3], fill=(*rgb, alpha // 3))
    pd.ellipse([int(size * 1.5), int(size * 1.5), int(size * 2.5), int(size * 2.5)], fill=(*rgb, alpha))
    p = p.filter(ImageFilter.GaussianBlur(size // 3))
    tile.paste(p, (x, y), p)


def snow(tile, x, y, size, angle, alpha, rgb):
    p = Image.new('RGBA', (size * 2, size * 2), (0, 0, 0, 0))
    pd = ImageDraw.Draw(p)
    pd.ellipse([size * 0.4, size * 0.4, size * 1.6, size * 1.6], fill=(*rgb, alpha))
    tile.paste(p, (x, y), p)


def fog(tile, x, y, size, angle, alpha, rgb):
    p = Image.new('RGBA', (size * 4, size * 2), (0, 0, 0, 0))
    pd = ImageDraw.Draw(p)
    pd.ellipse([0, size * 0.3, size * 4, size * 1.7], fill=(*rgb, alpha))
    p = p.filter(ImageFilter.GaussianBlur(size // 3))
    tile.paste(p, (x, y), p)


PAINTERS = {
    'petals': (petal, (18, 46), (-40, 40), (120, 200)),
    'rain':   (rain,   (40, 90), (6, 10),  (90, 150)),
    'motes':  (motes,  (5, 12),  (0, 0),    (110, 190)),
    'snow':   (snow,   (8, 20),  (0, 0),    (140, 220)),
    'fog':    (fog,    (60, 120), (0, 0),   (50, 80)),
}


def gen(out, ptype='petals', color='#FFC8D7', count=26, seed=42):
    random.seed(seed)
    rgb = hex_rgb(color)
    painter, (s0, s1), (a0, a1), (al0, al1) = PAINTERS[ptype]
    tile = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for _ in range(count):
        painter(tile,
                int(random.uniform(0, W)), int(random.uniform(0, H)),
                random.randint(s0, s1),
                random.uniform(a0, a1) if a0 != a1 else 0,
                random.randint(al0, al1), rgb)
    tile.save(out)
    print(f'OK: {out}  ({ptype} × {count}, 主色 {color})')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--type', default='petals', choices=list(PAINTERS))
    ap.add_argument('--color', default='#FFC8D7')
    ap.add_argument('--count', type=int, default=26)
    ap.add_argument('--seed', type=int, default=42)
    a = ap.parse_args()
    gen(a.out, a.type, a.color, a.count, a.seed)


if __name__ == '__main__':
    main()
