from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


RunnerMode = Literal["simulation", "real"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepDto(ApiModel):
    name: str
    kind: str
    target: str = ""
    value: str = ""
    enabled: bool = True
    wait_after: str = ""
    failure_policy: Literal["", "stop", "skip", "retry_step", "previous_image", "previous_click"] = ""
    failure_retries: int = Field(default=2, ge=0, le=20)
    verify_target: str = ""


class SongDto(ApiModel):
    title: str
    keyword: str
    duration_seconds: int = Field(ge=0)
    buffer_seconds: int = Field(default=5, ge=0)
    enabled: bool = True
    step_preset: str = ""


class SongGroupDto(ApiModel):
    name: str
    songs: list[SongDto] = Field(default_factory=list)
    step_preset: str = ""


class PlaylistDocumentDto(ApiModel):
    active_song_group: str
    song_groups: list[SongGroupDto]


class PresetDto(ApiModel):
    name: str
    steps: list[StepDto] = Field(default_factory=list)


class PointDto(ApiModel):
    name: str
    x: int
    y: int


class PointGroupDto(ApiModel):
    name: str
    points: list[PointDto] = Field(default_factory=list)


class ImageTargetDto(ApiModel):
    name: str
    template_path: str
    match_mode: Literal["smart", "grayscale", "edge", "masked", "masked_edge"] = "grayscale"
    mask_path: str = ""
    edge_low: int = Field(default=60, ge=0, le=255)
    edge_high: int = Field(default=160, ge=0, le=255)
    region: str = ""
    threshold: float = Field(default=0.85, ge=0, le=1)
    offset_x: int = 0
    offset_y: int = 0
    retry_seconds: float = Field(default=3.0, ge=0, le=120)
    retry_attempts: int = Field(default=5, ge=1, le=100)
    retry_interval: float = Field(default=0.25, ge=0, le=30)


class TargetLibraryDto(ApiModel):
    active_point_group: str
    point_groups: list[PointGroupDto]
    image_targets: list[ImageTargetDto] = Field(default_factory=list)


class TargetLibraryUpdateDto(ApiModel):
    document: TargetLibraryDto
    point_renames: dict[str, str] = Field(default_factory=dict)
    image_target_renames: dict[str, str] = Field(default_factory=dict)


class TemplateImportRequest(ApiModel):
    target_name: str
    filename: str = ""
    data_url: str


class TemplateImportResponse(ApiModel):
    template_path: str
    width: int
    height: int


class MaskImportRequest(ApiModel):
    target_name: str
    filename: str = ""
    data_url: str


class PointCaptureArmRequest(ApiModel):
    group_name: str
    point_name: str


class PointCaptureStateResponse(ApiModel):
    status: Literal["idle", "armed", "captured"]
    group_name: str = ""
    point_name: str = ""
    x: int | None = None
    y: int | None = None


class PointPreviewRequest(ApiModel):
    name: str
    x: int
    y: int
    duration: float = Field(default=2.6, ge=0.5, le=10.0)


class PointPreviewResponse(ApiModel):
    status: Literal["showing"]
    name: str
    x: int
    y: int
    duration: float


class RegionSelectionResponse(ApiModel):
    cancelled: bool
    x: int
    y: int
    width: int
    height: int


class VisionTestRequest(ApiModel):
    target: ImageTargetDto


class VisionTestResponse(ApiModel):
    matched: bool
    source: Literal["screen", "background"]
    x: int = 0
    y: int = 0
    score: float = 0
    width: int = 0
    height: int = 0
    error: str = ""
    match_mode: str = "grayscale"
    preview_data_url: str = ""
    search_x: int = 0
    search_y: int = 0
    search_width: int = 0
    search_height: int = 0
    capture_width: int = 0
    capture_height: int = 0


class RunnerStartRequest(ApiModel):
    active_group: str | None = None
    loop: bool = False
    random: bool = False
    simulation: bool = True


class RunPlanRequest(ApiModel):
    active_group: str | None = None


class RunPlanIssueDto(ApiModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    item_index: int | None = None
    item_name: str = ""
    step_index: int | None = None
    step_name: str = ""


class RunPlanItemDto(ApiModel):
    name: str
    group: str
    workflow: str
    actions: int = Field(ge=0)
    estimated_seconds: float = Field(ge=0)


class RunPlanResponse(ApiModel):
    ready: bool
    items: list[RunPlanItemDto]
    item_count: int = Field(ge=0)
    action_count: int = Field(ge=0)
    estimated_seconds: float = Field(ge=0)
    issues: list[RunPlanIssueDto]


class StepTestRequest(ApiModel):
    step: StepDto
    song: SongDto | None = None

class RunnerCommandResponse(ApiModel):
    status: str
    changed: bool = True
    mode: RunnerMode


class RunnerStateResponse(ApiModel):
    status: str
    active: bool
    mode: RunnerMode = "simulation"


class TargetSettingsDto(ApiModel):
    window_hint: str
    focus_window: bool = True
    input_mode: Literal["foreground", "window_message"] = "foreground"
    confirm_step_test: bool = True
    preview_clicks: bool = False


class WindowProbeRequest(ApiModel):
    window_hint: str = ""
    capture: bool = False


class WindowProbeResponse(ApiModel):
    found: bool
    window_hint: str = ""
    hwnd: int = 0
    pid: int = 0
    title: str = ""
    process_name: str = ""
    left: int = 0
    top: int = 0
    width: int = 0
    height: int = 0
    client_left: int = 0
    client_top: int = 0
    client_width: int = 0
    client_height: int = 0
    dpi: int = 96
    minimized: bool = False
    process_elevated: bool = False
    process_integrity: str = "unknown"
    app_elevated: bool = False
    app_integrity: str = "unknown"
    input_allowed: bool = True
    preview_data_url: str = ""
    capture_width: int = 0
    capture_height: int = 0
    error: str = ""


class PreflightCheckDto(ApiModel):
    key: str
    label: str
    ok: bool
    detail: str


class PreflightResponse(ApiModel):
    ready: bool
    checks: list[PreflightCheckDto]
    window: WindowProbeResponse

class StageConfigDto(ApiModel):
    base_url: str
    role_id: str = ""
    user_id: str = ""
    skey: str = ""
    sort: str = ""
    page_size: str = "20"
    contents: str = ""
    sub_types: str = ""
    actor_count_contents: str = ""
    work_filter: Literal["single", "all", "multi", "movie"] = "single"


class StageDocumentDto(ApiModel):
    config: StageConfigDto
    keyword: str = ""


class StageParseRequest(ApiModel):
    text: str


class StageSearchRequest(ApiModel):
    keyword: str
    page: int = Field(default=1, ge=1, le=100)
    duration_limit: int = Field(default=12, ge=0, le=100)
    config: StageConfigDto | None = None


class StageWorkDto(ApiModel):
    work_id: int
    name: str
    summary: str = ""
    designer_name: str = ""
    hot: int = 0
    like_count: int = 0
    collect_count: int = 0
    cover_url: str = ""
    category_label: str = ""
    work_type: int = 0
    sub_type: int = 0
    actor_count: int = 0
    duration_seconds: int = 0


class StageSearchResponse(ApiModel):
    keyword: str
    page: int
    works: list[StageWorkDto]


class StageCaptureStartRequest(ApiModel):
    timeout: int = Field(default=90, ge=15, le=180)


class StageCaptureStateResponse(ApiModel):
    status: Literal["idle", "listening", "validating", "completed", "failed"]
    message: str
    keyword: str = ""
    config: StageConfigDto | None = None
    works: list[StageWorkDto] = Field(default_factory=list)
    deadline: float = 0


class StageDiagnosticsSummaryDto(ApiModel):
    cache_files_seen: int = 0
    cache_hits: int = 0
    binary_hits: int = 0
    method_candidates: int = 0
    action_play_logs: int = 0
    qrcode_work_logs: int = 0
    voice_playback_logs: int = 0


class StageDiagnosticsStateResponse(ApiModel):
    status: Literal["idle", "running", "completed", "failed"]
    message: str
    summary: StageDiagnosticsSummaryDto = Field(default_factory=StageDiagnosticsSummaryDto)
    notes: list[str] = Field(default_factory=list)
    report: str = ""
    started_at: float = 0
    finished_at: float = 0


class HealthResponse(ApiModel):
    status: str = "ok"
    api_version: str
    runner_status: str


class EventDto(ApiModel):
    sequence: int
    timestamp: float
    type: str
    status: str
    data: dict[str, Any] = Field(default_factory=dict)
