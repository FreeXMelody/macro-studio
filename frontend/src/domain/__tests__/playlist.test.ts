import { describe, expect, it } from 'vitest'

import type { PlaylistDocumentDto, SongGroupDto } from '../../types/api'
import { clonePlaylist, formatDuration, parseDuration, reorderSongs, uniqueGroupName } from '../playlist'

function group(name: string, titles: string[] = []): SongGroupDto {
  return {
    name,
    step_preset: '',
    songs: titles.map((title) => ({
      title,
      keyword: title,
      duration_seconds: 10,
      buffer_seconds: 5,
      enabled: true,
      step_preset: '',
    })),
  }
}

describe('playlist domain helpers', () => {
  it('clones nested songs independently', () => {
    const source: PlaylistDocumentDto = { active_song_group: 'A', song_groups: [group('A', ['one'])] }
    const copy = clonePlaylist(source)
    copy.song_groups[0].songs[0].title = 'changed'
    expect(source.song_groups[0].songs[0].title).toBe('one')
  })

  it('formats and parses supported durations', () => {
    expect(formatDuration(65)).toBe('01:05')
    expect(parseDuration('01:05')).toBe(65)
    expect(parseDuration('90')).toBe(90)
    expect(parseDuration('1:99')).toBeNull()
  })

  it('chooses unique non-reserved group names', () => {
    const groups = [group('新歌曲组'), group('新歌曲组 2')]
    expect(uniqueGroupName(groups)).toBe('新歌曲组 3')
    expect(uniqueGroupName(groups, '古风')).toBe('古风')
  })

  it('reorders songs in place', () => {
    const target = group('A', ['one', 'two', 'three'])
    expect(reorderSongs(target, 0, 2)).toBe(true)
    expect(target.songs.map((song) => song.title)).toEqual(['two', 'three', 'one'])
  })
})
