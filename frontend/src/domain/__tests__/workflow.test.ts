import { describe, expect, it } from 'vitest'

import type { PresetDto } from '../../types/api'
import { actionType, clonePresets, emptyStep, reorderSteps, uniquePresetName } from '../workflow'

function preset(name: string, stepNames: string[] = []): PresetDto {
  return {
    name,
    steps: stepNames.map((stepName) => ({ ...emptyStep('wait'), name: stepName })),
  }
}

describe('workflow domain helpers', () => {
  it('clones nested steps independently', () => {
    const source = [preset('A', ['one'])]
    const copy = clonePresets(source)
    copy[0].steps[0].name = 'changed'
    expect(source[0].steps[0].name).toBe('one')
  })

  it('describes target and value requirements', () => {
    expect(actionType('click').needsTarget).toBe(true)
    expect(actionType('wait').needsTarget).toBeUndefined()
    expect(actionType('wait').needsValue).toBe(true)
    expect(emptyStep('enter').value).toBe('')
  })

  it('creates unique preset names', () => {
    expect(uniquePresetName([preset('流程'), preset('流程 2')], '流程')).toBe('流程 3')
  })

  it('reorders steps in place', () => {
    const target = preset('A', ['one', 'two', 'three'])
    expect(reorderSteps(target, 0, 2)).toBe(true)
    expect(target.steps.map((step) => step.name)).toEqual(['two', 'three', 'one'])
  })
})