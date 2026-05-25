import { describe, it, expect } from 'vitest'
import { calculateExpirationHours } from '../../utils/calculateExpirationHours'

describe('calculateExpirationHours', () => {
  describe('预设选项 "7 days"', () => {
    it('应返回 168 (7 * 24)', () => {
      expect(calculateExpirationHours('7 days')).toBe(168)
    })
  })

  describe('预设选项 "30 days"', () => {
    it('应返回 720 (30 * 24)', () => {
      expect(calculateExpirationHours('30 days')).toBe(720)
    })
  })

  describe('预设选项 "90 days"', () => {
    it('应返回 2160 (90 * 24)', () => {
      expect(calculateExpirationHours('90 days')).toBe(2160)
    })
  })

  describe('预设选项 "No expiration"', () => {
    it('应返回 0', () => {
      expect(calculateExpirationHours('No expiration')).toBe(0)
    })
  })

  describe('"Custom" 选项配合未来日期', () => {
    it('应返回约 48 小时', () => {
      const futureDate = new Date(Date.now() + 48 * 60 * 60 * 1000)
      const result = calculateExpirationHours('Custom', futureDate)
      expect(result).toBeGreaterThanOrEqual(47)
      expect(result).toBeLessThanOrEqual(49)
    })
  })

  describe('"Custom" 选项配合过去日期', () => {
    it('应返回 0', () => {
      const pastDate = new Date(Date.now() - 86400000)
      const result = calculateExpirationHours('Custom', pastDate)
      expect(result).toBe(0)
    })
  })

  describe('未知选项字符串', () => {
    it('应返回 undefined', () => {
      expect(calculateExpirationHours('1 year')).toBeUndefined()
    })
  })

  describe('"Custom" 选项无自定义日期', () => {
    it('应返回 undefined', () => {
      expect(calculateExpirationHours('Custom')).toBeUndefined()
    })
  })
})
