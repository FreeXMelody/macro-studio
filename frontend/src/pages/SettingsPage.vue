<script setup lang="ts">
import { computed, onDeactivated, ref, watch } from 'vue'
import { AlertTriangle, Check, Focus, LoaderCircle, Maximize2, MonitorCog, RefreshCw, Save, ScanLine, X } from '@lucide/vue'

import { useRuntimeStore } from '../stores/runtime'
import type { PreflightResponse, TargetSettingsDto, WindowProbeResponse } from '../types/api'

const runtime = useRuntimeStore()
const draft = ref<TargetSettingsDto>({ window_hint: '逆水寒手游桌面版', focus_window: true, input_mode: 'window_message', confirm_step_test: true, preview_clicks: false })
const probe = ref<WindowProbeResponse | null>(null)
const preflight = ref<PreflightResponse | null>(null)
const busy = ref<'probe' | 'capture' | 'save' | 'preflight' | ''>('')
const localError = ref('')
const notice = ref('')
const previewExpanded = ref(false)
const initialized = ref(false)
const dirty = computed(() => runtime.settings !== null && JSON.stringify(draft.value) !== JSON.stringify(runtime.settings))

onDeactivated(() => {
  previewExpanded.value = false
})

watch(() => runtime.settings, (value) => {
  if (!value) return
  if (!initialized.value || !dirty.value) draft.value = { ...value }
  initialized.value = true
}, { immediate: true, deep: true })

async function save() {
  busy.value = 'save'
  localError.value = ''
  try {
    draft.value = { ...await runtime.saveSettings({ ...draft.value }) }
    notice.value = '目标程序设置已保存'
    await inspect(false)
  } catch (error) {
    localError.value = error instanceof Error ? error.message : '保存失败'
  } finally {
    busy.value = ''
  }
}

async function inspect(capture: boolean) {
  busy.value = capture ? 'capture' : 'probe'
  localError.value = ''
  try {
    probe.value = await runtime.probeWindow(draft.value.window_hint, capture)
    if (!probe.value.found) localError.value = probe.value.error
  } catch (error) {
    localError.value = error instanceof Error ? error.message : '窗口探测失败'
  } finally {
    busy.value = ''
  }
}

async function runPreflight() {
  busy.value = 'preflight'
  localError.value = ''
  try {
    if (dirty.value) throw new Error('请先保存目标程序设置，再运行检查')
    preflight.value = await runtime.preflight()
  } catch (error) {
    localError.value = error instanceof Error ? error.message : '运行前检查失败'
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <div class="settings-page-shell">
  <main class="settings-page">
    <header class="settings-toolbar">
      <div><p class="section-kicker">GAME READY</p><h2>目标程序</h2><span>配置真实执行连接与后台输入</span></div>
      <div class="settings-toolbar-actions">
        <span v-if="notice" class="save-notice"><Check :size="14" />{{ notice }}</span>
        <button class="button secondary" type="button" :disabled="Boolean(busy)" @click="runPreflight"><ScanLine :size="15" />运行前检查</button>
        <button class="button primary" type="button" :disabled="!dirty || Boolean(busy)" @click="save"><LoaderCircle v-if="busy === 'save'" class="spin" :size="15" /><Save v-else :size="15" />保存设置</button>
      </div>
    </header>

    <Transition name="banner-slide"><div v-if="localError" class="playlist-error"><AlertTriangle :size="15" /><span>{{ localError }}</span><button type="button" title="关闭" @click="localError = ''">×</button></div></Transition>

    <div class="settings-workspace">
      <section class="settings-form-panel">
        <header><MonitorCog :size="18" /><div><h3>窗口连接</h3><p>窗口关键词会匹配游戏主窗口标题</p></div></header>
        <label class="form-field">窗口关键词<input v-model="draft.window_hint" placeholder="例如 逆水寒手游桌面版" /></label>
        <div class="settings-field-group">
          <span>输入模式</span>
          <div class="settings-segmented" role="radiogroup" aria-label="输入模式">
            <button type="button" :class="{ active: draft.input_mode === 'window_message' }" @click="draft.input_mode = 'window_message'">后台窗口消息</button>
            <button type="button" :class="{ active: draft.input_mode === 'foreground' }" @click="draft.input_mode = 'foreground'">前台输入</button>
          </div>
          <small>{{ draft.input_mode === 'window_message' ? '不移动物理鼠标；部分游戏控件可能拒绝窗口消息' : '兼容性更高，但会占用鼠标与键盘' }}</small>
        </div>
        <label class="settings-check"><input v-model="draft.focus_window" type="checkbox" /><span><strong>执行前聚焦窗口</strong><small>后台模式建议关闭；前台模式建议开启</small></span></label>
        <label class="settings-check"><input v-model="draft.confirm_step_test" type="checkbox" /><span><strong>单步实际测试前确认</strong><small>关闭后点击烧瓶按钮将立即执行；仍可按 F9 急停</small></span></label>
        <label class="settings-check"><input v-model="draft.preview_clicks" type="checkbox" /><span><strong>执行时显示点击位置</strong><small>点位与图像点击后短暂显示十字线，不会移动物理鼠标</small></span></label>
        <div class="settings-test-actions">
          <button class="button secondary" type="button" :disabled="Boolean(busy)" @click="inspect(false)"><LoaderCircle v-if="busy === 'probe'" class="spin" :size="15" /><RefreshCw v-else :size="15" />检测连接</button>
          <button class="button secondary" type="button" :disabled="Boolean(busy)" @click="inspect(true)"><LoaderCircle v-if="busy === 'capture'" class="spin" :size="15" /><Focus v-else :size="15" />后台截图测试</button>
        </div>
      </section>

      <section class="window-probe-panel" :class="{ empty: !probe }">
        <template v-if="probe">
          <div class="window-preview"><button v-if="probe.preview_data_url" type="button" title="放大后台截图" @click="previewExpanded = true"><img :src="probe.preview_data_url" alt="目标窗口后台截图" /><Maximize2 :size="16" /></button><MonitorCog v-else :size="34" /></div>
          <header><div><span :class="['connection-dot', { online: probe.found }]" /><h3>{{ probe.found ? probe.title : '未连接目标窗口' }}</h3></div><code v-if="probe.hwnd">HWND {{ probe.hwnd }}</code></header>
          <dl v-if="probe.found" class="window-facts">
            <div><dt>进程</dt><dd>{{ probe.process_name || probe.pid }}</dd></div>
            <div><dt>输入权限</dt><dd :class="{ 'permission-mismatch': !probe.input_allowed }">{{ probe.process_elevated ? '游戏管理员' : '游戏普通' }} / {{ probe.app_elevated ? '程序管理员' : '程序普通' }}</dd></div>
            <div><dt>窗口尺寸</dt><dd>{{ probe.width }} × {{ probe.height }}</dd></div>
            <div><dt>客户区</dt><dd>{{ probe.client_width }} × {{ probe.client_height }}</dd></div><div v-if="probe.capture_width"><dt>捕获帧</dt><dd>{{ probe.capture_width }} × {{ probe.capture_height }}</dd></div>
            <div><dt>DPI</dt><dd>{{ probe.dpi }} ({{ Math.round(probe.dpi / 96 * 100) }}%)</dd></div>
            <div><dt>窗口位置</dt><dd>{{ probe.left }}, {{ probe.top }}</dd></div>
            <div><dt>客户区原点</dt><dd>{{ probe.client_left }}, {{ probe.client_top }}</dd></div>
          </dl>
        </template>
        <template v-else><MonitorCog :size="34" /><strong>尚未检测目标窗口</strong><span>保存或检测后显示连接详情</span></template>
      </section>

      <section v-if="preflight" class="preflight-panel">
        <header><div><h3>运行前检查</h3><p>{{ preflight.ready ? '可以开始实际执行' : '仍有阻塞项需要处理' }}</p></div><span :class="['preflight-state', { ready: preflight.ready }]">{{ preflight.ready ? 'READY' : 'BLOCKED' }}</span></header>
        <div class="preflight-list"><div v-for="item in preflight.checks" :key="item.key" :class="{ failed: !item.ok }"><Check v-if="item.ok" :size="15" /><AlertTriangle v-else :size="15" /><strong>{{ item.label }}</strong><span>{{ item.detail }}</span></div></div>
      </section>
    </div>
  </main>

  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="previewExpanded && probe?.preview_data_url" class="dialog-backdrop capture-preview-backdrop" @mousedown.self="previewExpanded = false">
        <section class="capture-preview-dialog" role="dialog" aria-modal="true" aria-label="后台截图预览">
          <header><strong>{{ probe.title }}</strong><code>{{ probe.capture_width }} × {{ probe.capture_height }}</code><button class="icon-button small" type="button" title="关闭" @click="previewExpanded = false"><X :size="16" /></button></header>
          <img :src="probe.preview_data_url" alt="完整目标窗口后台截图" />
        </section>
      </div>
    </Transition>
  </Teleport>
  </div>
</template>
