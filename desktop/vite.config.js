import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// vite 构建 + vitest 共用配置
// vitest 通过 vitest config 读取 test 字段；vite build 忽略它
export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
