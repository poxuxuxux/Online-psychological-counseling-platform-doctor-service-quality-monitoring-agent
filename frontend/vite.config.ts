// 环节：项目配置层；用途：为开发、构建、部署或预览提供配置与入口。
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.API_PROXY_TARGET || 'http://127.0.0.1:8000'
  return {
    plugins: [vue()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: Object.fromEntries(
        ['/api', '/health', '/ready', '/docs', '/openapi.json'].map((path) => [
          path,
          { target, changeOrigin: true },
        ]),
      ),
    },
    build: { sourcemap: false, assetsDir: 'assets' },
    test: { include: ['tests/unit/**/*.test.ts'], environment: 'node' },
  }
})
