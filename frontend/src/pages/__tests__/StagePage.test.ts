import { reactive } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const runtime = reactive({
  isConnected: false,
  stage: {
    config: {
      base_url: 'http://hapi.hi.163.com/nshm/action-station/work/list/search',
      role_id: '1',
      user_id: '2',
      skey: 'secret',
      sort: 'hot',
      page_size: '18',
      contents: '',
      sub_types: '',
      actor_count_contents: '',
      work_filter: 'single',
    },
    keyword: '问爱',
  },
  stageWorks: [
    {
      work_id: 7,
      name: '问爱',
      summary: '测试作品简介',
      designer_name: '期迷',
      hot: 99,
      like_count: 8,
      collect_count: 12,
      cover_url: '',
      category_label: '单人',
      work_type: 1,
      sub_type: 1,
      actor_count: 1,
      duration_seconds: 30,
    },
  ],
  stageCapture: null,
  stageDiagnostics: {
    status: 'completed',
    message: '诊断完成',
    summary: {
      cache_files_seen: 12,
      cache_hits: 3,
      binary_hits: 2,
      method_candidates: 4,
      action_play_logs: 1,
      qrcode_work_logs: 1,
      voice_playback_logs: 0,
    },
    notes: ['发现桥接候选'],
    report: 'Macro Studio 剧组诊断报告',
    started_at: 1,
    finished_at: 2,
  },
  stageSearching: false,
  stageSaving: false,
  playlistSaving: false,
  playlists: {
    active_song_group: '古风',
    song_groups: [{ name: '古风', songs: [], step_preset: '播放流程' }],
  },
  presets: [],
  searchStage: vi.fn(),
  saveStage: vi.fn(),
  parseStageRequest: vi.fn(),
  startStageCapture: vi.fn(),
  refreshStageCapture: vi.fn(),
  startStageDiagnostics: vi.fn(),
  refreshStageDiagnostics: vi.fn(async () => runtime.stageDiagnostics),
  loadStageCover: vi.fn(),
  savePlaylists: vi.fn(async (document) => document),
})

vi.mock('../../stores/runtime', () => ({
  useRuntimeStore: () => runtime,
}))

import StagePage from '../StagePage.vue'

describe('StagePage', () => {
  beforeEach(() => {
    runtime.savePlaylists.mockClear()
  })

  it('renders work metadata and adds the selected result to a queue', async () => {
    const wrapper = mount(StagePage, { attachTo: document.body })

    expect(wrapper.text()).toContain('问爱')
    expect(wrapper.text()).toContain('期迷')
    expect(wrapper.text()).toContain('00:30')
    expect(wrapper.text()).toContain('测试作品简介')

    await wrapper.get('.stage-work-card').trigger('click')
    await wrapper.get('.stage-action-bar .button.primary').trigger('click')

    expect(runtime.savePlaylists).toHaveBeenCalledOnce()
    const saved = runtime.savePlaylists.mock.calls[0][0]
    expect(saved.song_groups[0].songs[0]).toMatchObject({
      title: '问爱',
      keyword: '问爱',
      duration_seconds: 30,
      buffer_seconds: 5,
    })
    wrapper.unmount()
  })

  it('opens the asynchronous diagnostics report panel', async () => {
    const wrapper = mount(StagePage, { attachTo: document.body })

    await wrapper.get('button[title="高级诊断"]').trigger('click')

    expect(wrapper.get('.stage-diagnostics-dialog').text()).toContain('诊断完成')
    expect(wrapper.get('.stage-diagnostics-dialog').text()).toContain('发现桥接候选')
    expect(wrapper.get('.stage-diagnostics-report').text()).toContain('Macro Studio 剧组诊断报告')
    expect(runtime.refreshStageDiagnostics).toHaveBeenCalled()
    wrapper.unmount()
  })
})