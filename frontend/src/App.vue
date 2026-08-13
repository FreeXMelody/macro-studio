<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Activity, Cable, ListMusic, ScanSearch, Settings, Wifi, WifiOff, Workflow } from '@lucide/vue'
import { useRoute } from 'vue-router'

import ConnectionDialog from './components/ConnectionDialog.vue'
import GlobalLogPanel from './components/GlobalLogPanel.vue'
import { useRuntimeStore } from './stores/runtime'

const runtime = useRuntimeStore()
const route = useRoute()
const connectionOpen = ref(false)
const pageTitle = computed(() => String(route.meta.title || 'Macro Studio'))

onMounted(() => runtime.initialize())
onBeforeUnmount(() => runtime.dispose())
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-mark" title="Macro Studio">M</div>
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
      </nav>
      <RouterLink class="nav-button settings-button" exact-active-class="active" to="/settings" title="目标程序设置">
        <Settings :size="20" />
        <span>设置</span>
      </RouterLink>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div>
          <h1>Macro Studio</h1>
          <span class="topbar-separator" />
          <p>{{ pageTitle }}</p>
        </div>
        <button class="connection-chip" :class="runtime.phase" type="button" @click="connectionOpen = true">
          <Wifi v-if="runtime.isConnected" :size="16" />
          <WifiOff v-else :size="16" />
          <span>{{ runtime.isConnected ? '本地服务已连接' : runtime.phase === 'connecting' ? '正在连接' : '本地服务未连接' }}</span>
          <code v-if="runtime.connection">{{ runtime.connection.port }}</code>
        </button>
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
