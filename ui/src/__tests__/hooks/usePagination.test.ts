import { describe, it, expect, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { usePagination } from '../../hooks/usePagination'

/**
 * 创建模拟的分页数据获取函数
 * @param totalPages - 模拟的总页数
 * @returns 模拟的 fetchFn 和用于跟踪调用次数的 spy
 */
function createMockFetchFn(totalPages: number = 3) {
  let callCount = 0
  const fetchFn = vi.fn().mockImplementation(() => {
    callCount++
    const page = callCount
    return Promise.resolve({
      items: Array.from({ length: 5 }, (_, i) => ({
        id: (page - 1) * 5 + i + 1,
        name: `Item ${(page - 1) * 5 + i + 1}`,
      })),
      next_page_token: page < totalPages ? `token-page-${page + 1}` : undefined,
    })
  })
  return fetchFn
}

describe('usePagination', () => {
  describe('初始加载成功', () => {
    it('应加载第一页数据并设置 currentPage 为 1', async () => {
      const fetchFn = createMockFetchFn()
      const { result } = renderHook(() => usePagination(fetchFn, 5))

      // 初始状态应为 loading
      expect(result.current.loading).toBe(true)
      expect(result.current.currentPage).toBe(1)

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.items).toHaveLength(5)
      expect(result.current.items[0]).toEqual({ id: 1, name: 'Item 1' })
      expect(result.current.currentPage).toBe(1)
      expect(result.current.error).toBeNull()
    })
  })

  describe('goNext 翻页', () => {
    it('应翻到下一页并加载新数据', async () => {
      const fetchFn = createMockFetchFn(3)
      const { result } = renderHook(() => usePagination(fetchFn, 5))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.nextPageToken).toBeDefined()

      act(() => {
        result.current.goNext()
      })

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.currentPage).toBe(2)
      expect(result.current.items[0]).toEqual({ id: 6, name: 'Item 6' })
    })
  })

  describe('goPrev 回退', () => {
    it('当 currentPage > 1 时应回到前一页', async () => {
      const fetchFn = createMockFetchFn(3)
      const { result } = renderHook(() => usePagination(fetchFn, 5))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // 先翻到第二页
      act(() => {
        result.current.goNext()
      })

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.currentPage).toBe(2)

      // 再翻回第一页
      act(() => {
        result.current.goPrev()
      })

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.currentPage).toBe(1)
    })
  })

  describe('reload 重置到第一页', () => {
    it('应重置 currentPage 为 1 并重新加载', async () => {
      const fetchFn = createMockFetchFn(3)
      const { result } = renderHook(() => usePagination(fetchFn, 5))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // 翻到第二页
      act(() => {
        result.current.goNext()
      })

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.currentPage).toBe(2)

      // reload
      act(() => {
        result.current.reload()
      })

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.currentPage).toBe(1)
    })
  })

  describe('fetch 失败后 error 状态', () => {
    it('应设置 error 消息', async () => {
      const fetchFn = vi.fn().mockRejectedValue(new Error('Network error'))
      const { result } = renderHook(() => usePagination(fetchFn, 5))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error).toBe('Network error')
      expect(result.current.items).toHaveLength(0)
    })
  })

  describe('currentPage === 1 时 goPrev 被阻止', () => {
    it('不应重新加载数据', async () => {
      const fetchFn = createMockFetchFn()
      const { result } = renderHook(() => usePagination(fetchFn, 5))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.currentPage).toBe(1)

      const callCountBefore = fetchFn.mock.calls.length;

      act(() => {
        result.current.goPrev()
      })

      expect(result.current.currentPage).toBe(1)
      // goPrev on page 1 should NOT trigger additional fetch calls
      expect(fetchFn.mock.calls.length).toBe(callCountBefore)
    })
  })

  describe('无 nextPageToken 时 goNext 被阻止', () => {
    it('不应翻页', async () => {
      // 只有一页数据
      const fetchFn = vi.fn().mockResolvedValue({
        items: [{ id: 1, name: 'Item 1' }],
        next_page_token: undefined,
      })
      const { result } = renderHook(() => usePagination(fetchFn, 5))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.nextPageToken).toBeUndefined()

      act(() => {
        result.current.goNext()
      })

      expect(result.current.currentPage).toBe(1)
      expect(fetchFn.mock.calls.length).toBe(1)
    })
  })
})
