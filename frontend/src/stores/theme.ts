import { ref, watch } from 'vue'
import { defineStore } from 'pinia'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'app-theme'

export const useThemeStore = defineStore('theme', () => {
  // 默认 dark；从 localStorage 恢复用户选择
  const saved = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
  const mode = ref<ThemeMode>((saved === 'light' || saved === 'dark') ? saved : 'dark')

  function apply() {
    document.documentElement.setAttribute('data-theme', mode.value)
  }

  function toggle() {
    mode.value = mode.value === 'dark' ? 'light' : 'dark'
  }

  function setMode(m: ThemeMode) {
    mode.value = m
  }

  // 初始化 + 响应变化
  apply()
  watch(mode, (val) => {
    localStorage.setItem(STORAGE_KEY, val)
    apply()
  })

  return { mode, toggle, setMode }
})
