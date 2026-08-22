<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Clapperboard,
  ClipboardPaste,
  Clock3,
  Copy,
  FileSearch,
  Heart,
  LoaderCircle,
  Play,
  Radio,
  Save,
  Search,
  Star,
  UserRound,
  X,
} from '@lucide/vue'

import AppSelect from '../components/AppSelect.vue'
import { useRuntimeStore } from '../stores/runtime'
import type { PlaylistDocumentDto, StageConfigDto, StageWorkDto, StageWorkFilter } from '../types/api'

const runtime = useRuntimeStore()
const config = ref<StageConfigDto>({
  base_url: 'http://hapi.hi.163.com/nshm/action-station/work/list/search',
  role_id: '',
  user_id: '',
  skey: '',
  sort: '',
  page_size: '20',
  contents: '',
  sub_types: '',
  actor_count_contents: '',
  work_filter: 'single',
})
const keyword = ref('')
const sortBy = ref('match')
const sortDescending = ref(true)
const selectedWorkId = ref<number | null>(null)
const targetGroup = ref('')
const advancedOpen = ref(false)
const diagnosticsOpen = ref(false)
const localError = ref('')
const notice = ref('')
const coverUrls = ref<Record<number, string>>({})
let captureTimer: number | undefined
let diagnosticsTimer: number | undefined
let coverGeneration = 0
let autoCaptureAttempted = false
const pageActive = ref(false)

const filterOptions: Array<{ value: StageWorkFilter; label: string }> = [
  { value: 'single', label: '单人' },
  { value: 'all', label: '全部' },
  { value: 'multi', label: '多人' },
  { value: 'movie', label: '映画 / 翻拍' },
]
const sortOptions = [
  { value: 'match', label: '名称匹配' },
  { value: 'hot', label: '热度' },
  { value: 'collect', label: '收藏' },
  { value: 'like', label: '喜欢' },
  { value: 'duration', label: '时长' },
]
const groupOptions = computed(() =>
  (runtime.playlists?.song_groups || []).map((group) => ({ value: group.name, label: group.name })),
)
const selectedWork = computed(
  () => runtime.stageWorks.find((work) => work.work_id === selectedWorkId.value) || null,
)
const captureActive = computed(() =>
  ['listening', 'validating'].includes(runtime.stageCapture?.status || ''),
)
const diagnosticsRunning = computed(() => runtime.stageDiagnostics?.status === 'running')
const captureTone = computed(() => {
  if (runtime.stageCapture?.status === 'completed') return 'success'
  if (runtime.stageCapture?.status === 'failed') return 'error'
  return captureActive.value ? 'active' : ''
})
const sortedWorks = computed(() => {
  const query = keyword.value.trim().toLocaleLowerCase()
  const value = (work: StageWorkDto): number => {
    if (sortBy.value === 'hot') return work.hot
    if (sortBy.value === 'collect') return work.collect_count
    if (sortBy.value === 'like') return work.like_count
    if (sortBy.value === 'duration') return work.duration_seconds
    const name = work.name.trim().toLocaleLowerCase()
    return (name === query ? 6 : 0) + (query && name.startsWith(query) ? 2 : 0) + (query && name.includes(query) ? 1 : 0)
  }
  return [...runtime.stageWorks].sort((left, right) => {
    const difference = value(left) - value(right)
    if (difference !== 0) return sortDescending.value ? -difference : difference
    return right.hot - left.hot
  })
})

watch(
  () => runtime.stage,
  (document) => {
    if (!document) return
    config.value = { ...document.config }
    if (!keyword.value) keyword.value = document.keyword
  },
  { immediate: true },
)

watch(
  () => runtime.playlists,
  (document) => {
    if (!document) return
    if (!document.song_groups.some((group) => group.name === targetGroup.value)) {
      targetGroup.value = document.active_song_group !== '全部'
        ? document.active_song_group
        : document.song_groups[0]?.name || ''
    }
  },
  { immediate: true },
)

watch(
  () => runtime.stageWorks,
  (works) => {
    selectedWorkId.value = works[0]?.work_id ?? null
    void loadCovers(works)
  },
  { immediate: true },
)

watch(
  () => runtime.isConnected,
  (connected) => {
    if (connected && pageActive.value) maybeStartAutoCapture()
  },
)

onActivated(() => {
  pageActive.value = true
  maybeStartAutoCapture()
  if (captureActive.value) scheduleCapturePoll()
  if (diagnosticsOpen.value && diagnosticsRunning.value) scheduleDiagnosticsPoll()
})

onDeactivated(() => {
  pageActive.value = false
  clearCaptureTimer()
  clearDiagnosticsTimer()
})
onBeforeUnmount(() => {
  clearCaptureTimer()
  clearDiagnosticsTimer()
  releaseCoverUrls()
})

function maybeStartAutoCapture() {
  if (!runtime.isConnected || autoCaptureAttempted) return
  autoCaptureAttempted = true
  void startCapture()
}

async function searchWorks() {
  const query = keyword.value.trim()
  if (!query) {
    localError.value = '请输入作品名称'
    return
  }
  localError.value = ''
  notice.value = ''
  try {
    await runtime.searchStage(query, { ...config.value })
    notice.value = '找到 ' + runtime.stageWorks.length + ' 个候选'
  } catch (cause) {
    localError.value = messageOf(cause, '搜索失败')
  }
}

async function saveConfig() {
  localError.value = ''
  try {
    await runtime.saveStage({ config: { ...config.value }, keyword: keyword.value.trim() })
    notice.value = '接口配置已保存'
  } catch (cause) {
    localError.value = messageOf(cause, '保存配置失败')
  }
}

async function importClipboard() {
  localError.value = ''
  try {
    const text = await navigator.clipboard.readText()
    const parsed = await runtime.parseStageRequest(text)
    config.value = { ...parsed.config }
    notice.value = '已从剪贴板读取请求参数'
  } catch (cause) {
    localError.value = messageOf(cause, '无法读取剪贴板请求')
  }
}

async function startCapture() {
  clearCaptureTimer()
  localError.value = ''
  notice.value = ''
  try {
    const state = await runtime.startStageCapture(90)
    if (state.status === 'failed') {
      localError.value = state.message
      return
    }
    scheduleCapturePoll()
  } catch (cause) {
    localError.value = messageOf(cause, '无法启动参数监听')
  }
}

function scheduleCapturePoll() {
  clearCaptureTimer()
  captureTimer = window.setTimeout(() => void pollCapture(), 500)
}

async function pollCapture() {
  try {
    const state = await runtime.refreshStageCapture()
    if (state.status === 'completed') {
      if (state.config) config.value = { ...state.config }
      if (state.keyword) keyword.value = state.keyword
      notice.value = state.message
      return
    }
    if (state.status === 'failed') {
      localError.value = state.message
      return
    }
    scheduleCapturePoll()
  } catch (cause) {
    localError.value = messageOf(cause, '读取监听状态失败')
  }
}

function clearCaptureTimer() {
  if (captureTimer !== undefined) {
    window.clearTimeout(captureTimer)
    captureTimer = undefined
  }
}

async function openDiagnostics() {
  diagnosticsOpen.value = true
  localError.value = ''
  try {
    const state = await runtime.refreshStageDiagnostics()
    if (state.status === 'running') scheduleDiagnosticsPoll()
  } catch (cause) {
    localError.value = messageOf(cause, '无法读取诊断状态')
  }
}

function closeDiagnostics() {
  diagnosticsOpen.value = false
  clearDiagnosticsTimer()
}

async function startDiagnostics() {
  clearDiagnosticsTimer()
  localError.value = ''
  try {
    const state = await runtime.startStageDiagnostics()
    if (state.status === 'running') scheduleDiagnosticsPoll()
  } catch (cause) {
    localError.value = messageOf(cause, '无法启动高级诊断')
  }
}

function scheduleDiagnosticsPoll() {
  clearDiagnosticsTimer()
  diagnosticsTimer = window.setTimeout(() => void pollDiagnostics(), 650)
}

async function pollDiagnostics() {
  try {
    const state = await runtime.refreshStageDiagnostics()
    if (state.status === 'running') scheduleDiagnosticsPoll()
  } catch (cause) {
    localError.value = messageOf(cause, '读取诊断状态失败')
  }
}

function clearDiagnosticsTimer() {
  if (diagnosticsTimer !== undefined) {
    window.clearTimeout(diagnosticsTimer)
    diagnosticsTimer = undefined
  }
}

async function copyDiagnosticReport() {
  const report = runtime.stageDiagnostics?.report || ''
  if (!report) return
  try {
    await navigator.clipboard.writeText(report)
    notice.value = '诊断报告已复制'
  } catch (cause) {
    localError.value = messageOf(cause, '复制诊断报告失败')
  }
}

async function addSelectedWork() {
  if (!selectedWork.value || !runtime.playlists || !targetGroup.value) return
  const document = JSON.parse(JSON.stringify(runtime.playlists)) as PlaylistDocumentDto
  const group = document.song_groups.find((item) => item.name === targetGroup.value)
  if (!group) {
    localError.value = '目标队列不存在'
    return
  }
  group.songs.push({
    title: selectedWork.value.name,
    keyword: keyword.value.trim() || selectedWork.value.name,
    duration_seconds: selectedWork.value.duration_seconds,
    buffer_seconds: 5,
    enabled: true,
    step_preset: '',
  })
  document.active_song_group = group.name
  try {
    await runtime.savePlaylists(document)
    notice.value = '已将“' + selectedWork.value.name + '”加入 ' + group.name
  } catch (cause) {
    localError.value = messageOf(cause, '加入队列失败')
  }
}

function chooseFilter(value: StageWorkFilter) {
  config.value.work_filter = value
}

async function loadCovers(works: StageWorkDto[]) {
  const generation = ++coverGeneration
  releaseCoverUrls()
  const next: Record<number, string> = {}
  await Promise.all(
    works.filter((work) => work.cover_url).map(async (work) => {
      try {
        const blob = await runtime.loadStageCover(work.work_id)
        if (generation !== coverGeneration) return
        next[work.work_id] = URL.createObjectURL(blob)
      } catch {
        // Cards retain a quiet placeholder when a remote cover cannot be loaded.
      }
    }),
  )
  if (generation === coverGeneration) coverUrls.value = next
  else Object.values(next).forEach(URL.revokeObjectURL)
}

function releaseCoverUrls() {
  Object.values(coverUrls.value).forEach(URL.revokeObjectURL)
  coverUrls.value = {}
}

function formatDuration(seconds: number) {
  if (!seconds) return '未知'
  const minutes = Math.floor(seconds / 60)
  const remainder = Math.round(seconds % 60)
  return String(minutes).padStart(2, '0') + ':' + String(remainder).padStart(2, '0')
}

function messageOf(cause: unknown, fallback: string) {
  return cause instanceof Error && cause.message ? cause.message : fallback
}
</script>

<template>
  <main class="stage-page">
    <header class="stage-toolbar">
      <div class="stage-search-field">
        <Search :size="17" />
        <input v-model="keyword" aria-label="作品名称" placeholder="搜索作品名称" @keydown.enter="searchWorks" />
      </div>
      <div class="stage-filter-segments" aria-label="作品分类">
        <button
          v-for="option in filterOptions"
          :key="option.value"
          type="button"
          :class="{ active: config.work_filter === option.value }"
          @click="chooseFilter(option.value)"
        >
          {{ option.label }}
        </button>
      </div>
      <button class="button primary stage-search-button" type="button" :disabled="runtime.stageSearching" @click="searchWorks">
        <LoaderCircle v-if="runtime.stageSearching" class="spin" :size="15" />
        <Search v-else :size="15" />
        搜索
      </button>
      <button class="icon-button" type="button" title="重新监听游戏参数" :disabled="captureActive" @click="startCapture">
        <LoaderCircle v-if="captureActive" class="spin" :size="17" />
        <Radio v-else :size="17" />
      </button>
      <button class="icon-button" type="button" title="高级诊断" :class="{ active: diagnosticsOpen }" @click="openDiagnostics">
        <FileSearch :size="17" />
      </button>
      <button class="icon-button" type="button" title="接口配置" :class="{ active: advancedOpen }" @click="advancedOpen = !advancedOpen">
        <ChevronDown :size="17" :class="{ 'rotate-half': advancedOpen }" />
      </button>
    </header>

    <Transition name="panel-reveal">
      <form v-if="advancedOpen" class="stage-config-panel" @submit.prevent="saveConfig">
        <label class="wide">搜索接口<input v-model="config.base_url" /></label>
        <label>Role ID<input v-model="config.role_id" /></label>
        <label>User ID<input v-model="config.user_id" /></label>
        <label class="wide">SKey<input v-model="config.skey" type="password" autocomplete="off" /></label>
        <label>服务端排序<input v-model="config.sort" /></label>
        <label>每页数量<input v-model="config.page_size" inputmode="numeric" /></label>
        <div class="stage-config-actions">
          <button class="button secondary compact" type="button" @click="importClipboard"><ClipboardPaste :size="14" />剪贴板导入</button>
          <button class="button secondary compact" type="submit" :disabled="runtime.stageSaving"><Save :size="14" />保存配置</button>
        </div>
      </form>
    </Transition>

    <div v-if="runtime.stageCapture" class="stage-capture-status" :class="captureTone">
      <Radio v-if="captureActive" :size="15" />
      <Check v-else-if="runtime.stageCapture.status === 'completed'" :size="15" />
      <AlertTriangle v-else-if="runtime.stageCapture.status === 'failed'" :size="15" />
      <span>{{ runtime.stageCapture.message }}</span>
    </div>
    <div v-if="localError || notice" class="stage-inline-message" :class="{ error: localError }">
      <AlertTriangle v-if="localError" :size="15" />
      <Check v-else :size="15" />
      <span>{{ localError || notice }}</span>
    </div>

    <section class="stage-results-bar">
      <div>
        <Clapperboard :size="17" />
        <strong>作品结果</strong>
        <span>{{ runtime.stageWorks.length }}</span>
      </div>
      <label class="stage-sort-direction"><input v-model="sortDescending" type="checkbox" />降序</label>
      <AppSelect v-model="sortBy" :options="sortOptions" label="排序方式" />
    </section>

    <section class="stage-results">
      <div v-if="runtime.stageSearching" class="stage-empty">
        <LoaderCircle class="spin" :size="28" />
        <strong>正在读取作品</strong>
      </div>
      <div v-else-if="!sortedWorks.length" class="stage-empty">
        <Clapperboard :size="32" />
        <strong>暂无搜索结果</strong>
      </div>
      <article
        v-for="work in sortedWorks"
        v-else
        :key="work.work_id"
        class="stage-work-card"
        :class="{ selected: selectedWorkId === work.work_id }"
        tabindex="0"
        @click="selectedWorkId = work.work_id"
        @keydown.enter="selectedWorkId = work.work_id"
      >
        <div class="stage-cover">
          <img v-if="coverUrls[work.work_id]" :src="coverUrls[work.work_id]" :alt="work.name" />
          <Clapperboard v-else :size="32" />
          <span>{{ work.category_label }}</span>
        </div>
        <div class="stage-work-body">
          <div class="stage-work-title">
            <h3>{{ work.name }}</h3>
            <code>#{{ work.work_id }}</code>
          </div>
          <p class="stage-author"><UserRound :size="13" />{{ work.designer_name || '未知作者' }}</p>
          <p class="stage-summary">{{ work.summary || '暂无简介' }}</p>
          <dl class="stage-metrics">
            <div><dt><Clock3 :size="13" />时长</dt><dd>{{ formatDuration(work.duration_seconds) }}</dd></div>
            <div><dt><Star :size="13" />热度</dt><dd>{{ work.hot }}</dd></div>
            <div><dt>收藏</dt><dd>{{ work.collect_count }}</dd></div>
            <div><dt><Heart :size="13" />喜欢</dt><dd>{{ work.like_count }}</dd></div>
          </dl>
        </div>
      </article>
    </section>

    <footer class="stage-action-bar">
      <div class="stage-selected-summary">
        <span>当前选择</span>
        <strong>{{ selectedWork?.name || '未选择作品' }}</strong>
        <small v-if="selectedWork">{{ selectedWork.designer_name }} · {{ formatDuration(selectedWork.duration_seconds) }}</small>
      </div>
      <AppSelect v-model="targetGroup" :options="groupOptions" label="目标队列" searchable search-placeholder="搜索队列" />
      <button class="button primary" type="button" :disabled="!selectedWork || !targetGroup || runtime.playlistSaving" @click="addSelectedWork">
        <LoaderCircle v-if="runtime.playlistSaving" class="spin" :size="15" />
        <Save v-else :size="15" />
        加入队列
      </button>
    </footer>

    <div v-if="diagnosticsOpen" class="dialog-backdrop stage-diagnostics-backdrop" @mousedown.self="closeDiagnostics">
      <section class="stage-diagnostics-dialog" role="dialog" aria-modal="true" aria-label="剧组站高级诊断">
        <header class="dialog-header">
          <div class="dialog-title-wrap">
            <span class="dialog-icon"><FileSearch :size="17" /></span>
            <div><h2>高级诊断</h2><p>{{ runtime.stageDiagnostics?.message || '尚未运行诊断' }}</p></div>
          </div>
          <button class="icon-button small" type="button" title="关闭" @click="closeDiagnostics"><X :size="16" /></button>
        </header>

        <div class="stage-diagnostics-content">
          <div class="stage-diagnostics-summary">
            <div><span>缓存文件</span><strong>{{ runtime.stageDiagnostics?.summary.cache_files_seen || 0 }}</strong></div>
            <div><span>缓存命中</span><strong>{{ runtime.stageDiagnostics?.summary.cache_hits || 0 }}</strong></div>
            <div><span>模块命中</span><strong>{{ runtime.stageDiagnostics?.summary.binary_hits || 0 }}</strong></div>
            <div><span>候选方法</span><strong>{{ runtime.stageDiagnostics?.summary.method_candidates || 0 }}</strong></div>
            <div><span>动作日志</span><strong>{{ runtime.stageDiagnostics?.summary.action_play_logs || 0 }}</strong></div>
            <div><span>二维码日志</span><strong>{{ runtime.stageDiagnostics?.summary.qrcode_work_logs || 0 }}</strong></div>
          </div>

          <div v-if="runtime.stageDiagnostics?.notes.length" class="stage-diagnostics-notes">
            <strong>结论</strong>
            <ul><li v-for="note in runtime.stageDiagnostics.notes" :key="note">{{ note }}</li></ul>
          </div>

          <pre class="stage-diagnostics-report">{{ runtime.stageDiagnostics?.report || '尚未生成报告。' }}</pre>
        </div>

        <footer class="dialog-actions stage-diagnostics-actions">
          <button class="button secondary" type="button" :disabled="!runtime.stageDiagnostics?.report" @click="copyDiagnosticReport">
            <Copy :size="14" />复制报告
          </button>
          <button class="button primary" type="button" :disabled="diagnosticsRunning" @click="startDiagnostics">
            <LoaderCircle v-if="diagnosticsRunning" class="spin" :size="15" />
            <Play v-else :size="15" />
            {{ diagnosticsRunning ? '诊断中' : '开始诊断' }}
          </button>
        </footer>
      </section>
    </div>
  </main>
</template>