import api from './index'
import type { TradeResponse } from '@/types/trade'

export function listTrades(strategyId?: string) {
  const params = strategyId ? { strategy_id: strategyId } : {}
  return api.get<TradeResponse[]>('/trades', { params })
}
