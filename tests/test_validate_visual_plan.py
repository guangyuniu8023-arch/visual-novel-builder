import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


VALIDATOR = Path(__file__).parents[1] / "scripts" / "validate_visual_plan.py"
DEFAULT_POLICY = {
    "min_pose_hold_lines": 3,
    "max_pose_changes_per_100_lines": 100,
    "max_visual_changes_per_100_lines": 100,
    "max_cg_per_scene": 2,
    "max_action_beats_per_scene": 2,
    "max_background_beats_per_scene": 4,
    "max_text_lead_transition_ms": 220,
}


class VisualPlanValidatorTest(unittest.TestCase):
    def run_case(self, plan, scene_text):
        plan = deepcopy(plan)
        plan.setdefault("version", 3)
        plan.setdefault("visual_policy", deepcopy(DEFAULT_POLICY))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scene"
            scene_dir.mkdir()
            (root / "visual_plan.json").write_text(
                json.dumps(plan, ensure_ascii=False), encoding="utf-8"
            )
            (scene_dir / "start.txt").write_text(scene_text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(root / "visual_plan.json"), str(scene_dir)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_text_led_environment_action_and_offstage_beats(self):
        plan = {
            "figure_catalog": {
                "hero_act_offer.png": {
                    "role": "action", "framing": "thigh_up", "pose": "站立递出信物", "expression": "温柔",
                    "action": "offer_token", "props": ["token"],
                    "allowed_beat_ids": ["offer"],
                },
                "hero_calm.png": {
                    "role": "dialogue_pose", "framing": "thigh_up", "pose": "放松站立", "expression": "平静",
                    "gesture": "relaxed", "usage_tags": ["calm"], "props": [],
                },
            },
            "beats": [
                {"id": "blackout", "scene": "start.txt", "lead_text": "蜂鸣声断了一拍。",
                 "text": "屏幕全部熄灭。", "mode": "background", "asset": "bg_dark.webp",
                 "timing": "text_leads", "character_state": "onstage", "description": "控制室断电"},
                {"id": "offer", "scene": "start.txt", "lead_text": "他拿起桌上的信物。",
                 "text": "他把信物递到你面前。", "mode": "figure", "asset": "hero_act_offer.png",
                 "timing": "text_leads", "character_state": "onstage", "description": "角色递出信物"},
                {"id": "radio", "scene": "start.txt", "lead_text": "他的脚步越过拐角。",
                 "text": "通讯里只剩风声。", "mode": "offstage", "timing": "text_leads",
                 "character_state": "offstage", "description": "人物离场后只剩通讯"},
            ],
        }
        scene = """:蜂鸣声断了一拍。;
; @visual:blackout
changeBg:bg_dark.webp -enter=enter -enterDuration=180;
:屏幕全部熄灭。;
:他拿起桌上的信物。;
; @visual:offer
changeFigure:hero_act_offer.png -center -enter=enter -enterDuration=180;
:他把信物递到你面前。;
; @pose:calm
changeFigure:hero_calm.png -center -enter=enter -enterDuration=150;
:他的脚步越过拐角。;
; @visual:radio
changeFigure:none -center -exit=exit -exitDuration=160;
:通讯里只剩风声。;
end;
"""
        result = self.run_case(plan, scene)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_lead_text_is_rejected(self):
        plan = {"figure_catalog": {}, "beats": [
            {"id": "blackout", "scene": "start.txt", "lead_text": "警报停了。",
             "text": "屏幕全部熄灭。", "mode": "background", "asset": "bg_dark.webp",
             "timing": "text_leads", "character_state": "onstage", "description": "控制室断电"}
        ]}
        scene = "; @visual:blackout\nchangeBg:bg_dark.webp -enter=enter -enterDuration=180;\n:屏幕全部熄灭。;\n"
        result = self.run_case(plan, scene)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("前没有可见 lead_text", result.stdout)

    def test_long_text_led_transition_is_rejected(self):
        plan = {"figure_catalog": {}, "beats": [
            {"id": "blackout", "scene": "start.txt", "lead_text": "警报停了。",
             "text": "屏幕全部熄灭。", "mode": "background", "asset": "bg_dark.webp",
             "timing": "text_leads", "character_state": "onstage", "description": "控制室断电"}
        ]}
        scene = ":警报停了。;\n; @visual:blackout\nchangeBg:bg_dark.webp -enter=enter -enterDuration=500;\n:屏幕全部熄灭。;\n"
        result = self.run_case(plan, scene)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("转场 500ms 过长", result.stdout)

    def test_action_pose_cannot_hang_into_later_dialogue(self):
        plan = {
            "figure_catalog": {"hero_act_offer.png": {
                "role": "action", "framing": "thigh_up", "pose": "递出信物", "expression": "温柔",
                "action": "offer", "props": ["token"], "allowed_beat_ids": ["offer"]}},
            "beats": [{"id": "offer", "scene": "start.txt", "lead_text": "他拿起信物。",
                       "text": "他把信物递到你面前。", "mode": "figure",
                       "asset": "hero_act_offer.png", "timing": "text_leads",
                       "character_state": "onstage", "description": "递出信物"}],
        }
        scene = """:他拿起信物。;
; @visual:offer
changeFigure:hero_act_offer.png -center -enter=enter -enterDuration=180;
:他把信物递到你面前。;
主角:之后我们谈谈别的。;
"""
        result = self.run_case(plan, scene)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("挂进了非授权文本", result.stdout)

    def test_dialogue_pose_must_hold_three_lines(self):
        catalog = {
            "hero_calm.png": {"role": "dialogue_pose", "framing": "thigh_up", "pose": "手插口袋", "expression": "平静",
                              "gesture": "hands_in_pockets", "usage_tags": ["calm"], "props": []},
            "hero_concerned.png": {"role": "dialogue_pose", "framing": "thigh_up", "pose": "身体前倾", "expression": "担心",
                                   "gesture": "leaning", "usage_tags": ["concerned"], "props": []},
        }
        plan = {"figure_catalog": catalog, "beats": [
            {"id": "enter", "scene": "start.txt", "text": "他走到你面前。", "mode": "figure",
             "asset": "hero_calm.png", "timing": "establish", "character_state": "onstage",
             "description": "人物进场"}
        ]}
        scene = """; @visual:enter
; @pose:calm
changeFigure:hero_calm.png -center -enter=enter -enterDuration=500;
:他走到你面前。;
; @pose:concerned
changeFigure:hero_concerned.png -center -enter=enter -enterDuration=150;
主角:你还好吗？;
"""
        result = self.run_case(plan, scene)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("仅持有 1 行", result.stdout)

    def test_project_visual_density_budget_is_enforced(self):
        plan = {"visual_policy": {**DEFAULT_POLICY, "max_visual_changes_per_100_lines": 24},
                "figure_catalog": {}, "beats": [
            {"id": "open", "scene": "start.txt", "text": "房间安静下来。", "mode": "background",
             "asset": "bg_a.webp", "timing": "establish", "character_state": "not_applicable",
             "description": "场景建立"},
            {"id": "dark", "scene": "start.txt", "lead_text": "灯闪了一下。",
             "text": "屏幕全部熄灭。", "mode": "background", "asset": "bg_b.webp",
             "timing": "text_leads", "character_state": "not_applicable", "description": "断电"},
        ]}
        scene = """; @visual:open
changeBg:bg_a.webp -enter=enter -enterDuration=500;
:房间安静下来。;
:灯闪了一下。;
; @visual:dark
changeBg:bg_b.webp -enter=enter -enterDuration=180;
:屏幕全部熄灭。;
"""
        result = self.run_case(plan, scene)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("全项目总视觉切换密度", result.stdout)

    def test_figure_pose_rejects_full_body_or_feet_dependent_direction(self):
        plan = {
            "figure_catalog": {
                "hero_command.png": {
                    "role": "dialogue_pose", "framing": "thigh_up",
                    "pose": "full-body stance with feet planted wide",
                    "expression": "坚定", "gesture": "open_hand",
                    "usage_tags": ["command"], "props": [],
                }
            },
            "beats": [
                {"id": "enter", "scene": "start.txt", "text": "他开始下令。",
                 "mode": "figure", "asset": "hero_command.png", "timing": "establish",
                 "character_state": "onstage", "description": "队长进场"}
            ],
        }
        scene = """; @visual:enter
; @pose:command
changeFigure:hero_command.png -center -enter=enter -enterDuration=500;
主角:保持队形。
"""
        result = self.run_case(plan, scene)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("依赖腿脚/全身远景", result.stdout)

    def test_departure_cannot_use_full_body_figure(self):
        plan = {
            "figure_catalog": {
                "hero_leave.png": {
                    "role": "action", "framing": "thigh_up", "pose": "背对镜头",
                    "expression": "冷淡", "gesture": "turned_away", "props": [],
                    "action": "离开画面", "allowed_beat_ids": ["leave"],
                }
            },
            "beats": [
                {"id": "leave", "scene": "start.txt", "lead_text": "他没有回头。",
                 "text": "他的背影走进通道。", "mode": "figure", "asset": "hero_leave.png",
                 "timing": "text_leads", "character_state": "onstage", "description": "角色离场"}
            ],
        }
        scene = """:他没有回头。;
; @visual:leave
changeFigure:hero_leave.png -center -enter=enter -enterDuration=180;
:他的背影走进通道。;
"""
        result = self.run_case(plan, scene)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("必须用 cg/offstage", result.stdout)


if __name__ == "__main__":
    unittest.main()
