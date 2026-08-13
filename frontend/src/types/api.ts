export type ConnectionPhase = 'disconnected' | 'connecting' | 'connected' | 'error'

export interface SidecarConnection {
  host: string
  port: number
  token: string
  api_version: string
}

export interface HealthResponse {
  status: string
  api_version: string
  runner_status: RunnerStatus
}

export type RunnerStatus =
  | 'idle'
  | 'starting'
  | 'running'
  | 'paused'
  | 'stopping'
  | 'stopped'
  | 'completed'
  | 'failed'

export interface StepDto {
  name: string
  kind: string
  target: string
  value: string
  enabled: boolean
  wait_after: string
  failure_policy: '' | 'stop' | 'skip' | 'retry_step' | 'previous_image'
  failure_retries: number
  verify_target: string
}

export interface SongDto {
  title: string
  keyword: string
  duration_seconds: number
  buffer_seconds: number
  enabled: boolean
  step_preset: string
}

export interface SongGroupDto {
  name: string
  songs: SongDto[]
  step_preset: string
}

export interface PlaylistDocumentDto {
  active_song_group: string
  song_groups: SongGroupDto[]
}

export interface PresetDto {
  name: string
  steps: StepDto[]
}

export type RunnerMode = 'simulation' | 'real'

export interface RunnerStateResponse {
  status: RunnerStatus
  active: boolean
  mode: RunnerMode
}

export interface RunnerCommandResponse {
  status: RunnerStatus
  changed: boolean
  mode: RunnerMode
}

export interface RunnerEvent {
  sequence: number
  timestamp: number
  type: string
  status: RunnerStatus | ''
  data: Record<string, unknown>
}

export interface RunnerStartRequest {
  active_group: string | null
  loop: boolean
  random: boolean
  simulation: boolean
}
export interface RunPlanIssue {
  severity: 'error' | 'warning'
  code: string
  message: string
  item_index: number | null
  item_name: string
  step_index: number | null
  step_name: string
}

export interface RunPlanItem {
  name: string
  group: string
  workflow: string
  actions: number
  estimated_seconds: number
}

export interface RunPlanResponse {
  ready: boolean
  items: RunPlanItem[]
  item_count: number
  action_count: number
  estimated_seconds: number
  issues: RunPlanIssue[]
}

export interface PointDto {
  name: string
  x: number
  y: number
}

export interface PointGroupDto {
  name: string
  points: PointDto[]
}

export type ImageMatchMode = 'smart' | 'grayscale' | 'edge' | 'masked' | 'masked_edge'

export interface ImageTargetDto {
  name: string
  template_path: string
  match_mode: ImageMatchMode
  mask_path: string
  edge_low: number
  edge_high: number
  region: string
  threshold: number
  offset_x: number
  offset_y: number
  retry_seconds: number
  retry_attempts: number
  retry_interval: number
}

export interface TargetLibraryDto {
  active_point_group: string
  point_groups: PointGroupDto[]
  image_targets: ImageTargetDto[]
}

export interface TemplateImportResponse {
  template_path: string
  width: number
  height: number
}
export interface PointCaptureState {
  status: 'idle' | 'armed' | 'captured'
  group_name: string
  point_name: string
  x: number | null
  y: number | null
}

export interface PointPreviewResponse {
  status: 'showing'
  name: string
  x: number
  y: number
  duration: number
}

export interface RegionSelectionResponse {
  cancelled: boolean
  x: number
  y: number
  width: number
  height: number
}

export interface VisionTestResponse {
  matched: boolean
  source: 'screen' | 'background'
  x: number
  y: number
  score: number
  width: number
  height: number
  error: string
  match_mode: string
  preview_data_url: string
  search_x: number
  search_y: number
  search_width: number
  search_height: number
  capture_width: number
  capture_height: number
}

export type InputMode = 'foreground' | 'window_message'

export interface TargetSettingsDto {
  window_hint: string
  focus_window: boolean
  input_mode: InputMode
  confirm_step_test: boolean
  preview_clicks: boolean
}

export interface WindowProbeResponse {
  found: boolean
  window_hint: string
  hwnd: number
  pid: number
  title: string
  process_name: string
  left: number
  top: number
  width: number
  height: number
  client_left: number
  client_top: number
  client_width: number
  client_height: number
  dpi: number
  minimized: boolean
  process_elevated: boolean
  process_integrity: string
  app_elevated: boolean
  app_integrity: string
  input_allowed: boolean
  preview_data_url: string
  capture_width: number
  capture_height: number
  error: string
}

export interface PreflightCheckDto {
  key: string
  label: string
  ok: boolean
  detail: string
}

export interface PreflightResponse {
  ready: boolean
  checks: PreflightCheckDto[]
  window: WindowProbeResponse
}
