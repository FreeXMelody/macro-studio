<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  AlertTriangle,
  Check,
  Copy,
  FlaskConical,
  GripVertical,
  MousePointer2,
  Pencil,
  Plus,
  Play,
  RotateCcw,
  Save,
  ShieldAlert,
  Trash2,
  Workflow,
  X,
} from '@lucide/vue'

import AppSelect from '../components/AppSelect.vue'
import { clonePlaylist } from '../domain/playlist'
import {
  ACTION_TYPE_OPTIONS,
  actionType,
  clonePresets,
  emptyStep,
  reorderSteps,
  uniquePresetName,
} from '../domain/workflow'
import { useRuntimeStore } from '../stores/runtime'
import type { PlaylistDocumentDto, PresetDto, StepDto } from '../types/api'

type NameDialogMode = 'add' | 'rename' | 'duplicate'

const runtime = useRuntimeStore()
const draft = ref<PresetDto[]>([])
const linkedPlaylists = ref<PlaylistDocumentDto | null>(null)
const baseline = ref('[]')
const playlistBaseline = ref('')
const initialized = ref(false)
const selectedPresetName = ref('')
const localError = ref('')
const notice = ref('')
const nameDialogOpen = ref(false)
const nameDialogMode = ref<NameDialogMode>('add')
const nameInput = ref('')
const stepDialogOpen = ref(false)
const editingStepIndex = ref<number | null>(null)
const stepForm = ref<StepDto>(emptyStep())
const confirmDeletePreset = ref(false)
const testStepIndex = ref<number | null>(null)
const suppressStepTestConfirmation = ref(false)
const draggedIndex = ref<number | null>(null)
const dropIndex = ref<number | null>(null)
const dragPoint = ref({ x: 0, y: 0 })

const selectedPreset = computed(
  () => draft.value.find((preset) => preset.name === selectedPresetName.value) ?? draft.value[0] ?? null,
)
const steps = computed(() => selectedPreset.value?.steps ?? [])
const enabledCount = computed(() => steps.value.filter((step) => step.enabled).length)
const dirty = computed(
  () =>
    JSON.stringify(draft.value) !== baseline.value ||
    JSON.stringify(linkedPlaylists.value) !== playlistBaseline.value,
)
const canSave = computed(() => runtime.isConnected && dirty.value && !runtime.presetSaving)
const typeOptions = ACTION_TYPE_OPTIONS.map(({ value, label }) => ({ value, label }))
const activePointGroup = computed(() => {
  const library = runtime.targets
  if (!library) return null
  return library.point_groups.find((group) => group.name === library.active_point_group) ?? library.point_groups[0] ?? null
})
const pointTargetOptions = computed(() => {
  const options = (activePointGroup.value?.points ?? []).map((point) => ({
    value: point.name,
    label: `${point.name} · X ${point.x}, Y ${point.y}`,
  }))
  const current = stepForm.value.target.trim()
  if (current && !options.some((option) => option.value === current)) {
    options.unshift({ value: current, label: `${current} · 未在当前点位组中找到` })
  }
  return options
})
const imageTargetOptions = computed(() => {
  const options = (runtime.targets?.image_targets ?? []).map((target) => ({
    value: target.name,
    label: `${target.name} · ${target.match_mode}`,
  }))
  const current = stepForm.value.value.trim()
  if (current && !options.some((option) => option.value === current)) {
    options.unshift({ value: current, label: `${current} · 图像目标不存在` })
  }
  return options
})
const currentType = computed(() => actionType(stepForm.value.kind))
const valueLabel = computed(() => {
  if (stepForm.value.kind === 'image_click') return '图像目标'
  if (stepForm.value.kind === 'wait') return '等待时长'
  if (['key', 'key_hold', 'key_down', 'key_up', 'hotkey', 'hotkey_hold'].includes(stepForm.value.kind)) {
    return '按键参数'
  }
  if (stepForm.value.kind === 'open_uri') return '链接或协议'
  if (stepForm.value.kind === 'http_request') return '请求'
  if (stepForm.value.kind === 'log') return '日志内容'
  return '参数'
})
const draggedStepName = computed(() =>
  draggedIndex.value === null ? '' : steps.value[draggedIndex.value]?.name || '',
)
const dragGhostStyle = computed(() => ({
  left: Math.max(8, Math.min(window.innerWidth - 224, dragPoint.value.x + 14)) + 'px',
  top: Math.max(8, Math.min(window.innerHeight - 42, dragPoint.value.y + 12)) + 'px',
}))

watch(
  [() => runtime.presets, () => runtime.playlists],
  () => {
    if (!initialized.value || !dirty.value) loadFromRuntime()
  },
  { deep: true, immediate: true },
)

onBeforeUnmount(clearPointerDrag)

function loadFromRuntime() {
  draft.value = clonePresets(runtime.presets)
  linkedPlaylists.value = runtime.playlists ? clonePlaylist(runtime.playlists) : null
  baseline.value = JSON.stringify(draft.value)
  playlistBaseline.value = JSON.stringify(linkedPlaylists.value)
  if (!draft.value.some((preset) => preset.name === selectedPresetName.value)) {
    selectedPresetName.value = draft.value[0]?.name || ''
  }
  initialized.value = true
  localError.value = ''
}

function selectPreset(name: string) {
  selectedPresetName.value = name
}

function openNameDialog(mode: NameDialogMode) {
  nameDialogMode.value = mode
  if (mode === 'add') nameInput.value = uniquePresetName(draft.value)
  else if (mode === 'rename') nameInput.value = selectedPreset.value?.name || ''
  else nameInput.value = uniquePresetName(draft.value, `${selectedPreset.value?.name || '动作预设'} 副本`)
  nameDialogOpen.value = true
}

function submitPresetName() {
  const name = nameInput.value.trim()
  if (!name) {
    localError.value = '动作预设名称不能为空'
    return
  }
  const current = selectedPreset.value
  const existing = draft.value.find((preset) => preset.name === name)
  if (existing && !(nameDialogMode.value === 'rename' && existing === current)) {
    localError.value = `动作预设名称重复：${name}`
    return
  }

  if (nameDialogMode.value === 'add') {
    draft.value.push({ name, steps: [] })
  } else if (nameDialogMode.value === 'duplicate' && current) {
    draft.value.push({ name, steps: current.steps.map((step) => ({ ...step })) })
  } else if (current) {
    const oldName = current.name
    current.name = name
    replacePresetReferences(oldName, name)
  }
  selectedPresetName.value = name
  nameDialogOpen.value = false
  localError.value = ''
}

function replacePresetReferences(oldName: string, nextName: string) {
  if (!linkedPlaylists.value || oldName === nextName) return
  linkedPlaylists.value.song_groups.forEach((group) => {
    if (group.step_preset === oldName) group.step_preset = nextName
    group.songs.forEach((song) => {
      if (song.step_preset === oldName) song.step_preset = nextName
    })
  })
}

function deletePreset() {
  const current = selectedPreset.value
  if (!current) return
  const index = draft.value.indexOf(current)
  replacePresetReferences(current.name, '')
  draft.value.splice(index, 1)
  selectedPresetName.value = draft.value[Math.min(index, draft.value.length - 1)]?.name || ''
  confirmDeletePreset.value = false
}

function openStep(index: number | null) {
  editingStepIndex.value = index
  stepForm.value = index === null ? emptyStep() : { ...steps.value[index] }
  stepDialogOpen.value = true
}

function setStepKind(kind: string) {
  const previous = actionType(stepForm.value.kind)
  const next = actionType(kind)
  if (!stepForm.value.name.trim() || stepForm.value.name === previous.label) stepForm.value.name = next.label
  stepForm.value.kind = kind
  if (!next.needsTarget) stepForm.value.target = ''
  if (!next.needsValue) stepForm.value.value = ''
}

function submitStep() {
  const preset = selectedPreset.value
  if (!preset) return
  const spec = actionType(stepForm.value.kind)
  const waitAfter = stepForm.value.wait_after.trim()
  if (waitAfter && !/^\d+(?:\.\d+)?$|^\d+:[0-5]\d(?:\.\d+)?$|^\d+:[0-5]\d:[0-5]\d(?:\.\d+)?$/.test(waitAfter)) {
    localError.value = '动作后等待请输入秒数，例如 0.5，或时间格式 00:02'
    return
  }
  const step: StepDto = {
    name: stepForm.value.name.trim() || spec.label,
    kind: stepForm.value.kind,
    target: spec.needsTarget ? stepForm.value.target.trim() : '',
    value: spec.needsValue ? stepForm.value.value.trim() : '',
    enabled: stepForm.value.enabled,
    wait_after: stepForm.value.kind === 'wait' ? '' : waitAfter,
  }
  if (spec.needsTarget && !step.target) {
    localError.value = '请填写动作点位'
    return
  }
  if (spec.needsValue && !step.value) {
    localError.value = `请填写${valueLabel.value}`
    return
  }
  if (editingStepIndex.value === null) preset.steps.push(step)
  else preset.steps[editingStepIndex.value] = step
  stepDialogOpen.value = false
  localError.value = ''
}

async function requestStepTest(index: number) {
  if (runtime.settings?.confirm_step_test === false) {
    await runStepTest(index)
    return
  }
  suppressStepTestConfirmation.value = false
  testStepIndex.value = index
}

async function confirmStepTest() {
  const index = testStepIndex.value
  testStepIndex.value = null
  if (index === null || !steps.value[index]) return
  if (suppressStepTestConfirmation.value && runtime.settings) {
    await runtime.saveSettings({ ...runtime.settings, confirm_step_test: false })
  }
  await runStepTest(index)
}

async function runStepTest(index: number) {
  const step = steps.value[index]
  if (!step) return
  localError.value = ''
  const started = await runtime.testStep({ ...step })
  notice.value = started
    ? `已启动单步测试：${step.name}，结果将写入运行日志`
    : `单步测试未能启动：${step.name}，请展开运行日志查看原因`
}
function duplicateStep(index: number) {
  const preset = selectedPreset.value
  if (!preset) return
  const source = preset.steps[index]
  preset.steps.splice(index + 1, 0, { ...source, name: `${source.name} 副本` })
}

function deleteStep(index: number) {
  selectedPreset.value?.steps.splice(index, 1)
}

function setStepEnabled(index: number, event: Event) {
  if (!selectedPreset.value) return
  selectedPreset.value.steps[index].enabled = (event.target as HTMLInputElement).checked
}

function parameterSummary(step: StepDto) {
  if (actionType(step.kind).needsTarget) return step.target || '未设置'
  if (actionType(step.kind).needsValue) return step.value || '未设置'
  return '无需参数'
}

function beginPointerDrag(index: number, event: PointerEvent) {
  if (event.button !== 0) return
  event.preventDefault()
  draggedIndex.value = index
  dropIndex.value = index
  dragPoint.value = { x: event.clientX, y: event.clientY }
  document.body.classList.add('workflow-is-dragging')
  document.addEventListener('pointermove', onPointerDrag)
  document.addEventListener('pointerup', finishPointerDrag, { once: true })
  document.addEventListener('pointercancel', clearPointerDrag, { once: true })
}

function onPointerDrag(event: PointerEvent) {
  if (draggedIndex.value === null) return
  dragPoint.value = { x: event.clientX, y: event.clientY }
  const row = document
    .elementsFromPoint(event.clientX, event.clientY)
    .map((element) => element.closest<HTMLTableRowElement>('tr[data-step-index]'))
    .find((element): element is HTMLTableRowElement => Boolean(element))
  if (!row) return
  const index = Number(row.dataset.stepIndex)
  if (Number.isInteger(index)) dropIndex.value = index
}

function finishPointerDrag() {
  const from = draggedIndex.value
  const to = dropIndex.value
  clearPointerDrag()
  if (selectedPreset.value && from !== null && to !== null) reorderSteps(selectedPreset.value, from, to)
}

function clearPointerDrag() {
  document.body.classList.remove('workflow-is-dragging')
  document.removeEventListener('pointermove', onPointerDrag)
  document.removeEventListener('pointerup', finishPointerDrag)
  document.removeEventListener('pointercancel', clearPointerDrag)
  draggedIndex.value = null
  dropIndex.value = null
}

function moveStepByKeyboard(index: number, direction: number) {
  const preset = selectedPreset.value
  if (!preset) return
  reorderSteps(preset, index, index + direction)
}

async function save() {
  if (!canSave.value) return
  localError.value = ''
  try {
    if (linkedPlaylists.value && JSON.stringify(linkedPlaylists.value) !== playlistBaseline.value) {
      await runtime.savePlaylists(clonePlaylist(linkedPlaylists.value))
    }
    const saved = await runtime.savePresets(clonePresets(draft.value))
    draft.value = clonePresets(saved)
    linkedPlaylists.value = runtime.playlists ? clonePlaylist(runtime.playlists) : linkedPlaylists.value
    baseline.value = JSON.stringify(draft.value)
    playlistBaseline.value = JSON.stringify(linkedPlaylists.value)
    notice.value = '工作流已保存'
    window.setTimeout(() => {
      if (notice.value === '工作流已保存') notice.value = ''
    }, 2200)
  } catch (error) {
    localError.value = error instanceof Error ? error.message : '保存工作流失败'
  }
}
</script>

<template>
  <main class="workflow-page">
    <template v-if="initialized && runtime.isConnected">
      <aside class="preset-rail">
        <header class="preset-rail-header">
          <div>
            <p class="section-kicker">WORKFLOWS</p>
            <h2>动作预设</h2>
          </div>
          <button class="icon-button" type="button" title="新建动作预设" @click="openNameDialog('add')">
            <Plus :size="17" />
          </button>
        </header>

        <div class="preset-list" role="listbox" aria-label="动作预设">
          <button
            v-for="preset in draft"
            :key="preset.name"
            class="preset-item"
            :class="{ active: preset.name === selectedPresetName }"
            type="button"
            role="option"
            :aria-selected="preset.name === selectedPresetName"
            @click="selectPreset(preset.name)"
          >
            <Workflow :size="16" />
            <span>{{ preset.name }}</span>
            <small>{{ preset.steps.length }}</small>
          </button>
          <button v-if="!draft.length" class="preset-empty-button" type="button" @click="openNameDialog('add')">
            <Plus :size="15" />新建第一个预设
          </button>
        </div>

        <div class="preset-rail-actions">
          <button class="icon-button small" type="button" title="重命名预设" :disabled="!selectedPreset" @click="openNameDialog('rename')">
            <Pencil :size="15" />
          </button>
          <button class="icon-button small" type="button" title="复制预设" :disabled="!selectedPreset" @click="openNameDialog('duplicate')">
            <Copy :size="15" />
          </button>
          <button class="icon-button small danger-icon" type="button" title="删除预设" :disabled="!selectedPreset" @click="confirmDeletePreset = true">
            <Trash2 :size="15" />
          </button>
        </div>
      </aside>

      <section class="workflow-editor">
        <header class="workflow-toolbar">
          <div>
            <h2>{{ selectedPreset?.name || '动作预设' }}</h2>
            <p>{{ steps.length }} 个动作 · {{ enabledCount }} 个启用</p>
          </div>
          <div class="workflow-actions">
            <Transition name="status-swap" mode="out-in">
              <span v-if="notice" key="notice" class="save-notice"><Check :size="14" />{{ notice }}</span>
              <span v-else-if="dirty" key="dirty" class="dirty-indicator">有未保存更改</span>
            </Transition>
            <button class="button secondary" type="button" :disabled="!dirty || runtime.presetSaving" @click="loadFromRuntime">
              <RotateCcw :size="15" />撤销更改
            </button>
            <button class="button primary" type="button" :disabled="!canSave" @click="save">
              <Save :size="15" :class="{ spin: runtime.presetSaving }" />
              {{ runtime.presetSaving ? '保存中' : '保存工作流' }}
            </button>
            <button class="button secondary" type="button" :disabled="!selectedPreset" @click="openStep(null)">
              <Plus :size="16" />添加动作
            </button>
          </div>
        </header>

        <Transition name="banner-slide">
          <div v-if="localError" class="playlist-error">
            <AlertTriangle :size="15" />
            <span>{{ localError }}</span>
            <button type="button" title="关闭" @click="localError = ''"><X :size="14" /></button>
          </div>
        </Transition>

        <div class="workflow-table-wrap">
          <table v-if="selectedPreset" class="workflow-table">
            <thead>
              <tr>
                <th aria-label="排序" />
                <th>动作</th>
                <th>类型</th>
                <th>点位或参数</th>
                <th>动作后等待</th>
                <th>状态</th>
                <th aria-label="操作" />
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(step, index) in steps"
                :key="`${step.name}-${index}`"
                :data-step-index="index"
                :data-kind="actionType(step.kind).category"
                :class="{
                  disabled: !step.enabled,
                  dragging: draggedIndex === index,
                  'drop-target': dropIndex === index && draggedIndex !== index,
                }"
              >
                <td class="drag-cell">
                  <button
                    class="drag-handle"
                    type="button"
                    :aria-label="'拖动排序：' + step.name"
                    title="拖动排序；方向键可微调"
                    @pointerdown="beginPointerDrag(index, $event)"
                    @keydown.up.prevent="moveStepByKeyboard(index, -1)"
                    @keydown.down.prevent="moveStepByKeyboard(index, 1)"
                  >
                    <GripVertical :size="16" />
                  </button>
                </td>
                <td>
                  <button class="workflow-step-title" type="button" @click="openStep(index)">
                    <span class="step-color-mark" />
                    <strong>{{ step.name }}</strong>
                  </button>
                </td>
                <td><span class="action-kind-badge">{{ actionType(step.kind).label }}</span></td>
                <td class="workflow-parameter">{{ parameterSummary(step) }}</td>
                <td><code>{{ step.wait_after || '—' }}</code></td>
                <td>
                  <label class="row-toggle" :title="step.enabled ? '已启用' : '已停用'">
                    <input type="checkbox" :checked="step.enabled" @change="setStepEnabled(index, $event)" />
                    <span />
                  </label>
                </td>
                <td>
                  <div class="row-actions">
                    <button class="icon-button small step-test-button" type="button" title="实际测试当前动作" :disabled="!step.enabled || runtime.isRunning" @click="requestStepTest(index)"><FlaskConical :size="14" /></button>
                    <button class="icon-button small" type="button" title="编辑动作" @click="openStep(index)"><Pencil :size="14" /></button>
                    <button class="icon-button small" type="button" title="复制动作" @click="duplicateStep(index)"><Copy :size="14" /></button>
                    <button class="icon-button small danger-icon" type="button" title="删除动作" @click="deleteStep(index)"><Trash2 :size="14" /></button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <div v-if="selectedPreset && !steps.length" class="playlist-empty">
            <MousePointer2 :size="28" />
            <strong>这个预设还没有动作</strong>
            <button class="button primary" type="button" @click="openStep(null)"><Plus :size="15" />添加第一个动作</button>
          </div>

          <div v-if="!selectedPreset" class="playlist-empty">
            <Workflow :size="28" />
            <strong>还没有动作预设</strong>
            <button class="button primary" type="button" @click="openNameDialog('add')"><Plus :size="15" />新建动作预设</button>
          </div>
        </div>
      </section>
    </template>

    <div v-else class="playlist-loading">
      <Workflow :size="28" />
      <strong>连接本地服务后管理工作流</strong>
    </div>

    <Teleport to="body">
      <Transition name="drag-ghost">
        <div v-if="draggedIndex !== null" class="playlist-drag-ghost workflow-drag-ghost" :style="dragGhostStyle">
          <GripVertical :size="15" />
          <span>{{ draggedStepName }}</span>
        </div>
      </Transition>
    </Teleport>

    <Transition name="dialog-motion">
      <div v-if="nameDialogOpen" class="dialog-backdrop" @mousedown.self="nameDialogOpen = false">
        <form class="connection-dialog compact-dialog" @submit.prevent="submitPresetName">
          <header class="dialog-header">
            <div class="dialog-title-wrap">
              <span class="dialog-icon"><Workflow :size="18" /></span>
              <div>
                <h2>{{ nameDialogMode === 'add' ? '新建动作预设' : nameDialogMode === 'rename' ? '重命名动作预设' : '复制动作预设' }}</h2>
              </div>
            </div>
            <button class="icon-button small" type="button" title="关闭" @click="nameDialogOpen = false"><X :size="15" /></button>
          </header>
          <div class="playlist-form single-field-form">
            <label><span>名称</span><input v-model="nameInput" autofocus maxlength="50" /></label>
          </div>
          <footer class="dialog-actions playlist-dialog-actions">
            <button class="button secondary" type="button" @click="nameDialogOpen = false">取消</button>
            <button class="button primary" type="submit">确认</button>
          </footer>
        </form>
      </div>
    </Transition>

    <Transition name="dialog-motion">
      <div v-if="stepDialogOpen" class="dialog-backdrop" @mousedown.self="stepDialogOpen = false">
        <form class="connection-dialog workflow-step-dialog" @submit.prevent="submitStep">
          <header class="dialog-header">
            <div class="dialog-title-wrap">
              <span class="dialog-icon"><MousePointer2 :size="18" /></span>
              <div><h2>{{ editingStepIndex === null ? '添加动作' : '编辑动作' }}</h2></div>
            </div>
            <button class="icon-button small" type="button" title="关闭" @click="stepDialogOpen = false"><X :size="15" /></button>
          </header>
          <div class="playlist-form workflow-step-form">
            <label><span>动作名称</span><input v-model="stepForm.name" autofocus maxlength="80" /></label>
            <div class="form-field">
              <span>动作类型</span>
              <AppSelect :model-value="stepForm.kind" :options="typeOptions" label="动作类型" @update:model-value="setStepKind" />
            </div>
            <div v-if="currentType.needsTarget" class="form-field">
              <span>点位名称</span>
              <AppSelect v-model="stepForm.target" :options="pointTargetOptions" label="点位名称" placeholder="选择已配置点位" searchable search-placeholder="搜索点位名称或坐标" />
            </div>
            <div v-if="stepForm.kind === 'image_click'" class="form-field">
              <span>图像目标</span>
              <AppSelect v-model="stepForm.value" :options="imageTargetOptions" label="图像目标" placeholder="选择已配置图像" searchable search-placeholder="搜索图像目标" />
            </div>
            <label v-else-if="currentType.needsValue">
              <span>{{ valueLabel }}</span>
              <input v-model="stepForm.value" :placeholder="currentType.placeholder" />
            </label>
            <label v-if="stepForm.kind !== 'wait'">
              <span>动作后等待（秒）</span>
              <input v-model="stepForm.wait_after" inputmode="decimal" placeholder="例如 0.5 或 00:02" />
            </label>
            <div class="queue-option workflow-enabled-option">
              <div><strong>启用动作</strong></div>
              <label class="row-toggle" :title="stepForm.enabled ? '已启用' : '已停用'">
                <input v-model="stepForm.enabled" type="checkbox" />
                <span />
              </label>
            </div>
          </div>
          <footer class="dialog-actions playlist-dialog-actions">
            <button class="button secondary" type="button" @click="stepDialogOpen = false">取消</button>
            <button class="button primary" type="submit">{{ editingStepIndex === null ? '添加' : '保存修改' }}</button>
          </footer>
        </form>
      </div>
    </Transition>

    <Transition name="dialog-motion">
      <div v-if="testStepIndex !== null" class="dialog-backdrop" @mousedown.self="testStepIndex = null">
        <section class="connection-dialog compact-dialog" role="alertdialog" aria-modal="true">
          <header class="dialog-header">
            <div class="dialog-title-wrap">
              <span class="dialog-icon warning"><ShieldAlert :size="18" /></span>
              <div><h2>实际测试当前动作</h2><p>该动作将立即发送到目标游戏窗口</p></div>
            </div>
          </header>
          <div class="confirmation-body">
            <p><strong>{{ testStepIndex !== null ? steps[testStepIndex]?.name : '' }}</strong></p>
            <p>确认目标窗口画面已准备好。执行期间可按 <kbd>F9</kbd> 急停。</p>
            <label class="settings-check step-test-preference">
              <input v-model="suppressStepTestConfirmation" type="checkbox" />
              <span><strong>不再提示</strong><small>可在“设置 → 目标程序”中重新开启</small></span>
            </label>
          </div>
          <footer class="dialog-actions confirmation-actions">
            <button class="button secondary" type="button" @click="testStepIndex = null">取消</button>
            <button class="button danger" type="button" @click="confirmStepTest"><Play :size="15" fill="currentColor" />开始实际测试</button>
          </footer>
        </section>
      </div>
    </Transition>
    <Transition name="dialog-motion">
      <div v-if="confirmDeletePreset" class="dialog-backdrop" @mousedown.self="confirmDeletePreset = false">
        <section class="connection-dialog compact-dialog" role="alertdialog" aria-modal="true">
          <header class="dialog-header">
            <div class="dialog-title-wrap">
              <span class="dialog-icon warning"><AlertTriangle :size="18" /></span>
              <div><h2>删除动作预设</h2></div>
            </div>
          </header>
          <div class="confirmation-body">
            <p>删除“{{ selectedPreset?.name }}”？引用这个预设的歌曲会恢复为继承模式。</p>
          </div>
          <footer class="dialog-actions confirmation-actions">
            <button class="button secondary" type="button" @click="confirmDeletePreset = false">取消</button>
            <button class="button danger" type="button" @click="deletePreset">删除</button>
          </footer>
        </section>
      </div>
    </Transition>
  </main>
</template>
