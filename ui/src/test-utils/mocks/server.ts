import { setupServer } from 'msw/node'
import { defaultHandlers } from './handlers'

/**
 * MSW Server 实例
 * 使用默认 handlers 预配置，测试中可通过 server.use() 覆盖
 */
export const server = setupServer(...defaultHandlers)
