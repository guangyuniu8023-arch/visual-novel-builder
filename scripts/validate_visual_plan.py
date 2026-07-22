#!/usr/bin/env python3
"""Validate SCRIPT-stage visual semantics before any image generation.

The validator binds `visual_plan.json` beats to WebGAL comments of the form
`; @visual:<beat_id>`.  Scene establishment may lead with the visual, but every
intra-scene change must be motivated by visible lead text before the command and
then held by supporting text after it.  It also enforces a visual-change budget
so semantic accuracy does not turn into constant image cutting.

Usage:
  python3 validate_visual_plan.py <visual_plan.json> <scene_dir>
Exit codes: 0=pass, 1=errors
"""

import argparse
import json
import os
import re
import sys
from collections import Counter


ANNOTATION_RE = re.compile(r"^;\s*@visual:([A-Za-z0-9_-]+)\s*$")
POSE_ANNOTATION_RE = re.compile(r"^;\s*@pose:([A-Za-z0-9_-]+)\s*$")

COMMANDS = {
    "changeBg", "changeFigure", "bgm", "vocal", "miniAvatar", "playEffect",
    "playVideo", "unlockCg", "unlockBgm", "choose", "setVar", "label",
    "jumpLabel", "changeScene", "callScene", "end", "filmMode", "setTextbox",
}

# These expressions describe changes a player can reasonably expect to see.
ENV_RE = re.compile(
    r"熄灭|亮起|断电|恢复供电|天亮|入夜|红光|警报光|灯光.*(?:变|闪)|"
    r"下雨|雨停|下雪|起雾|门.*(?:打开|关闭)|屏幕.*(?:黑|亮|熄|投影)"
)
OFFSTAGE_AUDIO_RE = re.compile(
    r"通讯(?:里|中)只剩|对讲机(?:里|中)只剩|只剩.*(?:杂音|风声)|"
    r"再也没有回到|声音从远处传来"
)
DEPARTURE_RE = re.compile(
    r"没有回头|背影|转身(?:离开|奔向|走向)|走进.*(?:黑暗|通道|隧道)|"
    r"离开(?:房间|画面|通道|站台)|奔向|跑向|越过警戒线"
)
TOUCH_ACTION_RE = re.compile(
    r"伸出手|递出|递给|放到.*面前|收回.*手|握住|抓住|抱住|拥抱|"
    r"跪下|单膝|按住.*伤口|拉到.*身后|覆住.*手|抛到.*手边|扣在.*腕"
)
FULL_BODY_FIGURE_RE = re.compile(
    r"full[- ]?body|entire figure|lower body|feet? planted|legs? visible|"
    r"knees? visible|boots? visible|walking|running|stride|"
    r"全身|双腿|膝盖|脚部|脚下|迈步|跨步|奔跑|跑向|走向|走进|转身离开",
    re.IGNORECASE,
)
RISK_RE = re.compile(
    "|".join((ENV_RE.pattern, OFFSTAGE_AUDIO_RE.pattern,
              DEPARTURE_RE.pattern, TOUCH_ACTION_RE.pattern))
)

ALLOWED_MODES = {"background", "figure", "cg", "offstage", "text_only"}
ALLOWED_STATES = {"onstage", "offstage", "not_applicable"}


def normalized(value: str) -> str:
    return re.sub(r"[\s`]+", "", value or "")


def visible_text(raw: str):
    """Return player-visible text for a WebGAL line, otherwise None."""
    line = raw.strip()
    if not line or line.startswith(";") or not line.endswith(";"):
        return None
    body = line[:-1].strip()
    if body.startswith(":"):
        return body[1:].strip()
    if ":" not in body:
        return None
    prefix, text = body.split(":", 1)
    if prefix.strip() in COMMANDS:
        return None
    return text.strip()


def load_json(path, errors):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"无法读取 visual plan: {path}: {exc}")
        return {}


def require_command(commands, prefix):
    return any(line.strip().startswith(prefix) for line in commands)


def command_duration(commands, prefix):
    for command in commands:
        if command.strip().startswith(prefix):
            match = re.search(r"-(?:enter|exit)Duration=(\d+)", command)
            return int(match.group(1)) if match else None
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("visual_plan")
    parser.add_argument("scene_dir")
    args = parser.parse_args()

    errors, warnings = [], []
    plan = load_json(args.visual_plan, errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    if plan.get("version") != 3:
        errors.append("visual_plan.version 必须为 3（文字引导 + 视觉预算 + 姿态持有）")
    policy = plan.get("visual_policy")
    if not isinstance(policy, dict):
        errors.append("visual_policy 必须是对象")
        policy = {}
    policy_defaults = {
        "min_pose_hold_lines": 3,
        "max_pose_changes_per_100_lines": 12,
        "max_visual_changes_per_100_lines": 24,
        "max_cg_per_scene": 2,
        "max_action_beats_per_scene": 2,
        "max_background_beats_per_scene": 4,
        "max_text_lead_transition_ms": 220,
    }
    for key, default in policy_defaults.items():
        value = policy.get(key)
        if not isinstance(value, int) or value <= 0:
            errors.append(f"visual_policy.{key} 必须是正整数")
            policy[key] = default
    catalog = plan.get("figure_catalog")
    beats = plan.get("beats")
    if not isinstance(catalog, dict):
        errors.append("figure_catalog 必须是对象")
        catalog = {}
    if not isinstance(beats, list) or not beats:
        errors.append("beats 必须是非空数组；高风险视觉变化不能留到 QA 才发现")
        beats = []

    beat_by_id = {}
    for index, beat in enumerate(beats, 1):
        if not isinstance(beat, dict):
            errors.append(f"beats[{index}] 必须是对象")
            continue
        beat_id = beat.get("id")
        if not isinstance(beat_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", beat_id):
            errors.append(f"beats[{index}].id 缺失或格式错误")
            continue
        if beat_id in beat_by_id:
            errors.append(f"visual beat id 重复: {beat_id}")
        beat_by_id[beat_id] = beat
        for key in ("scene", "text", "mode", "timing", "character_state", "description"):
            if not isinstance(beat.get(key), str) or not beat[key].strip():
                errors.append(f"beat '{beat_id}' 缺少 {key}")
        mode = beat.get("mode")
        if mode not in ALLOWED_MODES:
            errors.append(f"beat '{beat_id}' mode 非法: {mode}")
        if beat.get("character_state") not in ALLOWED_STATES:
            errors.append(f"beat '{beat_id}' character_state 非法")
        if mode in {"background", "figure", "cg"} and not beat.get("asset"):
            errors.append(f"beat '{beat_id}' mode={mode} 但没有 asset")
        if mode == "text_only" and not str(beat.get("reason", "")).strip():
            errors.append(f"beat '{beat_id}' text_only 必须写 reason")
        timing = beat.get("timing")
        if timing not in {"establish", "text_leads"}:
            errors.append(f"beat '{beat_id}' timing 必须是 establish/text_leads")
        if timing == "text_leads" and not str(beat.get("lead_text", "")).strip():
            errors.append(f"beat '{beat_id}' text_leads 必须写 lead_text")
        if timing == "establish" and str(beat.get("lead_text", "")).strip():
            errors.append(f"beat '{beat_id}' establish 不应写 lead_text")
        text = str(beat.get("text", ""))
        if ENV_RE.search(text) and mode not in {"background", "cg"}:
            errors.append(f"beat '{beat_id}' 是环境状态变化，必须用 background/cg")
        if OFFSTAGE_AUDIO_RE.search(text) and mode != "offstage":
            errors.append(f"beat '{beat_id}' 已是远程/失联声音，必须用 offstage 清掉立绘")
        if DEPARTURE_RE.search(text) and mode not in {"cg", "offstage"}:
            errors.append(
                f"beat '{beat_id}' 是离场/背影/步态动作，必须用 cg/offstage；"
                "不得用会拉远镜头的全身 figure"
            )
        if TOUCH_ACTION_RE.search(text) and mode not in {"figure", "cg"}:
            errors.append(f"beat '{beat_id}' 是可见肢体/道具动作，必须用专用 figure/cg")

    for asset, meta in catalog.items():
        if not isinstance(meta, dict):
            errors.append(f"figure_catalog.{asset} 必须是对象")
            continue
        role = meta.get("role")
        props = meta.get("props")
        if role not in {"dialogue_pose", "action"}:
            errors.append(f"figure_catalog.{asset}.role 必须是 dialogue_pose/action")
        if not isinstance(meta.get("pose"), str) or not meta["pose"].strip():
            errors.append(f"figure_catalog.{asset} 缺少 pose")
        if not isinstance(meta.get("expression"), str) or not meta["expression"].strip():
            errors.append(f"figure_catalog.{asset} 缺少 expression")
        if not isinstance(props, list):
            errors.append(f"figure_catalog.{asset}.props 必须是数组")
            props = []
        if meta.get("framing") != "thigh_up":
            errors.append(
                f"figure_catalog.{asset}.framing 必须为 thigh_up（所有立绘统一半身至大腿近景）"
            )
        framing_text = " ".join(
            str(meta.get(key, "")) for key in ("pose", "gesture", "action")
        )
        if FULL_BODY_FIGURE_RE.search(framing_text):
            errors.append(
                f"figure_catalog.{asset} 的姿态依赖腿脚/全身远景；改写为半身身体语言，"
                "或把该视觉节拍改为 cg/offstage"
            )
        if role == "dialogue_pose":
            if props:
                errors.append(f"dialogue pose {asset} 不得持有剧情道具: {props}")
            if meta.get("action"):
                errors.append(f"dialogue pose {asset} 不得声明剧情 action")
            if not isinstance(meta.get("gesture"), str) or not meta["gesture"].strip():
                errors.append(f"dialogue pose {asset} 必须声明 gesture（身体语言不能只换表情）")
            usage_tags = meta.get("usage_tags")
            if not isinstance(usage_tags, list) or not 1 <= len(usage_tags) <= 3:
                errors.append(f"dialogue pose {asset} 必须声明 1-3 个 usage_tags")
        if role == "action":
            if not isinstance(meta.get("action"), str) or not meta["action"].strip():
                errors.append(f"action 立绘 {asset} 必须声明 action")
            allowed = meta.get("allowed_beat_ids")
            if not isinstance(allowed, list) or not allowed:
                errors.append(f"action 立绘 {asset} 必须限定 allowed_beat_ids")
            else:
                for beat_id in allowed:
                    if beat_id not in beat_by_id:
                        errors.append(f"action 立绘 {asset} 引用了不存在的 beat: {beat_id}")

    if not os.path.isdir(args.scene_dir):
        errors.append(f"scene 目录不存在: {args.scene_dir}")
        scene_files = []
    else:
        scene_files = sorted(name for name in os.listdir(args.scene_dir)
                             if name.endswith(".txt"))

    annotations = []
    annotated_text_lines = set()
    referenced_figures = set()
    scene_lines = {}
    for scene in scene_files:
        path = os.path.join(args.scene_dir, scene)
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
        scene_lines[scene] = lines
        for line_no, raw in enumerate(lines, 1):
            stripped = raw.strip()
            if stripped.startswith("changeFigure:"):
                asset = stripped.split(":", 1)[1].split()[0].rstrip(";")
                if asset not in {"none", "delete", "null", ""}:
                    referenced_figures.add(asset)
            match = ANNOTATION_RE.match(stripped)
            if not match:
                continue
            beat_id = match.group(1)
            commands = []
            target_text = None
            target_line = None
            for cursor in range(line_no, len(lines)):
                candidate = lines[cursor]
                text = visible_text(candidate)
                if text is not None:
                    target_text = text
                    target_line = cursor + 1
                    break
                if candidate.strip() and not candidate.strip().startswith(";"):
                    commands.append(candidate.strip())
            lead_text = None
            lead_line = None
            for cursor in range(line_no - 2, -1, -1):
                candidate = visible_text(lines[cursor])
                if candidate is not None:
                    lead_text = candidate
                    lead_line = cursor + 1
                    break
            annotations.append((beat_id, scene, line_no, target_line, target_text,
                                commands, lead_line, lead_text))
            if target_line:
                annotated_text_lines.add((scene, target_line))
            beat = beat_by_id.get(beat_id)
            if beat and beat.get("timing") == "text_leads" and lead_line:
                annotated_text_lines.add((scene, lead_line))

        for line_no, raw in enumerate(lines, 1):
            text = visible_text(raw)
            if text and RISK_RE.search(text) and (scene, line_no) not in annotated_text_lines:
                errors.append(
                    f"{scene}:{line_no} 具体动作/状态变化缺少 '; @visual:<id>': {text[:48]}"
                )

    counts = Counter(item[0] for item in annotations)
    for beat_id in beat_by_id:
        if counts[beat_id] == 0:
            errors.append(f"visual beat 未在剧本标注: {beat_id}")
        elif counts[beat_id] > 1:
            errors.append(f"visual beat 被重复标注 {counts[beat_id]} 次: {beat_id}")

    scene_mode_counts = Counter()
    for beat_id, scene, anno_line, target_line, text, commands, lead_line, lead_text in annotations:
        beat = beat_by_id.get(beat_id)
        if not beat:
            errors.append(f"{scene}:{anno_line} 标注了不存在的 visual beat: {beat_id}")
            continue
        if beat.get("scene") != scene:
            errors.append(f"{scene}:{anno_line} beat '{beat_id}' 应位于 {beat.get('scene')}")
        if text is None:
            errors.append(f"{scene}:{anno_line} beat '{beat_id}' 后没有可见文本")
            continue
        if normalized(str(beat.get("text", ""))) not in normalized(text):
            errors.append(
                f"{scene}:{target_line} beat '{beat_id}' 文本不匹配；计划={beat.get('text')} 实际={text}"
            )
        timing = beat.get("timing")
        if timing == "text_leads":
            if lead_text is None:
                errors.append(f"{scene}:{anno_line} beat '{beat_id}' 前没有可见 lead_text")
            elif normalized(str(beat.get("lead_text", ""))) not in normalized(lead_text):
                errors.append(
                    f"{scene}:{lead_line} beat '{beat_id}' lead_text 不匹配；"
                    f"计划={beat.get('lead_text')} 实际={lead_text}"
                )
        mode, asset = beat.get("mode"), beat.get("asset")
        scene_mode_counts[(scene, mode)] += 1
        if mode == "background" and not require_command(commands, f"changeBg:{asset}"):
            errors.append(f"{scene}:{anno_line} beat '{beat_id}' 必须在承接文字前 changeBg:{asset}")
        elif mode == "figure":
            if not require_command(commands, f"changeFigure:{asset}"):
                errors.append(f"{scene}:{anno_line} beat '{beat_id}' 必须在承接文字前 changeFigure:{asset}")
            meta = catalog.get(asset)
            if not meta:
                errors.append(f"beat '{beat_id}' 使用的 figure 未登记: {asset}")
            elif meta.get("role") == "action" and beat_id not in meta.get("allowed_beat_ids", []):
                errors.append(f"action 立绘 {asset} 不允许用于 beat '{beat_id}'")
            elif TOUCH_ACTION_RE.search(text) and meta.get("role") != "action":
                errors.append(f"beat '{beat_id}' 是具体剧情动作，不能使用 dialogue pose {asset}")
        elif mode == "cg":
            if not require_command(commands, "changeFigure:none"):
                errors.append(f"{scene}:{anno_line} CG beat '{beat_id}' 前必须先清掉立绘")
            if not require_command(commands, f"changeBg:{asset}"):
                errors.append(f"{scene}:{anno_line} CG beat '{beat_id}' 必须在文字前 changeBg:{asset}")
        elif mode == "offstage" and not require_command(commands, "changeFigure:none"):
            errors.append(f"{scene}:{anno_line} offstage beat '{beat_id}' 必须在承接文字前退场")

        if timing == "text_leads":
            prefixes = []
            if mode == "background":
                prefixes = [f"changeBg:{asset}"]
            elif mode == "figure":
                prefixes = [f"changeFigure:{asset}"]
            elif mode == "cg":
                prefixes = ["changeFigure:none", f"changeBg:{asset}"]
            elif mode == "offstage":
                prefixes = ["changeFigure:none"]
            for prefix in prefixes:
                duration = command_duration(commands, prefix)
                if duration is None:
                    errors.append(
                        f"{scene}:{anno_line} beat '{beat_id}' 的 {prefix} 缺少 enter/exitDuration"
                    )
                elif duration > policy["max_text_lead_transition_ms"]:
                    errors.append(
                        f"{scene}:{anno_line} beat '{beat_id}' 转场 {duration}ms 过长；"
                        f"文字引导后上限为 {policy['max_text_lead_transition_ms']}ms"
                    )

    for scene in scene_files:
        if scene_mode_counts[(scene, "cg")] > policy["max_cg_per_scene"]:
            errors.append(
                f"{scene} CG beats={scene_mode_counts[(scene, 'cg')]} 超过预算 "
                f"{policy['max_cg_per_scene']}"
            )
        if scene_mode_counts[(scene, "background")] > policy["max_background_beats_per_scene"]:
            errors.append(
                f"{scene} background beats={scene_mode_counts[(scene, 'background')]} 超过预算 "
                f"{policy['max_background_beats_per_scene']}"
            )
        action_count = sum(
            1 for beat in beat_by_id.values()
            if beat.get("scene") == scene and beat.get("mode") == "figure"
            and catalog.get(beat.get("asset"), {}).get("role") == "action"
        )
        if action_count > policy["max_action_beats_per_scene"]:
            errors.append(
                f"{scene} action beats={action_count} 超过预算 "
                f"{policy['max_action_beats_per_scene']}"
            )

    # Linear staging audit.  This deliberately runs at SCRIPT time, before assets:
    # every background change and every figure enter/exit must belong to a beat;
    # action poses may only survive through their one declared target line.
    scoped_command_lines = {}
    target_beat = {}
    for beat_id, scene, anno_line, target_line, _text, _commands, _lead_line, _lead_text in annotations:
        beat = beat_by_id.get(beat_id)
        if not beat or target_line is None:
            continue
        target_beat[(scene, target_line)] = beat
        for command_line in range(anno_line + 1, target_line):
            scoped_command_lines[(scene, command_line)] = beat

    project_visible_count = 0
    project_dialogue_pose_changes = 0
    project_visual_changes = 0
    for scene, lines in scene_lines.items():
        current_figure = None
        offstage_locked = False
        pending_pose_tag = None
        visible_since_pose_change = 999
        visible_count = sum(1 for raw in lines if visible_text(raw) is not None)
        dialogue_pose_changes = 0
        visual_changes = 0
        for line_no, raw in enumerate(lines, 1):
            stripped = raw.strip()
            pose_match = POSE_ANNOTATION_RE.match(stripped)
            if pose_match:
                if pending_pose_tag is not None:
                    errors.append(f"{scene}:{line_no} 连续 @pose 未消费: {pending_pose_tag}")
                pending_pose_tag = pose_match.group(1)
                continue
            scoped_beat = scoped_command_lines.get((scene, line_no))
            if stripped.startswith("changeBg:") and scoped_beat is None:
                errors.append(
                    f"{scene}:{line_no} changeBg 未归属 visual beat；地点/灯光状态必须先进入 visual_plan"
                )
            if stripped.startswith("changeBg:"):
                visual_changes += 1
            if stripped.startswith("changeFigure:"):
                asset = stripped.split(":", 1)[1].split()[0].rstrip(";")
                if asset in {"none", "delete", "null", ""}:
                    if pending_pose_tag is not None:
                        errors.append(f"{scene}:{line_no} @pose:{pending_pose_tag} 后却执行退场")
                        pending_pose_tag = None
                    if current_figure is not None and scoped_beat is None:
                        errors.append(
                            f"{scene}:{line_no} 人物退场未归属 visual beat；离场不能是无语义清屏"
                        )
                    current_figure = None
                    visual_changes += 1
                else:
                    meta = catalog.get(asset, {})
                    if meta.get("role") == "dialogue_pose":
                        if pending_pose_tag is None:
                            errors.append(
                                f"{scene}:{line_no} dialogue pose {asset} 缺少 '; @pose:<usage_tag>'，"
                                "无法证明姿态与下一句文本匹配"
                            )
                        elif pending_pose_tag not in meta.get("usage_tags", []):
                            errors.append(
                                f"{scene}:{line_no} @pose:{pending_pose_tag} 不在 {asset} 的 "
                                f"usage_tags={meta.get('usage_tags', [])} 中"
                            )
                        pending_pose_tag = None
                        previous_meta = catalog.get(current_figure, {})
                        if previous_meta.get("role") == "dialogue_pose":
                            if asset == current_figure:
                                errors.append(f"{scene}:{line_no} 重复切入同一 dialogue pose: {asset}")
                            elif visible_since_pose_change < policy["min_pose_hold_lines"]:
                                errors.append(
                                    f"{scene}:{line_no} dialogue pose 仅持有 "
                                    f"{visible_since_pose_change} 行，低于最短 "
                                    f"{policy['min_pose_hold_lines']} 行"
                                )
                        dialogue_pose_changes += 1
                        visible_since_pose_change = 0
                    elif pending_pose_tag is not None:
                        errors.append(
                            f"{scene}:{line_no} @pose:{pending_pose_tag} 不能绑定剧情 action 立绘 {asset}"
                        )
                        pending_pose_tag = None
                    if current_figure is None and scoped_beat is None:
                        detail = "离场后重新出现" if offstage_locked else "人物进场"
                        errors.append(
                            f"{scene}:{line_no} {detail}未归属 visual beat: {asset}"
                        )
                    if scoped_beat is not None and scoped_beat.get("character_state") == "onstage":
                        offstage_locked = False
                    current_figure = asset
                    visual_changes += 1

            visible = visible_text(raw)
            if visible:
                visible_since_pose_change += 1
            if visible and pending_pose_tag is not None:
                errors.append(f"{scene}:{line_no} @pose:{pending_pose_tag} 后未切换 dialogue pose")
                pending_pose_tag = None
            beat = target_beat.get((scene, line_no))
            if beat and beat.get("mode") == "offstage":
                offstage_locked = True
                current_figure = None
            if visible and current_figure in catalog:
                meta = catalog[current_figure]
                if meta.get("role") == "action":
                    is_own_beat = (
                        beat is not None
                        and beat.get("id") in meta.get("allowed_beat_ids", [])
                        and beat.get("asset") == current_figure
                    )
                    if not is_own_beat:
                        errors.append(
                            f"{scene}:{line_no} action 立绘 {current_figure} 挂进了非授权文本；"
                            "动作结束后必须切到匹配文本的 dialogue pose 或退场"
                        )
        if pending_pose_tag is not None:
            errors.append(f"{scene}: 文件结束时 @pose:{pending_pose_tag} 仍未绑定立绘")
        project_visible_count += visible_count
        project_dialogue_pose_changes += dialogue_pose_changes
        project_visual_changes += visual_changes

    # 分支结局通常集中在一个短文件里，因此密度按全项目计算；章节内的
    # action/CG/background 上限仍在上方逐场景检查，避免单章变成幻灯片。
    if project_visible_count:
        pose_density = project_dialogue_pose_changes * 100 / project_visible_count
        visual_density = project_visual_changes * 100 / project_visible_count
        if pose_density > policy["max_pose_changes_per_100_lines"]:
            errors.append(
                f"全项目 dialogue pose 切换密度 {pose_density:.1f}/100行，超过预算 "
                f"{policy['max_pose_changes_per_100_lines']}"
            )
        if visual_density > policy["max_visual_changes_per_100_lines"]:
            errors.append(
                f"全项目总视觉切换密度 {visual_density:.1f}/100行，超过预算 "
                f"{policy['max_visual_changes_per_100_lines']}"
            )

    for asset in sorted(referenced_figures):
        if asset not in catalog:
            errors.append(f"剧本引用立绘 {asset}，但 figure_catalog 未登记其 dialogue_pose/action 语义")

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(
        f"\n视觉计划汇总: {len(beats)} beats, {len(catalog)} figures, "
        f"{len(annotations)} annotations, {project_dialogue_pose_changes} pose changes, "
        f"{project_visual_changes} visual changes / {project_visible_count} visible lines, "
        f"ERROR={len(errors)}, WARNING={len(warnings)}"
    )
    if errors:
        return 1
    print("PASS: SCRIPT 视觉语义校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
