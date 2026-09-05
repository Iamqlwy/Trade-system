import api from './index'
import type {
  EquityResponse,
  CompareResponse,
  RiskMetrics,
  DayTResponse,
  SettlementResponse,
  StatisticsResponse,
  PositionsResponse,
} from '@/types/analysis'

export function equityData(strategyId: string) {
  return api.get<EquityResponse>(`/analysis/equity-data/${strategyId}`)
}

export function compareData(ids: string[]) {
  return api.get<CompareResponse>('/analysis/compare-data', {
    params: { ids: ids.join(',') },
  })
}

export function riskData(strategyId: string) {
  return api.get<RiskMetrics>(`/analysis/risk-data/${strategyId}`)
}

export function daytData(strategyId: string, startDate?: string, endDate?: string) {
  return api.get<DayTResponse>(`/analysis/dayt-data/${strategyId}`, {
    params: { start_date: startDate || '', end_date: endDate || '' },
  })
}

export function settlementData(strategyId: string, status: string = '全部') {
  return api.get<SettlementResponse>(`/analysis/settlement-data/${strategyId}`, {
    params: { status },
  })
}

export function statisticsData(strategyId: string) {
  return api.get<StatisticsResponse>(`/analysis/statistics-data/${strategyId}`)
}

export function positionsData(strategyId?: string, useRealtime: boolean = true) {
  return api.get<PositionsResponse>('/analysis/positions-data', {
    params: { strategy_id: strategyId || '', use_realtime: useRealtime },
  })
}
