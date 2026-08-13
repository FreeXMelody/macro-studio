<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { Check, ChevronDown, Search } from '@lucide/vue'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    options: SelectOption[]
    label: string
    disabled?: boolean
    placeholder?: string
    searchable?: boolean
    searchPlaceholder?: string
  }>(),
  {
    disabled: false,
    placeholder: '请选择',
    searchable: false,
    searchPlaceholder: '搜索选项',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
}>()

const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const menu = ref<HTMLElement | null>(null)
const optionsPanel = ref<HTMLElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const query = ref('')
const open = ref(false)
const activeIndex = ref(-1)
const placement = ref<'top' | 'bottom'>('bottom')
const menuStyle = ref<CSSProperties>({})
const listboxId = `app-select-${useId()}`
let menuAnimations: Animation[] = []

const selected = computed(() => props.options.find((option) => option.value === props.modelValue) ?? null)
const filteredOptions = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  if (!needle) return props.options
  return props.options.filter((option) => `${option.label} ${option.value}`.toLocaleLowerCase().includes(needle))
})

watch(query, () => {
  activeIndex.value = filteredOptions.value.findIndex((option) => !option.disabled)
  void nextTick(syncMenuPosition)
})

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('scroll', syncMenuPosition, true)
  window.addEventListener('resize', syncMenuPosition)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('scroll', syncMenuPosition, true)
  window.removeEventListener('resize', syncMenuPosition)
  clearMenuAnimations()
})

function onDocumentPointerDown(event: PointerEvent) {
  const target = event.target as Node
  if (root.value && !root.value.contains(target) && !menu.value?.contains(target)) close()
}

function syncMenuPosition() {
  if (!open.value || !trigger.value) return
  const rect = trigger.value.getBoundingClientRect()
  const viewportPadding = 8
  const gap = 6
  const desiredHeight = Math.min(menu.value?.scrollHeight || 240, 240)
  const availableBelow = window.innerHeight - rect.bottom - gap - viewportPadding
  const availableAbove = rect.top - gap - viewportPadding
  const opensUpward = availableBelow < Math.min(180, desiredHeight) && availableAbove > availableBelow
  const availableHeight = Math.max(96, opensUpward ? availableAbove : availableBelow)
  const maxHeight = Math.min(240, availableHeight)
  const width = Math.min(rect.width, window.innerWidth - viewportPadding * 2)
  const left = Math.max(viewportPadding, Math.min(rect.left, window.innerWidth - width - viewportPadding))

  placement.value = opensUpward ? 'top' : 'bottom'
  menuStyle.value = {
    left: `${left}px`,
    top: opensUpward
      ? `${Math.max(viewportPadding, rect.top - Math.min(desiredHeight, maxHeight) - gap)}px`
      : `${rect.bottom + gap}px`,
    width: `${width}px`,
    maxHeight: `${maxHeight}px`,
  }

  if (menu.value) {
    Object.assign(menu.value.style, menuStyle.value)
  }
}

function clearMenuAnimations() {
  menuAnimations.forEach((animation) => animation.cancel())
  menuAnimations = []
}

function animateMenuEnter(element: Element, done: () => void) {
  const popup = element as HTMLElement
  syncMenuPosition()
  clearMenuAnimations()

  if (typeof popup.animate !== 'function') {
    done()
    return
  }

  const offset = placement.value === 'top' ? 6 : -6
  const popupAnimation = popup.animate(
    [
      { opacity: 0, transform: `translateY(${offset}px) scale(0.985)` },
      { opacity: 1, transform: 'translateY(0) scale(1)' },
    ],
    {
      duration: 180,
      easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
      fill: 'both',
    },
  )
  menuAnimations.push(popupAnimation)

  popup.querySelectorAll<HTMLElement>('.app-select-option').forEach((option, index) => {
    const optionAnimation = option.animate(
      [
        { opacity: 0, transform: `translateY(${placement.value === 'top' ? 5 : -5}px)` },
        { opacity: 1, transform: 'translateY(0)' },
      ],
      {
        duration: 140,
        delay: 18 + Math.min(index, 6) * 12,
        easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
        fill: 'both',
      },
    )
    menuAnimations.push(optionAnimation)
  })

  popupAnimation.finished
    .then(() => {
      clearMenuAnimations()
      done()
    })
    .catch(done)
}

function animateMenuLeave(element: Element, done: () => void) {
  const popup = element as HTMLElement
  clearMenuAnimations()

  if (typeof popup.animate !== 'function') {
    done()
    return
  }

  const offset = placement.value === 'top' ? 7 : -7
  const animation = popup.animate(
    [
      { opacity: 1, transform: 'translateY(0) scale(1)' },
      { opacity: 0, transform: `translateY(${offset}px) scale(0.97)` },
    ],
    {
      duration: 190,
      easing: 'cubic-bezier(0.4, 0, 1, 1)',
      fill: 'both',
    },
  )
  menuAnimations.push(animation)
  animation.finished
    .then(() => {
      clearMenuAnimations()
      done()
    })
    .catch(done)
}

function toggle() {
  if (props.disabled) return
  if (open.value) {
    close()
    return
  }
  activeIndex.value = Math.max(
    0,
    filteredOptions.value.findIndex((option) => option.value === props.modelValue && !option.disabled),
  )
  open.value = true
  void nextTick(() => {
    syncMenuPosition()
    const activeOption = menu.value?.querySelector<HTMLElement>(
      '.app-select-option.selected, .app-select-option.active',
    )
    const scroller = optionsPanel.value
    if (scroller && activeOption) {
      const optionTop = activeOption.offsetTop
      const optionBottom = optionTop + activeOption.offsetHeight
      if (optionTop < scroller.scrollTop) scroller.scrollTop = optionTop
      else if (optionBottom > scroller.scrollTop + scroller.clientHeight) {
        scroller.scrollTop = optionBottom - scroller.clientHeight
      }
    }
    if (props.searchable) searchInput.value?.focus()
  })
}

function close(restoreFocus = false) {
  open.value = false
  query.value = ''
  if (restoreFocus) void nextTick(() => trigger.value?.focus())
}

function choose(option: SelectOption) {
  if (option.disabled) return
  emit('update:modelValue', option.value)
  emit('change', option.value)
  close(true)
}

function moveActive(direction: number) {
  if (!open.value) {
    toggle()
    return
  }
  if (!filteredOptions.value.length) return
  let next = activeIndex.value
  for (let count = 0; count < filteredOptions.value.length; count += 1) {
    next = (next + direction + filteredOptions.value.length) % filteredOptions.value.length
    if (!filteredOptions.value[next].disabled) {
      activeIndex.value = next
      break
    }
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    moveActive(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    moveActive(-1)
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (!open.value) toggle()
    else if (activeIndex.value >= 0) choose(filteredOptions.value[activeIndex.value])
  } else if (event.key === 'Escape') {
    event.preventDefault()
    close(true)
  } else if (event.key === 'Tab') {
    close()
  }
}
function onSearchKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    moveActive(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    moveActive(-1)
  } else if (event.key === 'Enter' && activeIndex.value >= 0) {
    event.preventDefault()
    choose(filteredOptions.value[activeIndex.value])
  } else if (event.key === 'Escape') {
    event.preventDefault()
    close(true)
  }
}
</script>

<template>
  <div ref="root" class="app-select" :class="{ open, disabled }">
    <button
      ref="trigger"
      class="app-select-trigger"
      type="button"
      role="combobox"
      :aria-label="label"
      :aria-expanded="open"
      :aria-controls="listboxId"
      aria-haspopup="listbox"
      :disabled="disabled"
      @click="toggle"
      @keydown="onKeydown"
    >
      <span :class="{ placeholder: !selected }">{{ selected?.label || placeholder }}</span>
      <ChevronDown class="app-select-chevron" :size="15" />
    </button>
    <Teleport to="body">
      <Transition :css="false" @enter="animateMenuEnter" @leave="animateMenuLeave">
        <div
          v-if="open"
          :id="listboxId"
          ref="menu"
          class="app-select-menu"
          :class="{ searchable }"
          :data-placement="placement"
          :style="menuStyle"
          role="listbox"
          :aria-label="label"
        >
          <label v-if="searchable" class="app-select-search">
            <Search :size="14" />
            <input ref="searchInput" v-model="query" :placeholder="searchPlaceholder" @keydown="onSearchKeydown" />
          </label>
          <div ref="optionsPanel" class="app-select-options">
            <button
              v-for="(option, index) in filteredOptions"
              :key="option.value"
              class="app-select-option"
              :class="{ selected: option.value === modelValue, active: index === activeIndex }"
              type="button"
              role="option"
              :aria-selected="option.value === modelValue"
              :disabled="option.disabled"
              @pointerenter="activeIndex = index"
              @click="choose(option)"
            >
              <span>{{ option.label }}</span>
              <Check v-if="option.value === modelValue" :size="14" />
            </button>
            <div v-if="!filteredOptions.length" class="app-select-empty">没有匹配项</div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
