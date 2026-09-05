/**
 * 浏览器 OS 通知 — 全局单例
 *
 * 模块级单例管理 Notification 权限与发送。
 * 所有调用方共享同一份权限状态，避免重复请求。
 */
import { ref } from 'vue'
import router from '@/router'

// ── 模块级全局状态 ──
const permitted = ref(false)
const denied = ref(false)

// 初始化（SSR 安全）
if (typeof window !== 'undefined' && 'Notification' in window) {
  permitted.value = Notification.permission === 'granted'
  denied.value = Notification.permission === 'denied'
}

// ── 类型 ──
export interface NotifyOptions {
  title: string
  body?: string
  /** 通知图标，默认使用站点图标 */
  icon?: string
  tag?: string
  /** 点击通知后跳转的路由路径，不传则只 focus 窗口 */
  navigateTo?: string
}

/** 默认通知图标（站点图标） */
const DEFAULT_ICON = '/favicon.png'

// ── 内部辅助 ──

/**
 * 聚焦浏览器窗口。
 * 配合 Notification click 实现「点击通知跳回浏览器」。
 */
function focusWindow(): void {
  if (window.focus) {
    window.focus()
  }
}

// ── 公共 API ──

/**
 * 请求通知权限（应在用户认证后、页面首次加载时调用）。
 * 若已授权直接返回 true；若用户曾拒绝则不会再次弹窗。
 */
export async function requestNotificationPermission(): Promise<boolean> {
  if (!('Notification' in window)) {
    console.warn('[Notification] 浏览器不支持桌面通知')
    return false
  }
  if (Notification.permission === 'granted') {
    permitted.value = true
    denied.value = false
    return true
  }
  if (Notification.permission === 'denied') {
    denied.value = true
    return false
  }
  try {
    const result = await Notification.requestPermission()
    permitted.value = result === 'granted'
    denied.value = result === 'denied'
    return permitted.value
  } catch {
    // 某些旧浏览器会抛异常
    return false
  }
}

/**
 * 发送一条 OS 桌面通知。
 *
 * - 无论页面是否可见都会发送，确保用户不错过任何通知。
 * - 通知永久显示，直到用户点击或手动关闭（`requireInteraction: true`）。
 * - 点击通知自动聚焦浏览器窗口并可选跳转路由。
 *
 * @returns 是否成功发送
 */
export function notify(opts: NotifyOptions): boolean {
  if (!('Notification' in window)) return false
  if (Notification.permission !== 'granted') return false

  const n = new Notification(opts.title, {
    body: opts.body ?? '',
    icon: opts.icon ?? DEFAULT_ICON,
    tag: opts.tag,
    requireInteraction: true,
    silent: false,
  })

  n.onclick = () => {
    focusWindow()
    if (opts.navigateTo) {
      router.push(opts.navigateTo)
    }
    n.close()
  }

  return true
}

/** Vue composable 形式访问全局权限状态 */
export function useNotification() {
  return {
    permitted,
    denied,
    requestPermission: requestNotificationPermission,
    notify,
  }
}
