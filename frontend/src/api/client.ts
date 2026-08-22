import type {
  HealthResponse,
  ImageTargetDto,
  PlaylistDocumentDto,
  PointCaptureState,
  PointPreviewResponse,
  PresetDto,
  RunnerCommandResponse,
  RunnerEvent,
  RunPlanResponse,
  RunnerStartRequest,
  RunnerStateResponse,
  RegionSelectionResponse,
  SidecarConnection,
  TargetLibraryDto,
  TemplateImportResponse,
  VisionTestResponse,
  TargetSettingsDto,
  WindowProbeResponse,
  PreflightResponse,
  StepDto,
  SongDto,
  StageCaptureState,
  StageConfigDto,
  StageDocumentDto,
  StageSearchResponse,
} from '../types/api'

const SESSION_HEADER = 'X-Macro-Studio-Token'

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export class MacroStudioClient {
  readonly baseUrl: string
  readonly connection: SidecarConnection

  constructor(connection: SidecarConnection) {
    this.connection = connection
    this.baseUrl = `http://${connection.host}:${connection.port}`
  }

  health(): Promise<HealthResponse> {
    return this.request('/api/health')
  }

  playlists(): Promise<PlaylistDocumentDto> {
    return this.request('/api/playlists')
  }

  updatePlaylists(document: PlaylistDocumentDto): Promise<PlaylistDocumentDto> {
    return this.request('/api/playlists', {
      method: 'PUT',
      body: JSON.stringify(document),
    })
  }

  presets(): Promise<PresetDto[]> {
    return this.request('/api/presets')
  }

  updatePresets(presets: PresetDto[]): Promise<PresetDto[]> {
    return this.request('/api/presets', {
      method: 'PUT',
      body: JSON.stringify(presets),
    })
  }

  targets(): Promise<TargetLibraryDto> {
    return this.request('/api/targets')
  }

  updateTargets(
    document: TargetLibraryDto,
    pointRenames: Record<string, string> = {},
    imageTargetRenames: Record<string, string> = {},
  ): Promise<TargetLibraryDto> {
    return this.request('/api/targets', {
      method: 'PUT',
      body: JSON.stringify({
        document,
        point_renames: pointRenames,
        image_target_renames: imageTargetRenames,
      }),
    })
  }

  importTemplate(targetName: string, filename: string, dataUrl: string): Promise<TemplateImportResponse> {
    return this.request('/api/targets/templates', {
      method: 'POST',
      body: JSON.stringify({ target_name: targetName, filename, data_url: dataUrl }),
    })
  }

  importMask(targetName: string, filename: string, dataUrl: string): Promise<TemplateImportResponse> {
    return this.request('/api/targets/masks', {
      method: 'POST',
      body: JSON.stringify({ target_name: targetName, filename, data_url: dataUrl }),
    })
  }

  async maskBlob(targetName: string): Promise<Blob> {
    return this.assetBlob('/api/targets/' + encodeURIComponent(targetName) + '/mask', '遮罩预览')
  }

  async templateBlob(targetName: string): Promise<Blob> {
    return this.assetBlob('/api/targets/' + encodeURIComponent(targetName) + '/template', '模板预览')
  }

  private async assetBlob(path: string, label: string): Promise<Blob> {
    let response: Response
    try {
      response = await fetch(this.baseUrl + path, {
        headers: { [SESSION_HEADER]: this.connection.token },
      })
    } catch (error) {
      throw new ApiError(error instanceof Error ? error.message : '无法读取' + label)
    }
    if (!response.ok) throw new ApiError(label + '请求失败 (' + response.status + ')', response.status)
    return response.blob()
  }

  armPointCapture(groupName: string, pointName: string): Promise<PointCaptureState> {
    return this.request('/api/targets/point-capture/arm', {
      method: 'POST',
      body: JSON.stringify({ group_name: groupName, point_name: pointName }),
    })
  }

  pointCaptureState(): Promise<PointCaptureState> {
    return this.request('/api/targets/point-capture')
  }

  cancelPointCapture(): Promise<PointCaptureState> {
    return this.request('/api/targets/point-capture/cancel', { method: 'POST' })
  }

  previewPoint(name: string, x: number, y: number, duration = 2.6): Promise<PointPreviewResponse> {
    return this.request('/api/targets/point-preview', {
      method: 'POST',
      body: JSON.stringify({ name, x, y, duration }),
    })
  }

  selectRegion(): Promise<RegionSelectionResponse> {
    return this.request('/api/targets/select-region', { method: 'POST' })
  }

  testImageTarget(target: ImageTargetDto): Promise<VisionTestResponse> {
    return this.request('/api/targets/test-image', {
      method: 'POST',
      body: JSON.stringify({ target }),
    })
  }

  stage(): Promise<StageDocumentDto> {
    return this.request('/api/stage')
  }

  updateStage(document: StageDocumentDto): Promise<StageDocumentDto> {
    return this.request('/api/stage', { method: 'PUT', body: JSON.stringify(document) })
  }

  parseStageRequest(text: string): Promise<StageDocumentDto> {
    return this.request('/api/stage/parse', {
      method: 'POST',
      body: JSON.stringify({ text }),
    })
  }

  searchStage(keyword: string, config: StageConfigDto, page = 1): Promise<StageSearchResponse> {
    return this.request('/api/stage/search', {
      method: 'POST',
      body: JSON.stringify({ keyword, config, page, duration_limit: 12 }),
    })
  }

  startStageCapture(timeout = 90): Promise<StageCaptureState> {
    return this.request('/api/stage/capture', {
      method: 'POST',
      body: JSON.stringify({ timeout }),
    })
  }

  stageCaptureState(): Promise<StageCaptureState> {
    return this.request('/api/stage/capture')
  }

  stageCoverBlob(workId: number): Promise<Blob> {
    return this.assetBlob('/api/stage/works/' + workId + '/cover', '作品封面')
  }

  settings(): Promise<TargetSettingsDto> {
    return this.request('/api/settings')
  }

  updateSettings(document: TargetSettingsDto): Promise<TargetSettingsDto> {
    return this.request('/api/settings', { method: 'PUT', body: JSON.stringify(document) })
  }

  probeWindow(windowHint: string, capture = false): Promise<WindowProbeResponse> {
    return this.request('/api/settings/probe', {
      method: 'POST',
      body: JSON.stringify({ window_hint: windowHint, capture }),
    })
  }

  preflight(): Promise<PreflightResponse> {
    return this.request('/api/settings/preflight')
  }
  runner(): Promise<RunnerStateResponse> {
    return this.request('/api/runner')
  }

  runPlan(activeGroup: string | null): Promise<RunPlanResponse> {
    return this.request('/api/runner/plan', {
      method: 'POST',
      body: JSON.stringify({ active_group: activeGroup }),
    })
  }

  start(payload: RunnerStartRequest): Promise<RunnerCommandResponse> {
    return this.request('/api/runner/start', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  }

  testStep(step: StepDto, song?: SongDto): Promise<RunnerCommandResponse> {
    return this.request('/api/runner/test-step', {
      method: 'POST',
      body: JSON.stringify({ step, song: song || null }),
    })
  }
  pause(): Promise<RunnerCommandResponse> {
    return this.request('/api/runner/pause', { method: 'POST' })
  }

  resume(): Promise<RunnerCommandResponse> {
    return this.request('/api/runner/resume', { method: 'POST' })
  }

  stop(): Promise<RunnerCommandResponse> {
    return this.request('/api/runner/stop', { method: 'POST' })
  }

  eventsUrl(): string {
    const scheme = this.connection.host === 'localhost' || this.connection.host === '127.0.0.1' ? 'ws' : 'wss'
    const token = encodeURIComponent(this.connection.token)
    return `${scheme}://${this.connection.host}:${this.connection.port}/api/events?token=${token}`
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response: Response
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          [SESSION_HEADER]: this.connection.token,
          'Content-Type': 'application/json',
          ...init.headers,
        },
      })
    } catch (error) {
      throw new ApiError(error instanceof Error ? error.message : '无法连接本地服务')
    }
    if (!response.ok) {
      let detail = `请求失败 (${response.status})`
      try {
        const body = (await response.json()) as { detail?: string }
        detail = body.detail || detail
      } catch {
        // Keep the status-based message when the response has no JSON body.
      }
      throw new ApiError(detail, response.status)
    }
    return (await response.json()) as T
  }
}

export function parseRunnerEvent(raw: string): RunnerEvent | null {
  try {
    const event = JSON.parse(raw) as RunnerEvent
    if (!event || typeof event.type !== 'string' || typeof event.timestamp !== 'number') {
      return null
    }
    return event
  } catch {
    return null
  }
}
