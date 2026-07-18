#!/usr/bin/env python3
"""把游戏标题排版烘焙进标题页封面图（WebGAL 标题页不渲染文字标题，必须写进图里）。

设计感排版 = 主标题（大字/描边/投影）+ 英文副标（letterspacing + 上下装饰线）+ 可选 tagline。
标题必须像一个"游戏名"：2-6 字短词、有记忆钩子（来自角色台词/核心设定），禁止用一句口语长句。

用法:
  python3 bake_title.py <封面图> <主标题> [-o 输出] [--eng TEXT] [--tagline TEXT] \\
      [--y 0.12] [--stroke "#5B8DC9"] [--size 0.14]

示例:
  python3 bake_title.py title_main.jpg "差你两分" --eng "TWO POINTS AHEAD" \\
      --tagline "这一次，换我追你" --stroke "#5B8DC9"
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT = os.path.join(
    os.path.dirname(__file__), '..', 'assets', 'engine', 'assets',
    'ResourceHanRoundedCN-Regular-C1HdCLVq.ttf',
)


def text_w(draw, text, font, stroke_width=0, tracking=0):
    """含字距的文本宽度"""
    w = 0
    for ch in text:
        bbox = draw.textbbox((0, 0), ch, font=font, stroke_width=stroke_width)
        w += bbox[2] - bbox[0] + tracking
    return w - tracking if text else 0


def draw_tracked(draw, xy, text, font, fill, tracking=0, stroke_width=0, stroke_fill=None):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill,
                  stroke_width=stroke_width, stroke_fill=stroke_fill)
        bbox = draw.textbbox((0, 0), ch, font=font, stroke_width=stroke_width)
        x += bbox[2] - bbox[0] + tracking


def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def shadow_from_stroke(stroke):
    """投影色从描边色派生：取描边 22% 亮度的深色版本，保证投影与主题同色相。
    （旧版写死 (30,45,70) 暗蓝，琥珀/粉色主题下投影色偏色）"""
    r, g, b = hex_to_rgb(stroke)
    return (int(r * 0.22), int(g * 0.22), int(b * 0.22))


def bake(bg_path, title, out_path, eng=None, tagline=None, y_ratio=0.12,
         size_ratio=0.14, fill='#FFFFFF', stroke='#5B8DC9', font_path=None,
         shadow=None):
    img = Image.open(bg_path).convert('RGB')
    w, h = img.size
    fp = font_path or DEFAULT_FONT
    if not os.path.exists(fp):
        sys.exit(f'字体不存在: {fp}（用 --font 指定）')

    shadow_color = hex_to_rgb(shadow) if shadow else shadow_from_stroke(stroke)

    draw = ImageDraw.Draw(img)
    y = int(h * y_ratio)

    # ---- 主标题 ----
    fsize = int(w * size_ratio)
    fsize = max(48, min(fsize, int(h * 0.11)))
    font = ImageFont.truetype(fp, fsize)
    sw = max(3, fsize // 16)
    tracking = int(fsize * 0.08)
    tw = text_w(draw, title, font, sw, tracking)
    x = (w - tw) // 2
    # 投影
    off = max(3, fsize // 20)
    draw_tracked(draw, (x + off, y + off), title, font, shadow_color, tracking, sw, shadow_color)
    # 描边白字
    draw_tracked(draw, (x, y), title, font, fill, tracking, sw, stroke)
    y += int(fsize * 1.45)

    # ---- 英文副标（上下装饰线） ----
    if eng:
        esize = int(fsize * 0.22)
        efont = ImageFont.truetype(fp, esize)
        etrack = int(esize * 0.55)
        ew = text_w(draw, eng, efont, 0, etrack)
        line_w = int(ew * 0.55)
        gap = int(esize * 0.9)
        total_w = line_w * 2 + ew + gap * 2
        lx = (w - total_w) // 2
        ly = y + esize // 2
        line_color = (255, 255, 255)
        draw.line([(lx, ly), (lx + line_w, ly)], fill=line_color, width=max(2, esize // 12))
        draw.line([(lx + line_w + ew + gap * 2, ly), (lx + total_w, ly)], fill=line_color, width=max(2, esize // 12))
        draw_tracked(draw, (lx + line_w + gap, y), eng, efont, fill, etrack)
        y += int(esize * 2.6)

    # ---- tagline ----
    if tagline:
        if len(tagline) > 14:
            print(f'警告: tagline {len(tagline)} 字超过 14 字，可能溢出画面边缘，建议精简')
        tsize = int(fsize * 0.30)
        tfont = ImageFont.truetype(fp, tsize)
        ttrack = int(tsize * 0.30)
        tsw = max(2, tsize // 14)
        tw2 = text_w(draw, tagline, tfont, tsw, ttrack)
        tx = (w - tw2) // 2
        draw_tracked(draw, (tx + 2, y + 2), tagline, tfont, shadow_color, ttrack, tsw, shadow_color)
        draw_tracked(draw, (tx, y), tagline, tfont, fill, ttrack, tsw, stroke)

    # 封面瘦身：>1440 宽缩到 1440（解码成本 8MP→3.6MP），progressive JPEG
    # 让浏览器先出模糊全图再渐清——避免结局返回标题页时封面解码 1s+，
    # 露出备份背景/部分绘制的灰色块（引擎 React 封面层 remount 的固有间隙）
    if w > 1440:
        img = img.resize((1440, round(h * 1440 / w)), Image.LANCZOS)
        w, h = img.size
    img.save(out_path, quality=85, progressive=True)
    print(f'OK: {out_path}  ({w}x{h}, 主标题{fsize}px "{title}")')


def shrink_only(bg_path, out_path):
    """纯瘦身模式（--shrink-only）：不排版，只做缩放 + progressive 保存。
    封面直出流程（标题由生图模型画进底图）的入库瘦身步骤。"""
    img = Image.open(bg_path).convert('RGB')
    w, h = img.size
    if w > 1440:
        img = img.resize((1440, round(h * 1440 / w)), Image.LANCZOS)
        w, h = img.size
    img.save(out_path, quality=85, progressive=True)
    print(f'OK: {out_path}  ({w}x{h}, shrink-only)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('background')
    ap.add_argument('title', nargs='?', default=None,
                    help='主标题文字；--shrink-only 时可省略')
    ap.add_argument('--shrink-only', action='store_true',
                    help='不排版，只做缩放+progressive 瘦身（封面直出流程用）')
    ap.add_argument('-o', '--output', help='默认原地覆盖')
    ap.add_argument('--eng', default=None, help='英文副标题（自动加装饰线与宽字距）')
    ap.add_argument('--tagline', default=None, help='一句中文宣传语')
    ap.add_argument('--y', type=float, default=0.12, help='标题块顶部位置（高度比例）')
    ap.add_argument('--size', type=float, default=0.14, help='主标题字号（宽度比例）')
    ap.add_argument('--fill', default='#FFFFFF')
    ap.add_argument('--stroke', default='#5B8DC9', help='描边色，取皮肤主色')
    ap.add_argument('--shadow', default=None, help='投影色（缺省从描边色派生同色相深色）')
    ap.add_argument('--font', default=None)
    a = ap.parse_args()
    if a.shrink_only:
        shrink_only(a.background, a.output or a.background)
        return
    if not a.title:
        ap.error('缺少主标题文字（或使用 --shrink-only）')
    bake(a.background, a.title, a.output or a.background, a.eng, a.tagline,
         a.y, a.size, a.fill, a.stroke, a.font, a.shadow)


if __name__ == '__main__':
    main()
