import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import type { TickMap, TickData } from '@/types/ws'

export const useMarketStore = defineStore('market', () => {
  const ticks = reactive<TickMap>({})
  const connected = ref(false)

  function updateTicks(data: TickMap) {
    Object.assign(ticks, data)
  }

  function getTick(code: string): TickData | undefined {
    return ticks[code]
  }

  return { ticks, connected, updateTicks, getTick }
})
