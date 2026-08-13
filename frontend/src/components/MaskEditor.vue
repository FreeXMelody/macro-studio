<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  Brush,
  Check,
  Eraser,
  MousePointer2,
  Repeat2,
  Redo2,
  RotateCcw,
  Undo2,
  X,
} from '@lucide/vue'

type Tool = 'brush' | 'polygon'
type PaintMode = 'include' | 'exclude'
type PreviewMode = 'edit' | 'mask' | 'edge' | 'final'

const props = defineProps<{
  open: boolean
  imageSrc: string
  maskSrc?: string
  edgeLow: number
  edgeHigh: number
  matchMode: string
}>()

const emit = defineEmits<{
  close: []
  save: [dataUrl: string]
}>()

const canvas = ref<HTMLCanvasElement | null>(null)
const stage = ref<HTMLDivElement | null>(null)
const image = new Image()
const maskCanvas = document.createElement('canvas')
const edgeCanvas = document.createElement('canvas')
const tool = ref<Tool>('brush')
const paintMode = ref<PaintMode>('exclude')
const previewMode = ref<PreviewMode>('edit')
const brushSize = ref(28)
const drawing = ref(false)
const loading = ref(false)
const loadError = ref('')
const imageReady = ref(false)
const history = ref<ImageData[]>([])
const future = ref<ImageData[]>([])
const polygon = ref<Array<{ x: number; y: number }>>([])
const coverage = ref(0)
const canvasDisplayWidth = ref(0)
const canvasDisplayHeight = ref(0)
let stageObserver: ResizeObserver | null = null

const previewOptions: Array<{ value: PreviewMode; label: string }> = [
  { value: 'edit', label: '编辑叠加' },
  { value: 'mask', label: '遮罩黑白' },
  { value: 'edge', label: '边缘结果' },
  { value: 'final', label: '匹配输入' },
]

const canvasReady = computed(() => imageReady.value && image.naturalWidth > 0)
const canUndo = computed(() => history.value.length > 0)
const canRedo = computed(() => future.value.length > 0)
const canvasDisplayStyle = computed(() => canvasDisplayWidth.value && canvasDisplayHeight.value
  ? { width: canvasDisplayWidth.value + 'px', height: canvasDisplayHeight.value + 'px' }
  : undefined)

watch(
  () => [props.open, props.imageSrc, props.maskSrc] as const,
  ([open]) => {
    if (open) void initialize()
  },
)

watch(canvas, (target) => {
  if (target && props.open && canvasReady.value) scheduleRender()
})

watch(stage, (target) => {
  stageObserver?.disconnect()
  stageObserver = null
  if (!target) return
  stageObserver = new ResizeObserver(() => scheduleRender())
  stageObserver.observe(target)
  scheduleRender()
})

watch(
  () => [props.edgeLow, props.edgeHigh, props.matchMode, previewMode.value],
  () => {
    if (!canvasReady.value) return
    buildEdgePreview()
    render()
  },
)

onBeforeUnmount(() => {
  stageObserver?.disconnect()
  image.onload = null
  image.onerror = null
})

async function initialize() {
  if (!props.imageSrc) return
  loading.value = true
  loadError.value = ''
  imageReady.value = false
  history.value = []
  future.value = []
  polygon.value = []
  tool.value = 'brush'
  paintMode.value = 'exclude'
  previewMode.value = 'edit'
  await nextTick()
  try {
    await loadImage(image, props.imageSrc)
    imageReady.value = true
    maskCanvas.width = image.naturalWidth
    maskCanvas.height = image.naturalHeight
    edgeCanvas.width = image.naturalWidth
    edgeCanvas.height = image.naturalHeight
    const context = maskCanvas.getContext('2d', { willReadFrequently: true })!
    context.fillStyle = '#fff'
    context.fillRect(0, 0, maskCanvas.width, maskCanvas.height)
    if (props.maskSrc) {
      const initialMask = new Image()
      await loadImage(initialMask, props.maskSrc)
      context.drawImage(initialMask, 0, 0, maskCanvas.width, maskCanvas.height)
      thresholdMask()
    }
    buildEdgePreview()
    updateCoverage()
    scheduleRender()
  } catch (error) {
    imageReady.value = false
    loadError.value = error instanceof Error ? error.message : '无法读取模板图片'
  } finally {
    loading.value = false
    await nextTick()
    if (!loadError.value) scheduleRender()
  }
}

function scheduleRender() {
  window.requestAnimationFrame(() => {
    updateCanvasDisplaySize()
    render()
  })
}

function updateCanvasDisplaySize() {
  const container = stage.value
  if (!container || !canvasReady.value) return
  const style = window.getComputedStyle(container)
  const horizontalPadding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight)
  const verticalPadding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom)
  const availableWidth = Math.max(1, container.clientWidth - horizontalPadding - 2)
  const availableHeight = Math.max(1, container.clientHeight - verticalPadding - 2)
  const scale = Math.min(availableWidth / image.naturalWidth, availableHeight / image.naturalHeight)
  canvasDisplayWidth.value = Math.max(1, Math.floor(image.naturalWidth * scale))
  canvasDisplayHeight.value = Math.max(1, Math.floor(image.naturalHeight * scale))
}

function loadImage(target: HTMLImageElement, src: string) {
  return new Promise<void>((resolve, reject) => {
    target.onload = () => resolve()
    target.onerror = () => reject(new Error('无法读取图片'))
    target.src = src
  })
}

function render() {
  const target = canvas.value
  if (!target || !canvasReady.value) return
  target.width = image.naturalWidth
  target.height = image.naturalHeight
  const context = target.getContext('2d', { willReadFrequently: true })!
  context.clearRect(0, 0, target.width, target.height)

  const usesEdges = props.matchMode === 'edge' || props.matchMode === 'masked_edge' || props.matchMode === 'smart'
  const usesMask = props.matchMode.includes('masked') || props.matchMode === 'smart'

  if (previewMode.value === 'mask') {
    context.fillStyle = '#050708'
    context.fillRect(0, 0, target.width, target.height)
    context.drawImage(maskCanvas, 0, 0)
  } else if (previewMode.value === 'edge') {
    context.drawImage(edgeCanvas, 0, 0)
  } else {
    context.drawImage(previewMode.value === 'final' && usesEdges ? edgeCanvas : image, 0, 0)
    if (previewMode.value === 'edit' || (previewMode.value === 'final' && usesMask)) {
      const maskContext = maskCanvas.getContext('2d', { willReadFrequently: true })!
      const mask = maskContext.getImageData(0, 0, target.width, target.height).data
      const pixels = context.getImageData(0, 0, target.width, target.height)
      for (let index = 0; index < mask.length; index += 4) {
        if (mask[index] < 16) {
          if (previewMode.value === 'edit') {
            pixels.data[index] = Math.min(255, Math.round(pixels.data[index] * 0.28 + 118))
            pixels.data[index + 1] = Math.round(pixels.data[index + 1] * 0.18)
            pixels.data[index + 2] = Math.round(pixels.data[index + 2] * 0.18)
          } else {
            pixels.data[index] = Math.round(pixels.data[index] * 0.16)
            pixels.data[index + 1] = Math.round(pixels.data[index + 1] * 0.16)
            pixels.data[index + 2] = Math.round(pixels.data[index + 2] * 0.16)
          }
        }
      }
      context.putImageData(pixels, 0, 0)
    }
  }

  if (polygon.value.length) drawPolygon(context)
}

function buildEdgePreview() {
  if (!canvasReady.value) return
  const source = document.createElement('canvas')
  source.width = image.naturalWidth
  source.height = image.naturalHeight
  const sourceContext = source.getContext('2d', { willReadFrequently: true })!
  sourceContext.drawImage(image, 0, 0)
  const input = sourceContext.getImageData(0, 0, source.width, source.height)
  const output = sourceContext.createImageData(source.width, source.height)
  const gray = new Float32Array(source.width * source.height)
  for (let index = 0; index < gray.length; index += 1) {
    const offset = index * 4
    gray[index] = input.data[offset] * 0.299 + input.data[offset + 1] * 0.587 + input.data[offset + 2] * 0.114
  }
  const low = Math.max(0, Math.min(255, Number(props.edgeLow) || 0))
  for (let y = 1; y < source.height - 1; y += 1) {
    for (let x = 1; x < source.width - 1; x += 1) {
      const index = y * source.width + x
      const gx =
        -gray[index - source.width - 1] + gray[index - source.width + 1]
        - 2 * gray[index - 1] + 2 * gray[index + 1]
        - gray[index + source.width - 1] + gray[index + source.width + 1]
      const gy =
        -gray[index - source.width - 1] - 2 * gray[index - source.width] - gray[index - source.width + 1]
        + gray[index + source.width - 1] + 2 * gray[index + source.width] + gray[index + source.width + 1]
      const value = Math.hypot(gx, gy) >= low ? 255 : 0
      const offset = index * 4
      output.data[offset] = value
      output.data[offset + 1] = value
      output.data[offset + 2] = value
      output.data[offset + 3] = 255
    }
  }
  edgeCanvas.getContext('2d')!.putImageData(output, 0, 0)
}

function pointerPosition(event: PointerEvent) {
  const target = canvas.value!
  const rect = target.getBoundingClientRect()
  return {
    x: (event.clientX - rect.left) * target.width / rect.width,
    y: (event.clientY - rect.top) * target.height / rect.height,
  }
}

function onPointerDown(event: PointerEvent) {
  if (!canvasReady.value || !['edit', 'mask'].includes(previewMode.value)) return
  const point = pointerPosition(event)
  if (tool.value === 'polygon') {
    polygon.value.push(point)
    render()
    return
  }
  pushHistory()
  drawing.value = true
  canvas.value?.setPointerCapture(event.pointerId)
  paint(point, point)
}

let previousPoint: { x: number; y: number } | null = null

function onPointerMove(event: PointerEvent) {
  if (!drawing.value || tool.value === 'polygon') return
  const point = pointerPosition(event)
  paint(previousPoint || point, point)
}

function onPointerUp(event: PointerEvent) {
  if (!drawing.value) return
  drawing.value = false
  previousPoint = null
  canvas.value?.releasePointerCapture(event.pointerId)
  thresholdMask()
  updateCoverage()
  render()
}

function paint(from: { x: number; y: number }, to: { x: number; y: number }) {
  const context = maskCanvas.getContext('2d')!
  context.save()
  context.strokeStyle = paintMode.value === 'exclude' ? '#000' : '#fff'
  context.fillStyle = context.strokeStyle
  context.lineWidth = brushSize.value
  context.lineCap = 'round'
  context.lineJoin = 'round'
  context.beginPath()
  context.moveTo(from.x, from.y)
  context.lineTo(to.x, to.y)
  context.stroke()
  context.beginPath()
  context.arc(to.x, to.y, brushSize.value / 2, 0, Math.PI * 2)
  context.fill()
  context.restore()
  previousPoint = to
  render()
}

function finishPolygon() {
  if (polygon.value.length < 3) return
  pushHistory()
  const context = maskCanvas.getContext('2d')!
  context.fillStyle = paintMode.value === 'exclude' ? '#000' : '#fff'
  context.beginPath()
  context.moveTo(polygon.value[0].x, polygon.value[0].y)
  polygon.value.slice(1).forEach((point) => context.lineTo(point.x, point.y))
  context.closePath()
  context.fill()
  polygon.value = []
  thresholdMask()
  updateCoverage()
  render()
}

function cancelPolygon() {
  polygon.value = []
  render()
}

function drawPolygon(context: CanvasRenderingContext2D) {
  context.save()
  context.strokeStyle = '#75e1c3'
  context.fillStyle = '#75e1c3'
  context.lineWidth = Math.max(1, image.naturalWidth / 500)
  context.beginPath()
  polygon.value.forEach((point, index) => {
    if (!index) context.moveTo(point.x, point.y)
    else context.lineTo(point.x, point.y)
    context.fillRect(point.x - 2, point.y - 2, 4, 4)
  })
  context.stroke()
  context.restore()
}

function fillMask(value: number) {
  pushHistory()
  const context = maskCanvas.getContext('2d')!
  context.fillStyle = value ? '#fff' : '#000'
  context.fillRect(0, 0, maskCanvas.width, maskCanvas.height)
  polygon.value = []
  updateCoverage()
  render()
}

function invertMask() {
  pushHistory()
  const context = maskCanvas.getContext('2d')!
  const imageData = context.getImageData(0, 0, maskCanvas.width, maskCanvas.height)
  for (let index = 0; index < imageData.data.length; index += 4) {
    const value = 255 - imageData.data[index]
    imageData.data[index] = value
    imageData.data[index + 1] = value
    imageData.data[index + 2] = value
    imageData.data[index + 3] = 255
  }
  context.putImageData(imageData, 0, 0)
  polygon.value = []
  updateCoverage()
  render()
}

function thresholdMask() {
  const context = maskCanvas.getContext('2d', { willReadFrequently: true })!
  const pixels = context.getImageData(0, 0, maskCanvas.width, maskCanvas.height)
  for (let index = 0; index < pixels.data.length; index += 4) {
    const value = pixels.data[index] >= 16 ? 255 : 0
    pixels.data[index] = value
    pixels.data[index + 1] = value
    pixels.data[index + 2] = value
    pixels.data[index + 3] = 255
  }
  context.putImageData(pixels, 0, 0)
}

function pushHistory() {
  const context = maskCanvas.getContext('2d', { willReadFrequently: true })!
  history.value.push(context.getImageData(0, 0, maskCanvas.width, maskCanvas.height))
  if (history.value.length > 20) history.value.shift()
  future.value = []
}

function undo() {
  if (!history.value.length) return
  const context = maskCanvas.getContext('2d', { willReadFrequently: true })!
  future.value.push(context.getImageData(0, 0, maskCanvas.width, maskCanvas.height))
  context.putImageData(history.value.pop()!, 0, 0)
  updateCoverage()
  render()
}

function redo() {
  if (!future.value.length) return
  const context = maskCanvas.getContext('2d', { willReadFrequently: true })!
  history.value.push(context.getImageData(0, 0, maskCanvas.width, maskCanvas.height))
  context.putImageData(future.value.pop()!, 0, 0)
  updateCoverage()
  render()
}

function updateCoverage() {
  const pixels = maskCanvas.getContext('2d', { willReadFrequently: true })!
    .getImageData(0, 0, maskCanvas.width, maskCanvas.height).data
  let included = 0
  for (let index = 0; index < pixels.length; index += 4) {
    if (pixels[index] > 0) included += 1
  }
  coverage.value = pixels.length ? included / (pixels.length / 4) : 0
}

function save() {
  if (!coverage.value) return
  emit('save', maskCanvas.toDataURL('image/png'))
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="open" class="dialog-backdrop mask-editor-backdrop">
        <section class="mask-editor-dialog" role="dialog" aria-modal="true" aria-labelledby="mask-editor-title">
          <header class="mask-editor-header">
            <div>
              <h2 id="mask-editor-title">编辑有效区域</h2>
              <p>红色区域会被排除；白色遮罩参与比较，边缘预览不会自动修改遮罩</p>
            </div>
            <button class="icon-button small" type="button" title="关闭" @click="emit('close')"><X :size="16" /></button>
          </header>

          <div class="mask-editor-toolbar">
            <div class="mask-control-cluster">
              <span>操作</span>
              <div class="mask-tool-group paint-mode-group" role="radiogroup" aria-label="遮罩操作">
                <button type="button" :class="{ active: paintMode === 'include' }" @click="paintMode = 'include'"><Brush :size="14" />保留</button>
                <button type="button" :class="{ active: paintMode === 'exclude' }" @click="paintMode = 'exclude'"><Eraser :size="14" />排除</button>
              </div>
            </div>
            <div class="mask-control-cluster">
              <span>工具</span>
              <div class="mask-tool-group" role="radiogroup" aria-label="绘制工具">
                <button type="button" :class="{ active: tool === 'brush' }" @click="tool = 'brush'"><Brush :size="14" />画笔</button>
                <button type="button" :class="{ active: tool === 'polygon' }" @click="tool = 'polygon'"><MousePointer2 :size="14" />多边形</button>
              </div>
            </div>
            <label class="mask-brush-size" :class="{ muted: tool !== 'brush' }">大小<input v-model.number="brushSize" type="range" min="4" max="120" step="2" :disabled="tool !== 'brush'" /><output>{{ brushSize }}</output></label>
            <div class="mask-history-actions">
              <button class="icon-button small" type="button" title="撤销" :disabled="!canUndo" @click="undo"><Undo2 :size="15" /></button>
              <button class="icon-button small" type="button" title="重做" :disabled="!canRedo" @click="redo"><Redo2 :size="15" /></button>
              <button class="button secondary compact" type="button" @click="fillMask(255)">整张保留</button>
              <button class="button secondary compact" type="button" @click="invertMask"><Repeat2 :size="14" />反选</button>
              <button class="button secondary compact" type="button" @click="fillMask(0)"><RotateCcw :size="14" />整张排除</button>
            </div>
          </div>

          <div class="mask-preview-tabs" role="tablist" aria-label="遮罩预览">
            <button v-for="option in previewOptions" :key="option.value" type="button" :class="{ active: previewMode === option.value }" @click="previewMode = option.value">{{ option.label }}</button>
          </div>

          <div ref="stage" class="mask-canvas-stage" :class="{ loading }">
            <canvas
              ref="canvas"
              :style="canvasDisplayStyle"
              :class="{ drawable: previewMode === 'edit' || previewMode === 'mask' }"
              @pointerdown="onPointerDown"
              @pointermove="onPointerMove"
              @pointerup="onPointerUp"
              @pointercancel="onPointerUp"
            />
            <span v-if="loading">正在准备模板</span>
            <span v-else-if="loadError" class="mask-canvas-error">{{ loadError }}</span>
          </div>

          <footer class="mask-editor-footer">
            <div>
              <span>{{ paintMode === 'include' ? '保留' : '排除' }} · {{ tool === 'brush' ? '画笔' : '多边形' }}</span>
              <span>有效像素 {{ (coverage * 100).toFixed(1) }}%</span>
              <span v-if="polygon.length">{{ polygon.length }} 个套索节点</span>
            </div>
            <div v-if="polygon.length" class="polygon-actions">
              <button class="button secondary compact" type="button" @click="cancelPolygon">取消套索</button>
              <button class="button secondary compact" type="button" :disabled="polygon.length < 3" @click="finishPolygon"><Check :size="14" />完成多边形</button>
            </div>
            <div class="mask-editor-commands">
              <button class="button secondary" type="button" @click="emit('close')">取消</button>
              <button class="button primary" type="button" :disabled="!coverage" @click="save"><Check :size="15" />应用到目标</button>
            </div>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
