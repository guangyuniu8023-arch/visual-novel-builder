#!/usr/bin/env python3
"""gen_video.py — 结局结算短片生成（视频生成 provider 可插拔）

用法:
  python3 gen_video.py --prompt-file <分镜prompt.txt> --ref <角色主题图> --out <输出.mp4>
      [--ratio 9:16] [--duration 15] [--resolution 480p] [--no-audio] [--timeout 600]

流程: 上传/编码参考图 → Seedance 2.5 建任务 → 轮询 → 下载并校验（真 MP4 +
      ffprobe 时长）→ 自动更新 manifest 并写 Seedance 任务回执。

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
import base64
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- 配置解析（简单解析，避免依赖 pyyaml） ----------

def load_video_config():
    """读 tools/providers.yaml 的 video 段 → {provider: str, <provider名>: {k: v}}。"""
    cfg = {"provider": "seedance"}
    paths = [
        os.path.join(os.getcwd(), "tools", "providers.yaml"),
        os.path.join(HERE, "..", "tools", "providers.yaml"),
    ]
    path = next((candidate for candidate in paths if os.path.exists(candidate)), None)
    if path is None:
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
    try:
        from agent_gw import AgentGwClient  # type: ignore
        client = AgentGwClient()
        resp = client.upload_storage(file=local_path)
        url = getattr(resp, "signed_url", None)
        if url is None and isinstance(resp, dict):
            url = resp.get("signed_url") or resp.get("url")
        if url:
            return url
    except ImportError:
        pass
    mime = mimetypes.guess_type(local_path)[0] or "image/png"
    with open(local_path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def api(endpoint, key, method="GET", payload=None):
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode() if payload else None,
        method=method,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Seedance HTTP {exc.code}: {body[:1000]}") from exc


# ---------- provider 适配器 ----------

class SeedanceAdapter:
    """火山方舟 Seedance：POST 建任务 → GET 轮询 → content.video_url。"""

    def __init__(self, cfg):
        self.model_family = cfg.get("model_family", "")
        if self.model_family != "seedance-2.5":
            raise ValueError(
                "video.seedance.model_family 必须为 seedance-2.5；禁止切换或本地降级")
        self.model = cfg.get("model", "")
        if not self.model:
            raise ValueError("video.seedance.model 未配置 Seedance 2.5 endpoint")
        self.endpoint = cfg.get(
            "endpoint",
            "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks")
        self.key_env = cfg.get("api_key_env", "ARK_VIDEO_API_KEY")

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


def project_from_output(output_path: str) -> str:
    """Require projects/<id>/game/video/<file>.mp4 and return projects/<id>."""
    output = os.path.abspath(output_path)
    video_dir = os.path.dirname(output)
    game_dir = os.path.dirname(video_dir)
    if os.path.basename(video_dir) != "video" or os.path.basename(game_dir) != "game":
        raise ValueError("--out 必须位于 projects/<id>/game/video/，以便写入强制来源回执")
    return os.path.dirname(game_dir)


def project_relative(project_dir: str, path: str, label: str) -> str:
    absolute = os.path.abspath(path)
    relative = os.path.relpath(absolute, project_dir)
    if relative == ".." or relative.startswith(".." + os.sep):
        raise ValueError(f"{label} 必须位于项目目录内: {path}")
    return relative.replace(os.sep, "/")


def write_json_atomic(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def record_seedance_success(project_dir: str, args, adapter, task_id: str, duration: float) -> None:
    output_rel = project_relative(project_dir, args.out, "输出视频")
    prompt_rel = project_relative(project_dir, args.prompt_file, "分镜 prompt")
    ref_rel = project_relative(project_dir, args.ref, "参考图")
    stem = os.path.splitext(os.path.basename(args.out))[0]
    receipt_rel = f"video_receipts/{stem}.seedance.json"
    completed_at = datetime.now(timezone.utc).isoformat()
    receipt = {
        "schema_version": 1,
        "type": "seedance_video_receipt",
        "provider": "seedance",
        "model_family": adapter.model_family,
        "model": adapter.model,
        "task_id": task_id,
        "task_status": "succeeded",
        "generator": "scripts/gen_video.py",
        "prompt_file": prompt_rel,
        "reference_image": ref_rel,
        "output": output_rel,
        "ratio": args.ratio,
        "resolution": args.resolution,
        "duration_seconds": round(duration, 3),
        "generate_audio": not args.no_audio,
        "completed_at": completed_at,
    }
    write_json_atomic(os.path.join(project_dir, receipt_rel), receipt)

    manifest_path = os.path.join(project_dir, "manifest.json")
    manifest = {"assets": {}, "pending": []}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    assets = manifest.setdefault("assets", {})
    assets[output_rel.removeprefix("game/")] = {
        "type": "ending_video",
        "status": "ok",
        "provider": "seedance",
        "model_family": adapter.model_family,
        "model": adapter.model,
        "task_id": task_id,
        "task_status": "succeeded",
        "generator": "scripts/gen_video.py",
        "prompt_file": prompt_rel,
        "reference_image": ref_rel,
        "output": output_rel,
        "receipt": receipt_rel,
        "ratio": args.ratio,
        "resolution": args.resolution,
        "duration_seconds": round(duration, 3),
        "generate_audio": not args.no_audio,
        "completed_at": completed_at,
    }
    write_json_atomic(manifest_path, manifest)


# ---------- 主流程 ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--ref", required=True, help="角色主题图（本地路径，上传转 URL）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ratio", default="9:16")
    ap.add_argument("--duration", type=int, default=15)
    ap.add_argument("--resolution", default="480p")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--timeout", type=int, default=600, help="轮询超时秒数")
    args = ap.parse_args()

    try:
        project_dir = project_from_output(args.out)
        project_relative(project_dir, args.prompt_file, "分镜 prompt")
        project_relative(project_dir, args.ref, "参考图")
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    prompt = open(args.prompt_file, encoding="utf-8").read().strip()
    if not prompt:
        print("ERROR: --prompt-file 为空")
        return 1

    cfg = load_video_config()
    provider = cfg.get("provider", "seedance")
    if provider != "seedance":
        print("ERROR: visual-novel-builder 强制 video.provider=seedance，禁止切换或本地降级")
        return 1
    if provider not in PROVIDERS:
        print(f"ERROR: 未实现的 video provider: {provider}（已注册: {list(PROVIDERS)}）")
        return 1
    try:
        adapter = PROVIDERS[provider](cfg.get(provider, {}))
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    key = os.environ.get(adapter.key_env, "")
    if not key:
        print(f"ERROR: 环境变量 {adapter.key_env} 未设置（API key 禁止写进仓库，用 env 注入）")
        return 1

    print(f"provider={provider} model_family={adapter.model_family} model={adapter.model}")
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
    duration = float(dur)
    record_seedance_success(project_dir, args, adapter, task_id, duration)
    print(f"OK saved: {args.out}（时长 {duration:.1f}s，Seedance 回执已落档）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
