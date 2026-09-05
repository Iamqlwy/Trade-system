import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { requestNotificationPermission } from '@/composables/useNotification'
import './styles/main.css'

async function bootstrap() {
  console.log('[Main] 🚀 bootstrap 开始, pathname=%s', window.location.pathname)
  const app = createApp(App)

  app.use(createPinia())
  app.use(ElementPlus, { locale: zhCn })

  // 尽早初始化主题（在 mount 前应用 data-theme 属性，避免闪烁）
  const themeStore = useThemeStore()
  themeStore // 触发 store 初始化，apply() 会在 store 创建时调用

  // 必须在 auth 验证完成后再注册路由，确保路由守卫首次执行时 auth 状态已正确
  const router = (await import('./router')).default
  app.use(router)

  // 启动时验证 token 有效性
  const authStore = useAuthStore()
  await authStore.waitReady()
  console.log('[Main] waitReady 完成, isAuthenticated=%s, pathname=%s', authStore.isAuthenticated, window.location.pathname)

  // 如果 token 无效（用户被删除或已过期），在 mount 之前强制跳转登录页
  if (!authStore.isAuthenticated && !window.location.pathname.startsWith('/login')) {
    const next = encodeURIComponent(window.location.pathname + window.location.search)
    console.log('[Main] 🔴 未登录，强制跳转 /login?next=%s', next)
    window.location.href = `/login?next=${next}`
    return
  }

  console.log('[Main] ✅ app.mount, authenticated=%s', authStore.isAuthenticated)
  // 已登录用户自动请求通知权限（不阻塞 mount）
  if (authStore.isAuthenticated) {
    requestNotificationPermission()
  }
  app.mount('#app')
}

bootstrap()
