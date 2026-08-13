from dataclasses import asdict, replace

from models import Step


class PresetService:
    def __init__(self, presets, song_groups):
        self.presets = presets
        self.song_groups = song_groups

    def names(self):
        return [preset["name"] for preset in self.presets]

    def find(self, name):
        return next((preset for preset in self.presets if preset["name"] == name), None)

    @staticmethod
    def clone_steps(steps):
        return [replace(step) for step in steps]

    def unique_name(self, base):
        base = str(base or "").strip() or "新动作预设"
        existing = set(self.names())
        if base not in existing:
            return base
        index = 2
        while f"{base} {index}" in existing:
            index += 1
        return f"{base} {index}"

    def create(self, name, steps=()):
        name = str(name or "").strip()
        if not name:
            raise ValueError("动作预设名称不能为空")
        if self.find(name):
            raise ValueError("已经有同名动作预设")
        preset = {"name": name, "steps": self.clone_steps(steps)}
        self.presets.append(preset)
        return preset

    def save(self, name, steps):
        name = str(name or "").strip()
        if not name:
            raise ValueError("动作预设名称不能为空")
        preset = self.find(name)
        if preset is None:
            return self.create(name, steps)
        preset["steps"] = self.clone_steps(steps)
        return preset

    def copy(self, source_name, new_name):
        source = self.find(source_name)
        if source is None:
            raise ValueError("来源动作预设不存在")
        return self.create(new_name, source["steps"])

    def rename(self, old_name, new_name):
        preset = self.find(old_name)
        if preset is None:
            raise ValueError("动作预设不存在")
        new_name = str(new_name or "").strip()
        existing = self.find(new_name)
        if not new_name:
            raise ValueError("动作预设名称不能为空")
        if existing is not None and existing is not preset:
            raise ValueError("已经有同名动作预设")
        preset["name"] = new_name
        self.replace_references(old_name, new_name)
        return preset

    def delete(self, name):
        preset = self.find(name)
        if preset is None:
            return False
        self.presets.remove(preset)
        self.replace_references(name, "")
        return True

    def replace_references(self, old_name, new_name):
        for group in self.song_groups:
            if group.step_preset == old_name:
                group.step_preset = new_name
            for song in group.songs:
                if song.step_preset == old_name:
                    song.step_preset = new_name

    def resolve_steps(self, song, group, current_steps, active_name=""):
        song_name = getattr(song, "step_preset", "")
        preset = self.find(song_name) if song_name else None
        if preset:
            return preset["steps"], f"单曲:{song_name}"
        group_name = getattr(group, "step_preset", "")
        preset = self.find(group_name) if group_name else None
        if preset:
            return preset["steps"], f"歌曲组:{group_name}"
        preset = self.find(active_name) if active_name else None
        if preset:
            return preset["steps"], f"活动预设:{active_name}"
        return current_steps, "旧版当前动作序列"

    def to_data(self):
        return [{"name": preset["name"], "steps": [asdict(step) for step in preset["steps"]]} for preset in self.presets]
