import threading
from dataclasses import asdict

from backend.application.playlist_service import PlaylistService
from backend.application.preset_service import PresetService
from backend.application.sequence_runner import PreparedJob
from models import Song, SongGroup, Step


class CatalogService:
    def __init__(
        self,
        song_groups,
        presets,
        current_steps=(),
        active_song_group="",
        active_step_preset="",
        save_playlists=None,
        save_presets=None,
    ):
        if not song_groups:
            song_groups = [SongGroup(name="默认", songs=[])]
        self.playlist_service = PlaylistService(song_groups)
        self.preset_service = PresetService(presets, song_groups)
        self.current_steps = list(current_steps)
        preset_names = self.preset_service.names()
        self.active_step_preset = (
            active_step_preset if active_step_preset in preset_names else (preset_names[0] if preset_names else "")
        )
        self.active_song_group = self.playlist_service.normalize_active(active_song_group or song_groups[0].name)
        self._save_playlists = save_playlists
        self._save_presets = save_presets
        self._lock = threading.RLock()

    @classmethod
    def from_documents(cls, config_data, playlist_data, **kwargs):
        config_data = config_data if isinstance(config_data, dict) else {}
        song_groups, active_group = cls._groups_from_document(playlist_data)
        presets = []
        for item in config_data.get("step_presets", []):
            name = str(item.get("name", "")).strip()
            if name:
                presets.append({"name": name, "steps": [cls._step_from_data(step) for step in item.get("steps", [])]})
        current_steps = [cls._step_from_data(step) for step in config_data.get("steps", [])]
        return cls(
            song_groups,
            presets,
            current_steps,
            active_group,
            active_step_preset=str(config_data.get("active_step_preset", "")).strip(),
            **kwargs,
        )

    def playlists_document(self):
        with self._lock:
            return self.playlist_service.to_document(self.active_song_group)

    def presets_document(self):
        with self._lock:
            return self.preset_service.to_data()

    def replace_playlists(self, document):
        self._validate_playlist_document(document)
        groups, active_group = self._groups_from_document(document)
        with self._lock:
            self.playlist_service.groups[:] = groups
            self.preset_service.song_groups = self.playlist_service.groups
            self.active_song_group = self.playlist_service.normalize_active(active_group)
            snapshot = self.playlist_service.to_document(self.active_song_group)
            if self._save_playlists:
                self._save_playlists(snapshot)
            return snapshot

    @staticmethod
    def _validate_playlist_document(document):
        items = document.get("song_groups", []) if isinstance(document, dict) else []
        if not items:
            raise ValueError("至少需要保留一个歌曲组")
        names = set()
        for item in items:
            name = str(item.get("name", "")).strip()
            if not name:
                raise ValueError("歌曲组名称不能为空")
            if name == PlaylistService.ALL_GROUP:
                raise ValueError("“全部”是系统保留名称")
            if name in names:
                raise ValueError(f"歌曲组名称重复：{name}")
            names.add(name)

    def replace_presets(self, presets):
        parsed = []
        names = set()
        for item in presets:
            name = str(item.get("name", "")).strip()
            if not name:
                raise ValueError("动作预设名称不能为空")
            if name in names:
                raise ValueError(f"动作预设名称重复：{name}")
            names.add(name)
            parsed.append({"name": name, "steps": [self._step_from_data(step) for step in item.get("steps", [])]})
        with self._lock:
            self.preset_service.presets[:] = parsed
            valid_names = set(self.preset_service.names())
            if self.active_step_preset not in valid_names:
                self.active_step_preset = parsed[0]["name"] if parsed else ""
            for group in self.playlist_service.groups:
                if group.step_preset not in valid_names:
                    group.step_preset = ""
                for song in group.songs:
                    if song.step_preset not in valid_names:
                        song.step_preset = ""
            snapshot = self.preset_service.to_data()
            if self._save_presets:
                self._save_presets(snapshot)
            if self._save_playlists:
                self._save_playlists(self.playlist_service.to_document(self.active_song_group))
            return snapshot

    def replace_target_references(self, point_renames=None, image_target_renames=None):
        point_renames = point_renames or {}
        image_target_renames = image_target_renames or {}

        def update_step(step):
            if step.kind == "click" and step.target in point_renames:
                step.target = point_renames[step.target]
            if step.kind == "image_click" and step.value in image_target_renames:
                step.value = image_target_renames[step.value]

        with self._lock:
            for step in self.current_steps:
                update_step(step)
            for preset in self.preset_service.presets:
                for step in preset["steps"]:
                    update_step(step)

    def jobs(self, active_group=None, enabled_only=True):
        with self._lock:
            group = self.playlist_service.normalize_active(active_group or self.active_song_group)
            return self.playlist_service.jobs_for_view(group, enabled_only=enabled_only)

    def prepare_job(self, job):
        with self._lock:
            steps, preset_label = self.preset_service.resolve_steps(
                job.song,
                job.group,
                self.current_steps,
                self.active_step_preset,
            )
            return PreparedJob(
                steps=list(steps),
                label=job.song.title or job.song.keyword or "未命名歌曲",
                group_name=job.group.name,
                preset_label=preset_label,
                context={
                    "keyword": job.song.keyword,
                    "duration_seconds": job.song.duration_seconds,
                    "buffer_seconds": job.song.buffer_seconds,
                },
            )

    @staticmethod
    def _step_from_data(item):
        data = dict(item)
        data.setdefault("wait_after", "")
        return Step(**data)

    @classmethod
    def _groups_from_document(cls, data):
        if isinstance(data, dict):
            groups = []
            for item in data.get("song_groups", []):
                songs = [cls._song_from_data(song) for song in item.get("songs", [])]
                groups.append(SongGroup(name=item.get("name", "默认"), songs=songs, step_preset=item.get("step_preset", "")))
            if not groups:
                groups = [SongGroup(name="默认", songs=[])]
            active = data.get("active_song_group", groups[0].name)
            return groups, active
        songs = [cls._song_from_data(item) for item in data] if isinstance(data, list) else []
        return [SongGroup(name="默认", songs=songs)], "默认"

    @staticmethod
    def _song_from_data(item):
        return Song(
            title=item.get("title", ""),
            keyword=item.get("keyword", item.get("title", "")),
            duration_seconds=int(item.get("duration_seconds", 0)),
            buffer_seconds=int(item.get("buffer_seconds", 5)),
            enabled=bool(item.get("enabled", True)),
            step_preset=item.get("step_preset", ""),
        )

    def config_fragments(self):
        with self._lock:
            return {
                "steps": [asdict(step) for step in self.current_steps],
                "step_presets": self.preset_service.to_data(),
            }
