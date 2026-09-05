import { ref, watch, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { notify } from './useNotification'

export interface OrderConfirmNotification {
  confirmation_id: string
  api_token_name: string
  strategy_id: string
  strategy_name: string
  stock_code: string
  stock_name: string
  order_type: number
  price_type: number
  price: string
  order_volume: number
  order_remark: string
  expires_at: string
}

export interface ConfirmResultNotification {
  confirmation_id: string
  action: 'approved' | 'rejected'
  order_id?: string
}

const pendingConfirmations = ref<OrderConfirmNotification[]>([])
const connected = ref(false)

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

function getUrl(): string {
  const authStore = useAuthStore()
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const token = authStore.token || ''
  return `${protocol}//${host}/ws/notifications?token=${encodeURIComponent(token)}`
}

function connect() {
  const authStore = useAuthStore()
  if (!authStore.token) return

  ws = new WebSocket(getUrl())

  ws.onopen = () => {
    connected.value = true
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'order_confirm') {
        pendingConfirmations.value.push(msg.data)
        // OS 通知：有新的下单确认需要审批
        const d = msg.data as OrderConfirmNotification
        const action = d.order_type === 23 ? '买入' : '卖出'
        notify({
          title: '下单确认',
          body: `${d.strategy_name} ${action} ${d.stock_name || d.stock_code} ${d.order_volume}股 @${d.price}`,
          tag: `confirm-${d.confirmation_id}`,
          navigateTo: '/orders',
        })
      } else if (msg.type === 'order_confirm_result') {
        const result = msg.data as ConfirmResultNotification
        // 从待确认列表中移除
        pendingConfirmations.value = pendingConfirmations.value.filter(
          c => c.confirmation_id !== result.confirmation_id
        )
      } else if (msg.type === 'monitor_alert') {
        const d = msg as { monitor_name?: string; stock_code?: string; message?: string; is_error?: boolean }
        const title = d.is_error ? '⚠️ 监控错误' : '🔔 监控触发'
        const stock = d.stock_code ? `[${d.stock_code}] ` : ''
        notify({
          title,
          body: `${d.monitor_name || ''} ${stock}${d.message || ''}`,
          tag: `monitor-${msg.monitor_id}-${d.stock_code || 'x'}`,
          navigateTo: '/monitors',
        })
      }
    } catch {
      // ignore parse errors
    }
  }

  ws.onclose = () => {
    connected.value = false
    // 仅在 token 仍有效时自动重连，避免登出后无限重连
    const authStore = useAuthStore()
    if (authStore.token) {
      reconnectTimer = setTimeout(connect, 5000)
    }
  }

  ws.onerror = () => {
    ws?.close()
  }
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  ws?.close()
  ws = null
  connected.value = false
}

function removeConfirmation(id: string) {
  pendingConfirmations.value = pendingConfirmations.value.filter(
    c => c.confirmation_id !== id
  )
}

// 延迟连接：首次调用 useNotifications 时才连接，避免模块加载时 Pinia 未初始化
let autoConnected = false

/** 监听 auth 状态，登出时自动断开连接 */
function setupAuthListener() {
  const authStore = useAuthStore()
  watch(() => authStore.token, (token) => {
    if (!token) {
      disconnect()
    }
  })
}

export function useNotifications() {
  if (!autoConnected) {
    autoConnected = true
    connect()
    setupAuthListener()
  }

  onUnmounted(() => {
    // 不在组件卸载时断开，保持全局连接
    // 登出时由 setupAuthListener 负责断开
  })

  return {
    pendingConfirmations,
    connected,
    removeConfirmation,
    disconnect,
  }
}
