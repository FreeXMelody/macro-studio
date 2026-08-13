import base64
import io
import os
import tempfile
import unittest

from PIL import Image

from backend.application.target_service import TargetService


class TargetServiceTests(unittest.TestCase):
    def test_legacy_points_are_migrated_to_a_named_group(self):
        service = TargetService(
            {
                "active_point_group": "逆水寒",
                "points": [{"name": "搜索框", "x": 120, "y": 80}],
                "image_targets": [],
            },
            base_dir=os.getcwd(),
        )

        document = service.document()

        self.assertEqual(document["active_point_group"], "逆水寒")
        self.assertEqual(document["point_groups"][0]["points"][0]["name"], "搜索框")

    def test_replace_validates_and_forwards_reference_renames(self):
        saved = []
        renamed = []
        service = TargetService(
            {"point_groups": [{"name": "默认", "points": []}], "image_targets": []},
            base_dir=os.getcwd(),
            save_targets=lambda document, point_map, image_map: saved.append((document, point_map, image_map)),
            replace_references=lambda point_map, image_map: renamed.append((point_map, image_map)),
        )
        document = {
            "active_point_group": "默认",
            "point_groups": [{"name": "默认", "points": [{"name": "新点位", "x": 2, "y": 3}]}],
            "image_targets": [],
        }

        service.replace(document, {"旧点位": "新点位"}, {})

        self.assertEqual(saved[0][1], {"旧点位": "新点位"})
        self.assertEqual(renamed[0][0], {"旧点位": "新点位"})
        self.assertEqual(service.document()["point_groups"][0]["points"][0]["x"], 2)

    def test_import_template_is_saved_inside_image_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            source = io.BytesIO()
            Image.new("RGB", (24, 16), "#58c7aa").save(source, format="PNG")
            data_url = "data:image/png;base64," + base64.b64encode(source.getvalue()).decode("ascii")
            service = TargetService(
                {"point_groups": [{"name": "默认", "points": []}], "image_targets": []},
                base_dir=directory,
            )

            result = service.import_template("播放按钮", data_url, "../unsafe name.png")
            absolute = os.path.join(directory, result["template_path"])

            self.assertTrue(os.path.isfile(absolute))
            self.assertTrue(os.path.commonpath([directory, absolute]) == directory)
            self.assertEqual((result["width"], result["height"]), (24, 16))

    def test_import_mask_is_saved_as_binary_grayscale_image(self):
        with tempfile.TemporaryDirectory() as directory:
            source = io.BytesIO()
            image = Image.new("L", (20, 14), 0)
            image.paste(255, (4, 3, 16, 11))
            image.save(source, format="PNG")
            data_url = "data:image/png;base64," + base64.b64encode(source.getvalue()).decode("ascii")
            service = TargetService(
                {"point_groups": [{"name": "默认", "points": []}], "image_targets": []},
                base_dir=directory,
            )

            result = service.import_mask("播放按钮", data_url)
            absolute = os.path.join(directory, result["template_path"])

            self.assertTrue(os.path.isfile(absolute))
            with Image.open(absolute) as saved:
                self.assertEqual(saved.mode, "L")
                self.assertEqual(set(saved.getdata()), {0, 255})

    def test_old_image_targets_keep_grayscale_defaults(self):
        service = TargetService(
            {
                "point_groups": [{"name": "默认", "points": []}],
                "image_targets": [{"name": "按钮", "template_path": "button.png"}],
            },
            base_dir=os.getcwd(),
        )

        target = service.document()["image_targets"][0]

        self.assertEqual(target["match_mode"], "grayscale")
        self.assertEqual((target["edge_low"], target["edge_high"]), (60, 160))

    def test_template_preview_only_resolves_configured_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "template.png")
            Image.new("RGB", (8, 8), "white").save(path)
            service = TargetService(
                {
                    "point_groups": [{"name": "默认", "points": []}],
                    "image_targets": [{"name": "按钮", "template_path": "template.png"}],
                },
                base_dir=directory,
            )

            self.assertEqual(service.template_path("按钮"), path)
            with self.assertRaisesRegex(ValueError, "图像目标不存在"):
                service.template_path("../template.png")


if __name__ == "__main__":
    unittest.main()