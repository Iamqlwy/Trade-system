import { watch } from 'vue'
import { useWebSocket } from './useWebSocket'
import { useMarketStore } from '@/stores/market'
import { useAuthStore } from '@/stores/auth'
import type { TickMap } from '@/types/ws'

export function useTickStream() {
  const marketStore = useMarketStore()
  const authStore = useAuthStore()

  const { connected, connect, disconnect } = useWebSocket('/ws/tick', {
    onMessage: (data) => {
      marketStore.updateTicks(data as TickMap)
      // connected 状态由下方 watch 统一管理，此处不再重复赋值
    },
  })

  // 统一由 watch 同步连接状态，避免 onMessage 和 watch 双重写入
  watch(connected, (val) => {
    marketStore.connected = val
  })

  // 登出时断开 tick 连接，避免携带空 token 重连
  watch(() => authStore.token, (token) => {
    if (!token) {
      disconnect()
    }
  })

  return { connected, connect, disconnect }
}
