<script setup lang="ts">
import { computed } from 'vue'
import { ChevronDown, CircleAlert, Terminal, Trash2 } from '@lucide/vue'

import { useRuntimeStore } from '../stores/runtime'
import type { RunnerEvent } from '../types/api'

const runtime = useRuntimeStore()
const latestEvents = computed(() => [...runtime.events].reverse())

function eventTime(event: RunnerEvent) {
  return new Date(event.timestamp * 1000).toLocaleTimeString('zh-CN', { hour12: false })
}

function eventLabel(event: RunnerEvent) {
  const labels: Record<string, string> = {
    'connection.ready': '事件连接已建立',
    'runner.state_changed': '运行状态改变',
    'runner.started': '动作序列开始',
    'runner.completed': '动作序列完成',
    'runner.stopped': '动作序列已停止',
    'runner.failed': '动作序列失败',
    'runner.prepare_failed': '执行准备失败',
    'song.started': `开始：${String(event.data.label || '')}`,
    'song.completed': `完成：${String(event.data.label || '')}`,
    'song.next': '准备下一首',
    'step.started': `执行：${String(event.data.name || '')}`,
    'step.completed': `完成动作：${String(event.data.name || '')}`,
    'step.failed': `动作失败：${String(event.data.name || '')}`,
    'step.recovering': `恢复动作：${String(event.data.name || '')}`,
    'step.skipped': `已跳过动作：${String(event.data.name || '')}`,
    'cycle.order': '播放顺序已生成',
    'cycle.next': '开始下一轮',
    'command.failed': '命令执行失败',
    'region.selected': String(event.data.message || '识别区域已更新'),
    'vision.test_started': `开始测试识别：${String(event.data.name || '')}`,
    'vision.test.completed': `识别测试命中：${String(event.data.name || '')}`,
    'vision.test.failed': `识别测试失败：${String(event.data.name || '')}`,
  }
  if (event.type === 'log.appended') return String(event.data.message || '运行日志')
  return labels[event.type] || event.type
}

function eventDetail(event: RunnerEvent) {
  const error = String(event.data.error || '').trim()
  if (event.type === 'step.recovering') {
    const attempt = Number(event.data.attempt || 0)
    const limit = Number(event.data.limit || 0)
    const rollback = event.data.rollback ? `，回退到「${String(event.data.recovery_name || '')}」` : '，重试当前动作'
    return `第 ${attempt}/${limit} 次${rollback}${error ? `：${error}` : ''}`
  }
  if (event.type === 'step.skipped') {
    return error ? `失败策略：跳过；${error}` : '失败策略：跳过'
  }
  if (error) return error
  if (event.type === 'song.started') {
    return `动作来源：${String(event.data.preset || '未指定')}`
  }
  if (event.type === 'step.started' || event.type === 'step.completed') {
    return `动作类型：${String(event.data.action || 'unknown')}`
  }
  if (event.type === 'vision.test.completed') {
    return `置信度 ${Number(event.data.score || 0).toFixed(3)} · ${event.data.source === 'background' ? '后台截图' : '屏幕截图'}`
  }
  return ''
}

function isError(event: RunnerEvent) {
  return event.type.includes('failed') || event.type === 'command.failed'
}
</script>

<template>
  <section class="event-panel global-event-panel" :class="{ collapsed: !runtime.logExpanded }">
    <header class="event-header">
      <button class="event-toggle" type="button" @click="runtime.toggleLog">
        <Terminal :size="17" />
        <span>运行日志</span>
        <span class="event-count">{{ runtime.events.length }}</span>
        <ChevronDown class="collapse-chevron" :class="{ expanded: runtime.logExpanded }" :size="16" />
      </button>
      <button class="icon-button small" type="button" title="清空日志" :disabled="!runtime.events.length" @click="runtime.clearEvents">
        <Trash2 :size="15" />
      </button>
    </header>
    <Transition name="panel-collapse">
      <div v-if="runtime.logExpanded" class="event-list">
        <div v-if="!latestEvents.length" class="event-empty">等待运行事件</div>
        <div v-for="event in latestEvents" :key="`${event.sequence}-${event.timestamp}`" class="event-row" :class="{ error: isError(event) }">
          <time>{{ eventTime(event) }}</time>
          <CircleAlert v-if="isError(event)" :size="14" />
          <span v-else class="event-mark" />
          <div class="event-message">
            <strong>{{ eventLabel(event) }}</strong>
            <span v-if="eventDetail(event)">{{ eventDetail(event) }}</span>
          </div>
          <code>{{ event.status || 'local' }}</code>
        </div>
      </div>
    </Transition>
  </section>
</template>
