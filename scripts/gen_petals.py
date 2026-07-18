#!/usr/bin/env python3
"""生成标题页动态封面用的花瓣飘落 tile（透明 PNG，1440×2560，可垂直无缝循环）。

用法:
  python3 gen_petals.py --out game/background/title_petals.png [--color "#FFC8D7"] [--count 26]
"""
import argparse
import random

from PIL import Image, ImageDraw

W, H = 1440, 2560


def hex_rgba(hx, alpha):
    hx = hx.lstrip('#')
    return (int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16), alpha)


def gen(out, color='#FFC8D7', count=26, seed=42):
    random.seed(seed)
    tile = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    base = hex_rgba(color, 0)
    for _ in range(count):
        size = random.randint(18, 46)
        p = Image.new('RGBA', (size * 2, size * 2), (0, 0, 0, 0))
        pd = ImageDraw.Draw(p)
        alpha = random.randint(120, 200)
        pd.ellipse([size * 0.3, size * 0.6, size * 1.7, size * 1.5],
                   fill=(base[0], base[1], base[2], alpha))
        pd.ellipse([size * 0.5, size * 0.75, size * 1.3, size * 1.25],
                   fill=(min(255, base[0] + 25), min(255, base[1] + 25), min(255, base[2] + 25), min(255, alpha + 30)))
        p = p.rotate(random.uniform(0, 360), expand=True, resample=Image.BICUBIC)
        tile.paste(p, (int(random.uniform(0, W)), int(random.uniform(0, H))), p)
    tile.save(out)
    print(f'OK: {out}  ({count} 瓣, 主色 {color})')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--color', default='#FFC8D7', help='花瓣主色，随皮肤换')
    ap.add_argument('--count', type=int, default=26)
    ap.add_argument('--seed', type=int, default=42)
    a = ap.parse_args()
    gen(a.out, a.color, a.count, a.seed)


if __name__ == '__main__':
    main()
