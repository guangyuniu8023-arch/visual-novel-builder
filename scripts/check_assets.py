#!/usr/bin/env python3
"""check_assets.py — 资产核对：剧本引用 vs 实际文件 vs manifest

校验:
  1. 剧本中 changeBg/changeFigure/bgm/miniAvatar/playEffect/playVideo 引用的文件存在
  2. figure/ 下的 PNG 必须带透明通道（立绘硬性要求）
  3. manifest.json 中 pending 列表应为空（有遗留待生成资产则报错）

用法:
  python3 check_assets.py <game目录> <manifest.json路径>
退出码: 0=通过 1=存在问题
"""
import json
import os
import re
import struct
import sys

REF_RULES = [
    (re.compile(r"^changeBg\s*:\s*([^\s;-]+)"), "background"),
    (re.compile(r"^changeFigure\s*:\s*([^\s;-]+)"), "figure"),
    (re.compile(r"^bgm\s*:\s*([^\s;-]+)"), "bgm"),
    (re.compile(r"^miniAvatar\s*:\s*([^\s;-]+)"), "figure"),
    (re.compile(r"^playEffect\s*:\s*([^\s;-]+)"), "bgm"),
    (re.compile(r"^playVideo\s*:\s*([^\s;-]+)"), "video"),
    (re.compile(r"^unlockCg\s*:\s*([^\s;-]+)"), "background"),
    (re.compile(r"^unlockBgm\s*:\s*([^\s;-]+)"), "bgm"),
]

SPECIAL_VALUES = {"none", "delete", "null", ""}


def png_has_alpha(path: str) -> bool:
    """读取 PNG IHDR 的 color type，判断是否有 alpha 通道。"""
    try:
        with open(path, "rb") as f:
            sig = f.read(8)
            if sig != b"\x89PNG\r\n\x1a\n":
                return False
            f.read(4)  # length
            if f.read(4) != b"IHDR":
                return False
            f.read(8)  # width + height
            f.read(1)  # bit depth
            color_type = struct.unpack("B", f.read(1))[0]
            return color_type in (4, 6)  # 4=灰度+alpha, 6=RGBA
    except OSError:
        return False


def main() -> int:
    if len(sys.argv) != 3:
        print("用法: check_assets.py <game目录> <manifest.json路径>")
        return 1
    game_dir, manifest_path = sys.argv[1], sys.argv[2]
    scene_dir = os.path.join(game_dir, "scene")
    problems = []

    refs = []  # (场景文件, 行号, 目录, 文件名)
    if os.path.isdir(scene_dir):
        for fname in sorted(os.listdir(scene_dir)):
            if not fname.endswith(".txt"):
                continue
            with open(os.path.join(scene_dir, fname), encoding="utf-8") as f:
                for i, raw in enumerate(f, 1):
                    line = raw.split("//", 1)[0].strip()
                    for rule, sub in REF_RULES:
                        m = rule.match(line)
                        if m:
                            asset = m.group(1).strip()
                            if asset.lower() not in SPECIAL_VALUES:
                                refs.append((fname, i, sub, asset))

    for fname, i, sub, asset in refs:
        path = os.path.join(game_dir, sub, asset)
        if not os.path.exists(path):
            problems.append(f"缺失: {fname}:{i} 引用了不存在的文件 {sub}/{asset}")

    figure_dir = os.path.join(game_dir, "figure")
    if os.path.isdir(figure_dir):
        for f in sorted(os.listdir(figure_dir)):
            if f.endswith(".png"):
                if not png_has_alpha(os.path.join(figure_dir, f)):
                    problems.append(f"立绘无透明通道: figure/{f}（需按绿幕法重新生成/抠图）")

    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        pending = manifest.get("pending", [])
        if pending:
            problems.append(f"manifest 有 {len(pending)} 项待生成资产: "
                            + ", ".join(str(p)[:40] for p in pending[:5]))

    for p in problems:
        print(f"ERROR: {p}")
    print(f"\n核对汇总: 引用 {len(refs)} 处, 问题 {len(problems)} 个")
    if not problems:
        print("PASS: 资产核对通过")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
