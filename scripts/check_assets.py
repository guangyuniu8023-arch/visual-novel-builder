#!/usr/bin/env python3
"""check_assets.py — 资产核对：剧本引用 vs 实际文件 vs manifest vs 原创性

校验:
  1. 剧本中 changeBg/changeFigure/bgm/miniAvatar/playEffect/playVideo 引用的文件存在
  2. figure/ 下的 PNG 必须带透明通道、1024×1536，人物透明包围盒满足
     thigh_up 近景占幅，manifest prompt 不得诱导全身/腿脚/远景
  3. manifest.json 中 pending 列表应为空（有遗留待生成资产则报错）
  4. 粒子 tile 契约：background/title_particles.png 必须存在、不得与引擎旧默认件
     md5 相同；background/ 下出现 title_*.png 别名定制 tile（title_main/title_particles
     以外）= 命名错误（引擎挂载点只认 title_particles.png，别名永远不会生效）
  5. visual_plan 语义：所有立绘必须登记 dialogue_pose/action；manifest 的姿态、
     道具、动作与允许使用的 beat 必须和 SCRIPT 阶段 figure_catalog 一致
  6. 跨项目资产碰撞：game/ 下的图片/音频与同级其他项目（projects/*）md5 撞车
     即报错——不同游戏不得复用同一张背景/立绘（v8.3 教训：两项目共用雨夜街景）
  7. 结局视频来源：所有 playVideo 引用必须有 Seedance 2.5 manifest 元数据与
     gen_video.py 生成的 succeeded 任务回执；本地合成或手填元数据不得通过

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
import zlib

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
FIGURE_SIZE = (1024, 1536)
FIGURE_MIN_WIDTH_RATIO = 0.60
FIGURE_MAX_WIDTH_RATIO = 0.92
FIGURE_MIN_HEIGHT_RATIO = 0.88
FIGURE_MAX_TOP_RATIO = 0.08
FIGURE_MIN_BOTTOM_RATIO = 0.95
FIGURE_PROMPT_CROP_RE = re.compile(
    r"thigh[- ]?up|cropped at mid[- ]?thigh|cowboy shot|upper body|waist[- ]?up|"
    r"半身|大腿(?:中部)?构图|腰部以上",
    re.IGNORECASE,
)
FIGURE_PROMPT_FORBIDDEN_RE = re.compile(
    r"full[- ]?body|entire figure|distant shot|feet? planted|legs? visible|"
    r"knees? visible|boots? visible|walking|running|stride|"
    r"全身|双腿|膝盖入镜|脚部入镜|迈步|跨步|奔跑|跑向|走向|走进|转身离开",
    re.IGNORECASE,
)
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{5,}$")


def load_required_seedance_config():
    """Read the enforced Seedance family/model from this skill's providers.yaml."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "providers.yaml")
    expected = {"provider": "", "model_family": "", "model": ""}
    if not os.path.exists(path):
        return expected
    in_video = False
    in_seedance = False
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key, _, value = line.strip().partition(":")
        value = value.strip()
        if indent == 0:
            in_video = key == "video"
            in_seedance = False
        elif in_video and indent == 2:
            in_seedance = key == "seedance" and not value
            if key == "provider":
                expected["provider"] = value
        elif in_video and in_seedance and indent >= 4 and key in ("model_family", "model"):
            expected[key] = value
    return expected


def resolve_project_file(project_dir: str, relative: object):
    if not isinstance(relative, str) or not relative.strip() or os.path.isabs(relative):
        return None
    normalized = os.path.normpath(relative)
    if normalized == ".." or normalized.startswith(".." + os.sep):
        return None
    return os.path.join(project_dir, normalized)


def figure_prompt_has_forbidden_framing(prompt: str) -> bool:
    """Reject positive full-body directions while preserving explicit negatives."""
    cleaned = re.sub(r"\bno feet or boots visible\b", "", prompt, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:no|not|without)\s+(?:a\s+)?(?:full[- ]?body|entire figure|distant shot|"
        r"knees?|lower legs?|feet|boots?)(?:\s+(?:shot|visible))?\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"禁止全身|不展示(?:膝盖|小腿|脚|鞋|靴子)|(?:膝盖|小腿|脚|鞋|靴子)不入镜", "", cleaned)
    return bool(FIGURE_PROMPT_FORBIDDEN_RE.search(cleaned))


def md5_of(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def png_metadata(path: str):
    """Return (width, height, has_alpha, alpha_bbox) for common 8-bit PNGs.

    alpha_bbox is (left, top, right, bottom).  Pillow-generated figure PNGs are
    non-interlaced RGBA; unsupported PNG encodings still return dimensions and
    alpha presence, but bbox=None so the caller can reject an unverifiable sprite.
    """
    try:
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return None
            width = height = bit_depth = color_type = interlace = None
            idat = []
            while True:
                raw_len = f.read(4)
                if len(raw_len) != 4:
                    break
                length = struct.unpack(">I", raw_len)[0]
                chunk_type = f.read(4)
                data = f.read(length)
                f.read(4)  # CRC
                if chunk_type == b"IHDR":
                    width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                        ">IIBBBBB", data
                    )
                elif chunk_type == b"IDAT":
                    idat.append(data)
                elif chunk_type == b"IEND":
                    break
        if width is None:
            return None
        has_alpha = color_type in (4, 6)
        if not has_alpha or bit_depth != 8 or interlace != 0 or not idat:
            return width, height, has_alpha, None
        channels = 4 if color_type == 6 else 2
        stride = width * channels
        raw = zlib.decompress(b"".join(idat))
        expected = height * (stride + 1)
        if len(raw) != expected:
            return width, height, has_alpha, None
        prev = bytearray(stride)
        offset = 0
        min_x, min_y, max_x, max_y = width, height, -1, -1
        for y in range(height):
            filter_type = raw[offset]
            offset += 1
            scan = bytearray(raw[offset:offset + stride])
            offset += stride
            if filter_type not in (0, 1, 2, 3, 4):
                return width, height, has_alpha, None
            if filter_type:
                for i in range(stride):
                    left = scan[i - channels] if i >= channels else 0
                    up = prev[i]
                    upper_left = prev[i - channels] if i >= channels else 0
                    if filter_type == 1:
                        predictor = left
                    elif filter_type == 2:
                        predictor = up
                    elif filter_type == 3:
                        predictor = (left + up) // 2
                    else:
                        predictor = _paeth(left, up, upper_left)
                    scan[i] = (scan[i] + predictor) & 0xFF
            alpha_offset = 3 if color_type == 6 else 1
            for x, alpha in enumerate(scan[alpha_offset::channels]):
                if alpha > 8:
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
            prev = scan
        bbox = None if max_x < 0 else (min_x, min_y, max_x + 1, max_y + 1)
        return width, height, has_alpha, bbox
    except (OSError, ValueError, struct.error, zlib.error):
        return None


def png_has_alpha(path: str) -> bool:
    info = png_metadata(path)
    return bool(info and info[2])


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
                info = png_metadata(os.path.join(figure_dir, f))
                if not info or not info[2]:
                    problems.append(f"立绘无透明通道: figure/{f}（需按绿幕法重新生成/抠图）")
                    continue
                width, height, _, bbox = info
                if (width, height) != FIGURE_SIZE:
                    problems.append(
                        f"立绘尺寸错误: figure/{f} 为 {width}×{height}，"
                        f"必须是 {FIGURE_SIZE[0]}×{FIGURE_SIZE[1]}；不得拉伸，需重新生成"
                    )
                if bbox is None:
                    problems.append(f"立绘人物占幅无法解析: figure/{f}（请转为非交错 8-bit RGBA PNG）")
                else:
                    box_w = bbox[2] - bbox[0]
                    box_h = bbox[3] - bbox[1]
                    width_ratio = box_w / width
                    height_ratio = box_h / height
                    if not FIGURE_MIN_WIDTH_RATIO <= width_ratio <= FIGURE_MAX_WIDTH_RATIO:
                        problems.append(
                            f"立绘人物宽度占幅不合格: figure/{f}={width_ratio:.1%}，"
                            f"要求 {FIGURE_MIN_WIDTH_RATIO:.0%}-{FIGURE_MAX_WIDTH_RATIO:.0%}"
                        )
                    if height_ratio < FIGURE_MIN_HEIGHT_RATIO:
                        problems.append(
                            f"立绘人物高度占幅过小: figure/{f}={height_ratio:.1%}，"
                            f"至少 {FIGURE_MIN_HEIGHT_RATIO:.0%}"
                        )
                    if bbox[1] / height > FIGURE_MAX_TOP_RATIO:
                        problems.append(
                            f"立绘头顶留白过多: figure/{f}={bbox[1] / height:.1%}，"
                            f"最多 {FIGURE_MAX_TOP_RATIO:.0%}"
                        )
                    if bbox[3] / height < FIGURE_MIN_BOTTOM_RATIO:
                        problems.append(
                            f"立绘人物下缘过高: figure/{f}={bbox[3] / height:.1%}，"
                            f"应贴近画布底部（至少 {FIGURE_MIN_BOTTOM_RATIO:.0%}）"
                        )

    manifest = {"assets": {}, "pending": []}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        pending = manifest.get("pending", [])
        if pending:
            problems.append(f"manifest 有 {len(pending)} 项待生成资产: "
                            + ", ".join(str(p)[:40] for p in pending[:5]))
    else:
        problems.append(f"manifest 不存在: {manifest_path}")

    # 5. SCRIPT 阶段视觉语义必须被 ASSETS 原样消费，不能生图时把动作含义改掉。
    project_dir = os.path.dirname(os.path.abspath(game_dir.rstrip("/")))
    visual_plan_path = os.path.join(project_dir, "visual_plan.json")
    if not os.path.exists(visual_plan_path):
        problems.append("缺少 visual_plan.json（ASSETS 不得脱离 SCRIPT 视觉计划自由生图）")
        figure_catalog = {}
    else:
        try:
            with open(visual_plan_path, encoding="utf-8") as f:
                visual_plan = json.load(f)
            figure_catalog = visual_plan.get("figure_catalog", {})
            if not isinstance(figure_catalog, dict):
                problems.append("visual_plan.figure_catalog 必须是对象")
                figure_catalog = {}
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"visual_plan.json 无法读取: {exc}")
            figure_catalog = {}

    manifest_assets = manifest.get("assets", {})
    if not isinstance(manifest_assets, dict):
        problems.append("manifest.assets 必须是对象")
        manifest_assets = {}

    # 7. playVideo 不是“有一个 MP4 就算完成”：必须有 gen_video.py 自动落档的
    # Seedance 2.5 provenance 和相互一致的 succeeded 回执。
    required_video = load_required_seedance_config()
    if required_video != {
        "provider": "seedance", "model_family": "seedance-2.5",
        "model": required_video.get("model", ""),
    } or not required_video.get("model"):
        problems.append(
            "tools/providers.yaml 未锁定 video.provider=seedance、"
            "model_family=seedance-2.5 和具体 model endpoint")

    referenced_video_names = {asset for _, _, sub, asset in refs if sub == "video"}
    receipt_match_keys = (
        "provider", "model_family", "model", "task_id", "task_status", "generator",
        "prompt_file", "reference_image", "output",
    )
    for asset in sorted(referenced_video_names):
        manifest_key = f"video/{asset}"
        actual = manifest_assets.get(manifest_key, manifest_assets.get(asset))
        if not isinstance(actual, dict):
            problems.append(f"{manifest_key} 缺少 Seedance 2.5 manifest 来源记录")
            continue
        expected_values = {
            "provider": "seedance",
            "model_family": "seedance-2.5",
            "model": required_video.get("model"),
            "task_status": "succeeded",
            "generator": "scripts/gen_video.py",
            "output": f"game/video/{asset}",
        }
        for key, expected_value in expected_values.items():
            if actual.get(key) != expected_value:
                problems.append(
                    f"{manifest_key} {key}={actual.get(key)!r}，必须为 {expected_value!r}")
        task_id = actual.get("task_id")
        if not isinstance(task_id, str) or not TASK_ID_RE.match(task_id):
            problems.append(f"{manifest_key} 缺少有效 Seedance task_id")
        for field in ("prompt_file", "reference_image"):
            resolved = resolve_project_file(project_dir, actual.get(field))
            if not resolved or not os.path.isfile(resolved):
                problems.append(f"{manifest_key} {field} 必须指向项目内真实文件")
        receipt_path = resolve_project_file(project_dir, actual.get("receipt"))
        if not receipt_path or not os.path.isfile(receipt_path):
            problems.append(f"{manifest_key} 缺少 gen_video.py Seedance 任务回执")
            continue
        try:
            with open(receipt_path, encoding="utf-8") as handle:
                receipt = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{manifest_key} Seedance 回执无法读取: {exc}")
            continue
        if receipt.get("type") != "seedance_video_receipt":
            problems.append(f"{manifest_key} 回执类型不是 seedance_video_receipt")
        for key in receipt_match_keys:
            if receipt.get(key) != actual.get(key):
                problems.append(
                    f"{manifest_key} 回执字段 {key} 与 manifest 不一致: "
                    f"receipt={receipt.get(key)!r}, manifest={actual.get(key)!r}")

    referenced_figure_names = {asset for _, _, sub, asset in refs if sub == "figure"}
    for asset in sorted(referenced_figure_names):
        if asset not in figure_catalog:
            problems.append(f"立绘 figure/{asset} 被剧本引用但未登记 dialogue_pose/action 语义")

    semantic_keys = (
        "framing", "pose", "expression", "gesture", "usage_tags", "props",
        "action", "allowed_beat_ids",
    )
    for asset, expected in sorted(figure_catalog.items()):
        figure_path = os.path.join(game_dir, "figure", asset)
        if not os.path.exists(figure_path):
            problems.append(f"visual_plan 规划的立绘未生成: figure/{asset}")
        manifest_key = f"figure/{asset}"
        actual = manifest_assets.get(manifest_key, manifest_assets.get(asset))
        if not isinstance(actual, dict):
            problems.append(f"manifest 未登记视觉语义: {manifest_key}")
            continue
        # manifest 使用 visual_role，plan 使用 role；其余字段同名。
        actual_role = actual.get("visual_role", actual.get("role"))
        if actual_role != expected.get("role"):
            problems.append(
                f"{manifest_key} visual_role={actual_role!r}，与 visual_plan role={expected.get('role')!r} 不一致"
            )
        if actual.get("framing") != "thigh_up":
            problems.append(f"{manifest_key} framing 必须为 thigh_up")
        prompt = str(actual.get("prompt", ""))
        if not FIGURE_PROMPT_CROP_RE.search(prompt):
            problems.append(f"{manifest_key} prompt 缺少半身至大腿近景构图词")
        if figure_prompt_has_forbidden_framing(prompt):
            problems.append(f"{manifest_key} prompt 含全身/腿脚/远景诱导词，必须重写后重生")
        for key in semantic_keys:
            if key not in expected:
                continue
            expected_value = expected.get(key)
            if actual.get(key) != expected_value:
                problems.append(
                    f"{manifest_key} 的 {key} 与 visual_plan 不一致: "
                    f"manifest={actual.get(key)!r}, plan={expected_value!r}"
                )

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

    # 6. 跨项目资产碰撞（game/ 位于 projects/<id>/game 结构时启用）
    # 背景/BGM 撞车=ERROR（必须项目自产）；立绘撞车=WARN（同角色跨游戏复用是
    # 一致性需求，合法，但打印出来让 agent 与用户明确知情）。
    # 例外：同 IP 双版本（自由/孤独版这类"同一故事两种呈现"）共用背景合法——
    # 项目根放 `.asset_share_allow`（每行一个允许共用的兄弟项目 id）声明豁免，
    # 未声明即撞车 = 复用偷懒，ERROR。
    proj_dir = project_dir
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
