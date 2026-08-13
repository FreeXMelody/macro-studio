import type { SongDto } from '../types/api'

export interface RunItem {
  id: string
  name: string
  input: string
  group: string
  workflow: string
  durationSeconds: number
  bufferSeconds: number
  enabled: boolean
  sourceKind: 'playlist'
  source: SongDto
}

export function playlistRunItem(song: SongDto, group: string, index: number): RunItem {
  return {
    id: 'playlist:' + group + ':' + index,
    name: song.title || '未命名条目',
    input: song.keyword,
    group,
    workflow: song.step_preset || '继承分组',
    durationSeconds: song.duration_seconds,
    bufferSeconds: song.buffer_seconds,
    enabled: song.enabled,
    sourceKind: 'playlist',
    source: song,
  }
}