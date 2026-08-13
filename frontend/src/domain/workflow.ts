import type { PresetDto, StepDto } from '../types/api'

export interface ActionTypeSpec {
  value: string
  label: string
  category: 'pointer' | 'text' | 'wait' | 'keyboard' | 'transport' | 'utility'
  needsTarget?: boolean
  needsValue?: boolean
  placeholder?: string
}

export const ACTION_TYPE_OPTIONS: ActionTypeSpec[] = [
  { value: 'click', label: '点击点位', category: 'pointer', needsTarget: true, placeholder: '点位名称' },
  { value: 'image_click', label: '图像点击', category: 'pointer', needsValue: true, placeholder: '图像目标名称' },
  { value: 'paste', label: '粘贴文本', category: 'text', needsValue: true, placeholder: '支持 {keyword}' },
  { value: 'wait', label: '等待', category: 'wait', needsValue: true, placeholder: '秒数或 mm:ss' },
  { value: 'key', label: '单击按键', category: 'keyboard', needsValue: true, placeholder: '例如 space、esc、f5' },
  { value: 'key_hold', label: '长按按键', category: 'keyboard', needsValue: true, placeholder: '例如 space@0.8' },
  { value: 'key_down', label: '按下按键', category: 'keyboard', needsValue: true, placeholder: '按住直到 key_up' },
  { value: 'key_up', label: '抬起按键', category: 'keyboard', needsValue: true, placeholder: '例如 space' },
  { value: 'enter', label: 'Enter', category: 'keyboard' },
  { value: 'ctrl_a', label: 'Ctrl+A', category: 'keyboard' },
  { value: 'hotkey', label: '组合键', category: 'keyboard', needsValue: true, placeholder: '例如 ctrl+v' },
  { value: 'hotkey_hold', label: '组合键长按', category: 'keyboard', needsValue: true, placeholder: '例如 ctrl+space@0.5' },
  { value: 'open_uri', label: '打开链接或协议', category: 'transport', needsValue: true, placeholder: 'https://... 或 nsh://...' },
  { value: 'http_request', label: '发送 HTTP 请求', category: 'transport', needsValue: true, placeholder: 'GET http://127.0.0.1/...' },
  { value: 'log', label: '写入日志', category: 'utility', needsValue: true, placeholder: '日志内容' },
]

const actionTypeMap = new Map(ACTION_TYPE_OPTIONS.map((item) => [item.value, item]))

export function actionType(kind: string): ActionTypeSpec {
  return actionTypeMap.get(kind) ?? {
    value: kind,
    label: kind || '未知动作',
    category: 'utility',
    needsValue: true,
  }
}

export function clonePresets(presets: PresetDto[]): PresetDto[] {
  return presets.map((preset) => ({
    name: preset.name,
    steps: preset.steps.map((step) => ({ ...step })),
  }))
}

export function emptyStep(kind = 'click'): StepDto {
  return {
    name: actionType(kind).label,
    kind,
    target: '',
    value: '',
    enabled: true,
    wait_after: '',
  }
}

export function uniquePresetName(presets: PresetDto[], base = '新动作预设'): string {
  const normalized = base.trim() || '新动作预设'
  const names = new Set(presets.map((preset) => preset.name))
  if (!names.has(normalized)) return normalized
  let index = 2
  while (names.has(`${normalized} ${index}`)) index += 1
  return `${normalized} ${index}`
}

export function reorderSteps(preset: PresetDto, from: number, to: number): boolean {
  if (from === to || from < 0 || to < 0 || from >= preset.steps.length || to >= preset.steps.length) {
    return false
  }
  const [step] = preset.steps.splice(from, 1)
  preset.steps.splice(to, 0, step)
  return true
}