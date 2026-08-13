import type { PlaylistDocumentDto, SongDto, SongGroupDto } from '../types/api'

export function clonePlaylist(document: PlaylistDocumentDto): PlaylistDocumentDto {
  return {
    active_song_group: document.active_song_group,
    song_groups: document.song_groups.map((group) => ({
      name: group.name,
      step_preset: group.step_preset,
      songs: group.songs.map((song) => ({ ...song })),
    })),
  }
}

export function emptySong(): SongDto {
  return {
    title: '',
    keyword: '',
    duration_seconds: 0,
    buffer_seconds: 5,
    enabled: true,
    step_preset: '',
  }
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(Number(seconds) || 0))
  const minutes = Math.floor(total / 60)
  return `${String(minutes).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

export function parseDuration(value: string): number | null {
  const trimmed = value.trim()
  if (/^\d+$/.test(trimmed)) return Number(trimmed)
  const match = /^(\d+):([0-5]\d)$/.exec(trimmed)
  if (!match) return null
  return Number(match[1]) * 60 + Number(match[2])
}

export function uniqueGroupName(groups: SongGroupDto[], base = '新歌曲组'): string {
  const normalized = base.trim() || '新歌曲组'
  const names = new Set(groups.map((group) => group.name))
  if (normalized !== '全部' && !names.has(normalized)) return normalized
  let index = 2
  while (names.has(`${normalized} ${index}`)) index += 1
  return `${normalized} ${index}`
}

export function reorderSongs(group: SongGroupDto, from: number, to: number): boolean {
  if (from === to || from < 0 || to < 0 || from >= group.songs.length || to >= group.songs.length) {
    return false
  }
  const [song] = group.songs.splice(from, 1)
  group.songs.splice(to, 0, song)
  return true
}
