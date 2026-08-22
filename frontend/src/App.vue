<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Activity, Cable, Clapperboard, Copy, ListMusic, Minus, ScanSearch, Settings, Square, Wifi, WifiOff, Workflow, X } from '@lucide/vue'
import type { UnlistenFn } from '@tauri-apps/api/event'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { useRoute } from 'vue-router'

import brandIcon from './assets/macro-studio-icon.png'
import ConnectionDialog from './components/ConnectionDialog.vue'
import GlobalLogPanel from './components/GlobalLogPanel.vue'
import { useRuntimeStore } from './stores/runtime'

const runtime = useRuntimeStore()
const route = useRoute()
const connectionOpen = ref(false)
const pageTitle = computed(() => String(route.meta.title || 'Macro Studio'))
const isWindowMaximized = ref(false)
const desktopWindow = '__TAURI_INTERNALS__' in window ? getCurrentWindow() : null
let unlistenWindowResize: UnlistenFn | undefined

async function refreshWindowState() {
  if (desktopWindow) isWindowMaximized.value = await desktopWindow.isMaximized()
}

async function minimizeWindow() {
  await desktopWindow?.minimize()
}

async function toggleMaximizeWindow() {
  if (!desktopWindow) return
  await desktopWindow.toggleMaximize()
  await refreshWindowState()
}

async function closeWindow() {
  await desktopWindow?.close()
}

function handleTitlebarDoubleClick(event: MouseEvent) {
  if ((event.target as HTMLElement).closest('button, a, input, select')) return
  void toggleMaximizeWindow()
}

onMounted(async () => {
  runtime.initialize()
  if (!desktopWindow) return
  await refreshWindowState()
  unlistenWindowResize = await desktopWindow.onResized(refreshWindowState)
})

onBeforeUnmount(() => {
  unlistenWindowResize?.()
  runtime.dispose()
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-mark" title="Macro Studio"><img :src="brandIcon" alt="" /></div>
      <nav aria-label="主导航">
        <RouterLink class="nav-button" exact-active-class="active" to="/" title="运行中心">
          <Activity :size="20" />
          <span>运行</span>
        </RouterLink>
        <RouterLink class="nav-button" exact-active-class="active" to="/playlists" title="队列管理">
          <ListMusic :size="20" />
          <span>队列</span>
        </RouterLink>
        <RouterLink class="nav-button" exact-active-class="active" to="/workflows" title="工作流">
          <Workflow :size="20" />
          <span>工作流</span>
        </RouterLink>
        <RouterLink class="nav-button" exact-active-class="active" to="/targets" title="目标库">
          <ScanSearch :size="20" />
          <span>目标</span>
        </RouterLink>
        <RouterLink class="nav-button" exact-active-class="active" to="/stage" title="剧组站">
          <Clapperboard :size="20" />
          <span>剧组</span>
        </RouterLink>
      </nav>
      <RouterLink class="nav-button settings-button" exact-active-class="active" to="/settings" title="目标程序设置">
        <Settings :size="20" />
        <span>设置</span>
      </RouterLink>
    </aside>

    <section class="workspace">
      <header class="topbar" data-tauri-drag-region @dblclick="handleTitlebarDoubleClick">
        <div class="titlebar-identity" data-tauri-drag-region>
          <h1>Macro Studio</h1>
          <span class="topbar-separator" />
          <p>{{ pageTitle }}</p>
        </div>
        <div class="topbar-actions">
          <button class="connection-chip" :class="runtime.phase" type="button" @click="connectionOpen = true">
            <Wifi v-if="runtime.isConnected" :size="16" />
            <WifiOff v-else :size="16" />
            <span>{{ runtime.isConnected ? '本地服务已连接' : runtime.phase === 'connecting' ? '正在连接' : '本地服务未连接' }}</span>
            <code v-if="runtime.connection">{{ runtime.connection.port }}</code>
          </button>
          <div class="window-controls" aria-label="窗口控制">
            <button type="button" title="最小化" aria-label="最小化" @click="minimizeWindow">
              <Minus :size="16" :stroke-width="1.8" />
            </button>
            <button type="button" :title="isWindowMaximized ? '还原' : '最大化'" :aria-label="isWindowMaximized ? '还原' : '最大化'" @click="toggleMaximizeWindow">
              <Copy v-if="isWindowMaximized" :size="13" :stroke-width="1.7" />
              <Square v-else :size="12" :stroke-width="1.7" />
            </button>
            <button class="close-window" type="button" title="关闭" aria-label="关闭" @click="closeWindow">
              <X :size="17" :stroke-width="1.7" />
            </button>
          </div>
        </div>
      </header>

      <Transition name="banner-slide">
        <div v-if="runtime.error && runtime.phase !== 'connected'" class="error-banner">
          <Cable :size="17" />
          <span>{{ runtime.error }}</span>
          <button type="button" @click="connectionOpen = true">重新连接</button>
        </div>
      </Transition>

      <div class="route-stage">
        <RouterView v-slot="{ Component, route: currentRoute }">
          <Transition name="page-shift" mode="out-in">
            <KeepAlive>
              <component :is="Component" :key="currentRoute.name" />
            </KeepAlive>
          </Transition>
        </RouterView>
      </div>
      <GlobalLogPanel />

    </section>

    <ConnectionDialog :open="connectionOpen" @close="connectionOpen = false" />
  </div>
</template>
