#!/usr/bin/env python3
"""init_project.py — 创建乙游项目骨架与流水线状态文件

用法:
  python3 init_project.py <project_id> [--workspace <目录>] [--title <游戏标题>]

幂等：目录已存在时只补缺失文件，不覆盖已有内容。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

PROJECT_DIRS = [
    "character",
    "game/scene",
    "game/background",
    "game/figure",
    "game/bgm",
    "game/vocal",
    "game/video",
    "build",
    "qa_report",
]

DEFAULT_STATE = {
    "stage": "INTAKE",
    "gdd_confirmed": False,
    "script_valid": False,
    "assets_confirmed": False,
    "qa_passed": False,
    "history": [],
}

DEFAULT_CONFIG = """Game_name:{title};
Game_key:{key};
Title_img:title_main.jpg;
Title_bgm:;
Game_Logo:;
Enable_Appreciation:true;
Enable_Continue:true;
Enable_flowchart:true;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="创建乙游项目骨架")
    parser.add_argument("project_id", help="项目 ID（英文/数字/连字符）")
    parser.add_argument("--workspace", default=os.getcwd(), help="工作区目录（默认当前目录）")
    parser.add_argument("--title", default="", help="游戏标题（写入 config.txt 模板）")
    args = parser.parse_args()

    if not args.project_id.replace("-", "").replace("_", "").isalnum():
        print("ERROR: project_id 只能包含英文、数字、连字符、下划线", file=sys.stderr)
        return 1

    root = os.path.join(args.workspace, "projects", args.project_id)
    for d in PROJECT_DIRS:
        os.makedirs(os.path.join(root, d), exist_ok=True)

    state_path = os.path.join(root, "state.json")
    if not os.path.exists(state_path):
        state = dict(DEFAULT_STATE)
        state["project_id"] = args.project_id
        state["created_at"] = datetime.now(timezone.utc).isoformat()
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    config_path = os.path.join(root, "game", "config.txt")
    if not os.path.exists(config_path):
        key = args.project_id.replace("-", "").replace("_", "")[:10] or "otomegame"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_CONFIG.format(title=args.title or args.project_id, key=key))

    manifest_path = os.path.join(root, "manifest.json")
    if not os.path.exists(manifest_path):
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({"assets": {}, "pending": []}, f, ensure_ascii=False, indent=2)

    print(f"OK project ready: {root}")
    print(f"  state: {state_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
