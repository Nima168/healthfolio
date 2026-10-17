import { describe, expect, it } from 'vitest'

import { explainDosing } from './format'

describe('dosing notation', () => {
  it.each([
    ['1-0-1 (twice daily, after food)', '1-0-1 (morning and night) (twice daily, after food)'],
    ['1-0-0 (before breakfast)', '1-0-0 (morning only) (before breakfast)'],
    ['0-0-1', '0-0-1 (night only)'],
    ['1-1-1 after food', '1-1-1 (morning, afternoon, and night) after food'],
    ['0-1-0', '0-1-0 (afternoon only)'],
    ['1 - 0 - 1', '1 - 0 - 1 (morning and night)'],
  ])('explains %s', (text, expected) => {
    expect(explainDosing(text)).toBe(expected)
  })

  it.each([
    'once daily at night', // no notation: kept as written
    '0-0-0', // nothing to take: not explained
    '2-0-2', // not 0/1: not guessed
    '1-0-1-1', // four positions: not this notation
    '10-0-1',
    'SOS for pain (max 3 per day)',
  ])('leaves %s as written', (text) => {
    expect(explainDosing(text)).toBe(text)
  })
})
