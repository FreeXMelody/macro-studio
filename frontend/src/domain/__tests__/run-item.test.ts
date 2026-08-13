import { describe, expect, it } from 'vitest'

import { playlistRunItem } from '../run-item'

describe('run item adapters', () => {
  it('maps a playlist song into a generic run item without mutating it', () => {
    const song = {
      title: 'Demo',
      keyword: 'search text',
      duration_seconds: 12,
      buffer_seconds: 3,
      enabled: true,
      step_preset: '',
    }

    const item = playlistRunItem(song, 'Queue', 2)

    expect(item.id).toBe('playlist:Queue:2')
    expect(item.name).toBe('Demo')
    expect(item.workflow).toBe('继承分组')
    expect(item.durationSeconds + item.bufferSeconds).toBe(15)
    expect(item.source).toBe(song)
  })
})