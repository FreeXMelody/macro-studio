import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'

import AppSelect from '../AppSelect.vue'

const options = [
  { value: '', label: '当前动作序列' },
  { value: 'stage', label: '逆水寒剧组' },
]

describe('AppSelect', () => {
  it('opens and emits a selected value', async () => {
    const wrapper = mount(AppSelect, {
      props: { modelValue: '', options, label: '动作预设' },
      attachTo: document.body,
    })
    await wrapper.get('.app-select-trigger').trigger('click')
    expect(document.body.querySelector('.app-select-menu')).not.toBeNull()
    document.body.querySelectorAll<HTMLButtonElement>('.app-select-option')[1].click()
    await nextTick()
    expect(wrapper.emitted('update:modelValue')).toEqual([['stage']])
    expect(document.body.querySelector('.app-select-menu')).toBeNull()
    wrapper.unmount()
  })

  it('filters searchable options and selects the visible result', async () => {
    const wrapper = mount(AppSelect, {
      props: { modelValue: '', options, label: '动作预设', searchable: true },
      attachTo: document.body,
    })
    await wrapper.get('.app-select-trigger').trigger('click')
    const search = document.body.querySelector<HTMLInputElement>('.app-select-search input')
    expect(search).not.toBeNull()
    search!.value = '逆水寒'
    search!.dispatchEvent(new Event('input'))
    await nextTick()
    const visible = document.body.querySelectorAll<HTMLButtonElement>('.app-select-option')
    expect(visible).toHaveLength(1)
    expect(visible[0].textContent).toContain('逆水寒剧组')
    visible[0].click()
    await nextTick()
    expect(wrapper.emitted('update:modelValue')).toEqual([['stage']])
    wrapper.unmount()
  })
  it('supports keyboard selection', async () => {
    const wrapper = mount(AppSelect, {
      props: { modelValue: '', options, label: '动作预设' },
      attachTo: document.body,
    })
    const trigger = wrapper.get('.app-select-trigger')
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    await trigger.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toEqual([['stage']])
    wrapper.unmount()
  })
})
