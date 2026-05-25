import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * Vite配置文件
 * 配置React插件和开发服务器代理
 *
 * 代理配置将前端请求转发到后端服务，解决跨域问题
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      /**
       * 代理 /delta-sharing/admin 路径到 Admin API 端口 8089
       * 注意：此规则必须在通用 /delta-sharing 规则之前，确保精确匹配优先
       */
      '/delta-sharing/admin': {
        target: 'http://localhost:8089',
        changeOrigin: true,
        secure: false,
      },
      /**
       * 代理所有其他 /delta-sharing 开头的请求到 Data Plane 端口 8088
       */
      '/delta-sharing': {
        target: 'http://localhost:8088',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
