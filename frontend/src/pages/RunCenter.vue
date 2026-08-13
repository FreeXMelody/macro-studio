<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Check,
  CircleAlert,
  Clock3,
  ClipboardCheck,
  FilePlay,
  ListChecks,
  ListRestart,
  LoaderCircle,
  MonitorCog,
  Pause,
  Play,
  Repeat2,
  RotateCw,
  ShieldAlert,
  Shuffle,
  Square,
  TriangleAlert,
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
const pendingRunOnce = ref(false)
const showPlanReport = ref(false)

const groups = computed(() => ['全部', ...(runtime.playlists?.song_groups.map((group) => group.name) || [])])
const groupOptions = computed(() => groups.value.map((group) => ({ value: group, label: group })))
const queueDuration = computed(() =>
  runtime.visibleRunItems.reduce((total, item) => total + item.durationSeconds + item.bufferSeconds, 0),
)

function formatDuration(seconds: number) {
  const rounded = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(rounded / 60)
  const rest = rounded % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

async function inspectPlan(openReport = true) {
  try {
    const report = await runtime.inspectRunPlan()
    if (openReport) showPlanReport.value = true
    return report
  } catch (error) {
    runtime.error = error instanceof Error ? error.message : '运行计划检查失败'
    return null
  }
}

async function requestStart(once = false) {
  pendingRunOnce.value = once
  const report = await inspectPlan(false)
  if (!report) return
  if (!report.ready) {
    showPlanReport.value = true
    return
  }
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
  await runtime.start({ once })
}

function openSettings() {
  preflightReport.value = null
  void router.push('/settings')
}

async function confirmRealStart() {
  showRealConfirmation.value = false
  await runtime.start({ once: pendingRunOnce.value })
}
</script>

<template>
  <div class="run-center-shell">
  <main class="run-center">
    <section class="run-overview">
      <div class="run-title">
        <div>
          <p class="section-kicker">运行中心</p>
          <h2>{{ runtime.currentSong || '等待运行' }}</h2>
          <p class="current-step">{{ runtime.currentStep || '尚未执行动作' }}</p>
        </div>
        <RunnerStatusBadge :status="runtime.runner.status" />
      </div>

      <div class="progress-track" aria-hidden="true">
        <span :class="{ active: runtime.isRunning }" />
      </div>

      <dl class="run-facts">
        <div>
          <dt>执行范围</dt>
          <dd>{{ runtime.selectedGroup }}</dd>
        </div>
        <div>
          <dt>可用条目</dt>
          <dd>{{ runtime.enabledSongCount }} 个</dd>
        </div>
        <div>
          <dt>内容时长</dt>
          <dd>{{ formatDuration(queueDuration) }}</dd>
        </div>
        <div>
          <dt>执行模式</dt>
          <dd :class="{ 'real-mode-text': runtime.executionMode === 'real' }">{{ runtime.executionMode === 'real' ? '实际' : '加速演练' }}</dd>
        </div>
      </dl>
    </section>

    <section class="queue-section">
      <header class="section-header">
        <div>
          <h3><ListChecks :size="18" />执行队列</h3>
          <p>{{ runtime.visibleRunItems.length }} 个条目</p>
        </div>
        <div class="queue-tools">
          <div class="select-field">
            <span>队列分组</span>
            <AppSelect
              v-model="runtime.selectedGroup"
              :disabled="runtime.isRunning"
              :options="groupOptions"
              label="队列分组"
            />
          </div>
          <button
            class="icon-button"
            type="button"
            title="检查运行计划"
            :disabled="!runtime.isConnected || runtime.planChecking"
            @click="inspectPlan(true)"
          >
            <LoaderCircle v-if="runtime.planChecking" :size="17" class="spin" />
            <ClipboardCheck v-else :size="17" />
          </button>
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
              <th>条目</th>
              <th>工作流</th>
              <th>时长</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody v-if="runtime.visibleRunItems.length">
            <tr v-for="(item, index) in runtime.visibleRunItems" :key="item.id" :class="{ disabled: !item.enabled }">
              <td class="index-column">{{ index + 1 }}</td>
              <td>
                <div class="song-cell">
                  <span class="song-icon"><FilePlay :size="16" /></span>
                  <div>
                    <strong>{{ item.name }}</strong>
                    <span>{{ item.input }}</span>
                  </div>
                </div>
              </td>
              <td>{{ item.workflow }}</td>
              <td><Clock3 :size="14" />{{ formatDuration(item.durationSeconds + item.bufferSeconds) }}</td>
              <td><span class="song-state" :class="{ enabled: item.enabled }">{{ item.enabled ? '启用' : '停用' }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-if="!runtime.visibleRunItems.length" class="empty-state">
          <FilePlay :size="24" />
          <span>当前分组没有可运行条目</span>
        </div>
      </div>
    </section>

    <footer class="control-bar">
      <div class="mode-controls">
        <div class="execution-mode" :class="{ real: runtime.executionMode === 'real' }" role="radiogroup" aria-label="运行方式">
          <button
            type="button"
            :class="{ active: runtime.executionMode === 'simulation' }"
            :disabled="runtime.isRunning"
            @click="runtime.executionMode = 'simulation'"
            title="加速检查动作顺序、变量、等待和日志，不向目标窗口发送输入"
          >
            加速演练
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
        <button
          class="button secondary run-once-button"
          type="button"
          :disabled="!runtime.canStart || preflightChecking"
          title="忽略循环设置，仅运行当前队列一轮"
          @click="requestStart(true)"
        >
          <ListRestart :size="17" />
          运行一次
        </button>
        <button class="button primary start-button" type="button" :disabled="!runtime.canStart || preflightChecking" @click="requestStart(false)">
          <LoaderCircle v-if="runtime.commandPending || preflightChecking" class="spin" :size="17" />
          <Play v-else :size="17" fill="currentColor" />
          {{ runtime.loop ? '开始循环' : '开始运行' }}
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
            <header class="dialog-header"><div class="dialog-title-wrap"><span class="dialog-icon warning"><ShieldAlert :size="18" /></span><div><h2>实际执行尚未就绪</h2><p>先处理阻塞项，再启动当前工作流</p></div></div></header>
            <div class="preflight-dialog-list">
              <div v-for="item in preflightReport.checks" :key="item.key" :class="{ failed: !item.ok }"><Check v-if="item.ok" :size="15" /><CircleAlert v-else :size="15" /><strong>{{ item.label }}</strong><span>{{ item.detail }}</span></div>
            </div>
            <footer class="run-dialog-actions"><button class="button secondary" type="button" @click="preflightReport = null">关闭</button><button class="button primary" type="button" @click="openSettings"><MonitorCog :size="15" />打开目标程序设置</button></footer>
          </section>
        </div>
      </Transition>
    </Teleport>
    <Teleport to="body">
      <Transition name="dialog-motion">
        <div v-if="showPlanReport && runtime.runPlan" class="dialog-backdrop" @mousedown.self="showPlanReport = false">
          <section class="connection-dialog run-plan-dialog" role="dialog" aria-modal="true" aria-labelledby="run-plan-title">
            <header class="dialog-header">
              <div class="dialog-title-wrap">
                <span class="dialog-icon" :class="{ warning: !runtime.runPlan.ready }">
                  <ClipboardCheck v-if="runtime.runPlan.ready" :size="18" />
                  <TriangleAlert v-else :size="18" />
                </span>
                <div>
                  <h2 id="run-plan-title">运行计划报告</h2>
                  <p>{{ runtime.runPlan.ready ? '工作流可以开始演练' : '发现阻塞演练的问题' }}</p>
                </div>
              </div>
            </header>
            <div class="run-plan-body">
              <dl class="run-confirmation-facts">
                <div><dt>运行条目</dt><dd>{{ runtime.runPlan.item_count }} 个</dd></div>
                <div><dt>动作总数</dt><dd>{{ runtime.runPlan.action_count }} 个</dd></div>
                <div><dt>预计实时时长</dt><dd>{{ formatDuration(runtime.runPlan.estimated_seconds) }}</dd></div>
              </dl>
              <div v-if="runtime.runPlan.issues.length" class="run-plan-issues">
                <div
                  v-for="(issue, index) in runtime.runPlan.issues"
                  :key="issue.code + ':' + index"
                  class="run-plan-issue"
                  :class="issue.severity"
                >
                  <TriangleAlert :size="15" />
                  <div>
                    <strong>{{ issue.item_name || '执行队列' }}<template v-if="issue.step_name"> · {{ issue.step_name }}</template></strong>
                    <span>{{ issue.message }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="run-plan-ready">
                <ClipboardCheck :size="20" />
                <div><strong>没有发现配置问题</strong><span>演练将使用加速时间轴，不会向目标窗口发送输入。</span></div>
              </div>
            </div>
            <footer class="run-dialog-actions">
              <button class="button primary" type="button" @click="showPlanReport = false">完成</button>
            </footer>
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
                <h2 id="real-run-title">{{ pendingRunOnce ? '实际运行一次' : '开始实际运行' }}</h2>
                <p>将向目标窗口发送鼠标与键盘动作</p>
              </div>
            </div>
          </header>
          <div class="run-confirmation-body">
            <dl class="run-confirmation-facts">
              <div><dt>执行范围</dt><dd>{{ runtime.selectedGroup }}</dd></div>
              <div><dt>队列条目</dt><dd>{{ runtime.enabledSongCount }} 个</dd></div>
              <div><dt>运行轮次</dt><dd>{{ pendingRunOnce ? '仅一轮' : runtime.loop ? '持续循环' : '一轮' }}</dd></div>
            </dl>
            <p>请确认目标窗口与工作流配置正确。运行中按 <kbd>F9</kbd> 可随时急停。</p>
          </div>
          <footer class="run-dialog-actions">
            <button class="button secondary" type="button" @click="showRealConfirmation = false">取消</button>
            <button class="button danger" type="button" @click="confirmRealStart">
              <Play :size="16" fill="currentColor" />
              {{ pendingRunOnce ? '运行一次' : runtime.loop ? '开始循环' : '开始运行' }}
            </button>
          </footer>
          </section>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
