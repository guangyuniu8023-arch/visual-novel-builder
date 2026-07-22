#!/usr/bin/env python3
"""gen_image.py — 生图统一入口（provider 可插拔）

用法:
  python3 gen_image.py --prompt "..." --out <路径> [--asset-type general|figure]
      [--ratio 2:3|9:16|1:1|3:2|16:9]
      [--resolution 1K|2K|4K] [--ref <本地参考图>] [--chroma-key "#00FF00"]
      [--retries 3] [--seed N]

provider 配置: 与脚本同级的 tools/providers.yaml（不存在时用环境默认 agent_gw）
  provider: agent_gw          # 当前默认（Kimi agent-gw generate_image）
  # provider: openai_compat   # 预留: 任意 OpenAI 兼容 images API
  #   endpoint: https://...   #   api_key_env: XXX  model: xxx

依赖: agent-gw Python SDK (>=0.2.6)，key 来自 KIMI_API_KEY 或 ~/.kimi/agent-gw.json

--chroma-key: 生成后对图片按指定颜色抠图转透明 PNG（绿幕法，
              用于解决生图模型不支持透明底的约束，需要 Pillow）
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error


FIGURE_SIZE = (1024, 1536)
FIGURE_MIN_WIDTH_RATIO = 0.60
FIGURE_MAX_WIDTH_RATIO = 0.92
FIGURE_MIN_HEIGHT_RATIO = 0.88
FIGURE_MAX_TOP_RATIO = 0.08
FIGURE_MIN_BOTTOM_RATIO = 0.95
FIGURE_CROP_RE = re.compile(
    r"thigh[- ]?up|cropped at mid[- ]?thigh|cowboy shot|upper body|waist[- ]?up|"
    r"半身|大腿(?:中部)?构图|腰部以上",
    re.IGNORECASE,
)
FIGURE_FORBIDDEN_RE = re.compile(
    r"full[- ]?body|entire figure|distant shot|feet? planted|legs? visible|"
    r"knees? visible|boots? visible|walking|running|stride|"
    r"全身|双腿|膝盖入镜|脚部入镜|迈步|跨步|奔跑|跑向|走向|走进|转身离开",
    re.IGNORECASE,
)


def figure_prompt_has_forbidden_framing(prompt: str) -> bool:
    cleaned = re.sub(r"\bno feet or boots visible\b", "", prompt, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:no|not|without)\s+(?:a\s+)?(?:full[- ]?body|entire figure|distant shot|"
        r"knees?|lower legs?|feet|boots?)(?:\s+(?:shot|visible))?\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"禁止全身|不展示(?:膝盖|小腿|脚|鞋|靴子)|(?:膝盖|小腿|脚|鞋|靴子)不入镜", "", cleaned)
    return bool(FIGURE_FORBIDDEN_RE.search(cleaned))


def validate_figure_prompt(prompt: str) -> None:
    if not FIGURE_CROP_RE.search(prompt):
        raise ValueError("立绘 prompt 缺少 thigh-up/半身至大腿近景构图词")
    if figure_prompt_has_forbidden_framing(prompt):
        raise ValueError("立绘 prompt 含 full-body/腿脚/远景诱导词；改为半身身体语言或使用 CG")


def validate_figure_image(image_path: str) -> None:
    from PIL import Image
    img = Image.open(image_path).convert("RGBA")
    if img.size != FIGURE_SIZE:
        raise ValueError(
            f"立绘尺寸为 {img.size[0]}×{img.size[1]}，必须是 "
            f"{FIGURE_SIZE[0]}×{FIGURE_SIZE[1]}；不得拉伸，需重新生成"
        )
    bbox = img.getchannel("A").point(lambda value: 255 if value > 8 else 0).getbbox()
    if bbox is None:
        raise ValueError("立绘没有可见人物像素")
    width_ratio = (bbox[2] - bbox[0]) / img.width
    height_ratio = (bbox[3] - bbox[1]) / img.height
    if not FIGURE_MIN_WIDTH_RATIO <= width_ratio <= FIGURE_MAX_WIDTH_RATIO:
        raise ValueError(
            f"立绘人物宽度占幅 {width_ratio:.1%}，要求 "
            f"{FIGURE_MIN_WIDTH_RATIO:.0%}-{FIGURE_MAX_WIDTH_RATIO:.0%}"
        )
    if height_ratio < FIGURE_MIN_HEIGHT_RATIO:
        raise ValueError(
            f"立绘人物高度占幅 {height_ratio:.1%}，至少 {FIGURE_MIN_HEIGHT_RATIO:.0%}"
        )
    if bbox[1] / img.height > FIGURE_MAX_TOP_RATIO:
        raise ValueError(
            f"立绘头顶留白 {bbox[1] / img.height:.1%}，最多 {FIGURE_MAX_TOP_RATIO:.0%}"
        )
    if bbox[3] / img.height < FIGURE_MIN_BOTTOM_RATIO:
        raise ValueError(
            f"立绘人物下缘 {bbox[3] / img.height:.1%}，"
            f"应贴近画布底部（至少 {FIGURE_MIN_BOTTOM_RATIO:.0%}）"
        )


def load_provider_config():
    """读取 tools/providers.yaml 顶层字段（简单解析，避免依赖 pyyaml）。
    只解析缩进 0 的行——video: 等嵌套段的字段不得覆盖顶层 provider。"""
    cfg = {"provider": "agent_gw"}
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(os.getcwd(), "tools", "providers.yaml"),
                 os.path.join(here, "..", "tools", "providers.yaml")):
        if os.path.exists(cand):
            with open(cand, encoding="utf-8") as f:
                for line in f:
                    if line != line.lstrip():  # 跳过嵌套段（缩进行）
                        continue
                    line = line.strip()
                    if line and not line.startswith("#") and ":" in line:
                        k, v = line.split(":", 1)
                        cfg[k.strip()] = v.strip().strip('"').strip("'")
            break
    return cfg


def local_image_data_url(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def generate_ark_seedream(prompt, out, ratio, resolution, ref_paths, cfg):
    """火山方舟 Seedream 同步图片生成 API。API key 仅从环境变量读取。"""
    endpoint = cfg.get("endpoint", "https://ark.cn-beijing.volces.com/api/v3/images/generations")
    model = cfg.get("model", "")
    key_env = cfg.get("api_key_env", "ARK_API_KEY")
    key = os.environ.get(key_env, "")
    if not key:
        raise RuntimeError(f"环境变量 {key_env} 未设置")
    if not model:
        raise RuntimeError("ark_seedream provider 缺少 model/Endpoint ID")
    size_map = {
        "1:1": "1536x1536",
        "3:2": "1536x1024",
        "2:3": "1024x1536",
        "16:9": "2560x1440",
        "9:16": "1440x2560",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size_map[ratio],
        "response_format": "url",
        "watermark": False,
    }
    if ref_paths:
        payload["image"] = [local_image_data_url(path) for path in ref_paths]
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Seedream HTTP {exc.code}: {body[:1000]}") from exc
    items = data.get("data") or []
    if not items:
        raise RuntimeError(f"Seedream 未返回图片: {str(data)[:500]}")
    item = items[0]
    if item.get("url"):
        return save_with_requested_ext(item["url"], "image/jpeg", out)
    if item.get("b64_json"):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            handle.write(base64.b64decode(item["b64_json"]))
            tmp = handle.name
        from PIL import Image
        image = Image.open(tmp)
        want_ext = os.path.splitext(out)[1].lower()
        if want_ext in (".jpg", ".jpeg"):
            image.convert("RGB").save(out, quality=92)
        else:
            image.save(out)
        os.unlink(tmp)
        return out
    raise RuntimeError(f"Seedream 返回项缺少 url/b64_json: {str(item)[:300]}")


def ensure_agent_gw():
    try:
        import agent_gw  # noqa: F401
        return True
    except ImportError:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                            "agent-gw>=0.2.6"], capture_output=True)
        try:
            import agent_gw  # noqa: F401
            return True
        except ImportError:
            print("ERROR: agent-gw SDK 安装失败:", r.stderr.decode()[:300])
            return False


def upload_reference(client, local_path: str) -> str:
    """本地参考图 → 公网 URL（agent-gw upload_storage）。"""
    resp = client.upload_storage(file=local_path)
    url = getattr(resp, "signed_url", None)
    if url is None and isinstance(resp, dict):
        url = resp.get("signed_url") or resp.get("url")
    if not url:
        raise RuntimeError(f"参考图上传失败: {resp}")
    return url


def save_with_requested_ext(download_url: str, mime: str, out: str) -> str:
    """下载并按 --out 指定的扩展名落盘（服务端格式与此不一致时用 PIL 转）。

    教训：旧版直接按服务端 mime 定扩展名，--out x.jpg 会静默落成 x.png，
    导致装配时背景引用 404。现在以 --out 为准。
    """
    import tempfile
    src_ext = ".png" if "png" in mime else ".jpg"
    want_ext = os.path.splitext(out)[1].lower()
    if want_ext not in (".jpg", ".jpeg", ".png", ".webp"):
        want_ext = src_ext
    final = os.path.splitext(out)[0] + want_ext
    if want_ext == src_ext:
        subprocess.run(["curl", "-sL", "-o", final, download_url], check=True)
        return final
    with tempfile.NamedTemporaryFile(suffix=src_ext, delete=False) as tf:
        tmp = tf.name
    subprocess.run(["curl", "-sL", "-o", tmp, download_url], check=True)
    from PIL import Image
    img = Image.open(tmp)
    if want_ext in (".jpg", ".jpeg"):
        img = img.convert("RGB")  # jpg 不支持透明，去 alpha 防黑底报错
        img.save(final, quality=92)
    else:
        img.save(final)
    os.unlink(tmp)
    return final


def generate_agent_gw(prompt, out, ratio, resolution, ref_urls):
    from agent_gw import AgentGwClient  # type: ignore
    client = AgentGwClient()
    kwargs = {
        "description": prompt,
        "ratio": ratio,
        "resolution": resolution,
        "background": "opaque",
    }
    if ref_urls:
        kwargs["reference_image_urls"] = ref_urls
    resp = client.tools.generate_image(**kwargs)
    data = resp.json() if hasattr(resp, "json") else resp
    media = data.get("media") or {}
    if hasattr(media, "url"):
        url, mime = media.url, getattr(media, "mime_type", "")
    else:
        url, mime = media.get("url"), (media.get("mime_type") or "")
    if not url:
        raise RuntimeError(f"生图接口未返回图片: {str(data)[:300]}")
    return save_with_requested_ext(url, mime, out)


def chroma_key_to_alpha(image_path: str, key_color: str, tolerance: int = 60) -> str:
    """把接近 key_color 的像素转透明（绿幕法）。"""
    from PIL import Image
    img = Image.open(image_path).convert("RGBA")
    kr, kg, kb = int(key_color[1:3], 16), int(key_color[3:5], 16), int(key_color[5:7], 16)
    px = img.getdata()
    out = []
    for r, g, b, a in px:
        if abs(r - kr) < tolerance and abs(g - kg) < tolerance and abs(b - kb) < tolerance:
            out.append((r, g, b, 0))
        else:
            out.append((r, g, b, a))
    img.putdata(out)
    final = os.path.splitext(image_path)[0] + ".png"
    img.save(final)
    return final


def despill(image_path: str) -> int:
    """绿幕抠图后去绿边（深色发/深色衣服必做，否则立绘边缘一圈绿）。

    策略：不透明像素中 G 通道明显超过 R/B 的（绿溢出），把 G 压回 max(R,B)。
    返回修正的像素数。--chroma-key 后默认自动执行。
    """
    from PIL import Image
    img = Image.open(image_path).convert("RGBA")
    px = img.load()
    w, h = img.size
    fixed = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 0 and g > max(r, b) + 8:
                px[x, y] = (r, max(r, b), b, a)
                fixed += 1
    img.save(image_path)
    return fixed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--asset-type", default="general", choices=["general", "figure"],
                    help="figure 会强制半身构图提示词、1024×1536 RGBA 与人物占幅")
    ap.add_argument("--ratio", default="2:3", choices=["1:1", "3:2", "2:3", "16:9", "9:16"])
    ap.add_argument("--resolution", default="1K", choices=["1K", "2K", "4K"])
    ap.add_argument("--ref", action="append", default=[], help="本地参考图（可多次）")
    ap.add_argument("--chroma-key", default="", help='如 "#00FF00"，生成后抠图转透明')
    ap.add_argument("--no-despill", action="store_true",
                    help="关闭抠绿后的自动去绿边（默认开启，深色发/衣服必需）")
    ap.add_argument("--retries", type=int, default=3)
    args = ap.parse_args()

    if args.asset_type == "figure":
        try:
            validate_figure_prompt(args.prompt)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 1
        if args.ratio != "2:3":
            print("ERROR: 立绘必须使用 --ratio 2:3")
            return 1
        if not args.chroma_key:
            print('ERROR: 立绘必须使用 --chroma-key "#00FF00" 生成透明 PNG')
            return 1
        if os.path.splitext(args.out)[1].lower() != ".png":
            print("ERROR: 立绘 --out 必须是 .png")
            return 1

    # agent-gw 的 ratio/resolution 组合限制
    combo_ok = {
        "1K": ["1:1", "3:2", "2:3"],
        "2K": ["1:1", "16:9"],
        "4K": ["16:9", "9:16"],
    }
    if args.ratio not in combo_ok[args.resolution]:
        # 自动修正到最接近的合法组合
        args.resolution = "4K" if args.ratio == "9:16" else "1K"
        print(f"NOTE: 组合不支持，自动改为 resolution={args.resolution} ratio={args.ratio}")

    cfg = load_provider_config()
    provider = cfg.get("provider", "agent_gw")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    last_err = None
    for attempt in range(1, args.retries + 1):
        try:
            if provider == "agent_gw":
                if not ensure_agent_gw():
                    return 1
                from agent_gw import AgentGwClient  # type: ignore
                client = AgentGwClient()
                ref_urls = [upload_reference(client, p) for p in args.ref]
                final = generate_agent_gw(args.prompt, args.out, args.ratio,
                                          args.resolution, ref_urls)
            elif provider == "ark_seedream":
                final = generate_ark_seedream(args.prompt, args.out, args.ratio,
                                              args.resolution, args.ref, cfg)
            else:
                print(f"ERROR: 未实现的 provider: {provider}（已实现 agent_gw / ark_seedream）")
                return 1

            if args.chroma_key:
                final = chroma_key_to_alpha(final, args.chroma_key)
                if not args.no_despill:
                    fixed = despill(final)
                    if fixed:
                        print(f"NOTE: despill 修正 {fixed} 像素绿边")
            if args.asset_type == "figure":
                try:
                    validate_figure_image(final)
                except ValueError:
                    try:
                        os.unlink(final)
                    except OSError:
                        pass
                    raise
            print(f"OK saved: {final}")
            return 0
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"RETRY {attempt}/{args.retries}: {e}")
            # 424/429 限流：短退避无效，直接拉长到 30s+；其余错误渐进退避
            msg = str(e)
            if "424" in msg or "429" in msg or "rate" in msg.lower():
                time.sleep(30 + attempt * 10)
            else:
                time.sleep(min(attempt * 5, 20))

    print(f"ERROR: 生图失败（{args.retries} 次重试后）: {last_err}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
