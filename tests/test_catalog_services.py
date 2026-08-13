import json
import os
import tempfile
import unittest

from backend.application.playlist_service import PlaylistService
from backend.application.preset_service import PresetService
from backend.infrastructure.json_storage import CURRENT_SCHEMA_VERSION, load_json, save_json
from models import Song, SongGroup, Step


class PlaylistServiceTests(unittest.TestCase):
    def setUp(self):
        self.song_a = Song("A", "A", 10, enabled=True)
        self.song_b = Song("B", "B", 10, enabled=False)
        self.group_a = SongGroup("G1", [self.song_a, self.song_b])
        self.group_b = SongGroup("G2", [])
        self.service = PlaylistService([self.group_a, self.group_b])

    def test_jobs_respect_active_group_and_enabled_filter(self):
        jobs = self.service.jobs_for_view("G1", enabled_only=True)
        self.assertEqual([job.song.title for job in jobs], ["A"])
        all_jobs = self.service.jobs_for_view("全部")
        self.assertEqual([job.song.title for job in all_jobs], ["A", "B"])

    def test_move_song_preserves_object_and_serializes(self):
        moved = self.service.move_song(self.group_a, 0, self.group_b)
        self.assertIs(moved, self.song_a)
        self.assertEqual(self.group_a.songs, [self.song_b])
        self.assertEqual(self.group_b.songs, [self.song_a])
        document = self.service.to_document("G2")
        self.assertEqual(document["active_song_group"], "G2")
        self.assertEqual(document["song_groups"][1]["songs"][0]["title"], "A")

    def test_group_names_are_unique_and_reserved(self):
        self.assertEqual(self.service.unique_group_name("G1"), "G1 2")
        with self.assertRaises(ValueError):
            self.service.rename_group(self.group_a, "全部")


class PresetServiceTests(unittest.TestCase):
    def setUp(self):
        self.song = Song("A", "A", 10, step_preset="SongPreset")
        self.group = SongGroup("G", [self.song], step_preset="GroupPreset")
        self.song_steps = [Step("song", "click")]
        self.group_steps = [Step("group", "wait", value="1")]
        self.presets = [
            {"name": "SongPreset", "steps": self.song_steps},
            {"name": "GroupPreset", "steps": self.group_steps},
        ]
        self.service = PresetService(self.presets, [self.group])

    def test_song_then_group_then_current_precedence(self):
        current = [Step("current", "log")]
        steps, label = self.service.resolve_steps(self.song, self.group, current)
        self.assertIs(steps, self.song_steps)
        self.assertEqual(label, "单曲:SongPreset")
        self.song.step_preset = ""
        steps, label = self.service.resolve_steps(self.song, self.group, current)
        self.assertIs(steps, self.group_steps)
        self.assertEqual(label, "歌曲组:GroupPreset")
        self.group.step_preset = ""
        steps, label = self.service.resolve_steps(self.song, self.group, current, "SongPreset")
        self.assertIs(steps, self.song_steps)
        self.assertEqual(label, "活动预设:SongPreset")
        steps, label = self.service.resolve_steps(self.song, self.group, current)
        self.assertIs(steps, current)
        self.assertEqual(label, "旧版当前动作序列")

    def test_rename_and_delete_update_all_references(self):
        self.service.rename("SongPreset", "Renamed")
        self.assertEqual(self.song.step_preset, "Renamed")
        self.assertIsNotNone(self.service.find("Renamed"))
        self.assertTrue(self.service.delete("GroupPreset"))
        self.assertEqual(self.group.step_preset, "")

    def test_saved_steps_are_independent_clones(self):
        source = [Step("one", "click")]
        preset = self.service.save("New", source)
        source[0].name = "changed"
        self.assertEqual(preset["steps"][0].name, "one")


class JsonStorageTests(unittest.TestCase):
    def test_versioned_save_load_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            save_json(path, {"value": 1}, document_type="macro_config")
            with open(path, "r", encoding="utf-8") as stream:
                raw = json.load(stream)
            self.assertEqual(raw["_schema_version"], CURRENT_SCHEMA_VERSION)
            self.assertEqual(raw["_document_type"], "macro_config")
            self.assertEqual(load_json(path, {}, "macro_config"), {"value": 1})
            save_json(path, {"value": 2}, document_type="macro_config")
            self.assertTrue(os.path.exists(path + ".bak"))
            self.assertEqual(load_json(path + ".bak", {}, "macro_config"), {"value": 1})

    def test_legacy_document_remains_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "legacy.json")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({"legacy": True}, stream)
            self.assertEqual(load_json(path, {}, "macro_config"), {"legacy": True})

    def test_future_or_wrong_document_returns_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "future.json")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({"_schema_version": 99, "_document_type": "playlist"}, stream)
            self.assertEqual(load_json(path, {"fallback": True}, "macro_config"), {"fallback": True})


if __name__ == "__main__":
    unittest.main()
