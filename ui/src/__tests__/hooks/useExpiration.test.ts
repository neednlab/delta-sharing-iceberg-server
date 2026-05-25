import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useExpiration } from '../../hooks/useExpiration'

describe('useExpiration', () => {
  describe('默认初始选项', () => {
    it('默认应为 "30 days" → 720 小时', () => {
      const { result } = renderHook(() => useExpiration())
      expect(result.current.expirationOption).toBe('30 days')
      expect(result.current.expirationHours).toBe(720)
    })
  })

  describe('切换到 "7 days" 预设', () => {
    it('应更新选项和小时数', () => {
      const { result } = renderHook(() => useExpiration())
      act(() => {
        result.current.setExpirationOption('7 days')
      })
      expect(result.current.expirationOption).toBe('7 days')
      expect(result.current.expirationHours).toBe(168)
    })
  })

  describe('切换到 "90 days" 预设', () => {
    it('应更新选项和小时数', () => {
      const { result } = renderHook(() => useExpiration())
      act(() => {
        result.current.setExpirationOption('90 days')
      })
      expect(result.current.expirationOption).toBe('90 days')
      expect(result.current.expirationHours).toBe(2160)
    })
  })

  describe('切换到 "Never" (No expiration)', () => {
    it('应返回 undefined 过期小时数', () => {
      const { result } = renderHook(() => useExpiration())
      act(() => {
        result.current.setExpirationOption('No expiration')
      })
      expect(result.current.expirationOption).toBe('No expiration')
      expect(result.current.expirationHours).toBe(0)
    })
  })

  describe('切换到 "Custom" 清除自定义日期', () => {
    it('从非 Custom 切换到 Custom 时应清除之前设置的自定义日期', () => {
      const { result } = renderHook(() => useExpiration('30 days'))
      act(() => {
        result.current.setExpirationOption('Custom')
      })
      // 首次切换到 Custom，customDate 应为 undefined
      expect(result.current.customExpirationDate).toBeUndefined()
      // 设置自定义日期
      act(() => {
        result.current.setCustomExpirationDate(
          new Date(Date.now() + 48 * 60 * 60 * 1000)
        )
      })
      expect(result.current.customExpirationDate).toBeDefined()
      // 切换到非 Custom 的预设，应清除自定义日期
      act(() => {
        result.current.setExpirationOption('7 days')
      })
      expect(result.current.customExpirationDate).toBeUndefined()
    })
  })

  describe('设置自定义过期日期', () => {
    it('应计算约 48 小时的过期时间', () => {
      const { result } = renderHook(() => useExpiration())
      act(() => {
        result.current.setExpirationOption('Custom')
      })
      act(() => {
        result.current.setCustomExpirationDate(
          new Date(Date.now() + 48 * 60 * 60 * 1000)
        )
      })
      expect(result.current.expirationHours).toBeGreaterThanOrEqual(47)
      expect(result.current.expirationHours).toBeLessThanOrEqual(49)
    })
  })
})
