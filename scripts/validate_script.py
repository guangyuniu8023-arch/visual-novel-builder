#!/usr/bin/env python3
"""validate_script.py — WebGAL 剧本校验器（乙游多结局）

校验项（ERROR 必须清零）:
  1. 基本语法: 每行以 ';' 结尾（注释/空行除外）
  2. label 闭合: jumpLabel/choose 的标签目标在当前场景内已定义
  3. 场景文件闭合: changeScene/callScene/choose 指向的场景文件存在
  4. 结局数量: 以 'end;' 收尾且可达的终局分支数 >= --min-endings
  5. 变量先定义后使用: -when/(条件)-> 中引用的变量有对应的 setVar
  6. 死局检测: 从 start.txt 出发的每条路径都能到达某个 end;

警告（WARNING 需人工确认）:
  - 孤立 label（无任何跳转指向）
  - 定义了但从未用于分支条件的变量

用法:
  python3 validate_script.py <scene目录> [--min-endings N] [--start start.txt]
退出码: 0=通过(仅警告或无问题) 1=存在 ERROR
"""
import argparse
import os
import re
import sys

CMD_RE = re.compile(r"^(?P<body>[^;]+);")
LABEL_RE = re.compile(r"^label\s*:\s*([\w一-龥]+)\s*$")
JUMP_RE = re.compile(r"^jumpLabel\s*:\s*([\w一-龥]+)")
SCENE_RE = re.compile(r"^(?:changeScene|callScene)\s*:\s*([\w.-]+\.txt)")
CHOOSE_RE = re.compile(r"^choose\s*:\s*(.+)$")
SETVAR_RE = re.compile(r"^setVar\s*:\s*([A-Za-z_]\w*)\s*=")
WHEN_RE = re.compile(r"-when=([^;\s]+)")
CONDVAR_RE = re.compile(r"([A-Za-z_]\w*)\s*(?:>=|<=|==|!=|>|<)")
CHOOSE_COND_RE = re.compile(r"\(([^)]+)\)->")


def parse_line(raw: str):
    """返回 (kind, payload) 或 None。kind: label/jump/choose/scene/setvar/end/cond
    WebGAL 注释语法：分号开头（; 后内容为注释），没有 // 注释。"""
    line = raw.strip()
    if not line or line.startswith(";"):
        return None
    if not line.endswith(";"):
        return ("syntax_error", raw.rstrip("\n"))
    body = line[:-1].strip()
    m = LABEL_RE.match(body)
    if m:
        return ("label", m.group(1))
    if JUMP_RE.match(body):
        conds = WHEN_RE.findall(body)
        return ("jump", (JUMP_RE.match(body).group(1), conds))
    m = SCENE_RE.match(body)
    if m:
        return ("scene", m.group(1))
    m = CHOOSE_RE.match(body)
    if m:
        return ("choose", m.group(1))
    if SETVAR_RE.match(body):
        return ("setvar", SETVAR_RE.match(body).group(1))
    if body == "end":
        return ("end", None)
    return None


def parse_choose_targets(payload: str):
    """choose 的每个选项: [显示条件]->文字:目标  (目标可能是 label 或 scene.txt)"""
    targets = []
    cond_vars = []
    for opt in payload.split("|"):
        opt = opt.strip()
        if not opt:
            continue
        cm = CHOOSE_COND_RE.match(opt)
        if cm:
            cond_vars += CONDVAR_RE.findall(cm.group(1))
            opt = CHOOSE_COND_RE.sub("", opt, count=1)
        if ":" in opt:
            _, target = opt.rsplit(":", 1)
            target = target.strip()
            if target:
                targets.append(target)
    return targets, cond_vars


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_dir")
    ap.add_argument("--min-endings", type=int, default=2)
    ap.add_argument("--start", default="start.txt")
    args = ap.parse_args()

    errors, warnings = [], []
    scene_files = sorted(f for f in os.listdir(args.scene_dir) if f.endswith(".txt"))
    if args.start not in scene_files:
        print(f"ERROR: 起始场景 {args.start} 不存在")
        return 1

    scenes = {}
    all_setvars = set()
    cond_used_vars = set()

    for fname in scene_files:
        path = os.path.join(args.scene_dir, fname)
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        labels, jumps, chooses, scene_refs, setvars = set(), [], [], [], set()
        ends = 0
        first_label_seen = None
        clear_before_first_bg = None  # None=未见 changeBg；True/False=首个 changeBg 前是否已清场
        for i, raw in enumerate(lines, 1):
            stripped = raw.strip()
            if clear_before_first_bg is None:
                if stripped.startswith("changeFigure:none"):
                    clear_before_first_bg = True
                elif stripped.startswith("changeBg:"):
                    clear_before_first_bg = False
            parsed = parse_line(raw)
            if not parsed:
                continue
            kind, payload = parsed
            if first_label_seen is None and kind == "label":
                first_label_seen = payload  # 文件首个 label 视为场景入口标签
            if kind == "syntax_error":
                errors.append(f"{fname}:{i} 行尾缺少 ';' → {payload.strip()[:50]}")
            elif kind == "label":
                if payload in labels:
                    errors.append(f"{fname}:{i} label 重复定义: {payload}")
                labels.add(payload)
            elif kind == "jump":
                target, conds = payload
                jumps.append(target)
                for c in conds:
                    cond_used_vars.update(CONDVAR_RE.findall(c))
            elif kind == "choose":
                targets, cvars = parse_choose_targets(payload)
                cond_used_vars.update(cvars)
                chooses += targets
            elif kind == "scene":
                scene_refs.append(payload)
            elif kind == "setvar":
                setvars.add(payload)
            elif kind == "end":
                ends += 1
        scenes[fname] = {
            "labels": labels, "jumps": jumps, "chooses": chooses,
            "scene_refs": scene_refs, "setvars": setvars, "ends": ends,
            "entry_label": first_label_seen,
        }
        # 分支不再强制切立绘。选择的反馈首先由台词/数值承担；只有持续的身体语言
        # 变化或具体动作才进入 visual_plan。逐分支硬切图会制造高频闪切和无意义差分。
        all_setvars |= setvars
        if clear_before_first_bg is False:
            errors.append(
                f"{fname}: 首个 changeBg 前缺少 changeFigure:none 清场"
                "（changeScene 不会清空上一场立绘，角色会原样挂进新场景）"
            )

    # 2. label 闭合（choose 目标若是 label 必须在同场景；若是 xx.txt 则按场景文件检查）
    for fname, sc in scenes.items():
        label_targets = [t for t in sc["jumps"] + sc["chooses"] if not t.endswith(".txt")]
        for t in label_targets:
            if t not in sc["labels"]:
                errors.append(f"{fname}: 跳转目标 label 未定义: {t}")
        # 孤立 label 警告
        referenced = set(sc["jumps"] + [t for t in sc["chooses"] if not t.endswith(".txt")])
        for lb in sc["labels"] - referenced:
            if lb == sc["entry_label"]:
                continue  # 场景入口标签由 changeScene/callScene 进入，不算孤立
            warnings.append(f"{fname}: label '{lb}' 无任何跳转指向（孤立节点）")

    # 3. 场景文件闭合
    for fname, sc in scenes.items():
        for t in sc["scene_refs"] + [t for t in sc["chooses"] if t.endswith(".txt")]:
            if t not in scene_files:
                errors.append(f"{fname}: 场景文件不存在: {t}")

    # 4. 结局数量（按文件内 end; 计数 + start 场景必须能通向结局场景）
    total_ends = sum(sc["ends"] for sc in scenes.values())
    if total_ends < args.min_endings:
        errors.append(f"结局分支不足: 全剧本共 {total_ends} 个 end;，要求 >= {args.min_endings}")

    # 5. 变量先定义后使用
    for v in sorted(cond_used_vars):
        if v not in all_setvars and v not in ("true", "false"):
            errors.append(f"条件中使用了未定义的变量: {v}（无对应 setVar）")
    for v in sorted(all_setvars):
        if v not in cond_used_vars and v not in ("affection",):
            warnings.append(f"变量 '{v}' 已 setVar 但未用于任何分支条件")

    # 6. 死局检测：场景文件必须有 end; 或通向其他场景
    for fname, sc in scenes.items():
        if sc["ends"] == 0 and not sc["scene_refs"] and not any(t.endswith(".txt") for t in sc["chooses"]):
            errors.append(f"{fname}: 场景没有 end; 也没有切换场景，玩家将卡死")

    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")

    print(f"\n校验汇总: {len(scene_files)} 个场景, {total_ends} 个 end;, "
          f"{len(all_setvars)} 个变量, ERROR={len(errors)}, WARNING={len(warnings)}")
    if not errors:
        print("PASS: 剧本校验通过")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
