import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserInfo } from '@/types/auth'
import * as authApi from '@/api/auth'

const TOKEN_KEY = 'quant_token'
const USER_KEY = 'quant_user'

function loadUser(): UserInfo | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as UserInfo
  } catch {
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(TOKEN_KEY)
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<UserInfo | null>(loadUser())
  const _initialized = ref(false)

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const canUseAgent = computed(() => isAdmin.value || !!user.value?.can_use_agent)
  const canCreateReal = computed(() => isAdmin.value || !!user.value?.can_create_real)
  const maxStrategies = computed(() => isAdmin.value ? -1 : (user.value?.max_strategies ?? 10))
  const canUseCron = computed(() => isAdmin.value || !!user.value?.can_use_cron)
  const canUseMonitor = computed(() => isAdmin.value || !!user.value?.can_use_monitor)

  /** 等待启动时 token 验证完成 */
  async function waitReady() {
    if (_initialized.value) return
    if (!token.value) {
      _initialized.value = true
      return
    }
    try {
      // 给 fetchMe 加 10s 超时，避免弱网下路由永久阻塞
      const ok = await Promise.race([
        fetchMe(),
        new Promise<boolean>((_, reject) => setTimeout(() => reject(new Error('fetchMe timeout')), 10000)),
      ])
      _initialized.value = ok
    } catch {
      _initialized.value = true
    }
  }

  async function login(username: string, password: string) {
    const res = await authApi.login({ username, password })
    const { token: t, user: u } = res.data
    token.value = t
    user.value = u
    localStorage.setItem(TOKEN_KEY, t)
    localStorage.setItem(USER_KEY, JSON.stringify(u))
  }

  async function register(username: string, password: string) {
    const res = await authApi.register({ username, password })
    const { token: t, user: u } = res.data
    token.value = t
    user.value = u
    localStorage.setItem(TOKEN_KEY, t)
    localStorage.setItem(USER_KEY, JSON.stringify(u))
  }

  function logout() {
    // 幂等：已经是登出状态时直接返回，避免多次调用产生冗余操作
    if (!token.value && !user.value) return
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  async function fetchMe() {
    try {
      const res = await authApi.getMe()
      user.value = res.data
      localStorage.setItem(USER_KEY, JSON.stringify(res.data))
      return true
    } catch (err) {
      // 401 已由 api 拦截器处理 logout，这里仅处理其他错误
      // 避免与拦截器重复调用 logout
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status !== 401) {
        logout()
      }
      return false
    }
  }

  return {
    token, user, isAuthenticated, isAdmin,
    canUseAgent, canCreateReal, maxStrategies, canUseCron, canUseMonitor,
    login, register, logout, fetchMe, waitReady,
  }
})
