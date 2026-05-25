import { describe, it, expect } from 'vitest'
import { formatDate } from '../../utils/formatDate'

describe('formatDate', () => {
  describe('有效秒时间戳', () => {
    it('应返回包含年份的可读日期字符串', () => {
      const result = formatDate(1714233600)
      expect(result).not.toBe('-')
      expect(result).toContain('2024')
    })
  })

  describe('ISO 8601 数字字符串', () => {
    it('应返回包含年份的可读日期字符串', () => {
      const result = formatDate('1714233600')
      expect(result).not.toBe('-')
      expect(result).toContain('2024')
    })
  })

  describe('null 输入', () => {
    it('应返回 "-"', () => {
      const result = formatDate(null as unknown as number)
      expect(result).toBe('-')
    })
  })

  describe('undefined 输入', () => {
    it('应返回 "-"', () => {
      const result = formatDate(undefined as unknown as number)
      expect(result).toBe('-')
    })
  })

  describe('零值输入', () => {
    it('应返回 "-"', () => {
      const result = formatDate(0)
      expect(result).toBe('-')
    })
  })

  describe('负值输入', () => {
    it('应返回 "-"', () => {
      const result = formatDate(-1)
      expect(result).toBe('-')
    })
  })
})
