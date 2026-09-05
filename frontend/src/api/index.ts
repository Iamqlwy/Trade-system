import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import router from '@/router'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截器：注入 Bearer token
api.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  return config
})

// 响应拦截器：401 自动退出，403 权限提示
let isHandling401 = false

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status
    const url = err.config?.url ?? ''
    console.warn(`[API] 请求失败: ${err.config?.method?.toUpperCase()} ${url} → ${status}`, err.response?.data)

    if (status === 401) {
      // 登录 / 注册接口的 401 是"密码错误"，不应触发退出登录
      const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/register')

      if (isAuthEndpoint) {
        console.log('[API] 登录/注册 401（密码错误），不触发退出')
      } else {
        const authStore = useAuthStore()
        // 防止并发 401 重复触发 logout 和路由跳转
        if (!isHandling401 && authStore.token) {
          isHandling401 = true
          console.error('[API] 🔴 收到 401 未授权，准备退出登录', { url, hasToken: !!authStore.token })
          authStore.logout()
          const currentPath = router.currentRoute.value.fullPath
          router.push(currentPath === '/login' ? '/login' : `/login?next=${encodeURIComponent(currentPath)}`)
          ElMessage.error('登录已过期，请重新登录')
          // 延迟重置，确保路由跳转完成
          setTimeout(() => { isHandling401 = false }, 1000)
        }
      }
    } else if (status === 403) {
      const detail = err.response.data?.detail || '无权限执行此操作'
      console.warn('[API] 403 无权限:', detail)
      ElMessage.warning(detail)
    }
    return Promise.reject(err)
  },
)

export default api
