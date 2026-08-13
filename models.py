from dataclasses import dataclass


@dataclass
class Song:
    title: str
    keyword: str
    duration_seconds: int
    buffer_seconds: int = 5
    enabled: bool = True
    step_preset: str = ""


@dataclass
class SongGroup:
    name: str
    songs: list
    step_preset: str = ""


@dataclass
class PointDef:
    name: str
    x: int
    y: int


@dataclass
class PointGroup:
    name: str
    points: list


@dataclass
class ImageTarget:
    name: str
    template_path: str
    match_mode: str = "grayscale"
    mask_path: str = ""
    edge_low: int = 60
    edge_high: int = 160
    region: str = ""
    threshold: float = 0.85
    offset_x: int = 0
    offset_y: int = 0
    retry_seconds: float = 3.0


@dataclass
class Step:
    name: str
    kind: str
    target: str = ""
    value: str = ""
    enabled: bool = True
    wait_after: str = ""
