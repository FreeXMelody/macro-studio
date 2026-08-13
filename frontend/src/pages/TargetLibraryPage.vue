<script setup lang="ts">
import { computed, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { isTauri } from '@tauri-apps/api/core'
import { getCurrentWindow } from '@tauri-apps/api/window'
import {
  AlertTriangle,
  Check,
  Copy,
  Crosshair,
  Eye,
  FlaskConical,
  FolderPlus,
  Image as ImageIcon,
  Images,
  Keyboard,
  LoaderCircle,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  ScanLine,
  Trash2,
  Upload,
  X,
} from '@lucide/vue'

import AppSelect from '../components/AppSelect.vue'
import MaskEditor from '../components/MaskEditor.vue'
import { useRuntimeStore } from '../stores/runtime'
import type { ImageMatchMode, ImageTargetDto, PointDto, TargetLibraryDto, VisionTestResponse } from '../types/api'

type ViewMode = 'points' | 'images'
type NameDialogMode = 'add-group' | 'rename-group'
type DeleteTarget = { kind: 'group' } | { kind: 'point'; index: number } | { kind: 'image'; index: number }

interface ImageForm extends ImageTargetDto {
  regionEnabled: boolean
  regionX: number
  regionY: number
  regionWidth: number
  regionHeight: number
}

const runtime = useRuntimeStore()
const draft = ref<TargetLibraryDto | null>(null)
const viewMode = ref<ViewMode>('points')
const selectedGroupName = ref('')
const selectedImageIndex = ref(0)
const dirty = ref(false)
const localError = ref('')
const notice = ref('')
const pointRenames = ref<Record<string, string>>({})
const imageRenames = ref<Record<string, string>>({})
const nameDialogMode = ref<NameDialogMode>('add-group')
const nameDialogOpen = ref(false)
const nameInput = ref('')
const pointDialogOpen = ref(false)
const editingPointIndex = ref<number | null>(null)
const pointForm = ref<PointDto>({ name: '', x: 0, y: 0 })
const imageDialogOpen = ref(false)
const editingImageIndex = ref<number | null>(null)
const imageForm = ref<ImageForm>(emptyImageForm())
const pendingTemplateData = ref('')
const pendingTemplateFilename = ref('')
const pendingPreview = ref('')
const pendingMaskData = ref('')
const maskPreviewUrl = ref('')
const maskEditorOpen = ref(false)
const previewUrl = ref('')
const previewLoading = ref(false)
const deleteTarget = ref<DeleteTarget | null>(null)
const clickPreset = ref('center')
const fileInput = ref<HTMLInputElement | null>(null)
const capturePointIndex = ref<number | null>(null)
const previewPointIndex = ref<number | null>(null)
const regionCapturing = ref(false)
const visionTesting = ref(false)
const visionResult = ref<VisionTestResponse | null>(null)
const visionTestScope = ref('')
let captureTimer: number | undefined

const selectedGroup = computed(() => {
  if (!draft.value) return null
  return draft.value.point_groups.find((group) => group.name === selectedGroupName.value)
    ?? draft.value.point_groups[0]
    ?? null
})
const points = computed(() => selectedGroup.value?.points ?? [])
const selectedImage = computed(() => draft.value?.image_targets[selectedImageIndex.value] ?? null)
const canSave = computed(() => runtime.isConnected && dirty.value && !runtime.targetSaving)
const matchModeOptions: Array<{ value: ImageMatchMode; label: string }> = [
  { value: 'smart', label: '智能匹配（推荐）' },
  { value: 'grayscale', label: '灰度匹配' },
  { value: 'edge', label: '边缘匹配' },
  { value: 'masked', label: '遮罩灰度匹配' },
  { value: 'masked_edge', label: '遮罩边缘匹配' },
]
const matchModeLabels: Record<ImageMatchMode, string> = {
  smart: '智能',
  grayscale: '灰度',
  edge: '边缘',
  masked: '遮罩灰度',
  masked_edge: '遮罩边缘',
}
const maskEditorImageSrc = computed(() => pendingPreview.value || (editingImageIndex.value !== null ? previewUrl.value : ''))
const maskEditorMaskSrc = computed(() => pendingMaskData.value || maskPreviewUrl.value)
const usesEdges = computed(() => ['smart', 'edge', 'masked_edge'].includes(imageForm.value.match_mode))
const selectedUsesEdges = computed(() =>
  Boolean(selectedImage.value && ['smart', 'edge', 'masked_edge'].includes(selectedImage.value.match_mode)),
)
const usesMask = computed(() => ['smart', 'masked', 'masked_edge'].includes(imageForm.value.match_mode))

const clickPresetOptions = [
  { value: 'center', label: '居中' },
  { value: 'up', label: '中心上方 24 px' },
  { value: 'down', label: '中心下方 24 px' },
  { value: 'left', label: '中心左侧 24 px' },
  { value: 'right', label: '中心右侧 24 px' },
  { value: 'custom', label: '自定义偏移' },
]

watch(
  () => runtime.targets,
  (document) => {
    if (!document || dirty.value) return
    loadDraft(document)
  },
  { immediate: true },
)

watch(
  () => selectedImage.value?.name,
  () => void refreshPreview(),
)

function cloneDocument(document: TargetLibraryDto): TargetLibraryDto {
  return JSON.parse(JSON.stringify(document)) as TargetLibraryDto
}

function loadDraft(document: TargetLibraryDto) {
  draft.value = cloneDocument(document)
  selectedGroupName.value = document.point_groups.some((group) => group.name === document.active_point_group)
    ? document.active_point_group
    : document.point_groups[0]?.name || ''
  selectedImageIndex.value = Math.min(selectedImageIndex.value, Math.max(0, document.image_targets.length - 1))
  pointRenames.value = {}
  imageRenames.value = {}
  dirty.value = false
  localError.value = ''
  void refreshPreview()
}

function touch() {
  dirty.value = true
  notice.value = ''
  localError.value = ''
  if (draft.value) draft.value.active_point_group = selectedGroupName.value
}

function selectGroup(name: string) {
  void stopPointCapture()
  selectedGroupName.value = name
  if (draft.value) draft.value.active_point_group = name
}

function openGroupDialog(mode: NameDialogMode) {
  nameDialogMode.value = mode
  nameInput.value = mode === 'rename-group' ? selectedGroup.value?.name || '' : uniqueName('点位组', draft.value?.point_groups.map((group) => group.name) ?? [])
  nameDialogOpen.value = true
}

function submitGroup() {
  if (!draft.value || !selectedGroup.value) return
  const name = nameInput.value.trim()
  if (!name) return setError('点位组名称不能为空')
  const duplicate = draft.value.point_groups.some((group) => group.name === name && (nameDialogMode.value === 'add-group' || group !== selectedGroup.value))
  if (duplicate) return setError('已经有同名点位组')
  if (nameDialogMode.value === 'add-group') {
    draft.value.point_groups.push({ name, points: [] })
  } else {
    selectedGroup.value.name = name
  }
  selectedGroupName.value = name
  nameDialogOpen.value = false
  touch()
}

async function togglePointCapture(index: number) {
  if (!selectedGroup.value) return
  if (capturePointIndex.value === index) {
    await stopPointCapture()
    return
  }
  await stopPointCapture()
  capturePointIndex.value = index
  localError.value = ''
  try {
    await runtime.armPointCapture(selectedGroup.value.name, selectedGroup.value.points[index].name)
    scheduleCapturePoll()
  } catch (error) {
    capturePointIndex.value = null
    setError(error instanceof Error ? error.message : '无法启用 F8 采集')
  }
}

function scheduleCapturePoll() {
  if (captureTimer !== undefined) window.clearTimeout(captureTimer)
  if (capturePointIndex.value === null) return
  captureTimer = window.setTimeout(() => void pollPointCapture(), 180)
}

async function pollPointCapture() {
  const index = capturePointIndex.value
  const group = selectedGroup.value
  if (index === null || !group || !group.points[index]) return
  try {
    const state = await runtime.pointCaptureState()
    if (state.status === 'captured' && state.x !== null && state.y !== null) {
      const point = group.points[index]
      point.x = state.x
      point.y = state.y
      touch()
      notice.value = 'F8 已采集 ' + point.name + '：' + state.x + ', ' + state.y
      await runtime.armPointCapture(group.name, point.name)
    }
    scheduleCapturePoll()
  } catch (error) {
    capturePointIndex.value = null
    setError(error instanceof Error ? error.message : '读取 F8 采集状态失败')
  }
}

async function stopPointCapture() {
  if (captureTimer !== undefined) {
    window.clearTimeout(captureTimer)
    captureTimer = undefined
  }
  const wasActive = capturePointIndex.value !== null
  capturePointIndex.value = null
  if (wasActive && runtime.isConnected) {
    try {
      await runtime.cancelPointCapture()
    } catch {
      // The sidecar may already be reconnecting.
    }
  }
}

function openPoint(index: number | null) {
  editingPointIndex.value = index
  pointForm.value = index === null ? { name: '', x: 0, y: 0 } : { ...points.value[index] }
  pointDialogOpen.value = true
}

function submitPoint() {
  if (!selectedGroup.value) return
  const name = pointForm.value.name.trim()
  if (!name) return setError('点位名称不能为空')
  const duplicate = selectedGroup.value.points.some((point, index) => point.name === name && index !== editingPointIndex.value)
  if (duplicate) return setError('当前组已有同名点位')
  const next = { name, x: Math.round(Number(pointForm.value.x) || 0), y: Math.round(Number(pointForm.value.y) || 0) }
  if (editingPointIndex.value === null) {
    selectedGroup.value.points.push(next)
  } else {
    const oldName = selectedGroup.value.points[editingPointIndex.value].name
    selectedGroup.value.points[editingPointIndex.value] = next
    recordRename(pointRenames.value, oldName, name)
  }
  pointDialogOpen.value = false
  touch()
}

async function previewPoint(index: number) {
  const point = points.value[index]
  if (!point || previewPointIndex.value !== null) return
  previewPointIndex.value = index
  localError.value = ''
  try {
    const preview = await runtime.previewPoint(point.name, point.x, point.y)
    notice.value = `正在预览 ${preview.name}：${preview.x}, ${preview.y}`
    window.setTimeout(() => {
      if (notice.value.startsWith('正在预览 ' + preview.name)) notice.value = ''
    }, preview.duration * 1000)
  } catch (error) {
    setError(error instanceof Error ? error.message : '无法预览点位')
  } finally {
    window.setTimeout(() => {
      if (previewPointIndex.value === index) previewPointIndex.value = null
    }, 550)
  }
}

function openImage(index: number | null) {
  clearPendingPreview()
  editingImageIndex.value = index
  const target = index === null ? emptyImageTarget() : { ...draft!.value!.image_targets[index] }
  imageForm.value = toImageForm(target)
  clickPreset.value = inferClickPreset(target.offset_x, target.offset_y)
  pendingTemplateData.value = ''
  pendingTemplateFilename.value = ''
  pendingPreview.value = ''
  pendingMaskData.value = ''
  revokeMaskPreview()
  if (index !== null && target.mask_path) void loadMaskPreview(target)
  imageDialogOpen.value = true
  visionResult.value = null
  localError.value = ''
}

async function submitImage() {
  if (!draft.value) return
  const name = imageForm.value.name.trim()
  if (!name) return setError('图像目标名称不能为空')
  const duplicate = draft.value.image_targets.some((target, index) => target.name === name && index !== editingImageIndex.value)
  if (duplicate) return setError('已经有同名图像目标')
  const settingsError = validateVisionSettings()
  if (settingsError) return setError(settingsError)

  let templatePath = ''
  try {
    templatePath = await ensureTemplateImported(name)
  } catch (error) {
    return setError(error instanceof Error ? error.message : '模板导入失败')
  }
  if (!templatePath) return setError('请选择或粘贴一张模板图片')

  try {
    await ensureMaskImported(name)
  } catch (error) {
    return setError(error instanceof Error ? error.message : '遮罩导入失败')
  }
  const target = imageTargetFromForm(name, templatePath)
  if (target.region && (imageForm.value.regionWidth <= 0 || imageForm.value.regionHeight <= 0)) {
    return setError('识别区域的宽度和高度必须大于 0')
  }

  if (editingImageIndex.value === null) {
    draft.value.image_targets.push(target)
    selectedImageIndex.value = draft.value.image_targets.length - 1
  } else {
    const oldName = draft.value.image_targets[editingImageIndex.value].name
    draft.value.image_targets[editingImageIndex.value] = target
    selectedImageIndex.value = editingImageIndex.value
    recordRename(imageRenames.value, oldName, name)
  }
  imageDialogOpen.value = false
  touch()
  notice.value = '图像目标已更新，请再点击顶部的保存目标库'
  if (pendingPreview.value) {
    revokePreview()
    previewUrl.value = pendingPreview.value
    pendingPreview.value = ''
  } else {
    await refreshPreview()
  }
}

async function ensureTemplateImported(name: string) {
  let templatePath = imageForm.value.template_path.trim()
  if (pendingTemplateData.value) {
    const imported = await runtime.importTemplate(name, pendingTemplateFilename.value, pendingTemplateData.value)
    templatePath = imported.template_path
    imageForm.value.template_path = templatePath
    pendingTemplateData.value = ''
  }
  return templatePath
}

async function ensureMaskImported(name: string) {
  if (pendingMaskData.value) {
    const imported = await runtime.importMask(name, name + '_mask.png', pendingMaskData.value)
    imageForm.value.mask_path = imported.template_path
    pendingMaskData.value = ''
  }
  if (['masked', 'masked_edge'].includes(imageForm.value.match_mode) && !imageForm.value.mask_path) {
    throw new Error('当前匹配方式需要先编辑有效区域')
  }
  return imageForm.value.mask_path
}

async function loadMaskPreview(target: ImageTargetDto) {
  revokeMaskPreview()
  if (!target.mask_path || !runtime.isConnected) return
  const persistedName = Object.keys(imageRenames.value).find((name) => imageRenames.value[name] === target.name) || target.name
  try {
    maskPreviewUrl.value = await runtime.loadMaskPreview(persistedName)
  } catch {
    maskPreviewUrl.value = ''
  }
}

function openMaskEditor() {
  if (!maskEditorImageSrc.value) return setError('请先选择或粘贴模板图片')
  maskEditorOpen.value = true
}

function applyMask(dataUrl: string) {
  pendingMaskData.value = dataUrl
  revokeMaskPreview()
  maskPreviewUrl.value = dataUrl
  maskEditorOpen.value = false
  visionResult.value = null
}

function validateVisionSettings() {
  if (usesEdges.value && Number(imageForm.value.edge_low) >= Number(imageForm.value.edge_high)) {
    return '边缘高阈值必须大于低阈值'
  }
  return ''
}

function imageTargetFromForm(name: string, templatePath: string): ImageTargetDto {
  return {
    name,
    template_path: templatePath,
    match_mode: imageForm.value.match_mode,
    mask_path: imageForm.value.mask_path,
    edge_low: Math.max(0, Math.min(255, Math.round(Number(imageForm.value.edge_low) || 0))),
    edge_high: Math.max(0, Math.min(255, Math.round(Number(imageForm.value.edge_high) || 0))),
    region: imageForm.value.regionEnabled
      ? [imageForm.value.regionX, imageForm.value.regionY, imageForm.value.regionWidth, imageForm.value.regionHeight]
          .map((value) => Math.round(Number(value) || 0))
          .join(',')
      : '',
    threshold: Math.max(0, Math.min(1, Number(imageForm.value.threshold) || 0)),
    offset_x: Math.round(Number(imageForm.value.offset_x) || 0),
    offset_y: Math.round(Number(imageForm.value.offset_y) || 0),
    retry_seconds: Math.max(0, Number(imageForm.value.retry_seconds) || 0),
    retry_attempts: Math.max(1, Math.round(Number(imageForm.value.retry_attempts) || 1)),
    retry_interval: Math.max(0, Number(imageForm.value.retry_interval) || 0),
  }
}

async function captureRegion() {
  if (regionCapturing.value) return
  regionCapturing.value = true
  localError.value = ''
  visionResult.value = null
  const appWindow = isTauri() ? getCurrentWindow() : null
  try {
    if (appWindow) {
      await appWindow.hide()
      await new Promise((resolve) => window.setTimeout(resolve, 160))
    }
    const result = await runtime.selectRegion()
    if (!result.cancelled) {
      imageForm.value.regionEnabled = true
      imageForm.value.regionX = result.x
      imageForm.value.regionY = result.y
      imageForm.value.regionWidth = result.width
      imageForm.value.regionHeight = result.height
    }
  } catch (error) {
    setError(error instanceof Error ? error.message : '拖拽选区失败')
  } finally {
    if (appWindow) {
      await appWindow.show()
      await appWindow.setFocus()
    }
    regionCapturing.value = false
  }
}

async function testImage(target: ImageTargetDto, scope: string) {
  if (visionTesting.value) return
  visionTesting.value = true
  localError.value = ''
  visionResult.value = null
  visionTestScope.value = scope
  try {
    visionResult.value = await runtime.testImageTarget(target)
  } catch (error) {
    setError(error instanceof Error ? error.message : '测试识别失败')
  } finally {
    visionTesting.value = false
  }
}

async function testImageForm() {
  const name = imageForm.value.name.trim()
  if (!name) return setError('请先填写图像目标名称')
  const settingsError = validateVisionSettings()
  if (settingsError) return setError(settingsError)
  try {
    const templatePath = await ensureTemplateImported(name)
    if (!templatePath) return setError('请选择或粘贴一张模板图片')
    await ensureMaskImported(name)
    await testImage(imageTargetFromForm(name, templatePath), '编辑中参数，保存目标库后才会用于运行')
  } catch (error) {
    setError(error instanceof Error ? error.message : '模板导入失败')
  }
}

async function testSelectedImage() {
  if (selectedImage.value) {
    await testImage(
      { ...selectedImage.value },
      dirty.value ? '目标库草稿，保存后才会用于运行' : '已保存参数',
    )
  }
}

function handleRegionShortcut(event: KeyboardEvent) {
  if (!imageDialogOpen.value || !event.ctrlKey || event.key.toLowerCase() !== 'r') return
  event.preventDefault()
  void captureRegion()
}

function duplicateImage(index: number) {
  if (!draft.value) return
  const source = draft.value.image_targets[index]
  draft.value.image_targets.splice(index + 1, 0, {
    ...source,
    name: uniqueName(source.name + ' 副本', draft.value.image_targets.map((target) => target.name)),
  })
  selectedImageIndex.value = index + 1
  touch()
}

function confirmDelete() {
  if (!draft.value || !deleteTarget.value) return
  if (deleteTarget.value.kind === 'group') {
    if (draft.value.point_groups.length <= 1) return setError('至少需要保留一个点位组')
    const index = draft.value.point_groups.findIndex((group) => group.name === selectedGroupName.value)
    draft.value.point_groups.splice(index, 1)
    selectedGroupName.value = draft.value.point_groups[Math.max(0, index - 1)].name
  } else if (deleteTarget.value.kind === 'point') {
    selectedGroup.value?.points.splice(deleteTarget.value.index, 1)
  } else {
    draft.value.image_targets.splice(deleteTarget.value.index, 1)
    selectedImageIndex.value = Math.min(selectedImageIndex.value, Math.max(0, draft.value.image_targets.length - 1))
  }
  deleteTarget.value = null
  touch()
  void refreshPreview()
}

function applyClickPreset(value: string) {
  clickPreset.value = value
  const offsets: Record<string, [number, number]> = {
    center: [0, 0],
    up: [0, -24],
    down: [0, 24],
    left: [-24, 0],
    right: [24, 0],
  }
  if (offsets[value]) {
    imageForm.value.offset_x = offsets[value][0]
    imageForm.value.offset_y = offsets[value][1]
  }
}

function onOffsetInput() {
  clickPreset.value = inferClickPreset(imageForm.value.offset_x, imageForm.value.offset_y)
}

function inferClickPreset(x: number, y: number) {
  const known: Record<string, string> = {
    '0,0': 'center',
    '0,-24': 'up',
    '0,24': 'down',
    '-24,0': 'left',
    '24,0': 'right',
  }
  return known[String(x) + ',' + String(y)] || 'custom'
}

function openFilePicker() {
  fileInput.value?.click()
}

async function onFilePicked(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) await loadTemplateFile(file)
  ;(event.target as HTMLInputElement).value = ''
}

async function onTemplatePaste(event: ClipboardEvent) {
  const file = Array.from(event.clipboardData?.files ?? []).find((item) => item.type.startsWith('image/'))
  if (!file) return
  event.preventDefault()
  await loadTemplateFile(file, '剪贴板模板.png')
}

async function loadTemplateFile(file: File, preferredName = file.name) {
  if (!file.type.startsWith('image/')) return setError('请选择图片文件')
  const dataUrl = await readFile(file)
  imageForm.value.mask_path = ''
  pendingMaskData.value = ''
  revokeMaskPreview()
  pendingTemplateData.value = dataUrl
  pendingTemplateFilename.value = preferredName
  visionResult.value = null
  if (pendingPreview.value.startsWith('blob:')) URL.revokeObjectURL(pendingPreview.value)
  pendingPreview.value = URL.createObjectURL(file)
}

async function refreshPreview() {
  revokePreview()
  const target = selectedImage.value
  if (!target || !runtime.isConnected) return
  const persistedName = Object.keys(imageRenames.value).find((name) => imageRenames.value[name] === target.name) || target.name
  previewLoading.value = true
  try {
    previewUrl.value = await runtime.loadTemplatePreview(persistedName)
  } catch {
    previewUrl.value = ''
  } finally {
    previewLoading.value = false
  }
}

function revokePreview() {
  if (previewUrl.value.startsWith('blob:')) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

function clearPendingPreview() {
  if (pendingPreview.value.startsWith('blob:')) URL.revokeObjectURL(pendingPreview.value)
  pendingPreview.value = ''
  pendingTemplateData.value = ''
  pendingTemplateFilename.value = ''
  pendingMaskData.value = ''
  maskEditorOpen.value = false
  revokeMaskPreview()
}

function revokeMaskPreview() {
  if (maskPreviewUrl.value.startsWith('blob:')) URL.revokeObjectURL(maskPreviewUrl.value)
  maskPreviewUrl.value = ''
}

function closeImageDialog() {
  clearPendingPreview()
  imageDialogOpen.value = false
}

function resetDraft() {
  if (runtime.targets) loadDraft(runtime.targets)
}

async function save() {
  if (!draft.value || !canSave.value) return
  try {
    const saved = await runtime.saveTargets(cloneDocument(draft.value), pointRenames.value, imageRenames.value)
    loadDraft(saved)
    notice.value = '目标库已保存'
    window.setTimeout(() => {
      if (notice.value === '目标库已保存') notice.value = ''
    }, 2200)
  } catch (error) {
    setError(error instanceof Error ? error.message : '保存目标库失败')
  }
}

function recordRename(map: Record<string, string>, oldName: string, newName: string) {
  if (oldName === newName) return
  const original = Object.keys(map).find((key) => map[key] === oldName) || oldName
  delete map[oldName]
  if (original === newName) delete map[original]
  else map[original] = newName
}

function uniqueName(base: string, names: string[]) {
  if (!names.includes(base)) return base
  let index = 2
  while (names.includes(base + ' ' + index)) index += 1
  return base + ' ' + index
}

function emptyImageTarget(): ImageTargetDto {
  return {
    name: '',
    template_path: '',
    match_mode: 'smart',
    mask_path: '',
    edge_low: 60,
    edge_high: 160,
    region: '',
    threshold: 0.65,
    offset_x: 0,
    offset_y: 0,
    retry_seconds: 3,
    retry_attempts: 5,
    retry_interval: 0.25,
  }
}

function emptyImageForm(): ImageForm {
  return { ...emptyImageTarget(), regionEnabled: false, regionX: 0, regionY: 0, regionWidth: 0, regionHeight: 0 }
}

function toImageForm(target: ImageTargetDto): ImageForm {
  const parts = target.region.split(',').map((value) => Number(value.trim()) || 0)
  return {
    ...target,
    regionEnabled: parts.length === 4,
    regionX: parts[0] || 0,
    regionY: parts[1] || 0,
    regionWidth: parts[2] || 0,
    regionHeight: parts[3] || 0,
  }
}

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

function setError(message: string) {
  localError.value = message
}

onMounted(() => window.addEventListener('keydown', handleRegionShortcut))
onDeactivated(() => void stopPointCapture())
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleRegionShortcut)
  void stopPointCapture()
  revokePreview()
  if (pendingPreview.value.startsWith('blob:')) URL.revokeObjectURL(pendingPreview.value)
})
</script>

<template>
  <main class="target-page">
    <template v-if="draft">
      <header class="target-toolbar">
        <div>
          <p class="section-kicker">TARGET LIBRARY</p>
          <h2>目标库</h2>
        </div>
        <div class="target-view-switch" :class="viewMode">
          <button type="button" :class="{ active: viewMode === 'points' }" @click="viewMode = 'points'">
            <Crosshair :size="15" />点位
          </button>
          <button type="button" :class="{ active: viewMode === 'images' }" @click="viewMode = 'images'">
            <Images :size="15" />图像目标
          </button>
        </div>
        <div class="target-toolbar-actions">
          <Transition name="status-swap" mode="out-in">
            <span v-if="notice" key="notice" class="save-notice"><Check :size="14" />{{ notice }}</span>
            <span v-else-if="dirty" key="dirty" class="dirty-indicator">有未保存更改</span>
          </Transition>
          <button class="button secondary" type="button" :disabled="!dirty || runtime.targetSaving" @click="resetDraft">
            <RotateCcw :size="15" />撤销
          </button>
          <button class="button primary" type="button" :disabled="!canSave" @click="save">
            <Save :size="15" :class="{ spin: runtime.targetSaving }" />{{ runtime.targetSaving ? '保存中' : '保存目标库' }}
          </button>
        </div>
      </header>

      <Transition name="banner-slide">
        <div v-if="localError" class="playlist-error target-error">
          <AlertTriangle :size="15" /><span>{{ localError }}</span>
          <button type="button" title="关闭" @click="localError = ''"><X :size="14" /></button>
        </div>
      </Transition>

      <Transition name="target-view" mode="out-in">
        <section v-if="viewMode === 'points'" key="points" class="target-workspace point-workspace">
          <aside class="target-rail">
            <header>
              <div><span>点位组</span><small>{{ draft.point_groups.length }}</small></div>
              <button class="icon-button small" type="button" title="新建点位组" @click="openGroupDialog('add-group')"><FolderPlus :size="15" /></button>
            </header>
            <div class="target-rail-list">
              <button
                v-for="group in draft.point_groups"
                :key="group.name"
                class="target-rail-item"
                :class="{ active: group.name === selectedGroupName }"
                type="button"
                @click="selectGroup(group.name)"
              >
                <Crosshair :size="15" /><span>{{ group.name }}</span><small>{{ group.points.length }}</small>
              </button>
            </div>
            <footer>
              <button class="button secondary compact" type="button" @click="openGroupDialog('rename-group')"><Pencil :size="14" />重命名</button>
              <button class="icon-button danger-icon" type="button" title="删除点位组" @click="deleteTarget = { kind: 'group' }"><Trash2 :size="15" /></button>
            </footer>
          </aside>

          <div class="point-editor">
            <header class="target-section-header">
              <div><h3>{{ selectedGroup?.name }}</h3><p>点位使用屏幕坐标；预览位置与实际 click 动作一致</p></div>
              <div class="point-header-actions">
                <Transition name="status-swap">
                  <span v-if="capturePointIndex !== null" class="capture-status"><Keyboard :size="14" />F8 正在采集：{{ points[capturePointIndex]?.name }}</span>
                </Transition>
                <button class="button secondary" type="button" @click="openPoint(null)"><Plus :size="15" />添加点位</button>
              </div>
            </header>
            <div class="target-table-wrap">
              <table class="target-table">
                <thead><tr><th>名称</th><th>X</th><th>Y</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-for="(point, index) in points" :key="point.name" :class="{ 'capture-row': capturePointIndex === index }">
                    <td><button class="target-name-button" type="button" @click="openPoint(index)"><Crosshair :size="14" /><strong>{{ point.name }}</strong></button></td>
                    <td><code>{{ point.x }}</code></td><td><code>{{ point.y }}</code></td>
                    <td><div class="row-actions">
                      <button class="icon-button small capture-button" :class="{ active: capturePointIndex === index }" type="button" :title="capturePointIndex === index ? '停止 F8 采集' : '使用 F8 持续采集此点位'" @click="togglePointCapture(index)"><Keyboard :size="14" /></button>
                      <button class="icon-button small" type="button" title="编辑点位" @click="openPoint(index)"><Pencil :size="14" /></button>
                      <button class="icon-button small point-preview-button" :class="{ active: previewPointIndex === index }" type="button" title="预览点位" :disabled="previewPointIndex !== null" @click="previewPoint(index)"><LoaderCircle v-if="previewPointIndex === index" class="spin" :size="14" /><Eye v-else :size="14" /></button>
                      <button class="icon-button small danger-icon" type="button" title="删除点位" @click="deleteTarget = { kind: 'point', index }"><Trash2 :size="14" /></button>
                    </div></td>
                  </tr>
                </tbody>
              </table>
              <div v-if="!points.length" class="target-empty"><Crosshair :size="24" /><strong>这个组还没有点位</strong></div>
            </div>
          </div>
        </section>

        <section v-else key="images" class="target-workspace image-workspace">
          <aside class="image-target-list">
            <header class="target-section-header compact-header">
              <div><h3>图像目标</h3><p>{{ draft.image_targets.length }} 个模板</p></div>
              <button class="icon-button" type="button" title="新建图像目标" @click="openImage(null)"><Plus :size="16" /></button>
            </header>
            <div class="image-target-items">
              <button
                v-for="(target, index) in draft.image_targets"
                :key="target.name"
                class="image-target-item"
                :class="{ active: index === selectedImageIndex }"
                type="button"
                @click="selectedImageIndex = index"
              >
                <span class="image-target-icon"><ImageIcon :size="16" /></span>
                <span><strong>{{ target.name }}</strong><small>{{ matchModeLabels[target.match_mode] }} · 阈值 {{ target.threshold.toFixed(2) }} · 最多 {{ target.retry_attempts }} 次</small></span>
              </button>
            </div>
          </aside>

          <div v-if="selectedImage" class="image-inspector">
            <div class="preview-stage">
              <img v-if="previewUrl" :src="previewUrl" :alt="selectedImage.name + ' 模板预览'" />
              <div v-else class="preview-placeholder"><ImageIcon :size="32" /><span>{{ previewLoading ? '正在读取预览' : '模板预览不可用' }}</span></div>
            </div>
            <div class="image-target-details">
              <div class="detail-heading"><div><p class="section-kicker">IMAGE TARGET</p><h3>{{ selectedImage.name }}</h3></div>
                <div class="row-actions">
                  <button class="button secondary compact vision-test-button" type="button" :disabled="visionTesting" @click="testSelectedImage">
                    <LoaderCircle v-if="visionTesting" class="spin" :size="14" /><FlaskConical v-else :size="14" />测试识别
                  </button>
                  <button class="button secondary compact" type="button" @click="openImage(selectedImageIndex)"><Pencil :size="14" />编辑</button>
                  <button class="icon-button" type="button" title="复制图像目标" @click="duplicateImage(selectedImageIndex)"><Copy :size="15" /></button>
                  <button class="icon-button danger-icon" type="button" title="删除图像目标" @click="deleteTarget = { kind: 'image', index: selectedImageIndex }"><Trash2 :size="15" /></button>
                </div>
              </div>
              <Transition name="banner-slide">
                <div v-if="visionResult" class="vision-result" :class="{ failed: !visionResult.matched }">
                  <Check v-if="visionResult.matched" :size="15" /><AlertTriangle v-else :size="15" />
                  <span v-if="visionResult.matched">{{ visionResult.source === 'background' ? '后台截图' : '屏幕截图' }}命中，置信度 {{ visionResult.score.toFixed(3) }} · {{ visionTestScope }}</span>
                  <span v-else>{{ visionResult.error }} · {{ visionTestScope }}</span>
                  <code>{{ visionResult.match_mode }} · {{ visionResult.score.toFixed(3) }} · 候选 {{ visionResult.x }}, {{ visionResult.y }} · 范围 {{ visionResult.search_x }},{{ visionResult.search_y }},{{ visionResult.search_width }},{{ visionResult.search_height }}</code>
                </div>
              </Transition>
              <Transition name="banner-slide">
                <div v-if="visionResult?.preview_data_url" class="vision-debug-preview">
                  <img :src="visionResult.preview_data_url" alt="图像识别候选位置" />
                  <div class="vision-preview-legend"><span class="search-region">黄色：实际识别范围</span><span class="candidate-region">绿色：{{ visionResult.matched ? '命中位置' : '最高候选位置' }}</span></div>
                </div>
              </Transition>
              <dl class="target-facts">
                <div><dt>匹配方式</dt><dd>{{ matchModeLabels[selectedImage.match_mode] }}</dd></div>
                <div><dt>识别范围</dt><dd>{{ selectedImage.region || '目标窗口全区域' }}</dd></div>
                <div><dt>识别阈值</dt><dd>{{ selectedImage.threshold.toFixed(2) }}</dd></div>
                <div v-if="selectedUsesEdges" title="Canny 双阈值：低值影响弱轮廓，高值筛选强轮廓"><dt>边缘阈值</dt><dd>{{ selectedImage.edge_low }} / {{ selectedImage.edge_high }}</dd></div>
                <div><dt>点击偏移</dt><dd>{{ selectedImage.offset_x }}, {{ selectedImage.offset_y }}</dd></div>
                <div><dt>最多尝试</dt><dd>{{ selectedImage.retry_attempts }} 次</dd></div>
                <div><dt>重试间隔</dt><dd>{{ selectedImage.retry_interval }} 秒</dd></div>
                <div><dt>最长时限</dt><dd>{{ selectedImage.retry_seconds }} 秒</dd></div>
                <div class="wide"><dt>模板文件</dt><dd>{{ selectedImage.template_path }}</dd></div>
              </dl>
            </div>
          </div>
          <div v-else class="target-empty image-empty"><Images :size="28" /><strong>还没有图像目标</strong><button class="button primary" type="button" @click="openImage(null)"><Plus :size="15" />新建目标</button></div>
        </section>
      </Transition>
    </template>

    <div v-else class="catalog-unavailable"><AlertTriangle :size="28" /><strong>目标库尚未连接</strong><span>本地服务连接后会自动载入配置</span></div>

    <Transition name="dialog-fade">
      <div v-if="nameDialogOpen" class="dialog-backdrop" @mousedown.self="nameDialogOpen = false">
        <section class="connection-dialog compact-dialog">
          <header class="dialog-header"><div class="dialog-title-wrap"><span class="dialog-icon"><FolderPlus :size="17" /></span><div><h2>{{ nameDialogMode === 'add-group' ? '新建点位组' : '重命名点位组' }}</h2><p>整理同一应用或场景使用的坐标</p></div></div><button class="icon-button small" type="button" title="关闭" @click="nameDialogOpen = false"><X :size="15" /></button></header>
          <form class="playlist-form single-field-form" @submit.prevent="submitGroup"><label>名称<input v-model="nameInput" autofocus /></label><div class="dialog-actions playlist-dialog-actions"><button class="button secondary" type="button" @click="nameDialogOpen = false">取消</button><button class="button primary" type="submit">确定</button></div></form>
        </section>
      </div>
    </Transition>

    <Transition name="dialog-fade">
      <div v-if="pointDialogOpen" class="dialog-backdrop" @mousedown.self="pointDialogOpen = false">
        <section class="connection-dialog compact-dialog">
          <header class="dialog-header"><div class="dialog-title-wrap"><span class="dialog-icon"><Crosshair :size="17" /></span><div><h2>{{ editingPointIndex === null ? '添加点位' : '编辑点位' }}</h2><p>屏幕绝对坐标，与实际点击位置一致</p></div></div><button class="icon-button small" type="button" title="关闭" @click="pointDialogOpen = false"><X :size="15" /></button></header>
          <form class="playlist-form point-form" @submit.prevent="submitPoint">
            <label class="wide-field">名称<input v-model="pointForm.name" autofocus /></label>
            <label>X 坐标<input v-model.number="pointForm.x" type="number" /></label>
            <label>Y 坐标<input v-model.number="pointForm.y" type="number" /></label>
            <div class="dialog-actions playlist-dialog-actions"><button class="button secondary" type="button" @click="pointDialogOpen = false">取消</button><button class="button primary" type="submit">保存点位</button></div>
          </form>
        </section>
      </div>
    </Transition>

    <Transition name="dialog-fade">
      <div v-if="imageDialogOpen" class="dialog-backdrop" @mousedown.self="closeImageDialog" @paste="onTemplatePaste">
        <section class="connection-dialog image-target-dialog">
          <header class="dialog-header"><div class="dialog-title-wrap"><span class="dialog-icon"><ImageIcon :size="17" /></span><div><h2>{{ editingImageIndex === null ? '新建图像目标' : '编辑图像目标' }}</h2><p>粘贴截图或导入图片作为识别模板</p></div></div><button class="icon-button small" type="button" title="关闭" @click="closeImageDialog"><X :size="15" /></button></header>
          <form class="image-target-form" @submit.prevent="submitImage">
            <div class="image-form-scroll">
              <label class="form-field">名称<input v-model="imageForm.name" /></label>
              <div class="template-import">
                <div class="template-edit-preview"><img v-if="pendingPreview || (editingImageIndex !== null && previewUrl)" :src="pendingPreview || previewUrl" alt="待保存模板预览" /><ImageIcon v-else :size="28" /></div>
                <div><strong>{{ pendingTemplateFilename || imageForm.template_path || '尚未选择模板' }}</strong><span>可在此弹窗直接按 Ctrl+V 粘贴截图</span><button class="button secondary compact" type="button" @click="openFilePicker"><Upload :size="14" />选择图片</button><input ref="fileInput" class="visually-hidden" type="file" accept="image/*" @change="onFilePicked" /></div>
              </div>
              <div class="form-section vision-mode-section">
                <div class="form-section-title">
                  <div><strong>匹配方式</strong><span>智能模式会在有遮罩时自动使用遮罩边缘</span></div>
                </div>
                <div class="image-settings-grid match-settings-grid">
                  <label class="form-field wide-setting">算法<AppSelect v-model="imageForm.match_mode" :options="matchModeOptions" label="匹配方式" /></label>
                  <template v-if="usesEdges">
                    <label class="form-field" title="越低会保留更多弱轮廓，也更容易带入场景噪声">边缘低阈值 <output>{{ imageForm.edge_low }}</output><input v-model.number="imageForm.edge_low" class="range-input" min="0" max="254" step="1" type="range" /></label>
                    <label class="form-field" title="越高只保留更明显的强轮廓，但可能遗漏较淡的图标边缘">边缘高阈值 <output>{{ imageForm.edge_high }}</output><input v-model.number="imageForm.edge_high" class="range-input" min="1" max="255" step="1" type="range" /></label>
                  </template>
                </div>
                <div v-if="usesMask" class="mask-setting-row">
                  <div>
                    <strong>{{ pendingMaskData || imageForm.mask_path ? '有效区域已设置' : '尚未设置有效区域' }}</strong>
                    <span>{{ pendingMaskData ? '遮罩已修改；完成编辑后还需保存目标库' : imageForm.match_mode === 'smart' && !imageForm.mask_path ? '当前将自动使用纯边缘匹配' : '仅遮罩中的白色像素参与比较' }}</span>
                  </div>
                  <button class="button secondary compact" type="button" @click="openMaskEditor"><Pencil :size="14" />编辑有效区域</button>
                </div>
              </div>
              <div class="form-section">
                <div class="form-section-title region-section-title">
                  <div><strong>识别范围</strong><span>{{ imageForm.regionEnabled ? '只在目标窗口内的指定矩形中查找' : '在整个目标窗口内查找' }}</span></div>
                  <div class="region-tools">
                    <div class="region-mode-switch" role="radiogroup" aria-label="识别范围">
                      <button type="button" :class="{ active: !imageForm.regionEnabled }" @click="imageForm.regionEnabled = false">全窗口</button>
                      <button type="button" :class="{ active: imageForm.regionEnabled }" @click="imageForm.regionEnabled = true">限定区域</button>
                    </div>
                    <button class="button secondary compact" type="button" :disabled="regionCapturing" @click="captureRegion">
                      <LoaderCircle v-if="regionCapturing" class="spin" :size="14" /><ScanLine v-else :size="14" />拖拽选区 <kbd>Ctrl+R</kbd>
                    </button>
                  </div>
                </div>
                <Transition name="panel-collapse">
                  <div v-if="imageForm.regionEnabled" class="region-grid">
                    <label>X<input v-model.number="imageForm.regionX" type="number" /></label><label>Y<input v-model.number="imageForm.regionY" type="number" /></label><label>宽度<input v-model.number="imageForm.regionWidth" min="1" type="number" /></label><label>高度<input v-model.number="imageForm.regionHeight" min="1" type="number" /></label>
                  </div>
                </Transition>
              </div>
              <div class="form-section">
                <div class="form-section-title"><div><strong>识别与点击</strong><span>偏移以匹配框中心为基准</span></div></div>
                <div class="image-settings-grid">
                  <label class="form-field">识别阈值 <output>{{ imageForm.threshold.toFixed(2) }}</output><input v-model.number="imageForm.threshold" class="range-input" min="0" max="1" step="0.01" type="range" /></label>
                  <label class="form-field">最多尝试次数<input v-model.number="imageForm.retry_attempts" min="1" max="100" step="1" type="number" /></label>
                  <label class="form-field">重试间隔（秒）<input v-model.number="imageForm.retry_interval" min="0" max="30" step="0.05" type="number" /></label>
                  <label class="form-field">最长重试时限（秒）<input v-model.number="imageForm.retry_seconds" min="0" max="120" step="0.5" type="number" /></label>
                  <label class="form-field wide-setting">点击位置<AppSelect :model-value="clickPreset" :options="clickPresetOptions" label="点击位置" @update:model-value="applyClickPreset" /></label>
                  <label class="form-field">水平偏移<input v-model.number="imageForm.offset_x" type="number" @input="onOffsetInput" /></label>
                  <label class="form-field">垂直偏移<input v-model.number="imageForm.offset_y" type="number" @input="onOffsetInput" /></label>
                </div>
              </div>
              <Transition name="banner-slide">
                <div v-if="visionResult" class="vision-result dialog-result" :class="{ failed: !visionResult.matched }">
                  <Check v-if="visionResult.matched" :size="15" /><AlertTriangle v-else :size="15" />
                  <span v-if="visionResult.matched">{{ visionResult.source === 'background' ? '后台截图' : '屏幕截图' }}命中，置信度 {{ visionResult.score.toFixed(3) }} · {{ visionTestScope }}</span>
                  <span v-else>{{ visionResult.error }} · {{ visionTestScope }}</span>
                  <code>{{ visionResult.match_mode }} · {{ visionResult.score.toFixed(3) }} · 候选 {{ visionResult.x }}, {{ visionResult.y }} · 范围 {{ visionResult.search_x }},{{ visionResult.search_y }},{{ visionResult.search_width }},{{ visionResult.search_height }}</code>
                </div>
              </Transition>
              <div v-if="visionResult?.preview_data_url" class="vision-debug-preview dialog-debug-preview">
                <img :src="visionResult.preview_data_url" alt="图像识别候选位置" />
                <div class="vision-preview-legend"><span class="search-region">黄色：实际识别范围</span><span class="candidate-region">绿色：{{ visionResult.matched ? '命中位置' : '最高候选位置' }}</span></div>
              </div>
            </div>
            <div class="dialog-actions image-dialog-actions">
              <button class="button secondary test-button vision-test-button" type="button" :disabled="visionTesting" @click="testImageForm">
                <LoaderCircle v-if="visionTesting" class="spin" :size="14" /><FlaskConical v-else :size="14" />测试识别
              </button>
              <button class="button secondary" type="button" @click="closeImageDialog">取消</button>
              <button class="button primary" type="submit">完成编辑</button>
            </div>
          </form>
        </section>
      </div>
    </Transition>

    <MaskEditor
      :open="maskEditorOpen"
      :image-src="maskEditorImageSrc"
      :mask-src="maskEditorMaskSrc"
      :edge-low="imageForm.edge_low"
      :edge-high="imageForm.edge_high"
      :match-mode="imageForm.match_mode"
      @close="maskEditorOpen = false"
      @save="applyMask"
    />

    <Transition name="dialog-fade">
      <div v-if="deleteTarget" class="dialog-backdrop" @mousedown.self="deleteTarget = null">
        <section class="connection-dialog compact-dialog"><header class="dialog-header"><div class="dialog-title-wrap"><span class="dialog-icon warning"><Trash2 :size="17" /></span><div><h2>确认删除</h2><p>该操作会在保存目标库后生效</p></div></div></header><div class="confirmation-body"><p>确定删除当前{{ deleteTarget.kind === 'group' ? '点位组' : deleteTarget.kind === 'point' ? '点位' : '图像目标' }}吗？</p></div><div class="dialog-actions confirmation-actions"><button class="button secondary" type="button" @click="deleteTarget = null">取消</button><button class="button danger" type="button" @click="confirmDelete">删除</button></div></section>
      </div>
    </Transition>
  </main>
</template>
