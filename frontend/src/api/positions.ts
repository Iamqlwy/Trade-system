import api from './index'
import type { PositionResponse } from '@/types/position'

export function listPositions(strategyId: string) {
  return api.get<PositionResponse[]>(`/strategies/${strategyId}/positions`)
}

export function updateRemark(strategyId: string, stockCode: string, remark: string) {
  return api.put(`/strategies/${strategyId}/positions/${stockCode}/remark`, { remark })
}
