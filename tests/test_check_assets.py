import binascii
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


VALIDATOR = Path(__file__).parents[1] / "scripts" / "check_assets.py"
VALID_PROMPT = (
    "same character, arms crossed, visual novel character sprite, "
    "thigh-up medium close shot, cropped at mid-thigh, same camera distance, "
    "torso and both hands large and readable, no full body, no knees, "
    "no lower legs, no feet or boots visible, no distant shot, solid green background"
)


def png_chunk(kind, payload):
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_rgba_png(path, width, height, bbox):
    left, top, right, bottom = bbox
    transparent = b"\x00\x00\x00\x00"
    opaque = b"\x20\x30\x40\xff"
    rows = []
    for y in range(height):
        if top <= y < bottom:
            row = transparent * left + opaque * (right - left) + transparent * (width - right)
        else:
            row = transparent * width
        rows.append(b"\x00" + row)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + png_chunk(b"IEND", b"")
    )


class CheckAssetsFigureFramingTest(unittest.TestCase):
    def run_case(self, prompt=VALID_PROMPT, size=(1024, 1536), bbox=(154, 45, 870, 1536), framing="thigh_up"):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "projects" / "demo"
            game = project / "game"
            for sub in ("scene", "figure", "background"):
                (game / sub).mkdir(parents=True, exist_ok=True)
            (game / "scene" / "start.txt").write_text(
                "changeFigure:hero_calm.png -center;\n", encoding="utf-8"
            )
            (game / "background" / "title_particles.png").write_bytes(b"custom-particle")
            width, height = size
            write_rgba_png(game / "figure" / "hero_calm.png", width, height, bbox)
            meta = {
                "role": "dialogue_pose", "framing": framing, "pose": "微侧身抱臂",
                "expression": "平静", "gesture": "arms_crossed",
                "usage_tags": ["calm"], "props": [],
            }
            (project / "visual_plan.json").write_text(
                json.dumps({"figure_catalog": {"hero_calm.png": meta}, "beats": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            manifest_meta = {
                "visual_role": "dialogue_pose", "framing": framing, "pose": "微侧身抱臂",
                "expression": "平静", "gesture": "arms_crossed",
                "usage_tags": ["calm"], "props": [], "prompt": prompt,
            }
            manifest = project / "manifest.json"
            manifest.write_text(
                json.dumps({"assets": {"figure/hero_calm.png": manifest_meta}, "pending": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(game), str(manifest)],
                capture_output=True, text=True, check=False,
            )

    def test_valid_thigh_up_sprite_passes(self):
        result = self.run_case()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_full_body_prompt_is_rejected(self):
        result = self.run_case(prompt="full-body anime VN sprite, feet planted wide")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("全身/腿脚/远景诱导词", result.stdout)

    def test_wrong_canvas_size_is_rejected(self):
        result = self.run_case(size=(864, 1821), bbox=(130, 50, 735, 1821))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("必须是 1024×1536", result.stdout)

    def test_too_narrow_character_is_rejected(self):
        result = self.run_case(bbox=(260, 45, 760, 1536))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("人物宽度占幅不合格", result.stdout)


class CheckAssetsSeedanceProvenanceTest(unittest.TestCase):
    def run_case(self, valid=True, receipt_task_id="task-123456"):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "projects" / "demo"
            game = project / "game"
            for sub in ("scene", "background", "video"):
                (game / sub).mkdir(parents=True, exist_ok=True)
            (project / "storyboards").mkdir()
            (project / "character").mkdir()
            (project / "video_receipts").mkdir()
            (game / "scene" / "start.txt").write_text(
                "playVideo:card_he.mp4;\n", encoding="utf-8"
            )
            (game / "background" / "title_particles.png").write_bytes(b"custom-particle")
            (game / "video" / "card_he.mp4").write_bytes(b"video-placeholder")
            (project / "storyboards" / "he.txt").write_text("ending storyboard", encoding="utf-8")
            (project / "character" / "hero_ref.png").write_bytes(b"image-placeholder")
            (project / "visual_plan.json").write_text(
                json.dumps({"figure_catalog": {}, "beats": []}), encoding="utf-8"
            )
            record = {
                "type": "ending_video", "status": "ok",
                "provider": "seedance" if valid else "ffmpeg",
                "model_family": "seedance-2.5",
                "model": "ep-20260708102140-mxjvc",
                "task_id": "task-123456", "task_status": "succeeded",
                "generator": "scripts/gen_video.py",
                "prompt_file": "storyboards/he.txt",
                "reference_image": "character/hero_ref.png",
                "output": "game/video/card_he.mp4",
                "receipt": "video_receipts/card_he.seedance.json",
            }
            receipt = dict(record)
            receipt.update({"schema_version": 1, "type": "seedance_video_receipt"})
            receipt["task_id"] = receipt_task_id
            (project / "video_receipts" / "card_he.seedance.json").write_text(
                json.dumps(receipt), encoding="utf-8"
            )
            manifest = project / "manifest.json"
            manifest.write_text(
                json.dumps({"assets": {"video/card_he.mp4": record}, "pending": []}),
                encoding="utf-8",
            )
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(game), str(manifest)],
                capture_output=True, text=True, check=False,
            )

    def test_seedance_25_receipt_passes(self):
        result = self.run_case()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_local_video_provider_is_rejected(self):
        result = self.run_case(valid=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("必须为 'seedance'", result.stdout)

    def test_receipt_must_match_manifest(self):
        result = self.run_case(receipt_task_id="task-different")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("回执字段 task_id 与 manifest 不一致", result.stdout)


if __name__ == "__main__":
    unittest.main()
