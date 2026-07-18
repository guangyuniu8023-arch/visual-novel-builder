#!/usr/bin/env python3
"""trim_asset.py — 生成资产后处理（裁剪水印 / 转格式 / 封面瘦身）

生图模型出图底部普遍带水印条（60~130px 不等，4K 竖图按 130px 裁最稳），
且引擎装配要求 jpg。此脚本把这两步固化，避免每个项目手写 PIL。

用法:
  # 批量处理整个目录（背景/CG：裁水印 + 转 jpg）
  python3 trim_asset.py assets_raw/*.png --crop 130 --to jpg --out-dir game/background

  # 封面底图：裁水印 + 瘦身（2160 宽缩到 1440，质量 85，体积 ~1MB→~350KB，
  # 避免结局返回标题页时封面解码 1s+ 露出备份背景灰块）
  python3 trim_asset.py cover_raw.png --crop 130 --to jpg --cover --out-dir game/background

  # 只裁不转（立绘已抠透明时用，保持 png）
  python3 trim_asset.py ls_smile.png --crop 60

经验值（4K 9:16 = 2160×3840）:
  背景/CG 130px；立绘绿幕图 60px（水印小），若仍有残留再补到 130px。
"""
import argparse
import os
import sys


def process(path: str, crop: int, to: str, out_dir: str, cover: bool,
            quality: int) -> str:
    from PIL import Image
    img = Image.open(path)
    w, h = img.size
    # 水印条高度随图高缩放（以 3840 高为基准的 130px）
    c = min(round(crop * h / 3840), h // 8)
    if c > 0:
        img = img.crop((0, 0, w, h - c))
    if cover and img.width > 1440:
        img = img.resize((1440, round(img.height * 1440 / img.width)),
                         Image.LANCZOS)
    base = os.path.splitext(os.path.basename(path))[0]
    os.makedirs(out_dir or os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if to == "jpg":
        final = os.path.join(out_dir or ".", base + ".jpg")
        img.convert("RGB").save(final, quality=quality)
    else:
        final = os.path.join(out_dir or ".", base + ".png")
        img.save(final)
    return final


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--crop", type=int, default=130,
                    help="底部水印裁剪像素（按 3840 高缩放，默认 130）")
    ap.add_argument("--to", choices=["jpg", "png"], default="jpg")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--cover", action="store_true",
                    help="封面瘦身：宽度>1440 缩到 1440（返回标题页防灰块）")
    ap.add_argument("--quality", type=int, default=90)
    args = ap.parse_args()

    for p in args.inputs:
        if not os.path.exists(p):
            print(f"MISS: {p}")
            continue
        if args.cover:
            args.quality = min(args.quality, 85)
        final = process(p, args.crop, args.to, args.out_dir, args.cover,
                        args.quality)
        size_kb = os.path.getsize(final) // 1024
        print(f"OK: {final} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
