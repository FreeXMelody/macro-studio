<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  AlertTriangle,
  Check,
  Copy,
  FolderInput,
  FolderPlus,
  GripVertical,
  ListMusic,
  MoveRight,
  Music2,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  X,
} from '@lucide/vue'

import AppSelect from '../components/AppSelect.vue'
import { clonePlaylist, emptySong, formatDuration, parseDuration, reorderSongs, uniqueGroupName } from '../domain/playlist'
import { useRuntimeStore } from '../stores/runtime'
import type { PlaylistDocumentDto, SongDto } from '../types/api'

type NameDialogMode = 'add' | 'rename'
type ConfirmTarget = { kind: 'group' } | { kind: 'song'; index: number }

const runtime = useRuntimeStore()
const draft = ref<PlaylistDocumentDto | null>(null)
const selectedGroupName = ref('')
const dirty = ref(false)
const localError = ref('')
const notice = ref('')
const nameDialogOpen = ref(false)
const nameDialogMode = ref<NameDialogMode>('add')
const nameInput = ref('')
const songDialogOpen = ref(false)
const editingSongIndex = ref<number | null>(null)
const songForm = ref<SongDto>(emptySong())
const durationInput = ref('00:00')
const confirmTarget = ref<ConfirmTarget | null>(null)
const moveSongIndex = ref<number | null>(null)
const moveTargetName = ref('')
const draggedIndex = ref<number | null>(null)
const dropIndex = ref<number | null>(null)
const dragPoint = ref({ x: 0, y: 0 })

const selectedGroup = computed(() => {
  if (!draft.value) return null
  return draft.value.song_groups.find((group) => group.name === selectedGroupName.value) ?? draft.value.song_groups[0] ?? null
})
const songs = computed(() => selectedGroup.value?.songs ?? [])
const presetNames = computed(() => runtime.presets.map((preset) => preset.name))
const groupPresetOptions = computed(() => [
  { value: '', label: '使用当前动作序列' },
  ...presetNames.value.map((name) => ({ value: name, label: name })),
])
const songPresetOptions = computed(() => [
  { value: '', label: '继承歌曲组 / 当前序列' },
  ...presetNames.value.map((name) => ({ value: name, label: name })),
])
const moveGroupOptions = computed(() => otherGroups.value.map((group) => ({ value: group.name, label: group.name })))
const draggedSongTitle = computed(() =>
  draggedIndex.value === null ? '' : songs.value[draggedIndex.value]?.title || '',
)
const dragGhostStyle = computed(() => ({
  left: Math.max(8, Math.min(window.innerWidth - 224, dragPoint.value.x + 14)) + 'px',
  top: Math.max(8, Math.min(window.innerHeight - 42, dragPoint.value.y + 12)) + 'px',
}))
const enabledCount = computed(() => songs.value.filter((song) => song.enabled).length)
const totalDuration = computed(() =>
  songs.value.reduce((total, song) => total + song.duration_seconds + song.buffer_seconds, 0),
)
const canSave = computed(() => runtime.isConnected && dirty.value && !runtime.playlistSaving)
const otherGroups = computed(() =>
  draft.value?.song_groups.filter((group) => group.name !== selectedGroupName.value) ?? [],
)

watch(
  () => runtime.playlists,
  (document) => {
    if (!document || dirty.value) return
    loadDraft(document)
  },
  { immediate: true },
)

function loadDraft(document: PlaylistDocumentDto) {
  draft.value = clonePlaylist(document)
  const preferred = document.song_groups.some((group) => group.name === document.active_song_group)
    ? document.active_song_group
    : document.song_groups[0]?.name || ''
  selectedGroupName.value = preferred
  dirty.value = false
  localError.value = ''
}

function selectGroup(name: string) {
  selectedGroupName.value = name
  if (draft.value) draft.value.active_song_group = name
}

function touch() {
  dirty.value = true
  localError.value = ''
  notice.value = ''
  if (draft.value) draft.value.active_song_group = selectedGroupName.value
}

function openAddGroup() {
  nameDialogMode.value = 'add'
  nameInput.value = uniqueGroupName(draft.value?.song_groups ?? [])
  nameDialogOpen.value = true
}

function openRenameGroup() {
  if (!selectedGroup.value) return
  nameDialogMode.value = 'rename'
  nameInput.value = selectedGroup.value.name
  nameDialogOpen.value = true
}

function submitGroupName() {
  if (!draft.value || !selectedGroup.value) return
  const name = nameInput.value.trim()
  if (!name) {
    localError.value = '歌曲组名称不能为空'
    return
  }
  if (name === '全部') {
    localError.value = '“全部”是系统保留名称'
    return
  }
  const duplicate = draft.value.song_groups.some(
    (group) => group.name === name && (nameDialogMode.value === 'add' || group !== selectedGroup.value),
  )
  if (duplicate) {
    localError.value = '已经有同名歌曲组'
    return
  }
  if (nameDialogMode.value === 'add') {
    draft.value.song_groups.push({ name, songs: [], step_preset: '' })
  } else {
    selectedGroup.value.name = name
  }
  selectedGroupName.value = name
  nameDialogOpen.value = false
  touch()
}

function requestDeleteGroup() {
  if (!draft.value || !selectedGroup.value) return
  if (draft.value.song_groups.length <= 1) {
    localError.value = '至少需要保留一个歌曲组'
    return
  }
  confirmTarget.value = { kind: 'group' }
}

function openSong(index: number | null) {
  editingSongIndex.value = index
  songForm.value = index === null ? emptySong() : { ...songs.value[index] }
  durationInput.value = formatDuration(songForm.value.duration_seconds)
  songDialogOpen.value = true
  localError.value = ''
}

function submitSong() {
  if (!selectedGroup.value) return
  const title = songForm.value.title.trim()
  const keyword = songForm.value.keyword.trim() || title
  const duration = parseDuration(durationInput.value)
  if (!title) {
    localError.value = '歌曲名称不能为空'
    return
  }
  if (duration === null) {
    localError.value = '时长请填写秒数或 mm:ss，例如 90 或 01:30'
    return
  }
  const nextSong: SongDto = {
    ...songForm.value,
    title,
    keyword,
    duration_seconds: duration,
    buffer_seconds: Math.max(0, Math.floor(Number(songForm.value.buffer_seconds) || 0)),
  }
  if (editingSongIndex.value === null) {
    selectedGroup.value.songs.push(nextSong)
  } else {
    selectedGroup.value.songs[editingSongIndex.value] = nextSong
  }
  songDialogOpen.value = false
  touch()
}

function duplicateSong(index: number) {
  if (!selectedGroup.value) return
  const source = selectedGroup.value.songs[index]
  selectedGroup.value.songs.splice(index + 1, 0, {
    ...source,
    title: source.title + ' 副本',
  })
  touch()
}

function requestDeleteSong(index: number) {
  confirmTarget.value = { kind: 'song', index }
}

function confirmDelete() {
  if (!draft.value || !selectedGroup.value || !confirmTarget.value) return
  if (confirmTarget.value.kind === 'song') {
    selectedGroup.value.songs.splice(confirmTarget.value.index, 1)
  } else {
    const index = draft.value.song_groups.indexOf(selectedGroup.value)
    draft.value.song_groups.splice(index, 1)
    selectedGroupName.value = draft.value.song_groups[Math.max(0, index - 1)].name
  }
  confirmTarget.value = null
  touch()
}

function openMoveSong(index: number) {
  if (!otherGroups.value.length) {
    localError.value = '请先新建另一个歌曲组'
    return
  }
  moveSongIndex.value = index
  moveTargetName.value = otherGroups.value[0].name
}

function confirmMoveSong() {
  if (!draft.value || !selectedGroup.value || moveSongIndex.value === null) return
  const target = draft.value.song_groups.find((group) => group.name === moveTargetName.value)
  if (!target) return
  const [song] = selectedGroup.value.songs.splice(moveSongIndex.value, 1)
  target.songs.push(song)
  moveSongIndex.value = null
  touch()
}

function setGroupPreset(value: string) {
  if (!selectedGroup.value || selectedGroup.value.step_preset === value) return
  selectedGroup.value.step_preset = value
  touch()
}

function setEnabled(index: number, event: Event) {
  if (!selectedGroup.value) return
  selectedGroup.value.songs[index].enabled = (event.target as HTMLInputElement).checked
  touch()
}

function beginPointerDrag(index: number, event: PointerEvent) {
  if (event.button !== 0) return
  event.preventDefault()
  draggedIndex.value = index
  dropIndex.value = index
  dragPoint.value = { x: event.clientX, y: event.clientY }
  document.body.classList.add('playlist-is-dragging')
  document.addEventListener('pointermove', onPointerDrag)
  document.addEventListener('pointerup', finishPointerDrag, { once: true })
  document.addEventListener('pointercancel', cancelPointerDrag, { once: true })
}

function onPointerDrag(event: PointerEvent) {
  if (draggedIndex.value === null) return
  dragPoint.value = { x: event.clientX, y: event.clientY }
  const row = document
    .elementsFromPoint(event.clientX, event.clientY)
    .map((element) => element.closest<HTMLTableRowElement>('tr[data-song-index]'))
    .find((element): element is HTMLTableRowElement => Boolean(element))
  if (!row) return
  const index = Number(row.dataset.songIndex)
  if (Number.isInteger(index)) dropIndex.value = index
}

function finishPointerDrag() {
  const from = draggedIndex.value
  const to = dropIndex.value
  clearPointerDrag()
  if (selectedGroup.value && from !== null && to !== null && reorderSongs(selectedGroup.value, from, to)) {
    touch()
  }
}

function cancelPointerDrag() {
  clearPointerDrag()
}

function clearPointerDrag() {
  document.body.classList.remove('playlist-is-dragging')
  document.removeEventListener('pointermove', onPointerDrag)
  document.removeEventListener('pointerup', finishPointerDrag)
  document.removeEventListener('pointercancel', cancelPointerDrag)
  draggedIndex.value = null
  dropIndex.value = null
}

function moveSongByKeyboard(index: number, direction: number) {
  if (!selectedGroup.value) return
  const target = index + direction
  if (reorderSongs(selectedGroup.value, index, target)) touch()
}

onBeforeUnmount(cancelPointerDrag)

function resetDraft() {
  if (runtime.playlists) loadDraft(runtime.playlists)
}

async function save() {
  if (!draft.value || !canSave.value) return
  localError.value = ''
  try {
    const saved = await runtime.savePlaylists(clonePlaylist(draft.value))
    loadDraft(saved)
    notice.value = '歌单已保存'
    window.setTimeout(() => {
      if (notice.value === '歌单已保存') notice.value = ''
    }, 2200)
  } catch (error) {
    localError.value = error instanceof Error ? error.message : '保存歌单失败'
  }
}
</script>

<template>
  <main class="playlist-page">
    <template v-if="draft && selectedGroup">
      <aside class="group-rail">
        <header class="group-rail-header">
          <div>
            <p class="section-kicker">LIBRARY</p>
            <h2>歌曲组</h2>
          </div>
          <button class="icon-button" type="button" title="新建歌曲组" @click="openAddGroup">
            <FolderPlus :size="17" />
          </button>
        </header>

        <div class="group-list" role="listbox" aria-label="歌曲组">
          <button
            v-for="group in draft.song_groups"
            :key="group.name"
            class="group-item"
            :class="{ active: group.name === selectedGroupName }"
            type="button"
            role="option"
            :aria-selected="group.name === selectedGroupName"
            @click="selectGroup(group.name)"
          >
            <ListMusic :size="16" />
            <span>{{ group.name }}</span>
            <small>{{ group.songs.length }}</small>
          </button>
        </div>

        <div class="group-rail-actions">
          <button class="button secondary compact" type="button" @click="openRenameGroup">
            <Pencil :size="14" />重命名
          </button>
          <button class="icon-button danger-icon" type="button" title="删除歌曲组" @click="requestDeleteGroup">
            <Trash2 :size="15" />
          </button>
        </div>
      </aside>

      <section class="playlist-editor">
        <header class="playlist-toolbar">
          <div class="playlist-heading">
            <div>
              <h2>{{ selectedGroup.name }}</h2>
              <p>{{ songs.length }} 首歌曲 · {{ enabledCount }} 首启用 · 预计 {{ formatDuration(totalDuration) }}</p>
            </div>
            <div class="inline-field">
              <span>组动作预设</span>
              <AppSelect
                :model-value="selectedGroup.step_preset"
                :options="groupPresetOptions"
                label="组动作预设"
                @update:model-value="setGroupPreset"
              />
            </div>
          </div>
          <div class="playlist-actions">
            <Transition name="status-swap" mode="out-in">
              <span v-if="notice" key="notice" class="save-notice"><Check :size="14" />{{ notice }}</span>
              <span v-else-if="dirty" key="dirty" class="dirty-indicator">有未保存更改</span>
            </Transition>
            <button class="button secondary" type="button" :disabled="!dirty || runtime.playlistSaving" @click="resetDraft">
              <RotateCcw :size="15" />撤销更改
            </button>
            <button class="button primary" type="button" :disabled="!canSave" @click="save">
              <Save :size="15" :class="{ spin: runtime.playlistSaving }" />
              {{ runtime.playlistSaving ? '保存中' : '保存歌单' }}
            </button>
            <button class="button secondary add-song-button" type="button" @click="openSong(null)">
              <Plus :size="16" />添加歌曲
            </button>
          </div>
        </header>

        <Transition name="banner-slide">
          <div v-if="localError" class="playlist-error">
            <AlertTriangle :size="15" />
            <span>{{ localError }}</span>
            <button type="button" title="关闭" @click="localError = ''"><X :size="14" /></button>
          </div>
        </Transition>

        <div class="playlist-table-wrap">
          <table class="playlist-table">
            <thead>
              <tr>
                <th aria-label="排序" />
                <th>歌曲</th>
                <th>搜索词</th>
                <th>动作预设</th>
                <th>时长</th>
                <th>状态</th>
                <th aria-label="操作" />
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(song, index) in songs"
                :key="`${song.title}-${index}`"
                :data-song-index="index"
                :class="{
                  disabled: !song.enabled,
                  dragging: draggedIndex === index,
                  'drop-target': dropIndex === index && draggedIndex !== index,
                }"




              >
                <td class="drag-cell">
                  <button
                    class="drag-handle"
                    type="button"
                    :aria-label="'拖动排序：' + song.title"
                    title="拖动排序；方向键可微调"
                    @pointerdown="beginPointerDrag(index, $event)"
                    @keydown.up.prevent="moveSongByKeyboard(index, -1)"
                    @keydown.down.prevent="moveSongByKeyboard(index, 1)"
                  >
                    <GripVertical :size="16" />
                  </button>
                </td>
                <td>
                  <button class="song-title-button" type="button" @click="openSong(index)">
                    <span class="song-mini-icon"><Music2 :size="14" /></span>
                    <strong>{{ song.title }}</strong>
                  </button>
                </td>
                <td class="muted-cell">{{ song.keyword || song.title }}</td>
                <td>{{ song.step_preset || selectedGroup.step_preset || '当前动作序列' }}</td>
                <td><span class="duration-code">{{ formatDuration(song.duration_seconds) }}</span><small> +{{ song.buffer_seconds }}s</small></td>
                <td>
                  <label class="row-toggle" :title="song.enabled ? '已启用' : '已停用'">
                    <input type="checkbox" :checked="song.enabled" @change="setEnabled(index, $event)" />
                    <span />
                  </label>
                </td>
                <td>
                  <div class="row-actions">
                    <button class="icon-button small" type="button" title="编辑歌曲" @click="openSong(index)"><Pencil :size="14" /></button>
                    <button class="icon-button small" type="button" title="复制歌曲" @click="duplicateSong(index)"><Copy :size="14" /></button>
                    <button class="icon-button small" type="button" title="移动到其他歌曲组" @click="openMoveSong(index)"><MoveRight :size="14" /></button>
                    <button class="icon-button small danger-icon" type="button" title="删除歌曲" @click="requestDeleteSong(index)"><Trash2 :size="14" /></button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <div v-if="!songs.length" class="playlist-empty">
            <Music2 :size="28" />
            <strong>这个歌曲组还是空的</strong>
            <button class="button primary" type="button" @click="openSong(null)"><Plus :size="15" />添加第一首歌曲</button>
          </div>
        </div>
      </section>
    </template>

    <div v-else class="catalog-unavailable">
      <ListMusic :size="30" />
      <strong>{{ runtime.isConnected ? '正在读取歌单' : '连接本地服务后管理歌单' }}</strong>
      <span>歌单数据由本地 sidecar 读取并保存。</span>
    </div>

    <Teleport to="body">
      <Transition name="drag-ghost">
        <div v-if="draggedIndex !== null" class="playlist-drag-ghost" :style="dragGhostStyle">
          <GripVertical :size="15" />
          <span>{{ draggedSongTitle }}</span>
        </div>
      </Transition>
    </Teleport>

    <Transition name="dialog-motion">
      <div v-if="nameDialogOpen" class="dialog-backdrop" @mousedown.self="nameDialogOpen = false">
        <form class="connection-dialog compact-dialog" @submit.prevent="submitGroupName">
          <header class="dialog-header">
            <div class="dialog-title-wrap">
              <span class="dialog-icon"><FolderPlus :size="18" /></span>
              <div><h2>{{ nameDialogMode === 'add' ? '新建歌曲组' : '重命名歌曲组' }}</h2><p>歌曲可随时在分组之间移动</p></div>
            </div>
            <button class="icon-button small" type="button" title="关闭" @click="nameDialogOpen = false"><X :size="15" /></button>
          </header>
          <div class="playlist-form single-field-form">
            <label><span>名称</span><input v-model="nameInput" autofocus maxlength="40" /></label>
          </div>
          <footer class="dialog-actions playlist-dialog-actions">
            <button class="button secondary" type="button" @click="nameDialogOpen = false">取消</button>
            <button class="button primary" type="submit">确认</button>
          </footer>
        </form>
      </div>
    </Transition>

    <Transition name="dialog-motion">
      <div v-if="songDialogOpen" class="dialog-backdrop" @mousedown.self="songDialogOpen = false">
        <form class="connection-dialog song-dialog" @submit.prevent="submitSong">
          <header class="dialog-header">
            <div class="dialog-title-wrap">
              <span class="dialog-icon"><Music2 :size="18" /></span>
              <div><h2>{{ editingSongIndex === null ? '添加歌曲' : '编辑歌曲' }}</h2><p>搜索词为空时自动使用歌曲名称</p></div>
            </div>
            <button class="icon-button small" type="button" title="关闭" @click="songDialogOpen = false"><X :size="15" /></button>
          </header>
          <div class="playlist-form song-form-grid">
            <label><span>歌曲名称</span><input v-model="songForm.title" autofocus maxlength="80" /></label>
            <label><span>搜索词</span><input v-model="songForm.keyword" maxlength="120" placeholder="默认与歌曲名称相同" /></label>
            <label><span>作品时长</span><input v-model="durationInput" inputmode="numeric" placeholder="01:30" /></label>
            <label><span>结束后等待（秒）</span><input v-model.number="songForm.buffer_seconds" type="number" min="0" max="600" /></label>
            <div class="form-field wide-field">
              <span>动作预设</span>
              <AppSelect v-model="songForm.step_preset" :options="songPresetOptions" label="歌曲动作预设" />
            </div>
            <div class="queue-option wide-field">
              <div>
                <strong>加入播放队列</strong>
                <span>停用后保留歌曲，但运行时会自动跳过</span>
              </div>
              <label class="row-toggle" :title="songForm.enabled ? '已启用' : '已停用'">
                <input v-model="songForm.enabled" type="checkbox" />
                <span />
              </label>
            </div>
          </div>
          <footer class="dialog-actions playlist-dialog-actions">
            <button class="button secondary" type="button" @click="songDialogOpen = false">取消</button>
            <button class="button primary" type="submit">{{ editingSongIndex === null ? '添加' : '保存修改' }}</button>
          </footer>
        </form>
      </div>
    </Transition>

    <Transition name="dialog-motion">
      <div v-if="moveSongIndex !== null" class="dialog-backdrop" @mousedown.self="moveSongIndex = null">
        <form class="connection-dialog compact-dialog" @submit.prevent="confirmMoveSong">
          <header class="dialog-header">
            <div class="dialog-title-wrap">
              <span class="dialog-icon"><FolderInput :size="18" /></span>
              <div><h2>移动歌曲</h2><p>{{ songs[moveSongIndex]?.title }}</p></div>
            </div>
            <button class="icon-button small" type="button" title="关闭" @click="moveSongIndex = null"><X :size="15" /></button>
          </header>
          <div class="playlist-form single-field-form">
            <div class="form-field">
              <span>目标歌曲组</span>
              <AppSelect v-model="moveTargetName" :options="moveGroupOptions" label="目标歌曲组" />
            </div>
          </div>
          <footer class="dialog-actions playlist-dialog-actions">
            <button class="button secondary" type="button" @click="moveSongIndex = null">取消</button>
            <button class="button primary" type="submit">移动</button>
          </footer>
        </form>
      </div>
    </Transition>

    <Transition name="dialog-motion">
      <div v-if="confirmTarget" class="dialog-backdrop" @mousedown.self="confirmTarget = null">
        <section class="connection-dialog compact-dialog" role="alertdialog" aria-modal="true">
          <header class="dialog-header">
            <div class="dialog-title-wrap">
              <span class="dialog-icon warning"><AlertTriangle :size="18" /></span>
              <div><h2>确认删除</h2><p>这个操作会在保存歌单后生效</p></div>
            </div>
          </header>
          <div class="confirmation-body">
            <p v-if="confirmTarget.kind === 'group'">删除歌曲组“{{ selectedGroup?.name }}”以及其中 {{ songs.length }} 首歌曲？</p>
            <p v-else>删除歌曲“{{ songs[confirmTarget.index]?.title }}”？</p>
          </div>
          <footer class="dialog-actions confirmation-actions">
            <button class="button secondary" type="button" @click="confirmTarget = null">取消</button>
            <button class="button danger" type="button" @click="confirmDelete">删除</button>
          </footer>
        </section>
      </div>
    </Transition>
  </main>
</template>
