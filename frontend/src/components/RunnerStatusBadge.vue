<script setup lang="ts">
import { computed } from 'vue'

import type { RunnerStatus } from '../types/api'

const props = defineProps<{
  status: RunnerStatus
}>()

const label = computed(() => {
  const labels: Record<RunnerStatus, string> = {
    idle: '空闲',
    starting: '启动中',
    running: '运行中',
    paused: '已暂停',
    stopping: '停止中',
    stopped: '已停止',
    completed: '已完成',
    failed: '失败',
  }
  return labels[props.status]
})
</script>

<template>
  <Transition name="status-swap" mode="out-in">
    <span :key="status" class="status-badge" :class="`status-${status}`">
    <span class="status-dot" aria-hidden="true" />
    {{ label }}
    </span>
  </Transition>
</template>
