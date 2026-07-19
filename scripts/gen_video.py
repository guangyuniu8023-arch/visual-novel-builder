#!/usr/bin/env python3
"""gen_video.py — 结局结算短片生成（视频生成 provider 可插拔）

用法:
  python3 gen_video.py --prompt-file <分镜prompt.txt> --ref <角色主题图> --out <输出.mp4>
      [--ratio 9:16] [--duration 15] [--resolution 480p] [--no-audio] [--timeout 600]

流程: 上传参考图（agent_gw upload_storage → 公网 URL）→ provider 建任务 →
      轮询 → 下载并校验（真 MP4 + ffprobe 时长）。

provider 配置: tools/providers.yaml 的 video 段（与 gen_image.py 同款插拔模式）：
  video:
    provider: seedance        # 当前默认（火山方舟 Seedance 异步任务 API）
    seedance:
      model: doubao-seedance-2-0-fast-260128
      endpoint: https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks
      api_key_env: ARK_API_KEY
    # openai_compat:          # 预留：任意 OpenAI 兼容视频 API
    #   model/endpoint/api_key_env

**API key 一律走环境变量（各 provider 的 api_key_env），禁止写进脚本或仓库。**

新增 provider 的方法：在下方 PROVIDERS 注册表加一个适配器（实现
build_payload / parse_task / is_done / get_video_url 四个钩子），
并在 providers.yaml 配同名段。
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- 配置解析（简单解析，避免依赖 pyyaml） ----------

def load_video_config():
    """读 tools/providers.yaml 的 video 段 → {provider: str, <provider名>: {k: v}}。"""
    cfg = {"provider": "seedance"}
    path = os.path.join(HERE, "..", "tools", "providers.yaml")
    if not os.path.exists(path):
        return cfg
    in_video = False
    current = None
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip()
        if line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            key = line.strip()
            in_video = key == "video:"
            current = None
            continue
        if not in_video or ":" not in line:
            continue
        k, _, v = line.strip().partition(":")
        v = v.strip()
        if indent == 2:
            if v == "":
                current = k
                cfg.setdefault(current, {})
            else:
                cfg[k] = v
                current = None
        elif indent >= 4 and current:
            cfg[current][k] = v
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
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# ---------- provider 适配器 ----------

class SeedanceAdapter:
    """火山方舟 Seedance：POST 建任务 → GET 轮询 → content.video_url。"""

    def __init__(self, cfg):
        self.model = cfg.get("model", "doubao-seedance-2-0-fast-260128")
        self.endpoint = cfg.get(
            "endpoint",
            "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks")
        self.key_env = cfg.get("api_key_env", "ARK_API_KEY")

    def build_payload(self, prompt, ref_url, args):
        return {
            "model": self.model,
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": ref_url}, "role": "reference_image"},
            ],
            "generate_audio": not args.no_audio,
            "ratio": args.ratio,
            "duration": args.duration,
            "resolution": args.resolution,
            "watermark": False,
        }

    def create(self, key, payload):
        task = api(self.endpoint, key, "POST", payload)
        task_id = task.get("id")
        if not task_id:
            raise RuntimeError(f"建任务失败: {task}")
        return task_id

    def poll_once(self, key, task_id):
        return api(f"{self.endpoint}/{task_id}", key)

    @staticmethod
    def is_done(status_resp):
        s = status_resp.get("status")
        if s == "succeeded":
            return (status_resp.get("content") or {}).get("video_url")
        if s == "failed":
            raise RuntimeError(
                f"任务失败: {json.dumps(status_resp, ensure_ascii=False)[:500]}")
        return None


PROVIDERS = {"seedance": SeedanceAdapter}


# ---------- 主流程 ----------

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
    provider = cfg.get("provider", "seedance")
    if provider not in PROVIDERS:
        print(f"ERROR: 未实现的 video provider: {provider}（已注册: {list(PROVIDERS)}）")
        return 1
    adapter = PROVIDERS[provider](cfg.get(provider, {}))

    key = os.environ.get(adapter.key_env, "")
    if not key:
        print(f"ERROR: 环境变量 {adapter.key_env} 未设置（API key 禁止写进仓库，用 env 注入）")
        return 1

    print(f"provider={provider} model={adapter.model}")
    print("上传参考图…")
    ref_url = upload_ref(args.ref)
    print("创建任务…")
    try:
        task_id = adapter.create(key, adapter.build_payload(prompt, ref_url, args))
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1
    print(f"任务 {task_id}，轮询中…")

    deadline = time.time() + args.timeout
    video_url = None
    try:
        while time.time() < deadline:
            time.sleep(15)
            resp = adapter.poll_once(key, task_id)
            print(f"  {resp.get('status', '?')}")
            video_url = adapter.is_done(resp)
            if video_url:
                break
    except RuntimeError as e:
        print(f"ERROR: {e}")
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
