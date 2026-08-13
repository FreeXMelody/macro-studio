import { afterEach, describe, expect, it, vi } from 'vitest'

import { MacroStudioClient, parseRunnerEvent } from '../client'

const connection = {
  host: '127.0.0.1',
  port: 43210,
  token: 'unit-test-token',
  api_version: '0.1.0',
}

describe('MacroStudioClient', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('builds loopback HTTP and WebSocket endpoints', () => {
    const client = new MacroStudioClient(connection)
    expect(client.baseUrl).toBe('http://127.0.0.1:43210')
    expect(client.eventsUrl()).toBe('ws://127.0.0.1:43210/api/events?token=unit-test-token')
  })

  it('saves a playlist document with the session token', async () => {
    const document = {
      active_song_group: '古风',
      song_groups: [{ name: '古风', step_preset: '', songs: [] }],
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(document), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(new MacroStudioClient(connection).updatePlaylists(document)).resolves.toEqual(document)
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:43210/api/playlists',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify(document),
        headers: expect.objectContaining({ 'X-Macro-Studio-Token': 'unit-test-token' }),
      }),
    )
  })

  it('saves action presets through the typed endpoint', async () => {
    const presets = [
      {
        name: '播放流程',
        steps: [{
          name: '等待',
          kind: 'wait',
          target: '',
          value: '1',
          enabled: true,
          wait_after: '',
          failure_policy: 'stop' as const,
          failure_retries: 2,
          verify_target: '',
        }],
      },
    ]
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(presets), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(new MacroStudioClient(connection).updatePresets(presets)).resolves.toEqual(presets)
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:43210/api/presets',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify(presets),
      }),
    )
  })
})

describe('parseRunnerEvent', () => {
  it('accepts a transport event', () => {
    const event = parseRunnerEvent(
      JSON.stringify({ sequence: 1, timestamp: 1.5, type: 'runner.started', status: 'running', data: {} }),
    )
    expect(event?.type).toBe('runner.started')
  })

  it('rejects malformed values', () => {
    expect(parseRunnerEvent('{')).toBeNull()
    expect(parseRunnerEvent(JSON.stringify({ timestamp: 'now' }))).toBeNull()
  })
})
