import api from './index'
import type { StrategySummary, CreateStrategyRequest, UpdateStrategyRequest } from '@/types/strategy'

export function listStrategies() {
  return api.get<StrategySummary[]>('/strategies')
}

export function getStrategy(strategyId: string) {
  return api.get<StrategySummary>(`/strategies/${strategyId}`)
}

export function createStrategy(req: CreateStrategyRequest) {
  return api.post<{ success: boolean; strategy_id: string; message: string }>('/strategies', req)
}

export function updateStrategy(strategyId: string, req: UpdateStrategyRequest) {
  return api.put<StrategySummary>(`/strategies/${strategyId}`, req)
}

export function deleteStrategy(strategyId: string) {
  return api.delete<{ success: boolean; strategy_id: string; message: string }>(`/strategies/${strategyId}`)
}
