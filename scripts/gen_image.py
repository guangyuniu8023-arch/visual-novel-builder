#!/usr/bin/env python3
"""gen_image.py — 生图统一入口（provider 可插拔）

用法:
  python3 gen_image.py --prompt "..." --out <路径> [--ratio 2:3|9:16|1:1|3:2|16:9]
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
import os
import subprocess
import sys
import time


def load_provider_config():
    """读取 tools/providers.yaml（简单解析，避免依赖 pyyaml）。"""
    cfg = {"provider": "agent_gw"}
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "..", "tools", "providers.yaml"),
                 os.path.join(os.getcwd(), "tools", "providers.yaml")):
        if os.path.exists(cand):
            with open(cand, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and ":" in line:
                        k, v = line.split(":", 1)
                        cfg[k.strip()] = v.strip().strip('"').strip("'")
            break
    return cfg


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
    ap.add_argument("--ratio", default="2:3", choices=["1:1", "3:2", "2:3", "16:9", "9:16"])
    ap.add_argument("--resolution", default="1K", choices=["1K", "2K", "4K"])
    ap.add_argument("--ref", action="append", default=[], help="本地参考图（可多次）")
    ap.add_argument("--chroma-key", default="", help='如 "#00FF00"，生成后抠图转透明')
    ap.add_argument("--no-despill", action="store_true",
                    help="关闭抠绿后的自动去绿边（默认开启，深色发/衣服必需）")
    ap.add_argument("--retries", type=int, default=3)
    args = ap.parse_args()

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
            else:
                print(f"ERROR: 未实现的 provider: {provider}（请在 tools/providers.yaml 配置 agent_gw 或自行扩展）")
                return 1

            if args.chroma_key:
                final = chroma_key_to_alpha(final, args.chroma_key)
                if not args.no_despill:
                    fixed = despill(final)
                    if fixed:
                        print(f"NOTE: despill 修正 {fixed} 像素绿边")
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
