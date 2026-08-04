import os
import random
import re
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import asdict
from tkinter import filedialog, messagebox, simpledialog, ttk

from automation import (
    VK_A,
    VK_F8,
    VK_F9,
    VK_V,
    click_xy,
    find_window,
    focus_window,
    get_cursor_pos,
    hotkey_ctrl,
    press_enter,
    set_clipboard_text,
    user32,
)
from models import ImageTarget, PointDef, PointGroup, Song, SongGroup, Step
from storage import load_json, save_json
from utils import format_duration, parse_duration, render_template
from vision import locate_template


APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "macro_config.json")
PLAYLIST_PATH = os.path.join(APP_DIR, "playlist.json")
DEFAULT_WINDOW_HINT = "逆水寒手游桌面版"

class MacroStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Macro Studio - 剧组自动操作")
        self.fit_initial_window()

        self.config_data = self.load_config()
        self.point_groups = self.load_point_groups(self.config_data)
        self.active_point_group = tk.StringVar(value=self.config_data.get("active_point_group", self.point_groups[0].name))
        if not self.find_point_group(self.active_point_group.get()):
            self.active_point_group.set(self.point_groups[0].name)
        self.points = self.current_points()
        self.image_targets = self.load_image_targets(self.config_data.get("image_targets", []))
        self.steps = [self.step_from_data(item) for item in self.config_data.get("steps", [])]
        self.step_presets = self.load_step_presets(self.config_data.get("step_presets", []))
        self.active_step_preset = tk.StringVar(value=self.config_data.get("active_step_preset", ""))
        self.loaded_step_preset_name = self.active_step_preset.get()
        playlist_data = load_json(PLAYLIST_PATH, [])
        self.song_groups, active_song_group = self.load_song_groups(playlist_data)
        self.active_song_group = tk.StringVar(value=active_song_group)
        self.song_group_step_preset = tk.StringVar(value="")
        self.song_view_refs = []
        self.songs = self.current_songs()
        self.worker = None
        self.hotkey_thread = None
        self.hotkey_stop_event = threading.Event()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.active_mode = tk.StringVar(value="playlist")
        self.playback_loop_var = tk.BooleanVar(value=bool(self.config_data.get("playback_loop", False)))
        self.playback_random_var = tk.BooleanVar(value=bool(self.config_data.get("playback_random", False)))

        self.colors = {
            "bg": "#0f1115",
            "panel": "#171a21",
            "panel2": "#1f2430",
            "text": "#edf0f5",
            "muted": "#aab2c0",
            "accent": "#73d6b6",
            "line": "#303746",
            "danger": "#ff7b7b",
        }
        self.configure(bg=self.colors["bg"])
        self.setup_style()
        self.build_ui()
        self.try_maximize_window()
        self.refresh_all()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.start_hotkey_thread()

    def fit_initial_window(self):
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        max_w = max(900, screen_w - 40)
        max_h = max(640, screen_h - 80)
        width = min(max_w, max(1480, int(screen_w * 0.92)))
        height = min(max_h, max(860, int(screen_h * 0.88)))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(1280, width), min(780, height))
        self.after(50, self.try_maximize_window)

    def try_maximize_window(self):
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

    def load_config(self):
        data = load_json(CONFIG_PATH, None)
        if data:
            return data
        legacy = load_json(os.path.join(APP_DIR, "config.json"), {})
        legacy_points = legacy.get("points", {})
        points = []
        labels = {
            "search_box": "搜索框",
            "hot_sort": "热度排序",
            "first_result": "第一个结果",
            "play_button": "播放按钮",
        }
        for key, point in legacy_points.items():
            if point:
                points.append({"name": labels.get(key, key), "x": point["x"], "y": point["y"]})
        if not points:
            points = [
                {"name": "搜索框", "x": 0, "y": 0},
                {"name": "热度排序", "x": 0, "y": 0},
                {"name": "第一个结果", "x": 0, "y": 0},
                {"name": "播放按钮", "x": 0, "y": 0},
            ]
        return {
            "window_hint": legacy.get("window_hint", DEFAULT_WINDOW_HINT),
            "focus_window": True,
            "points": points,
            "steps": [
                {"name": "点击搜索框", "kind": "click", "target": "搜索框", "value": "", "enabled": True},
                {"name": "输入搜索词", "kind": "paste", "target": "", "value": "{keyword}", "enabled": True},
                {"name": "回车搜索", "kind": "enter", "target": "", "value": "", "enabled": True},
                {"name": "等待搜索", "kind": "wait", "target": "", "value": str(legacy.get("search_wait_seconds", 2)), "enabled": True},
                {"name": "点击热度排序", "kind": "click", "target": "热度排序", "value": "", "enabled": True},
                {"name": "等待排序", "kind": "wait", "target": "", "value": str(legacy.get("sort_wait_seconds", 1)), "enabled": True},
                {"name": "打开第一个结果", "kind": "click", "target": "第一个结果", "value": "", "enabled": True},
                {"name": "等待详情", "kind": "wait", "target": "", "value": str(legacy.get("open_wait_seconds", 2)), "enabled": True},
                {"name": "点击播放", "kind": "click", "target": "播放按钮", "value": "", "enabled": True},
                {"name": "等待本首结束", "kind": "wait", "target": "", "value": "{total}", "enabled": True},
            ],
        }

    def song_from_data(self, item):
        return Song(
            title=item.get("title", ""),
            keyword=item.get("keyword", item.get("title", "")),
            duration_seconds=int(item.get("duration_seconds", 0)),
            buffer_seconds=int(item.get("buffer_seconds", 5)),
            enabled=bool(item.get("enabled", True)),
            step_preset=item.get("step_preset", ""),
        )

    def load_song_groups(self, data):
        if isinstance(data, dict):
            groups = [
                SongGroup(name=item.get("name", "默认"), songs=[self.song_from_data(song) for song in item.get("songs", [])], step_preset=item.get("step_preset", ""))
                for item in data.get("song_groups", [])
            ]
            if not groups:
                groups = [SongGroup(name="默认", songs=[], step_preset="")]
            active = data.get("active_song_group", groups[0].name)
            if active != "全部" and not any(group.name == active for group in groups):
                active = groups[0].name
            return groups, active
        songs = [self.song_from_data(item) for item in data] if isinstance(data, list) else []
        return [SongGroup(name="默认", songs=songs, step_preset="")], "默认"

    def find_song_group(self, name):
        return next((group for group in self.song_groups if group.name == name), None)

    def current_song_group(self):
        group = self.find_song_group(self.active_song_group.get())
        return group or self.song_groups[0]

    def is_all_songs_view(self):
        return self.active_song_group.get() == "全部"

    def current_songs(self):
        if self.is_all_songs_view():
            return [song for group in self.song_groups for song in group.songs]
        return self.current_song_group().songs

    def unique_song_group_name(self, base):
        existing = {group.name for group in self.song_groups}
        if base not in existing and base != "全部":
            return base
        index = 2
        while f"{base} {index}" in existing:
            index += 1
        return f"{base} {index}"

    def load_step_presets(self, data):
        presets = []
        if isinstance(data, list):
            for item in data:
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                presets.append({"name": name, "steps": [self.step_from_data(step) for step in item.get("steps", [])]})
        return presets


    def step_data_list(self, steps):
        return [asdict(step) for step in steps]

    def loaded_step_preset(self):
        name = getattr(self, "loaded_step_preset_name", "")
        return self.find_step_preset(name) if name else None

    def step_preset_has_unsaved_changes(self):
        preset = self.loaded_step_preset()
        if not preset:
            return False
        return self.step_data_list(self.steps) != self.step_data_list(preset["steps"])

    def save_loaded_step_preset(self):
        preset = self.loaded_step_preset()
        if not preset:
            return False
        preset["steps"] = self.clone_steps(self.steps)
        self.active_step_preset.set(preset["name"])
        self.persist()
        self.refresh_step_presets()
        self.write_log(f"已保存动作预设：{preset['name']}")
        return True

    def confirm_save_dirty_step_preset(self, action_text):
        if not self.step_preset_has_unsaved_changes():
            return True
        name = getattr(self, "loaded_step_preset_name", "")
        result = messagebox.askyesnocancel(
            "保存动作预设",
            f"动作预设「{name}」有未保存的修改。要先保存再{action_text}吗？\n\n是：保存后继续\n否：不保存继续\n取消：留在当前编辑区",
            parent=self,
        )
        if result is None:
            return False
        if result:
            return self.save_loaded_step_preset()
        return True
    def step_preset_names(self):
        return [preset["name"] for preset in self.step_presets]

    def find_step_preset(self, name):
        return next((preset for preset in self.step_presets if preset["name"] == name), None)

    def clone_steps(self, steps):
        return [Step(name=step.name, kind=step.kind, target=step.target, value=step.value, enabled=step.enabled, wait_after=step.wait_after) for step in steps]

    def step_from_data(self, item):
        data = dict(item)
        data.setdefault("wait_after", "")
        return Step(**data)

    def load_image_targets(self, data):
        targets = []
        if isinstance(data, list):
            for item in data:
                name = str(item.get("name", "")).strip()
                template_path = str(item.get("template_path", "")).strip()
                if not name:
                    continue
                try:
                    threshold = float(item.get("threshold", 0.85))
                except (TypeError, ValueError):
                    threshold = 0.85
                try:
                    retry_seconds = float(item.get("retry_seconds", 3.0))
                except (TypeError, ValueError):
                    retry_seconds = 3.0
                try:
                    offset_x = int(item.get("offset_x", 0))
                    offset_y = int(item.get("offset_y", 0))
                except (TypeError, ValueError):
                    offset_x = 0
                    offset_y = 0
                targets.append(ImageTarget(
                    name=name,
                    template_path=template_path,
                    region=str(item.get("region", "")).strip(),
                    threshold=threshold,
                    offset_x=offset_x,
                    offset_y=offset_y,
                    retry_seconds=retry_seconds,
                ))
        return targets

    def find_image_target(self, name):
        target_name = (name or "").strip()
        return next((target for target in self.image_targets if target.name == target_name), None)

    def unique_image_target_name(self, base):
        existing = {target.name for target in self.image_targets}
        if base not in existing:
            return base
        index = 2
        while f"{base} {index}" in existing:
            index += 1
        return f"{base} {index}"
    def load_point_groups(self, data):
        raw_groups = data.get("point_groups") or []
        groups = []
        if raw_groups:
            for group in raw_groups:
                points = [PointDef(**point) for point in group.get("points", [])]
                groups.append(PointGroup(name=group.get("name", "未命名"), points=points))
        else:
            legacy_points = data.get("points", [])
            points = [PointDef(**point) for point in legacy_points]
            name = data.get("active_point_group") or "逆水寒"
            groups.append(PointGroup(name=name, points=points))
        if not groups:
            groups.append(PointGroup(name="默认", points=[]))
        return groups

    def find_point_group(self, name):
        for group in self.point_groups:
            if group.name == name:
                return group
        return None

    def current_group(self):
        group = self.find_point_group(self.active_point_group.get())
        if group is None:
            group = self.point_groups[0]
            self.active_point_group.set(group.name)
        return group

    def current_points(self):
        return self.current_group().points
    def setup_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        self.option_add("*Font", "{Microsoft YaHei UI} 10")
        self.tk.call("tk", "scaling", 1.25)
        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(family="Microsoft YaHei UI", size=10)
        text_font = tkfont.nametofont("TkTextFont")
        text_font.configure(family="Microsoft YaHei UI", size=10)
        fixed_font = tkfont.nametofont("TkFixedFont")
        fixed_font.configure(family="Cascadia Mono", size=10)
        style.configure(".", font=("Microsoft YaHei UI", 10), background=self.colors["bg"], foreground=self.colors["text"], fieldbackground=self.colors["panel2"], bordercolor=self.colors["line"], lightcolor=self.colors["line"], darkcolor=self.colors["line"])
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Panel.TFrame", background=self.colors["panel"])
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"])
        style.configure("Muted.TLabel", foreground=self.colors["muted"])
        style.configure("Panel.TLabel", background=self.colors["panel"], foreground=self.colors["text"])
        style.configure("TButton", background=self.colors["panel2"], foreground=self.colors["text"], padding=(12, 8), borderwidth=0)
        style.map("TButton", background=[("active", "#2a3140")])
        style.configure("Accent.TButton", background=self.colors["accent"], foreground="#07110e", padding=(14, 8), borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#8ce6c9")])
        style.configure("TEntry", padding=8, insertcolor=self.colors["text"], fieldbackground=self.colors["panel2"], foreground=self.colors["text"], borderwidth=0)
        style.configure(
            "TCombobox",
            padding=7,
            background=self.colors["panel2"],
            fieldbackground=self.colors["panel2"],
            foreground=self.colors["text"],
            selectbackground=self.colors["panel2"],
            selectforeground=self.colors["text"],
            arrowcolor=self.colors["text"],
            bordercolor=self.colors["line"],
            lightcolor=self.colors["panel2"],
            darkcolor=self.colors["panel2"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.colors["panel2"]), ("disabled", "#151922")],
            foreground=[("readonly", self.colors["text"]), ("disabled", self.colors["muted"])],
            selectbackground=[("readonly", self.colors["panel2"])],
            selectforeground=[("readonly", self.colors["text"])],
            arrowcolor=[("active", self.colors["accent"]), ("readonly", self.colors["text"])],
        )
        self.option_add("*TCombobox*Listbox.background", self.colors["panel2"])
        self.option_add("*TCombobox*Listbox.foreground", self.colors["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", "#2b5c50")
        self.option_add("*TCombobox*Listbox.selectForeground", self.colors["text"])
        style.configure("Treeview", font=("Microsoft YaHei UI", 10), background=self.colors["panel"], fieldbackground=self.colors["panel"], foreground=self.colors["text"], rowheight=34, borderwidth=0)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"), background=self.colors["panel2"], foreground=self.colors["muted"], padding=8, borderwidth=0)
        style.map("Treeview", background=[("selected", "#2b5c50")], foreground=[("selected", self.colors["text"])])
        style.configure("TLabelframe", background=self.colors["panel"], foreground=self.colors["muted"], borderwidth=1)
        style.configure("TLabelframe.Label", background=self.colors["panel"], foreground=self.colors["muted"])
        style.configure("TCheckbutton", background=self.colors["panel"], foreground=self.colors["text"])
        style.map("TCheckbutton", background=[("active", self.colors["panel"])])

    def build_ui(self):
        shell = ttk.Frame(self, padding=16)
        shell.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(shell)
        header.pack(fill=tk.X)
        title_box = ttk.Frame(header)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(title_box, text="Macro Studio", font=("Microsoft YaHei UI", 20, "bold")).pack(anchor=tk.W)
        ttk.Label(title_box, text="点位采集、动作排序、歌单变量，一起串起来。", style="Muted.TLabel").pack(anchor=tk.W, pady=(2, 0))
        action_box = ttk.Frame(header)
        action_box.pack(side=tk.RIGHT)
        ttk.Button(action_box, text="保存", command=self.persist).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(action_box, text="运行一次", command=self.start_single).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(action_box, text="随机", variable=self.playback_random_var).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(action_box, text="循环", variable=self.playback_loop_var).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(action_box, text="播放歌单", style="Accent.TButton", command=self.start_playlist).pack(side=tk.LEFT)

        window_bar = ttk.Frame(shell, style="Panel.TFrame", padding=12)
        window_bar.pack(fill=tk.X, pady=(14, 12))
        ttk.Label(window_bar, text="窗口关键词", style="Panel.TLabel").pack(side=tk.LEFT)
        self.window_hint = tk.StringVar(value=self.config_data.get("window_hint", DEFAULT_WINDOW_HINT))
        ttk.Entry(window_bar, textvariable=self.window_hint, width=28).pack(side=tk.LEFT, padx=10)
        self.focus_var = tk.BooleanVar(value=bool(self.config_data.get("focus_window", True)))
        ttk.Checkbutton(window_bar, text="执行前聚焦窗口", variable=self.focus_var).pack(side=tk.LEFT, padx=(2, 12))
        ttk.Button(window_bar, text="检测", command=self.check_window).pack(side=tk.LEFT)
        self.window_status = tk.StringVar(value="未检测")
        ttk.Label(window_bar, textvariable=self.window_status, style="Panel.TLabel").pack(side=tk.LEFT, padx=12)
        ttk.Button(window_bar, text="暂停/继续", command=self.toggle_pause).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(window_bar, text="停止 / F9", command=self.stop_playback).pack(side=tk.RIGHT)

        main = ttk.PanedWindow(shell, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(main)
        center = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=2)
        main.add(center, weight=3)
        main.add(right, weight=2)

        self.build_points_panel(left)
        self.build_steps_panel(center)
        self.build_playlist_panel(right)

        self.log = tk.Text(shell, height=6, bg="#10141b", fg=self.colors["text"], insertbackground=self.colors["text"], relief=tk.FLAT, padx=10, pady=8, wrap=tk.WORD)
        self.log.pack(fill=tk.X, pady=(12, 0))
        self.write_log("准备好了。F8 采集当前鼠标坐标，F9 强制停止当前动作序列。")

    def build_points_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="点位", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=(0, 8))

        group_bar = ttk.Frame(frame, style="Panel.TFrame")
        group_bar.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(group_bar, text="点位组", style="Panel.TLabel").pack(side=tk.LEFT)
        self.point_group_combo = ttk.Combobox(group_bar, textvariable=self.active_point_group, width=14, values=[], state="readonly")
        self.point_group_combo.pack(side=tk.LEFT, padx=(8, 6))
        self.point_group_combo.bind("<<ComboboxSelected>>", self.on_point_group_changed)
        ttk.Button(group_bar, text="新建组", command=self.add_point_group).pack(side=tk.LEFT)
        ttk.Button(group_bar, text="重命名组", command=self.rename_point_group).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(group_bar, text="删除组", command=self.delete_point_group).pack(side=tk.LEFT, padx=(6, 0))

        self.point_table = ttk.Treeview(frame, columns=("name", "xy"), show="headings", selectmode="browse")
        self.point_table.heading("name", text="名称")
        self.point_table.heading("xy", text="坐标")
        self.point_table.column("name", width=130)
        self.point_table.column("xy", width=110, anchor=tk.CENTER)
        self.point_table.pack(fill=tk.BOTH, expand=True)

        form = ttk.Frame(frame, style="Panel.TFrame")
        form.pack(fill=tk.X, pady=(10, 0))
        self.point_name = tk.StringVar()
        ttk.Entry(form, textvariable=self.point_name).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(form, text="新增", command=self.add_point).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(form, text="重命名", command=self.rename_point).pack(side=tk.LEFT, padx=(6, 0))

        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text="F8 采集选中点位", command=self.explain_f8_capture).pack(side=tk.LEFT)
        ttk.Button(buttons, text="删除", command=self.delete_point).pack(side=tk.LEFT, padx=8)
        self.point_table.bind("<<TreeviewSelect>>", self.on_point_selected)
    def build_steps_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="动作序列", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=4)
        preset_bar = ttk.Frame(frame, style="Panel.TFrame")
        preset_bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(preset_bar, text="预设", style="Panel.TLabel").pack(side=tk.LEFT)
        self.step_preset_combo = ttk.Combobox(preset_bar, textvariable=self.active_step_preset, width=22, state="readonly")
        self.step_preset_combo.pack(side=tk.LEFT, padx=(8, 6))
        ttk.Button(preset_bar, text="图像目标", command=self.open_image_target_manager).pack(side=tk.RIGHT)

        preset_actions = ttk.Frame(frame, style="Panel.TFrame")
        preset_actions.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(preset_actions, text="新建预设", command=self.new_step_preset).pack(side=tk.LEFT)
        ttk.Button(preset_actions, text="保存预设", command=self.save_step_preset).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(preset_actions, text="载入", command=self.load_selected_step_preset).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(preset_actions, text="复制", command=self.copy_step_preset).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(preset_actions, text="重命名", command=self.rename_step_preset).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(preset_actions, text="删除", command=self.delete_step_preset).pack(side=tk.LEFT, padx=(6, 0))
        self.step_table = ttk.Treeview(frame, columns=("on", "name", "kind", "target", "value", "wait_after"), show="headings", selectmode="browse")
        for col, text, width in [
            ("on", "启用", 48), ("name", "动作", 150), ("kind", "类型", 90), ("target", "点位", 110), ("value", "参数", 130), ("wait_after", "后等待", 72)
        ]:
            self.step_table.heading(col, text=text)
            self.step_table.column(col, width=width, anchor=tk.CENTER if col in ("on", "kind") else tk.W)
        self.step_table.pack(fill=tk.BOTH, expand=True)
        self.step_table.tag_configure("drop_target", background="#315f56")
        self.step_table.bind("<<TreeviewSelect>>", self.on_step_selected)
        self.step_table.bind("<ButtonPress-1>", self.on_step_drag_start)
        self.step_table.bind("<B1-Motion>", self.on_step_drag_motion)
        self.step_table.bind("<ButtonRelease-1>", self.on_step_drag_drop)
        self.step_table.bind("<Escape>", self.cancel_step_drag)

        form = ttk.Frame(frame, style="Panel.TFrame")
        form.pack(fill=tk.X, pady=(10, 0))
        self.step_name = tk.StringVar()
        self.step_kind = tk.StringVar(value="click")
        self.step_target = tk.StringVar()
        self.step_value = tk.StringVar()
        self.step_wait_after = tk.StringVar()
        self.step_enabled = tk.BooleanVar(value=True)
        ttk.Entry(form, textvariable=self.step_name, width=18).pack(side=tk.LEFT, padx=(0, 6))
        self.kind_combo = ttk.Combobox(form, textvariable=self.step_kind, width=10, values=["click", "image_click", "paste", "wait", "key", "enter", "ctrl_a", "hotkey", "log"], state="readonly")
        self.kind_combo.pack(side=tk.LEFT, padx=(0, 6))
        self.kind_combo.bind("<<ComboboxSelected>>", self.on_step_kind_changed)
        self.target_combo = ttk.Combobox(form, textvariable=self.step_target, width=14, values=[], state="readonly")
        self.target_combo.pack(side=tk.LEFT, padx=(0, 6))
        self.value_entry = ttk.Entry(form, textvariable=self.step_value, width=18)
        self.value_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(form, text="后等待", style="Panel.TLabel").pack(side=tk.LEFT, padx=(8, 4))
        self.wait_after_entry = ttk.Entry(form, textvariable=self.step_wait_after, width=7)
        self.wait_after_entry.pack(side=tk.LEFT)
        ttk.Checkbutton(form, text="启用", variable=self.step_enabled).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(frame, text="参数：paste=粘贴文本，wait=等待时间，key=按键名，hotkey=组合键，image_click=图像目标名称；其它动作通常只填点位和后等待。", style="Muted.TLabel").pack(anchor=tk.W, pady=(8, 0))

        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text="新增", command=self.add_step).pack(side=tk.LEFT)
        ttk.Button(buttons, text="更新", command=self.update_step).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="复制", command=self.duplicate_step).pack(side=tk.LEFT)
        ttk.Button(buttons, text="删除", command=self.delete_step).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="上移", command=lambda: self.move_step(-1)).pack(side=tk.LEFT)
        ttk.Button(buttons, text="下移", command=lambda: self.move_step(1)).pack(side=tk.LEFT, padx=6)

    def build_playlist_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="歌单变量", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=(8, 0))

        group_bar = ttk.Frame(frame, style="Panel.TFrame")
        group_bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(group_bar, text="歌曲组", style="Panel.TLabel").pack(side=tk.LEFT)
        self.song_group_combo = ttk.Combobox(group_bar, textvariable=self.active_song_group, width=12, state="readonly")
        self.song_group_combo.pack(side=tk.LEFT, padx=(8, 6))
        self.song_group_combo.bind("<<ComboboxSelected>>", self.on_song_group_changed)
        ttk.Button(group_bar, text="新建", command=self.add_song_group).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(group_bar, text="重命名", command=self.rename_song_group).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(group_bar, text="删除", command=self.delete_song_group).pack(side=tk.LEFT)

        song_preset_bar = ttk.Frame(frame, style="Panel.TFrame")
        song_preset_bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(song_preset_bar, text="动作预设", style="Panel.TLabel").pack(side=tk.LEFT)
        self.song_step_preset_combo = ttk.Combobox(song_preset_bar, textvariable=self.song_group_step_preset, width=18, state="readonly")
        self.song_step_preset_combo.pack(side=tk.LEFT, padx=(8, 6))
        self.song_step_preset_combo.bind("<<ComboboxSelected>>", self.on_song_group_step_preset_changed)
        ttk.Label(song_preset_bar, text="空=使用当前动作序列", style="Muted.TLabel").pack(side=tk.LEFT)

        self.song_table = ttk.Treeview(frame, columns=("on", "group", "title", "keyword", "preset", "time"), show="headings", selectmode="browse")
        for col, text, width in [("on", "启用", 44), ("group", "分组", 68), ("title", "作品", 104), ("keyword", "搜索词", 104), ("preset", "预设", 90), ("time", "等待", 64)]:
            self.song_table.heading(col, text=text)
            self.song_table.column(col, width=width, anchor=tk.CENTER if col in ("on", "time") else tk.W)
        self.song_table.pack(fill=tk.BOTH, expand=True)
        self.song_table.bind("<<TreeviewSelect>>", self.on_song_selected)

        form = ttk.Frame(frame, style="Panel.TFrame")
        form.pack(fill=tk.X, pady=(10, 0))
        self.song_title = tk.StringVar()
        self.song_keyword = tk.StringVar()
        self.song_duration = tk.StringVar(value="03:30")
        self.song_buffer = tk.StringVar(value="5")
        self.song_step_preset = tk.StringVar(value="")
        self.song_enabled = tk.BooleanVar(value=True)
        song_row1 = ttk.Frame(form, style="Panel.TFrame")
        song_row1.pack(fill=tk.X)
        for var, width in [(self.song_title, 14), (self.song_keyword, 14), (self.song_duration, 8), (self.song_buffer, 6)]:
            ttk.Entry(song_row1, textvariable=var, width=width).pack(side=tk.LEFT, padx=(0, 6))
        song_row2 = ttk.Frame(form, style="Panel.TFrame")
        song_row2.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(song_row2, text="动作预设", style="Panel.TLabel").pack(side=tk.LEFT)
        self.song_preset_combo = ttk.Combobox(song_row2, textvariable=self.song_step_preset, width=18, state="readonly")
        self.song_preset_combo.pack(side=tk.LEFT, padx=(8, 10))
        ttk.Checkbutton(song_row2, text="启用", variable=self.song_enabled).pack(side=tk.LEFT)
        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text="新增", command=self.add_song).pack(side=tk.LEFT)
        ttk.Button(buttons, text="更新", command=self.update_song).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="删除", command=self.delete_song).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="移动到", command=self.move_song_to_group).pack(side=tk.LEFT)
        order_buttons = ttk.Frame(frame, style="Panel.TFrame")
        order_buttons.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(order_buttons, text="上移", command=lambda: self.move_song(-1)).pack(side=tk.LEFT)
        ttk.Button(order_buttons, text="下移", command=lambda: self.move_song(1)).pack(side=tk.LEFT, padx=6)
        help_text = "变量：{title} {keyword} {duration} {buffer} {total}；选择“全部”可汇总播放所有分组。"
        ttk.Label(frame, text=help_text, style="Muted.TLabel").pack(anchor=tk.W, pady=(10, 0))


    def refresh_image_targets(self):
        if not hasattr(self, "image_target_table"):
            return
        for item in self.image_target_table.get_children():
            self.image_target_table.delete(item)
        for idx, target in enumerate(self.image_targets):
            self.image_target_table.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    target.name,
                    target.template_path,
                    target.region or "全屏",
                    f"{float(target.threshold):.2f}",
                    f"{target.offset_x}, {target.offset_y}",
                    f"{float(target.retry_seconds):.1f}s",
                ),
            )

    def open_image_target_manager(self):
        if hasattr(self, "image_target_window") and self.image_target_window.winfo_exists():
            self.image_target_window.lift()
            self.image_target_window.focus_force()
            return
        win = tk.Toplevel(self)
        self.image_target_window = win
        win.title("图像目标")
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(max(1120, int(screen_w * 0.78)), max(760, screen_w - 80))
        height = min(max(760, int(screen_h * 0.78)), max(560, screen_h - 100))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.minsize(min(980, width), min(680, height))
        win.configure(bg=self.colors["bg"])
        win.transient(self)

        scroll_host = ttk.Frame(win)
        scroll_host.pack(fill=tk.BOTH, expand=True)
        scroll_canvas = tk.Canvas(scroll_host, bg=self.colors["bg"], highlightthickness=0)
        scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_bar = ttk.Scrollbar(scroll_host, orient=tk.VERTICAL, command=scroll_canvas.yview)
        scroll_bar.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_canvas.configure(yscrollcommand=scroll_bar.set)
        shell = ttk.Frame(scroll_canvas, padding=14)
        shell_id = scroll_canvas.create_window((0, 0), window=shell, anchor=tk.NW)
        shell.bind("<Configure>", lambda _event: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>", lambda event: scroll_canvas.itemconfigure(shell_id, width=event.width))
        scroll_canvas.bind_all("<MouseWheel>", lambda event: scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))
        win.bind("<Destroy>", lambda event: scroll_canvas.unbind_all("<MouseWheel>") if event.widget is win else None)
        ttk.Label(shell, text="图像目标", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor=tk.W)
        ttk.Label(shell, text="image_click 会按名称读取这里的模板，识别到后点击模板中心。", style="Muted.TLabel").pack(anchor=tk.W, pady=(2, 10))

        self.image_target_table = ttk.Treeview(shell, columns=("name", "template", "region", "threshold", "offset", "retry"), show="headings", selectmode="browse", height=8)
        for col, label, width in [
            ("name", "名称", 120),
            ("template", "模板图", 280),
            ("region", "区域", 120),
            ("threshold", "阈值", 70),
            ("offset", "偏移", 80),
            ("retry", "重试", 70),
        ]:
            self.image_target_table.heading(col, text=label)
            self.image_target_table.column(col, width=width, anchor=tk.CENTER if col in ("threshold", "offset", "retry") else tk.W)
        self.image_target_table.pack(fill=tk.BOTH, expand=True)
        self.image_target_table.bind("<<TreeviewSelect>>", self.on_image_target_selected)

        form = ttk.Frame(shell, style="Panel.TFrame", padding=10)
        form.pack(fill=tk.X, pady=(10, 0))
        self.image_target_name = tk.StringVar()
        self.image_target_template = tk.StringVar()
        self.image_target_region = tk.StringVar()
        self.image_target_threshold = tk.StringVar(value="0.85")
        self.image_target_offset_x = tk.StringVar(value="0")
        self.image_target_offset_y = tk.StringVar(value="0")
        self.image_target_retry = tk.StringVar(value="3")

        row1 = ttk.Frame(form, style="Panel.TFrame")
        row1.pack(fill=tk.X)
        ttk.Label(row1, text="名称", style="Panel.TLabel").pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.image_target_name, width=18).pack(side=tk.LEFT, padx=(6, 10))
        ttk.Label(row1, text="模板", style="Panel.TLabel").pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.image_target_template).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        ttk.Button(row1, text="选择图片", command=self.choose_image_target_file).pack(side=tk.LEFT)
        ttk.Button(row1, text="读取剪贴板", command=self.choose_image_target_clipboard).pack(side=tk.LEFT, padx=(6, 0))

        row2 = ttk.Frame(form, style="Panel.TFrame")
        row2.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(row2, text="识别区域", style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(row2, textvariable=self.image_target_region, width=24).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(row2, text="拖拽选区 Ctrl+R", command=self.start_image_region_capture).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row2, text="全屏", command=lambda: self.image_target_region.set("")).pack(side=tk.LEFT)

        row3 = ttk.Frame(form, style="Panel.TFrame")
        row3.pack(fill=tk.X, pady=(8, 0))
        for label, var, width in [
            ("阈值", self.image_target_threshold, 7),
            ("偏移X", self.image_target_offset_x, 7),
            ("偏移Y", self.image_target_offset_y, 7),
            ("重试秒", self.image_target_retry, 7),
        ]:
            ttk.Label(row3, text=label, style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 4))
            ttk.Entry(row3, textvariable=var, width=width).pack(side=tk.LEFT, padx=(0, 12))

        preview = ttk.Frame(shell, style="Panel.TFrame", padding=10)
        preview.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(preview, text="模板预览", style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 10))
        self.image_target_preview = tk.Label(preview, text="暂无图片", width=34, height=8, bg="#10141b", fg=self.colors["muted"], anchor=tk.CENTER, relief=tk.FLAT)
        self.image_target_preview.pack(side=tk.LEFT)
        self.image_target_preview_info = tk.StringVar(value="选择或读取剪贴板后显示预览")
        ttk.Label(preview, textvariable=self.image_target_preview_info, style="Muted.TLabel").pack(side=tk.LEFT, padx=(12, 0), fill=tk.X, expand=True)
        self.image_target_preview_image = None

        actions = ttk.Frame(shell)
        actions.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(actions, text="新增", command=self.add_image_target).pack(side=tk.LEFT)
        ttk.Button(actions, text="更新", command=self.update_image_target).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="复制", command=self.duplicate_image_target).pack(side=tk.LEFT)
        ttk.Button(actions, text="删除", command=self.delete_image_target).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="填入当前动作", command=self.use_image_target_in_step).pack(side=tk.RIGHT)

        self.refresh_image_targets()



    def start_image_region_capture(self):
        if hasattr(self, "region_capture_window") and self.region_capture_window.winfo_exists():
            self.region_capture_window.lift()
            return
        self.region_capture_restore_state = {
            "root_state": self.state(),
            "image_target_visible": hasattr(self, "image_target_window") and self.image_target_window.winfo_exists() and self.image_target_window.state() != "withdrawn",
        }
        self.withdraw()
        if hasattr(self, "image_target_window") and self.image_target_window.winfo_exists():
            self.image_target_window.withdraw()
        overlay = tk.Toplevel(self)
        self.region_capture_window = overlay
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        try:
            overlay.attributes("-alpha", 0.32)
        except tk.TclError:
            pass
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        overlay.geometry(f"{screen_w}x{screen_h}+0+0")
        overlay.configure(bg="black")
        canvas = tk.Canvas(overlay, bg="black", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill=tk.BOTH, expand=True)
        self.region_capture_canvas = canvas
        self.region_capture_start = None
        self.region_capture_rect = None
        self.region_capture_text = canvas.create_text(
            screen_w // 2,
            36,
            text="拖拽选择识别区域，松开确认；Esc 或右键取消",
            fill="#ffffff",
            font=("Microsoft YaHei UI", 16, "bold"),
        )
        overlay.bind("<Escape>", self.cancel_image_region_capture)
        overlay.bind("<Button-3>", self.cancel_image_region_capture)
        canvas.bind("<ButtonPress-1>", self.on_image_region_drag_start)
        canvas.bind("<B1-Motion>", self.on_image_region_drag_motion)
        canvas.bind("<ButtonRelease-1>", self.on_image_region_drag_release)
        overlay.focus_force()
        try:
            overlay.grab_set()
        except tk.TclError:
            pass
        self.write_log("拖拽选择图像识别区域，Esc 或右键取消。")

    def on_image_region_drag_start(self, event):
        self.region_capture_start = (event.x_root, event.y_root, event.x, event.y)
        if self.region_capture_rect:
            self.region_capture_canvas.delete(self.region_capture_rect)
            self.region_capture_rect = None

    def on_image_region_drag_motion(self, event):
        if not self.region_capture_start:
            return
        _start_root_x, _start_root_y, start_x, start_y = self.region_capture_start
        if self.region_capture_rect:
            self.region_capture_canvas.delete(self.region_capture_rect)
        self.region_capture_rect = self.region_capture_canvas.create_rectangle(
            start_x,
            start_y,
            event.x,
            event.y,
            outline=self.colors["accent"],
            width=3,
        )

    def on_image_region_drag_release(self, event):
        if not self.region_capture_start:
            self.cancel_image_region_capture()
            return
        start_root_x, start_root_y, _start_x, _start_y = self.region_capture_start
        left = min(start_root_x, event.x_root)
        top = min(start_root_y, event.y_root)
        width = abs(event.x_root - start_root_x)
        height = abs(event.y_root - start_root_y)
        if width < 5 or height < 5:
            self.cancel_image_region_capture()
            self.write_log("已取消选区：区域太小。")
            return
        self.image_target_region.set(f"{left},{top},{width},{height}")
        self.finish_image_region_capture()
        self.write_log(f"已采集识别区域：{left},{top},{width},{height}")

    def cancel_image_region_capture(self, _event=None):
        self.finish_image_region_capture()
        self.write_log("已取消拖拽选区。")

    def finish_image_region_capture(self):
        if hasattr(self, "region_capture_window") and self.region_capture_window.winfo_exists():
            try:
                self.region_capture_window.grab_release()
            except tk.TclError:
                pass
            self.region_capture_window.destroy()
        self.region_capture_start = None
        self.region_capture_rect = None
        self.restore_after_region_capture()

    def restore_after_region_capture(self):
        state = getattr(self, "region_capture_restore_state", {}) or {}
        try:
            self.deiconify()
            root_state = state.get("root_state")
            if root_state == "zoomed":
                self.state("zoomed")
            elif root_state == "iconic":
                self.state("normal")
        except tk.TclError:
            pass
        if state.get("image_target_visible") and hasattr(self, "image_target_window") and self.image_target_window.winfo_exists():
            try:
                self.image_target_window.deiconify()
                self.image_target_window.lift()
                self.image_target_window.focus_force()
            except tk.TclError:
                pass
        self.region_capture_restore_state = {}
    def update_image_target_preview(self):
        if not hasattr(self, "image_target_preview"):
            return
        path = self.image_target_template.get().strip()
        self.image_target_preview.configure(image="", text="暂无图片")
        self.image_target_preview_image = None
        if not path:
            self.image_target_preview_info.set("选择或读取剪贴板后显示预览")
            return
        if not os.path.exists(path):
            self.image_target_preview_info.set(f"文件不存在：{path}")
            return
        try:
            from PIL import Image, ImageTk
            image = Image.open(path).convert("RGB")
            original_w, original_h = image.size
            max_w, max_h = 240, 140
            ratio = min(max_w / original_w, max_h / original_h, 1.0)
            preview_w = max(1, int(original_w * ratio))
            preview_h = max(1, int(original_h * ratio))
            image = image.resize((preview_w, preview_h), Image.LANCZOS)
            photo = ImageTk.PhotoImage(image)
        except Exception as exc:
            self.image_target_preview_info.set(f"无法预览：{exc}")
            return
        self.image_target_preview_image = photo
        self.image_target_preview.configure(image=photo, text="")
        self.image_target_preview_info.set(f"{original_w} x {original_h}，预览 {preview_w} x {preview_h}")
    def image_target_index(self):
        if not hasattr(self, "image_target_table"):
            return None
        selection = self.image_target_table.selection()
        return int(selection[0]) if selection else None

    def on_image_target_selected(self, _event=None):
        idx = self.image_target_index()
        if idx is None or idx < 0 or idx >= len(self.image_targets):
            return
        target = self.image_targets[idx]
        self.image_target_name.set(target.name)
        self.image_target_template.set(target.template_path)
        self.image_target_region.set(target.region)
        self.image_target_threshold.set(str(target.threshold))
        self.image_target_offset_x.set(str(target.offset_x))
        self.image_target_offset_y.set(str(target.offset_y))
        self.image_target_retry.set(str(target.retry_seconds))
        self.update_image_target_preview()


    def safe_template_filename(self, name):
        base = (name or "").strip() or time.strftime("clipboard_%Y%m%d_%H%M%S")
        base = re.sub(r"[\\/:*?\"<>|]+", "_", base)
        base = re.sub(r"\s+", "_", base).strip("._ ")
        return base or time.strftime("clipboard_%Y%m%d_%H%M%S")

    def unique_template_path(self, name):
        folder = os.path.join(APP_DIR, "image_templates")
        os.makedirs(folder, exist_ok=True)
        base = self.safe_template_filename(name)
        path = os.path.join(folder, f"{base}.png")
        index = 2
        while os.path.exists(path):
            path = os.path.join(folder, f"{base}_{index}.png")
            index += 1
        return path

    def choose_image_target_clipboard(self):
        try:
            from PIL import Image, ImageGrab
        except Exception as exc:
            messagebox.showerror("读取剪贴板", "读取剪贴板截图需要 Pillow。", parent=getattr(self, "image_target_window", self))
            return
        try:
            data = ImageGrab.grabclipboard()
        except Exception as exc:
            messagebox.showerror("读取剪贴板", f"无法读取剪贴板：{exc}", parent=getattr(self, "image_target_window", self))
            return
        image = None
        if isinstance(data, Image.Image):
            image = data
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, str) and os.path.exists(item):
                    try:
                        image = Image.open(item)
                        break
                    except OSError:
                        continue
        if image is None:
            messagebox.showwarning("读取剪贴板", "剪贴板里没有可用的截图。可以先用 Win+Shift+S 截图后再点这里。", parent=getattr(self, "image_target_window", self))
            return
        if not self.image_target_name.get().strip():
            self.image_target_name.set(self.unique_image_target_name("剪贴板模板"))
        path = self.unique_template_path(self.image_target_name.get())
        image.convert("RGB").save(path, "PNG")
        self.image_target_template.set(path)
        self.write_log(f"已从剪贴板保存模板图：{path}")
    def choose_image_target_file(self):
        path = filedialog.askopenfilename(
            parent=getattr(self, "image_target_window", self),
            title="选择模板图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")],
        )
        if path:
            self.image_target_template.set(path)
            if not self.image_target_name.get().strip():
                self.image_target_name.set(self.unique_image_target_name(os.path.splitext(os.path.basename(path))[0]))
            self.update_image_target_preview()

    def build_image_target_from_form(self):
        name = self.image_target_name.get().strip()
        if not name:
            raise ValueError("请输入图像目标名称。")
        template_path = self.image_target_template.get().strip()
        if not template_path:
            raise ValueError("请选择模板图片。")
        try:
            threshold = float(self.image_target_threshold.get().strip() or "0.85")
            offset_x = int(float(self.image_target_offset_x.get().strip() or "0"))
            offset_y = int(float(self.image_target_offset_y.get().strip() or "0"))
            retry_seconds = float(self.image_target_retry.get().strip() or "3")
        except ValueError as exc:
            raise ValueError("阈值、偏移和重试秒数需要填写数字。") from exc
        if threshold <= 0 or threshold > 1:
            raise ValueError("阈值应在 0 到 1 之间，例如 0.85。")
        if retry_seconds < 0:
            raise ValueError("重试秒数不能小于 0。")
        return ImageTarget(
            name=name,
            template_path=template_path,
            region=self.image_target_region.get().strip(),
            threshold=threshold,
            offset_x=offset_x,
            offset_y=offset_y,
            retry_seconds=retry_seconds,
        )

    def add_image_target(self):
        try:
            target = self.build_image_target_from_form()
        except ValueError as exc:
            messagebox.showwarning("图像目标", str(exc), parent=getattr(self, "image_target_window", self))
            return
        if self.find_image_target(target.name):
            messagebox.showwarning("名称重复", "已经有同名图像目标。", parent=getattr(self, "image_target_window", self))
            return
        self.image_targets.append(target)
        self.persist()
        self.refresh_image_targets()
        self.image_target_table.selection_set(str(len(self.image_targets) - 1))
        self.write_log(f"已新增图像目标：{target.name}")

    def update_image_target(self):
        idx = self.image_target_index()
        if idx is None or idx < 0 or idx >= len(self.image_targets):
            messagebox.showwarning("先选目标", "请先选择要更新的图像目标。", parent=getattr(self, "image_target_window", self))
            return
        old_name = self.image_targets[idx].name
        try:
            target = self.build_image_target_from_form()
        except ValueError as exc:
            messagebox.showwarning("图像目标", str(exc), parent=getattr(self, "image_target_window", self))
            return
        if target.name != old_name and self.find_image_target(target.name):
            messagebox.showwarning("名称重复", "已经有同名图像目标。", parent=getattr(self, "image_target_window", self))
            return
        self.image_targets[idx] = target
        if target.name != old_name:
            self.rename_image_target_refs(old_name, target.name)
        self.persist()
        self.refresh_image_targets()
        self.refresh_steps()
        self.image_target_table.selection_set(str(idx))
        self.write_log(f"已更新图像目标：{target.name}")

    def duplicate_image_target(self):
        idx = self.image_target_index()
        if idx is None or idx < 0 or idx >= len(self.image_targets):
            messagebox.showwarning("先选目标", "请先选择要复制的图像目标。", parent=getattr(self, "image_target_window", self))
            return
        source = self.image_targets[idx]
        target = ImageTarget(
            name=self.unique_image_target_name(f"{source.name} 副本"),
            template_path=source.template_path,
            region=source.region,
            threshold=source.threshold,
            offset_x=source.offset_x,
            offset_y=source.offset_y,
            retry_seconds=source.retry_seconds,
        )
        self.image_targets.append(target)
        self.persist()
        self.refresh_image_targets()
        self.image_target_table.selection_set(str(len(self.image_targets) - 1))
        self.write_log(f"已复制图像目标：{source.name}")

    def delete_image_target(self):
        idx = self.image_target_index()
        if idx is None or idx < 0 or idx >= len(self.image_targets):
            messagebox.showwarning("先选目标", "请先选择要删除的图像目标。", parent=getattr(self, "image_target_window", self))
            return
        target = self.image_targets[idx]
        if not messagebox.askyesno("删除图像目标", f"确定删除图像目标「{target.name}」吗？引用它的 image_click 参数会被清空。", parent=getattr(self, "image_target_window", self)):
            return
        del self.image_targets[idx]
        self.rename_image_target_refs(target.name, "")
        self.persist()
        self.refresh_image_targets()
        self.refresh_steps()
        self.write_log(f"已删除图像目标：{target.name}")

    def rename_image_target_refs(self, old_name, new_name):
        for step in self.steps:
            if step.kind == "image_click" and step.value == old_name:
                step.value = new_name
        for preset in self.step_presets:
            for step in preset["steps"]:
                if step.kind == "image_click" and step.value == old_name:
                    step.value = new_name

    def use_image_target_in_step(self):
        idx = self.image_target_index()
        if idx is None or idx < 0 or idx >= len(self.image_targets):
            messagebox.showwarning("先选目标", "请先选择一个图像目标。", parent=getattr(self, "image_target_window", self))
            return
        target = self.image_targets[idx]
        self.step_kind.set("image_click")
        self.step_value.set(target.name)
        self.step_target.set("")
        self.update_step_form_state()
        self.write_log(f"当前动作参数已填入图像目标：{target.name}")
    def refresh_all(self):
        self.points = self.current_points()
        self.refresh_point_groups()
        self.refresh_points()
        self.refresh_steps()
        self.refresh_step_presets()
        self.refresh_song_groups()
        self.refresh_songs()
        self.target_combo.configure(values=[p.name for p in self.points])

    def refresh_point_groups(self):
        if hasattr(self, "point_group_combo"):
            names = [group.name for group in self.point_groups]
            self.point_group_combo.configure(values=names)
            if self.active_point_group.get() not in names and names:
                self.active_point_group.set(names[0])
    def refresh_points(self):
        self.points = self.current_points()
        for item in self.point_table.get_children():
            self.point_table.delete(item)
        for idx, point in enumerate(self.points):
            xy = "未采集" if point.x == 0 and point.y == 0 else f"{point.x}, {point.y}"
            self.point_table.insert("", tk.END, iid=str(idx), values=(point.name, xy))

    def refresh_step_presets(self):
        names = self.step_preset_names()
        if hasattr(self, "step_preset_combo"):
            self.step_preset_combo.configure(values=names)
            if self.active_step_preset.get() and self.active_step_preset.get() not in names:
                self.active_step_preset.set("")
        if hasattr(self, "song_step_preset_combo"):
            self.song_step_preset_combo.configure(values=[""] + names)
            self.sync_song_group_step_preset()
        if hasattr(self, "song_preset_combo"):
            self.song_preset_combo.configure(values=[""] + names)


    def new_step_preset(self):
        if not self.confirm_save_dirty_step_preset("新建空预设"):
            return
        default_name = self.unique_step_preset_name("新动作预设")
        name = simpledialog.askstring("新建动作预设", "预设名称：", initialvalue=default_name, parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if self.find_step_preset(name):
            messagebox.showwarning("名称重复", "已经有同名动作预设。")
            return
        if self.steps and not messagebox.askyesno("新建预设", "新建空预设会清空当前动作序列编辑区，继续吗？"):
            return
        self.step_presets.append({"name": name, "steps": []})
        self.active_step_preset.set(name)
        self.loaded_step_preset_name = name
        self.steps = []
        self.persist()
        self.refresh_step_presets()
        self.refresh_steps()
        self.update_step_form_state()
        self.write_log(f"已新建动作预设：{name}")

    def save_step_preset(self):
        name = simpledialog.askstring("保存动作预设", "预设名称：", initialvalue=self.active_step_preset.get(), parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        existing = self.find_step_preset(name)
        if existing and not messagebox.askyesno("覆盖预设", f"预设「{name}」已经存在，要覆盖吗？"):
            return
        snapshot = self.clone_steps(self.steps)
        if existing:
            existing["steps"] = snapshot
        else:
            self.step_presets.append({"name": name, "steps": snapshot})
        self.active_step_preset.set(name)
        self.loaded_step_preset_name = name
        self.persist()
        self.refresh_step_presets()
        self.write_log(f"已保存动作预设：{name}")

    def load_selected_step_preset(self):
        name = self.active_step_preset.get().strip()
        if not name:
            messagebox.showwarning("先选预设", "请先选择要载入的动作预设。")
            return
        preset = self.find_step_preset(name)
        if not preset:
            messagebox.showwarning("预设不存在", "这个动作预设已经不存在。")
            self.refresh_step_presets()
            return
        previous_loaded = getattr(self, "loaded_step_preset_name", "")
        if not self.confirm_save_dirty_step_preset(f"载入「{name}」"):
            self.active_step_preset.set(previous_loaded)
            return
        if self.steps and name != previous_loaded and not messagebox.askyesno("载入预设", f"载入「{name}」会替换当前动作序列，继续吗？"):
            self.active_step_preset.set(previous_loaded)
            return
        self.steps = self.clone_steps(preset["steps"])
        self.loaded_step_preset_name = name
        self.active_step_preset.set(name)
        self.persist()
        self.refresh_steps()
        self.write_log(f"已载入动作预设：{name}")
    def copy_step_preset(self):
        source_name = self.active_step_preset.get().strip()
        if not source_name:
            messagebox.showwarning("先选预设", "请先选择要复制的动作预设。")
            return
        preset = self.find_step_preset(source_name)
        if not preset:
            messagebox.showwarning("预设不存在", "这个动作预设已经不存在。")
            self.refresh_step_presets()
            return
        default_name = self.unique_step_preset_name(f"{source_name} 副本")
        name = simpledialog.askstring("复制动作预设", "新预设名称：", initialvalue=default_name, parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if self.find_step_preset(name):
            messagebox.showwarning("名称重复", "已经有同名动作预设。")
            return
        self.step_presets.append({"name": name, "steps": self.clone_steps(preset["steps"])})
        self.active_step_preset.set(name)
        self.persist()
        self.refresh_step_presets()
        self.write_log(f"已复制动作预设：{source_name} -> {name}")

    def rename_step_preset(self):
        old_name = self.active_step_preset.get().strip()
        if not old_name:
            messagebox.showwarning("先选预设", "请先选择要重命名的动作预设。")
            return
        preset = self.find_step_preset(old_name)
        if not preset:
            messagebox.showwarning("预设不存在", "这个动作预设已经不存在。")
            self.refresh_step_presets()
            return
        new_name = simpledialog.askstring("重命名动作预设", "新预设名称：", initialvalue=old_name, parent=self)
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        if self.find_step_preset(new_name):
            messagebox.showwarning("名称重复", "已经有同名动作预设。")
            return
        preset["name"] = new_name
        for group in self.song_groups:
            if group.step_preset == old_name:
                group.step_preset = new_name
            for song in group.songs:
                if getattr(song, "step_preset", "") == old_name:
                    song.step_preset = new_name
        self.active_step_preset.set(new_name)
        self.persist()
        self.refresh_step_presets()
        self.refresh_songs()
        self.write_log(f"已重命名动作预设：{old_name} -> {new_name}")
    def unique_step_preset_name(self, base):
        existing = set(self.step_preset_names())
        if base not in existing:
            return base
        index = 2
        while f"{base} {index}" in existing:
            index += 1
        return f"{base} {index}"
    def delete_step_preset(self):
        name = self.active_step_preset.get().strip()
        if not name:
            messagebox.showwarning("先选预设", "请先选择要删除的动作预设。")
            return
        preset = self.find_step_preset(name)
        if not preset:
            self.refresh_step_presets()
            return
        if not messagebox.askyesno("删除预设", f"确定删除动作预设「{name}」吗？"):
            return
        self.step_presets.remove(preset)
        for group in self.song_groups:
            if group.step_preset == name:
                group.step_preset = ""
            for song in group.songs:
                if getattr(song, "step_preset", "") == name:
                    song.step_preset = ""
        self.active_step_preset.set("")
        self.persist()
        self.refresh_step_presets()
        self.write_log(f"已删除动作预设：{name}")

    def refresh_steps(self):
        for item in self.step_table.get_children():
            self.step_table.delete(item)
        for idx, step in enumerate(self.steps):
            self.step_table.insert("", tk.END, iid=str(idx), values=("是" if step.enabled else "否", step.name, step.kind, step.target, step.value, step.wait_after))

    def refresh_song_groups(self):
        if hasattr(self, "song_group_combo"):
            names = ["全部"] + [group.name for group in self.song_groups]
            self.song_group_combo.configure(values=names)
            if self.active_song_group.get() not in names:
                self.active_song_group.set(self.song_groups[0].name)

    def refresh_songs(self):
        self.songs = self.current_songs()
        self.song_view_refs = []
        for item in self.song_table.get_children():
            self.song_table.delete(item)
        for group in self.song_groups:
            if not self.is_all_songs_view() and group.name != self.active_song_group.get():
                continue
            for song_index, song in enumerate(group.songs):
                iid = str(len(self.song_view_refs))
                self.song_view_refs.append((group, song_index, song))
                self.song_table.insert("", tk.END, iid=iid, values=("是" if song.enabled else "否", group.name, song.title, song.keyword, song.step_preset or "继承", format_duration(song.duration_seconds + song.buffer_seconds)))

    def selected_song_ref(self):
        idx = self.table_index(self.song_table)
        if idx is None or idx < 0 or idx >= len(self.song_view_refs):
            return None
        return self.song_view_refs[idx]

    def select_song_object(self, song):
        for idx, (_group, _song_index, item) in enumerate(self.song_view_refs):
            if item is song:
                self.song_table.selection_set(str(idx))
                self.song_table.see(str(idx))
                return
    def table_index(self, table):
        selection = table.selection()
        return int(selection[0]) if selection else None

    def sync_song_group_step_preset(self):
        if not hasattr(self, "song_step_preset_combo"):
            return
        if self.is_all_songs_view():
            self.song_group_step_preset.set("按歌曲组")
            self.song_step_preset_combo.configure(state="disabled")
            return
        group = self.current_song_group()
        names = self.step_preset_names()
        if group.step_preset and group.step_preset not in names:
            group.step_preset = ""
        self.song_group_step_preset.set(group.step_preset)
        self.song_step_preset_combo.configure(state="readonly")

    def on_song_group_step_preset_changed(self, _event=None):
        if self.is_all_songs_view():
            self.sync_song_group_step_preset()
            return
        group = self.current_song_group()
        value = self.song_group_step_preset.get().strip()
        group.step_preset = value if self.find_step_preset(value) else ""
        self.song_group_step_preset.set(group.step_preset)
        self.persist()
        label = group.step_preset or "当前动作序列"
        self.write_log(f"歌曲组「{group.name}」动作预设：{label}")
    def on_song_group_changed(self, _event=None):
        self.song_table.selection_remove(self.song_table.selection())
        self.song_title.set("")
        self.song_keyword.set("")
        self.song_step_preset.set("")
        self.refresh_songs()
        self.sync_song_group_step_preset()
        self.write_log(f"已切换歌曲组：{self.active_song_group.get()}")

    def add_song_group(self):
        name = simpledialog.askstring("新建歌曲组", "歌曲组名称：", parent=self)
        if not name:
            return
        name = self.unique_song_group_name(name.strip())
        self.song_groups.append(SongGroup(name=name, songs=[], step_preset=""))
        self.active_song_group.set(name)
        self.persist()
        self.refresh_song_groups()
        self.refresh_songs()
        self.write_log(f"已新建歌曲组：{name}")

    def rename_song_group(self):
        if self.is_all_songs_view():
            messagebox.showwarning("不能重命名", "“全部”是汇总视图，不能重命名。")
            return
        group = self.current_song_group()
        name = simpledialog.askstring("重命名歌曲组", "新名称：", initialvalue=group.name, parent=self)
        if not name:
            return
        name = name.strip()
        if name == "全部":
            messagebox.showwarning("名称保留", "“全部”是系统保留名称。")
            return
        if name != group.name and self.find_song_group(name):
            messagebox.showwarning("名称重复", "已经有同名歌曲组。")
            return
        old_name = group.name
        group.name = name
        self.active_song_group.set(name)
        self.persist()
        self.refresh_song_groups()
        self.refresh_songs()
        self.write_log(f"已重命名歌曲组：{old_name} -> {name}")

    def delete_song_group(self):
        if self.is_all_songs_view():
            messagebox.showwarning("不能删除", "“全部”是汇总视图，不能删除。")
            return
        if len(self.song_groups) <= 1:
            messagebox.showwarning("不能删除", "至少需要保留一个歌曲组。")
            return
        group = self.current_song_group()
        if not messagebox.askyesno("删除歌曲组", f"确定删除歌曲组「{group.name}」吗？其中歌曲会一起删除。"):
            return
        self.song_groups.remove(group)
        self.active_song_group.set(self.song_groups[0].name)
        self.persist()
        self.refresh_song_groups()
        self.refresh_songs()
        self.write_log(f"已删除歌曲组：{group.name}")
    def on_point_group_changed(self, _event=None):
        self.points = self.current_points()
        self.point_table.selection_remove(self.point_table.selection())
        self.point_name.set("")
        self.refresh_all()
        self.write_log(f"已切换点位组：{self.active_point_group.get()}")

    def unique_group_name(self, base):
        existing = {group.name for group in self.point_groups}
        if base not in existing:
            return base
        index = 2
        while f"{base} {index}" in existing:
            index += 1
        return f"{base} {index}"

    def add_point_group(self):
        name = simpledialog.askstring("新建点位组", "点位组名称：", parent=self)
        if not name:
            return
        name = self.unique_group_name(name.strip())
        self.point_groups.append(PointGroup(name=name, points=[]))
        self.active_point_group.set(name)
        self.persist()
        self.refresh_all()
        self.write_log(f"已新建点位组：{name}")

    def rename_point_group(self):
        group = self.current_group()
        name = simpledialog.askstring("重命名点位组", "新名称：", initialvalue=group.name, parent=self)
        if not name:
            return
        name = name.strip()
        if name != group.name and self.find_point_group(name):
            messagebox.showwarning("名称重复", "已经有同名点位组。")
            return
        old_name = group.name
        group.name = name
        self.active_point_group.set(name)
        self.persist()
        self.refresh_all()
        self.write_log(f"已重命名点位组：{old_name} -> {name}")

    def delete_point_group(self):
        if len(self.point_groups) <= 1:
            messagebox.showwarning("不能删除", "至少需要保留一个点位组。")
            return
        group = self.current_group()
        if not messagebox.askyesno("删除点位组", f"确定删除点位组「{group.name}」吗？其中点位会一起删除。"):
            return
        self.point_groups.remove(group)
        self.active_point_group.set(self.point_groups[0].name)
        self.persist()
        self.refresh_all()
        self.write_log(f"已删除点位组：{group.name}")

    def on_point_selected(self, _event=None):
        idx = self.table_index(self.point_table)
        if idx is not None:
            self.point_name.set(self.points[idx].name)

    def on_step_selected(self, _event=None):
        idx = self.table_index(self.step_table)
        if idx is None:
            return
        step = self.steps[idx]
        self.step_name.set(step.name)
        self.step_kind.set(step.kind)
        self.step_target.set(step.target)
        self.step_value.set(step.value)
        self.step_wait_after.set(getattr(step, "wait_after", ""))
        self.step_enabled.set(step.enabled)
        self.update_step_form_state()

    def on_step_kind_changed(self, _event=None):
        self.update_step_form_state()

    def update_step_form_state(self):
        kind = self.step_kind.get()
        current_target = self.step_target.get()
        self.target_combo.configure(values=[p.name for p in self.points])
        needs_target = kind == "click"
        self.target_combo.configure(state="readonly" if needs_target else "disabled")
        if not needs_target:
            self.step_target.set("")
        elif current_target:
            self.step_target.set(current_target)

        value_enabled = kind in ("paste", "wait", "key", "hotkey", "log", "image_click")
        self.value_entry.configure(state="normal" if value_enabled else "disabled")
        if not value_enabled:
            self.step_value.set("")
        self.wait_after_entry.configure(state="disabled" if kind == "wait" else "normal")
        if kind == "wait":
            self.step_wait_after.set("")

    def on_step_drag_start(self, event):
        if self.step_table.identify_region(event.x, event.y) not in ("cell", "tree"):
            self.drag_step_iid = None
            return
        self.drag_step_iid = self.step_table.identify_row(event.y)
        self.drag_over_iid = None
        if self.drag_step_iid:
            self.step_table.configure(cursor="fleur")
            self.step_table.selection_set(self.drag_step_iid)

    def on_step_drag_motion(self, event):
        if not self.drag_step_iid:
            return
        target_iid = self.step_table.identify_row(event.y)
        if target_iid:
            self.set_drag_target(target_iid)

    def on_step_drag_drop(self, event):
        source_iid = self.drag_step_iid
        target_iid = self.step_table.identify_row(event.y) or self.drag_over_iid
        self.drag_step_iid = None
        self.clear_step_drag_feedback()
        self.step_table.configure(cursor="")
        if not source_iid or not target_iid or source_iid == target_iid:
            return
        source_idx = int(source_iid)
        target_idx = int(target_iid)
        bbox = self.step_table.bbox(target_iid)
        insert_after = bool(bbox and event.y > bbox[1] + bbox[3] / 2)
        step = self.steps.pop(source_idx)
        if source_idx < target_idx:
            target_idx -= 1
        if insert_after:
            target_idx += 1
        target_idx = max(0, min(target_idx, len(self.steps)))
        self.steps.insert(target_idx, step)
        self.persist()
        self.refresh_steps()
        self.step_table.selection_set(str(target_idx))
        self.write_log(f"已拖动排序：{step.name}")

    def cancel_step_drag(self, _event=None):
        self.drag_step_iid = None
        self.clear_step_drag_feedback()
        self.step_table.configure(cursor="")

    def set_drag_target(self, iid):
        if iid == self.drag_over_iid:
            return
        if self.drag_over_iid and self.step_table.exists(self.drag_over_iid):
            self.step_table.item(self.drag_over_iid, tags=())
        self.drag_over_iid = iid if iid else None
        if self.drag_over_iid and self.step_table.exists(self.drag_over_iid):
            self.step_table.item(self.drag_over_iid, tags=("drop_target",))

    def clear_step_drag_feedback(self, _event=None):
        if self.drag_over_iid and self.step_table.exists(self.drag_over_iid):
            self.step_table.item(self.drag_over_iid, tags=())
        self.drag_over_iid = None
    def on_song_selected(self, _event=None):
        ref = self.selected_song_ref()
        if ref is None:
            return
        _group, _song_index, song = ref
        self.song_title.set(song.title)
        self.song_keyword.set(song.keyword)
        self.song_duration.set(format_duration(song.duration_seconds))
        self.song_buffer.set(str(song.buffer_seconds))
        self.song_step_preset.set(getattr(song, "step_preset", ""))
        self.song_enabled.set(song.enabled)

    def add_point(self):
        name = self.point_name.get().strip()
        if not name:
            messagebox.showwarning("需要名称", "请输入新点位名称。")
            return
        if any(point.name == name for point in self.points):
            messagebox.showwarning("名称重复", "已经有同名点位。")
            return
        self.points.append(PointDef(name=name, x=0, y=0))
        self.persist()
        self.refresh_all()
        idx = len(self.points) - 1
        self.point_table.selection_set(str(idx))
        self.write_log(f"已新增点位：{name}")

    def rename_point(self):
        idx = self.table_index(self.point_table)
        if idx is None:
            messagebox.showwarning("先选点位", "请先选择要重命名的点位。")
            return
        name = self.point_name.get().strip()
        if not name:
            messagebox.showwarning("需要名称", "点位名称不能为空。")
            return
        old_name = self.points[idx].name
        if name != old_name and any(point.name == name for point in self.points):
            messagebox.showwarning("名称重复", "已经有同名点位。")
            return
        self.points[idx].name = name
        for step in self.steps:
            if step.target == old_name:
                step.target = name
        self.persist()
        self.refresh_all()
        self.point_table.selection_set(str(idx))
        self.write_log(f"已重命名点位：{old_name} -> {name}")

    def save_point_name(self):
        if self.table_index(self.point_table) is None:
            self.add_point()
        else:
            self.rename_point()
    def explain_f8_capture(self):
        messagebox.showinfo("F8 采集", "选中一个点位后，把鼠标移到目标位置，按 F8 即可采集当前坐标。")

    def capture_selected_point(self):
        self.capture_current_selected_point()

    def capture_current_selected_point(self):
        idx = self.table_index(self.point_table)
        if idx is None:
            self.write_log("F8 未采集：请先选中一个点位。")
            return
        group = self.current_group()
        if idx < 0 or idx >= len(group.points):
            self.write_log("F8 未采集：点位已经不存在。")
            return
        x, y = get_cursor_pos()
        group.points[idx].x = x
        group.points[idx].y = y
        self.points = self.current_points()
        self.persist()
        self.refresh_all()
        self.point_table.selection_set(str(idx))
        self.write_log(f"F8 已采集 {group.name} / {group.points[idx].name}: {x}, {y}")

    def arm_capture_selected_point(self):
        self.explain_f8_capture()

    def emergency_stop_hotkey(self):
        self.stop_event.set()
        self.pause_event.set()
        self.write_log("F9 急停：已请求停止当前动作序列。")

    def start_hotkey_thread(self):
        if self.hotkey_thread and self.hotkey_thread.is_alive():
            return
        self.hotkey_thread = threading.Thread(target=self.hotkey_worker, daemon=True)
        self.hotkey_thread.start()

    def hotkey_worker(self):
        while not self.hotkey_stop_event.is_set():
            if user32.GetAsyncKeyState(VK_F8) & 1:
                self.after(0, self.capture_current_selected_point)
            if user32.GetAsyncKeyState(VK_F9) & 1:
                self.after(0, self.emergency_stop_hotkey)
            time.sleep(0.05)

    def delete_point(self):
        idx = self.table_index(self.point_table)
        if idx is None:
            messagebox.showwarning("先选点位", "请先选择要删除的点位。")
            return
        name = self.points[idx].name
        if not messagebox.askyesno("删除点位", f"确定删除「{name}」吗？关联动作的点位会被清空。"):
            return
        del self.points[idx]
        for step in self.steps:
            if step.target == name:
                step.target = ""
        self.persist()
        self.refresh_all()
    def build_step_from_form(self):
        name = self.step_name.get().strip() or self.step_kind.get()
        kind = self.step_kind.get()
        target = self.step_target.get().strip() if kind == "click" else ""
        return Step(name=name, kind=kind, target=target, value=self.step_value.get().strip(), enabled=self.step_enabled.get(), wait_after=self.step_wait_after.get().strip())

    def add_step(self):
        step = self.build_step_from_form()
        idx = self.table_index(self.step_table)
        insert_at = idx + 1 if idx is not None else len(self.steps)
        self.steps.insert(insert_at, step)
        self.persist()
        self.refresh_steps()
        self.step_table.selection_set(str(insert_at))
        self.update_step_form_state()
        self.write_log(f"已新增动作：{step.name}")

    def update_step(self):
        idx = self.table_index(self.step_table)
        if idx is None:
            messagebox.showwarning("先选动作", "请先选择要更新的动作。")
            return
        step = self.build_step_from_form()
        self.steps[idx] = step
        self.persist()
        self.refresh_steps()
        self.step_table.selection_set(str(idx))
        self.update_step_form_state()
        self.write_log(f"已更新动作：{step.name}")

    def save_step(self):
        if self.table_index(self.step_table) is None:
            self.add_step()
        else:
            self.update_step()

    def duplicate_step(self):
        idx = self.table_index(self.step_table)
        if idx is None:
            messagebox.showwarning("先选动作", "请先选择要复制的动作。")
            return
        source = self.steps[idx]
        clone = Step(name=f"{source.name} 副本", kind=source.kind, target=source.target, value=source.value, enabled=source.enabled, wait_after=source.wait_after)
        insert_at = idx + 1
        self.steps.insert(insert_at, clone)
        self.persist()
        self.refresh_steps()
        self.step_table.selection_set(str(insert_at))
        self.write_log(f"已复制动作：{source.name}")

    def delete_step(self):
        idx = self.table_index(self.step_table)
        if idx is None:
            messagebox.showwarning("先选动作", "请先选择要删除的动作。")
            return
        step = self.steps[idx]
        if not messagebox.askyesno("删除动作", f"确定删除「{step.name}」吗？"):
            return
        del self.steps[idx]
        self.persist()
        self.refresh_steps()
    def move_step(self, direction):
        idx = self.table_index(self.step_table)
        if idx is None:
            return
        target = idx + direction
        if target < 0 or target >= len(self.steps):
            return
        self.steps[idx], self.steps[target] = self.steps[target], self.steps[idx]
        self.persist()
        self.refresh_steps()
        self.step_table.selection_set(str(target))

    def build_song_from_form(self):
        title = self.song_title.get().strip()
        if not title:
            messagebox.showwarning("需要作品名", "作品名不能为空。")
            return None
        try:
            return Song(title=title, keyword=self.song_keyword.get().strip() or title, duration_seconds=parse_duration(self.song_duration.get()), buffer_seconds=parse_duration(self.song_buffer.get()), enabled=self.song_enabled.get(), step_preset=self.song_step_preset.get().strip())
        except ValueError as exc:
            messagebox.showerror("时长格式不对", str(exc))
            return None

    def add_song(self):
        song = self.build_song_from_form()
        if song is None:
            return
        target_group = self.current_song_group() if not self.is_all_songs_view() else self.song_groups[0]
        ref = self.selected_song_ref()
        insert_at = ref[1] + 1 if ref and ref[0] is target_group else len(target_group.songs)
        target_group.songs.insert(insert_at, song)
        self.persist()
        self.refresh_songs()
        self.select_song_object(song)
        self.write_log(f"已新增歌曲到「{target_group.name}」：{song.title}")

    def update_song(self):
        ref = self.selected_song_ref()
        if ref is None:
            messagebox.showwarning("先选歌曲", "请先选择要更新的歌曲。")
            return
        song = self.build_song_from_form()
        if song is None:
            return
        group, song_index, _old_song = ref
        group.songs[song_index] = song
        self.persist()
        self.refresh_songs()
        self.select_song_object(song)
        self.write_log(f"已更新歌曲：{song.title}")

    def save_song(self):
        if self.selected_song_ref() is None:
            self.add_song()
        else:
            self.update_song()

    def delete_song(self):
        ref = self.selected_song_ref()
        if ref is None:
            messagebox.showwarning("先选歌曲", "请先选择要删除的歌曲。")
            return
        group, song_index, song = ref
        if not messagebox.askyesno("删除歌曲", f"确定从「{group.name}」删除「{song.title}」吗？"):
            return
        del group.songs[song_index]
        self.persist()
        self.refresh_songs()

    def choose_song_group_target(self, title, prompt, target_names):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.configure(bg=self.colors["panel"])
        dialog.transient(self)
        dialog.resizable(False, False)
        selected = tk.StringVar(value=target_names[0])
        result = {"value": None}
        body = ttk.Frame(dialog, style="Panel.TFrame", padding=14)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text=prompt, style="Panel.TLabel", wraplength=320).pack(anchor=tk.W)
        combo = ttk.Combobox(body, textvariable=selected, values=target_names, state="readonly", width=28)
        combo.pack(fill=tk.X, pady=(10, 12))
        combo.focus_set()
        buttons = ttk.Frame(body, style="Panel.TFrame")
        buttons.pack(fill=tk.X)

        def confirm():
            result["value"] = selected.get()
            dialog.destroy()

        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="移动", style="Accent.TButton", command=confirm).pack(side=tk.RIGHT, padx=(0, 8))
        dialog.bind("<Return>", lambda _event: confirm())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.grab_set()
        self.wait_window(dialog)
        return result["value"]
    def move_song_to_group(self):
        ref = self.selected_song_ref()
        if ref is None:
            messagebox.showwarning("先选歌曲", "请先选择要移动的歌曲。")
            return
        source_group, song_index, song = ref
        target_names = [group.name for group in self.song_groups if group is not source_group]
        if not target_names:
            messagebox.showinfo("没有目标分组", "请先新建另一个歌曲组，再移动歌曲。")
            return
        target_name = self.choose_song_group_target("移动歌曲", f"把「{song.title}」移动到哪个歌曲组？", target_names)
        if not target_name:
            return
        target_name = target_name.strip()
        target_group = self.find_song_group(target_name)
        if target_group is None or target_group is source_group:
            messagebox.showwarning("目标无效", "请输入另一个已有歌曲组名称。")
            return
        moved_song = source_group.songs.pop(song_index)
        target_group.songs.append(moved_song)
        self.active_song_group.set(target_group.name)
        self.persist()
        self.refresh_song_groups()
        self.refresh_songs()
        self.select_song_object(moved_song)
        self.write_log(f"已移动歌曲：{moved_song.title}，{source_group.name} -> {target_group.name}")
    def move_song(self, direction):
        if self.is_all_songs_view():
            messagebox.showinfo("全部视图", "“全部”是汇总视图，请切到具体歌曲组后调整顺序。")
            return
        ref = self.selected_song_ref()
        if ref is None:
            return
        group, song_index, _song = ref
        target = song_index + direction
        if target < 0 or target >= len(group.songs):
            return
        group.songs[song_index], group.songs[target] = group.songs[target], group.songs[song_index]
        moved_song = group.songs[target]
        self.persist()
        self.refresh_songs()
        self.select_song_object(moved_song)

    def persist(self):
        self.points = self.current_points()
        self.config_data = {
            "window_hint": self.window_hint.get().strip(),
            "focus_window": self.focus_var.get(),
            "playback_loop": self.playback_loop_var.get() if hasattr(self, "playback_loop_var") else False,
            "playback_random": self.playback_random_var.get() if hasattr(self, "playback_random_var") else False,
            "active_point_group": self.active_point_group.get(),
            "point_groups": [
                {"name": group.name, "points": [asdict(point) for point in group.points]}
                for group in self.point_groups
            ],
            "points": [asdict(point) for point in self.points],
            "steps": [asdict(step) for step in self.steps],
            "image_targets": [asdict(target) for target in self.image_targets],
            "active_step_preset": self.active_step_preset.get() if hasattr(self, "active_step_preset") else "",
            "step_presets": [
                {"name": preset["name"], "steps": [asdict(step) for step in preset["steps"]]}
                for preset in self.step_presets
            ],
        }
        save_json(CONFIG_PATH, self.config_data)
        save_json(PLAYLIST_PATH, {
            "active_song_group": self.active_song_group.get() if hasattr(self, "active_song_group") else self.song_groups[0].name,
            "song_groups": [
                {"name": group.name, "step_preset": group.step_preset, "songs": [asdict(song) for song in group.songs]}
                for group in self.song_groups
            ],
        })
        self.write_log("已保存。") if hasattr(self, "log") else None
    def check_window(self):
        window = find_window(self.window_hint.get())
        if window:
            self.window_status.set(f"已找到：{window['title']}")
            self.write_log(f"找到窗口 hwnd={window['hwnd']} title={window['title']}")
        else:
            self.window_status.set("没有找到")
            self.write_log("没有找到窗口，请改一下关键词。")

    def current_song_jobs(self, enabled_only=False):
        jobs = []
        for group in self.song_groups:
            if not self.is_all_songs_view() and group.name != self.active_song_group.get():
                continue
            for song in group.songs:
                if enabled_only and not song.enabled:
                    continue
                jobs.append({"song": song, "group": group})
        return jobs

    def steps_for_song(self, song, group):
        song_preset = getattr(song, "step_preset", "")
        preset = self.find_step_preset(song_preset) if song_preset else None
        if preset:
            return preset["steps"], f"单曲:{song_preset}"
        group_preset = getattr(group, "step_preset", "")
        preset = self.find_step_preset(group_preset) if group_preset else None
        if preset:
            return preset["steps"], f"歌曲组:{group_preset}"
        return self.steps, "当前动作序列"

    def start_single(self):
        ref = self.selected_song_ref()
        if ref is not None:
            group, _song_index, song = ref
            self.start_worker([{"song": song, "group": group}])
            return
        jobs = self.current_song_jobs(enabled_only=True)
        if jobs:
            self.start_worker([jobs[0]])
        else:
            self.start_worker([{"song": Song(title="", keyword="", duration_seconds=0, buffer_seconds=0, enabled=True), "group": self.current_song_group()}])

    def start_playlist(self):
        self.persist()
        jobs = self.current_song_jobs(enabled_only=True)
        if not jobs:
            messagebox.showwarning("歌单为空", "没有启用的歌曲。")
            return
        loop_enabled = self.playback_loop_var.get()
        random_enabled = self.playback_random_var.get()
        names = "、".join(job["song"].title for job in jobs[:5])
        suffix = "..." if len(jobs) > 5 else ""
        modes = []
        if random_enabled:
            modes.append("随机")
        if loop_enabled:
            modes.append("循环")
        mode_text = f"（{' / '.join(modes)}）" if modes else ""
        group_label = self.active_song_group.get()
        self.write_log(f"播放歌单「{group_label}」{mode_text}：共 {len(jobs)} 首；{names}{suffix}")
        self.start_worker(jobs, loop_enabled=loop_enabled, random_enabled=random_enabled)

    def start_worker(self, jobs, loop_enabled=False, random_enabled=False):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("正在运行", "动作序列已经在运行。")
            return
        self.persist()
        self.stop_event.clear()
        self.pause_event.set()
        self.worker = threading.Thread(target=self.run_sequence_worker, args=(jobs, loop_enabled, random_enabled), daemon=True)
        self.worker.start()

    def stop_playback(self):
        self.stop_event.set()
        self.pause_event.set()
        self.write_log("已请求停止。")

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.write_log("已暂停。")
        else:
            self.pause_event.set()
            self.write_log("继续。")

    def run_sequence_worker(self, jobs, loop_enabled=False, random_enabled=False):
        cycle = 0
        while not self.stop_event.is_set():
            cycle += 1
            cycle_jobs = list(jobs)
            if random_enabled:
                random.shuffle(cycle_jobs)
            total_songs = len(cycle_jobs)
            if loop_enabled or random_enabled:
                order = "、".join(job["song"].title for job in cycle_jobs[:5])
                suffix = "..." if len(cycle_jobs) > 5 else ""
                self.after(0, lambda c=cycle, o=order, s=suffix: self.write_log(f"第 {c} 轮顺序：{o}{s}"))
            for song_index, job in enumerate(cycle_jobs, start=1):
                if self.stop_event.is_set():
                    break
                song = job["song"]
                group = job["group"]
                steps, preset_label = self.steps_for_song(song, group)
                self.points = self.current_points()
                point_map = {point.name: point for point in self.points}
                window = find_window(self.window_hint.get()) if self.focus_var.get() else None
                if self.focus_var.get() and not window:
                    self.after(0, lambda: self.write_log("运行失败：找不到目标窗口。"))
                    self.stop_event.set()
                    break
                if window:
                    focus_window(window["hwnd"])
                label = song.title if song else "单次运行"
                prefix = f"第 {cycle} 轮 " if loop_enabled else ""
                self.after(0, lambda l=label, i=song_index, t=total_songs, p=prefix, g=group.name, preset=preset_label: self.write_log(f"开始 {p}{i}/{t}: {l} [{g} / {preset}]"))
                for step in steps:
                    if self.stop_event.is_set():
                        break
                    if not step.enabled:
                        continue
                    self.pause_event.wait()
                    try:
                        self.execute_step(step, point_map, song)
                    except Exception as exc:
                        self.after(0, lambda e=exc, s=step: self.write_log(f"动作失败「{s.name}」：{e}"))
                        self.stop_event.set()
                        break
                if self.stop_event.is_set():
                    break
                self.after(0, lambda l=label, i=song_index, t=total_songs, p=prefix: self.write_log(f"完成 {p}{i}/{t}: {l}"))
                if song_index < total_songs:
                    self.after(0, lambda i=song_index + 1, t=total_songs, p=prefix: self.write_log(f"准备下一首 {p}{i}/{t}"))
                    self.wait_interruptible(1)
            if self.stop_event.is_set() or not loop_enabled:
                break
            self.after(0, lambda c=cycle + 1: self.write_log(f"循环播放：准备第 {c} 轮"))
            self.wait_interruptible(1)
        if self.stop_event.is_set():
            self.after(0, lambda: self.write_log("动作序列已停止。"))
        else:
            self.after(0, lambda: self.write_log("动作序列结束。"))
    def execute_step(self, step, point_map, song):
        kind = step.kind
        value = render_template(step.value, song)
        if kind == "click":
            point = point_map.get(step.target)
            if not point:
                raise RuntimeError(f"点位不存在：{step.target}")
            if point.x == 0 and point.y == 0:
                raise RuntimeError(f"点位未采集：{step.target}")
            self.after(0, lambda: self.write_log(f"点击 {step.target}"))
            click_xy(point.x, point.y)
        elif kind == "image_click":
            target = self.find_image_target(value)
            if not target:
                names = "、".join(item.name for item in self.image_targets) or "暂无图像目标"
                raise RuntimeError(f"图像目标不存在：{value or '未填写'}。当前可用：{names}")
            self.after(0, lambda n=target.name: self.write_log(f"识别图像目标：{n}"))
            deadline = time.time() + max(0.0, float(target.retry_seconds))
            last_error = None
            while True:
                if self.stop_event.is_set():
                    return
                try:
                    match = locate_template(target.template_path, target.region, target.threshold)
                    click_x = match.x + int(target.offset_x)
                    click_y = match.y + int(target.offset_y)
                    self.after(0, lambda n=target.name, s=match.score, x=click_x, y=click_y: self.write_log(f"图像命中 {n} score={s:.3f}，点击 {x}, {y}"))
                    click_xy(click_x, click_y)
                    break
                except Exception as exc:
                    last_error = exc
                    if time.time() >= deadline:
                        raise RuntimeError(f"图像目标识别失败：{target.name}；{last_error}") from exc
                    self.wait_interruptible(0.25)
        elif kind == "paste":
            if value == "" and song is not None:
                value = song.keyword or song.title
            self.after(0, lambda v=value: self.write_log(f"粘贴：{v}"))
            set_clipboard_text(value)
            time.sleep(0.12)
            hotkey_ctrl(VK_V)
        elif kind == "wait":
            seconds = parse_duration(value)
            self.after(0, lambda: self.write_log(f"等待 {format_duration(seconds)}"))
            self.wait_interruptible(seconds)
        elif kind == "enter":
            self.after(0, lambda: self.write_log("按 Enter"))
            press_enter()
        elif kind == "ctrl_a":
            self.after(0, lambda: self.write_log("按 Ctrl+A"))
            hotkey_ctrl(VK_A)
        elif kind == "key":
            key_name = value.strip()
            vk = key_code_from_name(key_name)
            self.after(0, lambda k=key_name: self.write_log(f"按键：{k}"))
            press_key(vk)
        elif kind == "hotkey":
            keys = [part.strip() for part in value.replace("，", "+").split("+") if part.strip()]
            if not keys:
                raise RuntimeError("hotkey 参数不能为空，例如 ctrl+v。")
            self.after(0, lambda k="+".join(keys): self.write_log(f"快捷键：{k}"))
            hotkey(keys)
        elif kind == "log":
            self.after(0, lambda: self.write_log(value))
        else:
            raise RuntimeError(f"未知动作类型：{kind}")

        wait_after = render_template(step.wait_after, song).strip()
        if kind != "wait" and wait_after:
            seconds = parse_duration(wait_after)
            self.after(0, lambda: self.write_log(f"动作后等待 {format_duration(seconds)}"))
            self.wait_interruptible(seconds)
        time.sleep(0.08)
    def wait_interruptible(self, seconds):
        remaining = max(0, seconds)
        last_tick = time.time()
        while remaining > 0:
            if self.stop_event.is_set():
                return False
            if not self.pause_event.is_set():
                self.pause_event.wait(0.2)
                last_tick = time.time()
                continue
            time.sleep(min(0.2, remaining))
            now = time.time()
            remaining -= now - last_tick
            last_tick = now
        return True

    def write_log(self, message):
        stamp = time.strftime("%H:%M:%S")
        self.log.insert(tk.END, f"[{stamp}] {message}\n")
        self.log.see(tk.END)

    def on_close(self):
        self.hotkey_stop_event.set()
        self.stop_event.set()
        self.persist()
        self.destroy()


if __name__ == "__main__":
    app = MacroStudio()
    app.mainloop()









































































































