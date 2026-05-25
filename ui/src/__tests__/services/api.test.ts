import { describe, it, expect } from 'vitest'
import { buildUrl, handleResponse } from '../../services/api'

describe('buildUrl', () => {
  describe('无参数', () => {
    it('应返回原始 baseUrl', () => {
      expect(buildUrl('/delta-sharing/admin/v1/shares')).toBe(
        '/delta-sharing/admin/v1/shares'
      )
    })

    it('应返回无参数的原始 URL', () => {
      expect(buildUrl('/delta-sharing/admin/v1/shares', undefined)).toBe(
        '/delta-sharing/admin/v1/shares'
      )
    })
  })

  describe('多个有效参数', () => {
    it('应正确拼接多个查询参数', () => {
      const result = buildUrl('/delta-sharing/admin/v1/shares', {
        maxResults: 20,
        pageToken: 'abc123',
      })
      expect(result).toContain('maxResults=20')
      expect(result).toContain('pageToken=abc123')
      expect(result).toContain('?')
    })
  })

  describe('参数含 undefined/null/空字符串被省略', () => {
    it('应省略 undefined 参数', () => {
      const result = buildUrl('/delta-sharing/admin/v1/shares', {
        maxResults: 20,
        pageToken: undefined,
      })
      expect(result).toContain('maxResults=20')
      expect(result).not.toContain('pageToken')
    })

    it('应省略 null 参数', () => {
      const result = buildUrl(
        '/delta-sharing/admin/v1/shares',
        { maxResults: 20, comment: null as unknown as undefined }
      )
      expect(result).toContain('maxResults=20')
      expect(result).not.toContain('comment')
    })

    it('应省略空字符串参数', () => {
      const result = buildUrl('/delta-sharing/admin/v1/shares', {
        maxResults: 20,
        name: '',
      })
      expect(result).toContain('maxResults=20')
      expect(result).not.toContain('name')
    })
  })

  describe('特殊字符 URL 编码', () => {
    it('应编码空格（使用 + 或 %20）', () => {
      const result = buildUrl('/delta-sharing/admin/v1/shares', {
        name: 'test share',
      })
      expect(result).toMatch(/name=test\+share/)
    })
  })
})

describe('handleResponse', () => {
  describe('200 正常 JSON 响应', () => {
    it('应返回解析后的 JSON 对象', async () => {
      const response = new Response(JSON.stringify({ items: [] }), {
        status: 200,
      })
      const result = await handleResponse(response)
      expect(result).toEqual({ items: [] })
    })
  })

  describe('204 空响应', () => {
    it('应返回空对象 {}', async () => {
      const response = new Response(null, { status: 204 })
      const result = await handleResponse(response)
      expect(result).toEqual({})
    })
  })

  describe('500 错误 JSON 响应', () => {
    it('应抛出包含错误消息的 Error', async () => {
      const response = new Response(
        JSON.stringify({ message: 'Internal error' }),
        { status: 500 }
      )
      await expect(handleResponse(response)).rejects.toThrow('Internal error')
    })
  })

  describe('404 无 body 错误响应', () => {
    it('应抛出包含 "404" 的 Error', async () => {
      const response = new Response('', { status: 404, statusText: 'Not Found' })
      await expect(handleResponse(response)).rejects.toThrow('404')
    })
  })

  describe('响应体为空字符串的成功响应', () => {
    it('应返回空对象 {}', async () => {
      const response = new Response('', { status: 200 })
      const result = await handleResponse(response)
      expect(result).toEqual({})
    })
  })
})
