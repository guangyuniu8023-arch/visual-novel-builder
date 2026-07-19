#!/usr/bin/env python3
"""check_assets.py — 资产核对：剧本引用 vs 实际文件 vs manifest vs 原创性

校验:
  1. 剧本中 changeBg/changeFigure/bgm/miniAvatar/playEffect/playVideo 引用的文件存在
  2. figure/ 下的 PNG 必须带透明通道（立绘硬性要求）
  3. manifest.json 中 pending 列表应为空（有遗留待生成资产则报错）
  4. 粒子 tile 契约：background/title_particles.png 必须存在、不得与引擎旧默认件
     md5 相同；background/ 下出现 title_*.png 别名定制 tile（title_main/title_particles
     以外）= 命名错误（引擎挂载点只认 title_particles.png，别名永远不会生效）
  5. 跨项目资产碰撞：game/ 下的图片/音频与同级其他项目（projects/*）md5 撞车
     即报错——不同游戏不得复用同一张背景/立绘（v8.3 教训：两项目共用雨夜街景）

用法:
  python3 check_assets.py <game目录> <manifest.json路径>
退出码: 0=通过 1=存在问题
"""
import hashlib
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

# 引擎旧默认粒子 tile（白色光斑）的 md5——已删除，撞此 hash = 沿用默认件
DEFAULT_TILE_MD5 = {"a5d1b2a8a2502a03d51c100e210076ea"}
# tile 合法文件名（引擎挂载点）
TILE_NAME = "title_particles.png"
IMG_AUDIO_EXT = {".png", ".jpg", ".jpeg", ".webp", ".mp3", ".ogg", ".wav"}


def md5_of(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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

    # 4. 粒子 tile 契约
    bg_dir = os.path.join(game_dir, "background")
    if os.path.isdir(bg_dir):
        tile = os.path.join(bg_dir, TILE_NAME)
        if not os.path.exists(tile):
            problems.append(f"缺少 background/{TILE_NAME}（粒子 tile 必须项目自产，"
                            f"tools: gen_particles.py / gen_image.py）")
        elif md5_of(tile) in DEFAULT_TILE_MD5:
            problems.append(f"background/{TILE_NAME} 与引擎旧默认光斑 tile 相同，"
                            f"必须按本项目主题推导自产")
        for f in sorted(os.listdir(bg_dir)):
            if (f.startswith("title_") and f.endswith(".png")
                    and f not in (TILE_NAME,) and not f.startswith("title_main")):
                problems.append(f"background/{f} 疑似定制粒子 tile 但命名错误——引擎"
                                f"挂载点只认 {TILE_NAME}，别名永远不会生效（改名或删除）")

    # 5. 跨项目资产碰撞（game/ 位于 projects/<id>/game 结构时启用）
    # 背景/BGM 撞车=ERROR（必须项目自产）；立绘撞车=WARN（同角色跨游戏复用是
    # 一致性需求，合法，但打印出来让 agent 与用户明确知情）。
    # 例外：同 IP 双版本（自由/孤独版这类"同一故事两种呈现"）共用背景合法——
    # 项目根放 `.asset_share_allow`（每行一个允许共用的兄弟项目 id）声明豁免，
    # 未声明即撞车 = 复用偷懒，ERROR。
    proj_dir = os.path.dirname(os.path.abspath(game_dir.rstrip("/")))
    projects_root = os.path.dirname(proj_dir)
    proj_id = os.path.basename(proj_dir)
    allow_path = os.path.join(proj_dir, ".asset_share_allow")
    allow = set()
    if os.path.exists(allow_path):
        with open(allow_path, encoding="utf-8") as f:
            allow = {ln.strip() for ln in f if ln.strip() and not ln.startswith("#")}
    warns = []
    if os.path.isdir(projects_root):
        own = {}
        for sub in ("background", "figure", "bgm"):
            d = os.path.join(game_dir, sub)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if os.path.splitext(f)[1].lower() in IMG_AUDIO_EXT:
                    p = os.path.join(d, f)
                    own[md5_of(p)] = f"{sub}/{f}"
        for sibling in sorted(os.listdir(projects_root)):
            sib_game = os.path.join(projects_root, sibling, "game")
            if sibling == proj_id or sibling in allow or not os.path.isdir(sib_game):
                continue
            for sub in ("background", "figure", "bgm"):
                d = os.path.join(sib_game, sub)
                if not os.path.isdir(d):
                    continue
                for f in sorted(os.listdir(d)):
                    if os.path.splitext(f)[1].lower() not in IMG_AUDIO_EXT:
                        continue
                    h = md5_of(os.path.join(d, f))
                    if h in own:
                        msg = (f"跨项目资产复用: {own[h]} 与项目 "
                               f"{sibling}/{sub}/{f} 完全相同（md5 碰撞）")
                        if sub == "figure":
                            warns.append(msg + "（同角色复用属一致性，确认有意为之即可）")
                        else:
                            problems.append(msg + "，不同游戏不得复用同一张背景/同一段音频")

    for p in problems:
        print(f"ERROR: {p}")
    for w in warns:
        print(f"WARN: {w}")
    print(f"\n核对汇总: 引用 {len(refs)} 处, 问题 {len(problems)} 个")
    if not problems:
        print("PASS: 资产核对通过")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
