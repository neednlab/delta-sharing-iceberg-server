import { http, HttpResponse } from 'msw'
import type { AppConfig } from '../../types'

/**
 * 默认 AppConfig 数据，用于配置 API 的默认响应
 */
const DEFAULT_CONFIG: AppConfig = {
  token: {
    max_tokens_per_recipient: 5,
    rotation_period_hours: 720,
    default_expiration_hours: 720,
  },
}

/**
 * MSW 默认请求处理器
 * 为 Admin API 端点提供通用的默认响应
 * 测试中可通过 server.use() 覆盖特定 handler
 */
export const defaultHandlers = [
  http.get('/delta-sharing/admin/v1/shares', () => {
    return HttpResponse.json({ items: [], next_page_token: undefined })
  }),

  http.get('/delta-sharing/admin/v1/recipients', () => {
    return HttpResponse.json({ items: [], next_page_token: undefined })
  }),

  http.get('/delta-sharing/admin/v1/config', () => {
    return HttpResponse.json(DEFAULT_CONFIG)
  }),
]
