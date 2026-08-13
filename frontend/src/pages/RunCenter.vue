<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Check,
  CircleAlert,
  Clock3,
  ListMusic,
  LoaderCircle,
  Music2,
  MonitorCog,
  Pause,
  Play,
  Repeat2,
  RotateCw,
  ShieldAlert,
  Shuffle,
  Square,
} from '@lucide/vue'

import AppSelect from '../components/AppSelect.vue'
import RunnerStatusBadge from '../components/RunnerStatusBadge.vue'
import { useRuntimeStore } from '../stores/runtime'
import type { PreflightResponse } from '../types/api'

const runtime = useRuntimeStore()
const router = useRouter()
const showRealConfirmation = ref(false)
const preflightReport = ref<PreflightResponse | null>(null)
const preflightChecking = ref(false)

const groups = computed(() => ['全部', ...(runtime.playlists?.song_groups.map((group) => group.name) || [])])
const groupOptions = computed(() => groups.value.map((group) => ({ value: group, label: group })))
const queueDuration = computed(() =>
  runtime.visibleSongs.reduce((total, song) => total + song.duration_seconds + song.buffer_seconds, 0),
)

function formatDuration(seconds: number) {
  const rounded = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(rounded / 60)
  const rest = rounded % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

async function requestStart() {
  if (runtime.executionMode === 'real') {
    preflightChecking.value = true
    try {
      preflightReport.value = await runtime.preflight()
      if (preflightReport.value.ready) showRealConfirmation.value = true
    } finally {
      preflightChecking.value = false
    }
    return
  }
  await runtime.start()
}

function openSettings() {
  preflightReport.value = null
  void router.push('/settings')
}

async function confirmRealStart() {
  showRealConfirmation.value = false
  await runtime.start()
}
</script>

<template>
  <div class="run-center-shell">
  <main class="run-center">
    <section class="run-overview">
      <div class="run-title">
        <div>
          <p class="section-kicker">运行中心</p>
          <h2>{{ runtime.currentSong || '等待播放' }}</h2>
          <p class="current-step">{{ runtime.currentStep || '尚未执行动作' }}</p>
        </div>
        <RunnerStatusBadge :status="runtime.runner.status" />
      </div>

      <div class="progress-track" aria-hidden="true">
        <span :class="{ active: runtime.isRunning }" />
      </div>

      <dl class="run-facts">
        <div>
          <dt>播放范围</dt>
          <dd>{{ runtime.selectedGroup }}</dd>
        </div>
        <div>
          <dt>可用歌曲</dt>
          <dd>{{ runtime.enabledSongCount }} 首</dd>
        </div>
        <div>
          <dt>预计时长</dt>
          <dd>{{ formatDuration(queueDuration) }}</dd>
        </div>
        <div>
          <dt>执行模式</dt>
          <dd :class="{ 'real-mode-text': runtime.executionMode === 'real' }">{{ runtime.executionMode === 'real' ? '实际' : '模拟' }}</dd>
        </div>
      </dl>
    </section>

    <section class="queue-section">
      <header class="section-header">
        <div>
          <h3><ListMusic :size="18" />播放队列</h3>
          <p>{{ runtime.visibleSongs.length }} 首歌曲</p>
        </div>
        <div class="queue-tools">
          <div class="select-field">
            <span>歌曲组</span>
            <AppSelect
              v-model="runtime.selectedGroup"
              :disabled="runtime.isRunning"
              :options="groupOptions"
              label="歌曲组"
            />
          </div>
          <button class="icon-button" type="button" title="刷新运行状态" :disabled="!runtime.isConnected" @click="runtime.refreshRunner">
            <RotateCw :size="17" />
          </button>
        </div>
      </header>

      <div class="queue-table-wrap">
        <table class="queue-table">
          <thead>
            <tr>
              <th class="index-column">#</th>
              <th>歌曲</th>
              <th>动作预设</th>
              <th>时长</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody v-if="runtime.visibleSongs.length">
            <tr v-for="(song, index) in runtime.visibleSongs" :key="`${song.title}-${index}`" :class="{ disabled: !song.enabled }">
              <td class="index-column">{{ index + 1 }}</td>
              <td>
                <div class="song-cell">
                  <span class="song-icon"><Music2 :size="16" /></span>
                  <div>
                    <strong>{{ song.title || '未命名歌曲' }}</strong>
                    <span>{{ song.keyword }}</span>
                  </div>
                </div>
              </td>
              <td>{{ song.step_preset || '继承歌曲组' }}</td>
              <td><Clock3 :size="14" />{{ formatDuration(song.duration_seconds + song.buffer_seconds) }}</td>
              <td><span class="song-state" :class="{ enabled: song.enabled }">{{ song.enabled ? '启用' : '停用' }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-if="!runtime.visibleSongs.length" class="empty-state">
          <Music2 :size="24" />
          <span>当前歌曲组为空</span>
        </div>
      </div>
    </section>

    <footer class="control-bar">
      <div class="mode-controls">
        <div class="execution-mode" :class="{ real: runtime.executionMode === 'real' }" role="radiogroup" aria-label="执行模式">
          <button
            type="button"
            :class="{ active: runtime.executionMode === 'simulation' }"
            :disabled="runtime.isRunning"
            @click="runtime.executionMode = 'simulation'"
          >
            模拟
          </button>
          <button
            type="button"
            class="real-option"
            :class="{ active: runtime.executionMode === 'real' }"
            :disabled="runtime.isRunning"
            @click="runtime.executionMode = 'real'"
          >
            实际
          </button>
        </div>
        <label class="toggle-control" :class="{ active: runtime.loop }">
          <input v-model="runtime.loop" type="checkbox" :disabled="runtime.isRunning" />
          <Repeat2 :size="16" />
          <span>循环</span>
        </label>
        <label class="toggle-control" :class="{ active: runtime.random }">
          <input v-model="runtime.random" type="checkbox" :disabled="runtime.isRunning" />
          <Shuffle :size="16" />
          <span>随机</span>
        </label>
      </div>

      <div class="transport-controls">
        <button class="button primary start-button" type="button" :disabled="!runtime.canStart || preflightChecking" @click="requestStart">
          <LoaderCircle v-if="runtime.commandPending || preflightChecking" class="spin" :size="17" />
          <Play v-else :size="17" fill="currentColor" />
          开始播放
        </button>
        <Transition name="control-swap" mode="out-in">
          <button v-if="runtime.runner.status !== 'paused'" key="pause" class="button secondary" type="button" :disabled="!runtime.canPause" @click="runtime.pause">
            <Pause :size="17" />
            暂停
          </button>
          <button v-else key="resume" class="button secondary" type="button" :disabled="!runtime.canResume" @click="runtime.resume">
            <Play :size="17" />
            继续
          </button>
        </Transition>
        <button class="button danger" type="button" :disabled="!runtime.canStop" @click="runtime.stop">
          <Square :size="15" fill="currentColor" />
          停止
        </button>
      </div>
    </footer>
  </main>
    <Teleport to="body">
      <Transition name="dialog-motion">
        <div v-if="preflightReport && !preflightReport.ready" class="dialog-backdrop" @mousedown.self="preflightReport = null">
          <section class="connection-dialog preflight-dialog" role="alertdialog" aria-modal="true">
            <header class="dialog-header"><div class="dialog-title-wrap"><span class="dialog-icon warning"><ShieldAlert :size="18" /></span><div><h2>实际执行尚未就绪</h2><p>先处理阻塞项，再启动游戏工作流</p></div></div></header>
            <div class="preflight-dialog-list">
              <div v-for="item in preflightReport.checks" :key="item.key" :class="{ failed: !item.ok }"><Check v-if="item.ok" :size="15" /><CircleAlert v-else :size="15" /><strong>{{ item.label }}</strong><span>{{ item.detail }}</span></div>
            </div>
            <footer class="dialog-actions confirmation-actions"><button class="button secondary" type="button" @click="preflightReport = null">关闭</button><button class="button primary" type="button" @click="openSettings"><MonitorCog :size="15" />打开目标程序设置</button></footer>
          </section>
        </div>
      </Transition>
    </Teleport>
    <Teleport to="body">
      <Transition name="dialog-motion">
        <div v-if="showRealConfirmation" class="dialog-backdrop" @mousedown.self="showRealConfirmation = false">
        <section class="connection-dialog real-run-dialog" role="alertdialog" aria-modal="true" aria-labelledby="real-run-title">
          <header class="dialog-header">
            <div class="dialog-title-wrap">
              <span class="dialog-icon warning"><ShieldAlert :size="18" /></span>
              <div>
                <h2 id="real-run-title">开始实际执行</h2>
                <p>将向目标窗口发送鼠标与键盘动作</p>
              </div>
            </div>
          </header>
          <div class="confirmation-body">
            <p>请确认目标窗口与当前工作流配置正确。运行中按 <kbd>F9</kbd> 可随时急停。</p>
          </div>
          <footer class="dialog-actions confirmation-actions">
            <button class="button secondary" type="button" @click="showRealConfirmation = false">取消</button>
            <button class="button danger" type="button" @click="confirmRealStart">
              <Play :size="16" fill="currentColor" />
              开始执行
            </button>
          </footer>
          </section>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
