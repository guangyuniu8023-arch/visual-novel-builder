#!/usr/bin/env python3
"""gen_video.py — 结局结算短片生成（Seedance / 火山方舟视频生成）

用法:
  python3 gen_video.py --prompt-file <分镜prompt.txt> --ref <角色主题图> --out <输出.mp4>
      [--ratio 9:16] [--duration 15] [--resolution 480p] [--no-audio]

流程: 上传参考图（agent_gw upload_storage → 公网 URL）→ 建任务 → 轮询 →
      下载并校验（真 MP4 + ffprobe 时长）。

配置: tools/providers.yaml 的 video 段（model/endpoint/api_key_env）。
      **API key 走环境变量（默认 ARK_API_KEY），禁止写进脚本或仓库。**
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))


def load_video_config():
    """读 tools/providers.yaml 的 video 段（简单解析，避免依赖 pyyaml）。"""
    cfg = {
        "model": "doubao-seedance-2-0-fast-260128",
        "endpoint": "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks",
        "api_key_env": "ARK_API_KEY",
    }
    path = os.path.join(HERE, "..", "tools", "providers.yaml")
    if not os.path.exists(path):
        return cfg
    in_video = False
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip()
        if line.strip().startswith("#"):
            continue
        if not line.startswith(" ") and line.rstrip().endswith(":"):
            in_video = line.strip() == "video:"
            continue
        if in_video and ":" in line:
            k, _, v = line.strip().partition(":")
            v = v.strip()
            if k in cfg and v:
                cfg[k] = v
    return cfg


def upload_ref(local_path: str) -> str:
    """本地参考图 → 公网 URL（agent_gw upload_storage，与 gen_image.py 同通道）。"""
    from agent_gw import AgentGwClient  # type: ignore
    client = AgentGwClient()
    resp = client.upload_storage(file=local_path)
    url = getattr(resp, "signed_url", None)
    if url is None and isinstance(resp, dict):
        url = resp.get("signed_url") or resp.get("url")
    if not url:
        raise RuntimeError(f"参考图上传失败: {resp}")
    return url


def api(endpoint, key, method="GET", payload=None):
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode() if payload else None,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file")
    ap.add_argument("--prompt")
    ap.add_argument("--ref", required=True, help="角色主题图（本地路径，上传转 URL）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ratio", default="9:16")
    ap.add_argument("--duration", type=int, default=15)
    ap.add_argument("--resolution", default="480p")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--timeout", type=int, default=600, help="轮询超时秒数")
    args = ap.parse_args()

    prompt = args.prompt
    if args.prompt_file:
        prompt = open(args.prompt_file, encoding="utf-8").read().strip()
    if not prompt:
        print("ERROR: 需要 --prompt-file 或 --prompt")
        return 1

    cfg = load_video_config()
    key = os.environ.get(cfg["api_key_env"], "")
    if not key:
        print(f"ERROR: 环境变量 {cfg['api_key_env']} 未设置（API key 禁止写进仓库，用 env 注入）")
        return 1

    print("上传参考图…")
    ref_url = upload_ref(args.ref)
    payload = {
        "model": cfg["model"],
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": ref_url}, "role": "reference_image"},
        ],
        "generate_audio": not args.no_audio,
        "ratio": args.ratio,
        "duration": args.duration,
        "resolution": args.resolution,
        "watermark": False,
    }
    print("创建任务…")
    task = api(cfg["endpoint"], key, "POST", payload)
    task_id = task.get("id")
    if not task_id:
        print(f"ERROR: 建任务失败: {task}")
        return 1
    print(f"任务 {task_id}，轮询中…")

    deadline = time.time() + args.timeout
    video_url = None
    while time.time() < deadline:
        time.sleep(15)
        st = api(f"{cfg['endpoint']}/{task_id}", key)
        status = st.get("status")
        print(f"  {status}")
        if status == "succeeded":
            video_url = (st.get("content") or {}).get("video_url")
            break
        if status == "failed":
            print(f"ERROR: 任务失败: {json.dumps(st, ensure_ascii=False)[:500]}")
            return 1
    if not video_url:
        print("ERROR: 轮询超时")
        return 1

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + ".tmp"
    urllib.request.urlretrieve(video_url, tmp)
    os.replace(tmp, args.out)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", args.out],
        capture_output=True, text=True)
    dur = probe.stdout.strip()
    if probe.returncode != 0 or not dur:
        print("ERROR: 下载文件不是有效视频")
        return 1
    print(f"OK saved: {args.out}（时长 {float(dur):.1f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
