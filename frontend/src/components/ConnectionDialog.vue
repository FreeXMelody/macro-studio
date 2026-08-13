<script setup lang="ts">
import { ref, watch } from 'vue'
import { Cable, LoaderCircle, X } from '@lucide/vue'

import { useRuntimeStore } from '../stores/runtime'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const runtime = useRuntimeStore()
const host = ref('127.0.0.1')
const port = ref<number | null>(null)
const token = ref('')

watch(
  () => props.open,
  (open) => {
    if (!open) return
    host.value = runtime.connection?.host || '127.0.0.1'
    port.value = runtime.connection?.port || null
    token.value = runtime.connection?.token || ''
  },
)

async function submit() {
  if (!host.value.trim() || !port.value || !token.value) return
  await runtime.connect({
    host: host.value.trim(),
    port: Number(port.value),
    token: token.value,
    api_version: '',
  })
  if (runtime.phase === 'connected') emit('close')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-motion">
      <div v-if="open" class="dialog-backdrop" @mousedown.self="emit('close')">
      <section class="connection-dialog" role="dialog" aria-modal="true" aria-labelledby="connection-title">
        <header class="dialog-header">
          <div class="dialog-title-wrap">
            <span class="dialog-icon"><Cable :size="18" /></span>
            <div>
              <h2 id="connection-title">本地服务连接</h2>
              <p>{{ runtime.connection ? `${runtime.connection.host}:${runtime.connection.port}` : '未连接' }}</p>
            </div>
          </div>
          <button class="icon-button" type="button" title="关闭" @click="emit('close')">
            <X :size="18" />
          </button>
        </header>

        <form class="connection-form" @submit.prevent="submit">
          <label>
            <span>主机</span>
            <input v-model="host" autocomplete="off" spellcheck="false" />
          </label>
          <label>
            <span>端口</span>
            <input v-model.number="port" type="number" min="1" max="65535" inputmode="numeric" />
          </label>
          <label class="full-field">
            <span>会话令牌</span>
            <input v-model="token" type="password" autocomplete="off" spellcheck="false" />
          </label>

          <p v-if="runtime.error" class="form-error">{{ runtime.error }}</p>

          <footer class="dialog-actions">
            <button class="button secondary" type="button" @click="emit('close')">取消</button>
            <button class="button primary" type="submit" :disabled="runtime.phase === 'connecting'">
              <LoaderCircle v-if="runtime.phase === 'connecting'" class="spin" :size="16" />
              <Cable v-else :size="16" />
              连接
            </button>
          </footer>
        </form>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
