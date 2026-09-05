import { ref, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

interface UseWebSocketOptions {
  onMessage?: (data: unknown) => void
  onError?: (event: Event) => void
  reconnectInterval?: number
  maxReconnectAttempts?: number
}

export function useWebSocket(path: string, options: UseWebSocketOptions = {}) {
  const {
    onMessage,
    onError,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
  } = options

  const connected = ref(false)
  let ws: WebSocket | null = null
  let reconnectCount = 0
  let pingTimer: ReturnType<typeof setInterval> | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  // 消息队列：WS 未就绪时暂存，连接好后自动 flush
  let sendQueue: (string | object)[] = []
  // 记录当前连接使用的 token，用于检测 token 变更
  let connectedToken: string | null = null

  function getToken(): string {
    const authStore = useAuthStore()
    return authStore.token || ''
  }

  function getUrl(token: string): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    return `${protocol}//${host}${path}?token=${encodeURIComponent(token)}`
  }

  /** 将队列中的消息全部发出 */
  function flushQueue() {
    if (!ws || ws.readyState !== WebSocket.OPEN || sendQueue.length === 0) return
    const queue = sendQueue
    sendQueue = []
    for (const msg of queue) {
      ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
  }

  function connect() {
    const currentToken = getToken()
    if (ws?.readyState === WebSocket.OPEN) {
      // 如果已有连接但 token 变了，先断开重建
      if (connectedToken === currentToken) return
      disconnect()
    }

    try {
      ws = new WebSocket(getUrl(currentToken))
      connectedToken = currentToken

      ws.onopen = () => {
        connected.value = true
        reconnectCount = 0
        // 连接成功，先 flush 队列中的消息
        flushQueue()
        // 心跳：每 30 秒 ping
        pingTimer = setInterval(() => {
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send('ping')
          }
        }, 30000)
      }

      ws.onmessage = (event) => {
        if (event.data === 'pong') return
        try {
          const data = JSON.parse(event.data)
          onMessage?.(data)
        } catch {
          // ignore parse errors
        }
      }

      ws.onerror = (event) => {
        onError?.(event)
      }

      ws.onclose = () => {
        connected.value = false
        cleanup()
        if (reconnectCount < maxReconnectAttempts) {
          reconnectCount++
          const delay = reconnectInterval * Math.pow(1.5, reconnectCount - 1)
          reconnectTimer = setTimeout(connect, delay)
        }
      }
    } catch {
      // connection failed
    }
  }

  function disconnect() {
    reconnectCount = maxReconnectAttempts // prevent reconnect
    cleanup()
    ws?.close()
    ws = null
    connectedToken = null
    connected.value = false
    sendQueue = []
  }

  function send(data: string | object) {
    if (ws?.readyState === WebSocket.OPEN) {
      // 连接就绪：先 flush 队列中的积压消息，再发送当前消息
      flushQueue()
      ws.send(typeof data === 'string' ? data : JSON.stringify(data))
    } else {
      // WS 未就绪：排队等待，连接好后自动发送
      sendQueue.push(data)
    }
  }

  function cleanup() {
    if (pingTimer) {
      clearInterval(pingTimer)
      pingTimer = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  onUnmounted(() => {
    disconnect()
  })

  return { connected, connect, disconnect, send }
}
