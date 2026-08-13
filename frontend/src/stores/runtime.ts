import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { invoke, isTauri } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'

import { MacroStudioClient, parseRunnerEvent } from '../api/client'
import type {
  ConnectionPhase,
  HealthResponse,
  ImageTargetDto,
  PlaylistDocumentDto,
  PointCaptureState,
  PointPreviewResponse,
  PresetDto,
  RunnerEvent,
  RunnerMode,
  RegionSelectionResponse,
  RunnerStateResponse,
  RunnerStatus,
  SidecarConnection,
  TargetLibraryDto,
  TemplateImportResponse,
  VisionTestResponse,
  TargetSettingsDto,
  WindowProbeResponse,
  PreflightResponse,
  StepDto,
} from '../types/api'

const MAX_EVENTS = 300

export const useRuntimeStore = defineStore('runtime', () => {
  const phase = ref<ConnectionPhase>('disconnected')
  const connection = ref<SidecarConnection | null>(null)
  const health = ref<HealthResponse | null>(null)
  const playlists = ref<PlaylistDocumentDto | null>(null)
  const presets = ref<PresetDto[]>([])
  const targets = ref<TargetLibraryDto | null>(null)
  const settings = ref<TargetSettingsDto | null>(null)
  const settingsSaving = ref(false)
  const runner = ref<RunnerStateResponse>({ status: 'idle', active: false, mode: 'simulation' })
  const events = ref<RunnerEvent[]>([])
  const error = ref('')
  const selectedGroup = ref('全部')
  const loop = ref(false)
  const random = ref(false)
  const executionMode = ref<RunnerMode>('simulation')
  const logExpanded = ref(true)
  const currentSong = ref('')
  const currentStep = ref('')
  const commandPending = ref(false)
  const playlistSaving = ref(false)
  const presetSaving = ref(false)
  const targetSaving = ref(false)
  const client = shallowRef<MacroStudioClient | null>(null)
  const socket = shallowRef<WebSocket | null>(null)
  let reconnectTimer: number | undefined
  let sidecarUnlisten: UnlistenFn | undefined
  let sidecarErrorUnlisten: UnlistenFn | undefined
  let sidecarExitUnlisten: UnlistenFn | undefined
  let intentionalDisconnect = false
  let localSequence = -1

  const isConnected = computed(() => phase.value === 'connected')
  const isRunning = computed(() => ['starting', 'running', 'paused', 'stopping'].includes(runner.value.status))
  const canStart = computed(() => isConnected.value && !isRunning.value && !commandPending.value)
  const canPause = computed(() => isConnected.value && runner.value.status === 'running' && !commandPending.value)
  const canResume = computed(() => isConnected.value && runner.value.status === 'paused' && !commandPending.value)
  const canStop = computed(() => isConnected.value && isRunning.value && !commandPending.value)
  const activeGroup = computed(() => {
    if (!playlists.value) return null
    if (selectedGroup.value === '全部') return null
    return playlists.value.song_groups.find((group) => group.name === selectedGroup.value) ?? null
  })
  const visibleSongs = computed(() => {
    if (!playlists.value) return []
    if (activeGroup.value) return activeGroup.value.songs
    return playlists.value.song_groups.flatMap((group) => group.songs)
  })
  const enabledSongCount = computed(() => visibleSongs.value.filter((song) => song.enabled).length)

  async function initialize() {
    if (isTauri()) {
      sidecarUnlisten = await listen<SidecarConnection>('sidecar-ready', ({ payload }) => {
        void connect(payload)
      })
      sidecarErrorUnlisten = await listen<string>('sidecar-error', ({ payload }) => {
        fail(new Error(payload), '本地服务启动失败')
      })
      sidecarExitUnlisten = await listen('sidecar-exited', () => {
        closeSocket()
        phase.value = 'error'
        error.value = '本地服务已退出'
      })
      try {
        const current = await invoke<SidecarConnection | null>('sidecar_connection')
        if (current) {
          await connect(current)
        } else {
          phase.value = 'connecting'
        }
      } catch (cause) {
        fail(cause, '无法获取 sidecar 状态')
      }
      return
    }
    const host = import.meta.env.VITE_API_HOST as string | undefined
    const port = Number(import.meta.env.VITE_API_PORT || 0)
    const token = import.meta.env.VITE_API_TOKEN as string | undefined
    if (host && port && token) {
      await connect({ host, port, token, api_version: '' })
    }
  }

  async function connect(nextConnection: SidecarConnection) {
    intentionalDisconnect = false
    clearReconnect()
    closeSocket()
    phase.value = 'connecting'
    error.value = ''
    connection.value = nextConnection
    const nextClient = new MacroStudioClient(nextConnection)
    client.value = nextClient
    try {
      const [nextHealth, nextPlaylists, nextPresets, nextTargets, nextSettings, nextRunner] = await Promise.all([
        nextClient.health(),
        nextClient.playlists(),
        nextClient.presets(),
        nextClient.targets(),
        nextClient.settings(),
        nextClient.runner(),
      ])
      health.value = nextHealth
      playlists.value = nextPlaylists
      presets.value = nextPresets
      targets.value = nextTargets
      settings.value = nextSettings
      runner.value = nextRunner
      executionMode.value = nextRunner.mode
      selectedGroup.value = nextPlaylists.active_song_group || '全部'
      phase.value = 'connected'
      openSocket()
    } catch (cause) {
      fail(cause, '连接本地服务失败')
    }
  }

  function disconnect() {
    intentionalDisconnect = true
    clearReconnect()
    closeSocket()
    phase.value = 'disconnected'
    connection.value = null
    client.value = null
    health.value = null
  }

  async function start() {
    if (!client.value || !canStart.value) return
    await runCommand(async () => {
      const response = await client.value!.start({
        active_group: selectedGroup.value,
        loop: loop.value,
        random: random.value,
        simulation: executionMode.value === 'simulation',
      })
      applyRunnerStatus(response.status, response.mode)
    })
  }

  async function testStep(step: StepDto) {
    if (!client.value || !canStart.value) return false
    const song = visibleSongs.value.find((item) => item.enabled)
    return runCommand(async () => {
      const response = await client.value!.testStep({ ...step }, song ? { ...song } : undefined)
      applyRunnerStatus(response.status, response.mode)
    })
  }
  async function pause() {
    if (!client.value || !canPause.value) return
    await runCommand(async () => applyRunnerStatus((await client.value!.pause()).status))
  }

  async function resume() {
    if (!client.value || !canResume.value) return
    await runCommand(async () => applyRunnerStatus((await client.value!.resume()).status))
  }

  async function stop() {
    if (!client.value || !canStop.value) return
    await runCommand(async () => applyRunnerStatus((await client.value!.stop()).status))
  }

  async function refreshRunner() {
    if (!client.value) return
    try {
      runner.value = await client.value.runner()
    } catch (cause) {
      fail(cause, '刷新运行状态失败')
    }
  }

  async function savePlaylists(document: PlaylistDocumentDto) {
    if (!client.value || !isConnected.value) {
      throw new Error('本地服务未连接')
    }
    playlistSaving.value = true
    try {
      const saved = await client.value.updatePlaylists(document)
      playlists.value = saved
      selectedGroup.value = saved.active_song_group
      return saved
    } finally {
      playlistSaving.value = false
    }
  }

  async function savePresets(document: PresetDto[]) {
    if (!client.value || !isConnected.value) {
      throw new Error('本地服务未连接')
    }
    presetSaving.value = true
    try {
      const saved = await client.value.updatePresets(document)
      presets.value = saved
      return saved
    } finally {
      presetSaving.value = false
    }
  }

  async function saveTargets(
    document: TargetLibraryDto,
    pointRenames: Record<string, string> = {},
    imageTargetRenames: Record<string, string> = {},
  ) {
    if (!client.value || !isConnected.value) {
      throw new Error('本地服务未连接')
    }
    targetSaving.value = true
    try {
      const saved = await client.value.updateTargets(document, pointRenames, imageTargetRenames)
      targets.value = saved
      return saved
    } finally {
      targetSaving.value = false
    }
  }

  async function importTemplate(targetName: string, filename: string, dataUrl: string): Promise<TemplateImportResponse> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    return client.value.importTemplate(targetName, filename, dataUrl)
  }

  async function importMask(targetName: string, filename: string, dataUrl: string): Promise<TemplateImportResponse> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    return client.value.importMask(targetName, filename, dataUrl)
  }

  async function loadMaskPreview(targetName: string): Promise<string> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    return URL.createObjectURL(await client.value.maskBlob(targetName))
  }

  async function loadTemplatePreview(targetName: string): Promise<string> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    return URL.createObjectURL(await client.value.templateBlob(targetName))
  }

  async function armPointCapture(groupName: string, pointName: string): Promise<PointCaptureState> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    return client.value.armPointCapture(groupName, pointName)
  }

  async function pointCaptureState(): Promise<PointCaptureState> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    return client.value.pointCaptureState()
  }

  async function cancelPointCapture(): Promise<PointCaptureState> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    return client.value.cancelPointCapture()
  }

  async function previewPoint(name: string, x: number, y: number, duration = 2.6): Promise<PointPreviewResponse> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    return client.value.previewPoint(name, x, y, duration)
  }

  async function selectRegion(): Promise<RegionSelectionResponse> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    const result = await client.value.selectRegion()
    if (!result.cancelled) {
      appendLocalEvent('region.selected', {
        message: `已选择识别区域：${result.x}, ${result.y}, ${result.width} x ${result.height}`,
      })
    }
    return result
  }

  async function testImageTarget(target: ImageTargetDto): Promise<VisionTestResponse> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    appendLocalEvent('vision.test_started', { name: target.name })
    try {
      const result = await client.value.testImageTarget(target)
      appendLocalEvent(result.matched ? 'vision.test.completed' : 'vision.test.failed', {
        name: target.name,
        score: result.score,
        error: result.error,
        source: result.source,
      })
      return result
    } catch (cause) {
      const message = errorMessage(cause, '测试识别失败')
      appendLocalEvent('vision.test.failed', { name: target.name, error: message })
      throw cause
    }
  }

  async function saveSettings(document: TargetSettingsDto): Promise<TargetSettingsDto> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    settingsSaving.value = true
    try {
      const saved = await client.value.updateSettings(document)
      settings.value = saved
      return saved
    } finally {
      settingsSaving.value = false
    }
  }

  async function probeWindow(windowHint: string, capture = false): Promise<WindowProbeResponse> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    return client.value.probeWindow(windowHint, capture)
  }

  async function preflight(): Promise<PreflightResponse> {
    if (!client.value || !isConnected.value) throw new Error('本地服务未连接')
    return client.value.preflight()
  }
  function clearEvents() {
    events.value = []
  }

  function toggleLog() {
    logExpanded.value = !logExpanded.value
  }

  function dispose() {
    intentionalDisconnect = true
    clearReconnect()
    closeSocket()
    sidecarUnlisten?.()
    sidecarErrorUnlisten?.()
    sidecarExitUnlisten?.()
    sidecarUnlisten = undefined
    sidecarErrorUnlisten = undefined
    sidecarExitUnlisten = undefined
  }

  async function runCommand(command: () => Promise<void>) {
    commandPending.value = true
    error.value = ''
    try {
      await command()
      return true
    } catch (cause) {
      const message = errorMessage(cause, '命令执行失败')
      error.value = message
      appendLocalEvent('command.failed', { error: message })
      return false
    } finally {
      commandPending.value = false
    }
  }

  function appendLocalEvent(type: string, data: Record<string, unknown>, status: RunnerStatus | '' = runner.value.status) {
    consumeEvent({
      sequence: localSequence--,
      timestamp: Date.now() / 1000,
      type,
      status,
      data,
    })
  }

  function openSocket() {
    if (!client.value) return
    closeSocket()
    const nextSocket = new WebSocket(client.value.eventsUrl())
    socket.value = nextSocket
    nextSocket.onmessage = ({ data }) => {
      if (typeof data !== 'string') return
      const event = parseRunnerEvent(data)
      if (event) consumeEvent(event)
    }
    nextSocket.onopen = () => {
      phase.value = 'connected'
      error.value = ''
    }
    nextSocket.onerror = () => {
      error.value = '事件连接暂时不可用'
    }
    nextSocket.onclose = () => {
      if (socket.value === nextSocket) socket.value = null
      if (!intentionalDisconnect && client.value) {
        phase.value = 'connecting'
        scheduleReconnect()
      }
    }
  }

  function consumeEvent(event: RunnerEvent) {
    if (event.type === 'connection.heartbeat') return
    events.value.push(event)
    if (events.value.length > MAX_EVENTS) {
      events.value.splice(0, events.value.length - MAX_EVENTS)
    }
    if (event.status) {
      const eventMode = event.data.mode === 'real' ? 'real' : event.data.mode === 'simulation' ? 'simulation' : undefined
      applyRunnerStatus(event.status, eventMode)
    }
    if (event.type === 'song.started') {
      currentSong.value = String(event.data.label || '')
    } else if (event.type === 'step.started') {
      currentStep.value = String(event.data.name || '')
    } else if (['runner.completed', 'runner.stopped', 'runner.failed'].includes(event.type)) {
      currentStep.value = ''
      void refreshRunner()
    }
  }

  function applyRunnerStatus(status: RunnerStatus, mode?: RunnerMode) {
    runner.value = {
      status,
      active: ['starting', 'running', 'paused', 'stopping'].includes(status),
      mode: mode || runner.value.mode,
    }
  }

  function scheduleReconnect() {
    clearReconnect()
    reconnectTimer = window.setTimeout(() => {
      if (connection.value) void connect(connection.value)
    }, 1500)
  }

  function clearReconnect() {
    if (reconnectTimer !== undefined) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = undefined
    }
  }

  function closeSocket() {
    const activeSocket = socket.value
    socket.value = null
    if (activeSocket) {
      activeSocket.onclose = null
      activeSocket.close()
    }
  }

  function fail(cause: unknown, fallback: string) {
    error.value = errorMessage(cause, fallback)
    phase.value = 'error'
  }

  function errorMessage(cause: unknown, fallback: string) {
    return cause instanceof Error && cause.message ? cause.message : fallback
  }

  return {
    phase,
    connection,
    health,
    playlists,
    presets,
    targets,
    settings,
    runner,
    events,
    error,
    selectedGroup,
    loop,
    random,
    executionMode,
    logExpanded,
    currentSong,
    currentStep,
    commandPending,
    playlistSaving,
    presetSaving,
    targetSaving,
    settingsSaving,
    isConnected,
    isRunning,
    canStart,
    canPause,
    canResume,
    canStop,
    visibleSongs,
    enabledSongCount,
    initialize,
    connect,
    disconnect,
    start,
    testStep,
    pause,
    resume,
    stop,
    refreshRunner,
    savePlaylists,
    savePresets,
    saveTargets,
    importTemplate,
    importMask,
    loadMaskPreview,
    loadTemplatePreview,
    armPointCapture,
    pointCaptureState,
    cancelPointCapture,
    previewPoint,
    selectRegion,
    testImageTarget,
    saveSettings,
    probeWindow,
    preflight,
    clearEvents,
    toggleLog,
    dispose,
  }
})
