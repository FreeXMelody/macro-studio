from dataclasses import asdict

from backend.application.sequence_runner import RunnerJob
from models import SongGroup


class PlaylistService:
    ALL_GROUP = "全部"

    def __init__(self, groups):
        self.groups = groups

    def find_group(self, name):
        return next((group for group in self.groups if group.name == name), None)

    def normalize_active(self, name):
        if name == self.ALL_GROUP:
            return name
        return name if self.find_group(name) else self.groups[0].name

    def current_group(self, name):
        return self.find_group(name) or self.groups[0]

    def songs_for_view(self, active_group):
        if active_group == self.ALL_GROUP:
            return [song for group in self.groups for song in group.songs]
        return self.current_group(active_group).songs

    def jobs_for_view(self, active_group, enabled_only=False):
        jobs = []
        for group in self.groups:
            if active_group != self.ALL_GROUP and group.name != active_group:
                continue
            for song in group.songs:
                if enabled_only and not song.enabled:
                    continue
                jobs.append(RunnerJob(song=song, group=group))
        return jobs

    @staticmethod
    def job(song, group):
        return RunnerJob(song=song, group=group)

    def unique_group_name(self, base):
        base = str(base or "").strip() or "新歌曲组"
        existing = {group.name for group in self.groups}
        if base not in existing and base != self.ALL_GROUP:
            return base
        index = 2
        while f"{base} {index}" in existing:
            index += 1
        return f"{base} {index}"

    def add_group(self, name):
        unique_name = self.unique_group_name(name)
        group = SongGroup(name=unique_name, songs=[], step_preset="")
        self.groups.append(group)
        return group

    def rename_group(self, group, name):
        name = str(name or "").strip()
        if not name:
            raise ValueError("歌曲组名称不能为空")
        if name == self.ALL_GROUP:
            raise ValueError("“全部”是系统保留名称")
        existing = self.find_group(name)
        if existing is not None and existing is not group:
            raise ValueError("已经有同名歌曲组")
        old_name = group.name
        group.name = name
        return old_name, name

    def delete_group(self, group):
        if len(self.groups) <= 1:
            raise ValueError("至少需要保留一个歌曲组")
        self.groups.remove(group)
        return self.groups[0]

    def move_song(self, source_group, song_index, target_group):
        if source_group is target_group:
            raise ValueError("目标歌曲组必须不同于来源歌曲组")
        song = source_group.songs.pop(song_index)
        target_group.songs.append(song)
        return song

    def move_song_within_group(self, group, song_index, direction):
        target = song_index + int(direction)
        if target < 0 or target >= len(group.songs):
            return song_index
        group.songs[song_index], group.songs[target] = group.songs[target], group.songs[song_index]
        return target

    def to_document(self, active_group):
        return {
            "active_song_group": self.normalize_active(active_group),
            "song_groups": [
                {
                    "name": group.name,
                    "step_preset": group.step_preset,
                    "songs": [asdict(song) for song in group.songs],
                }
                for group in self.groups
            ],
        }
