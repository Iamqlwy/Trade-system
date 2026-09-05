import api from './index'
import type { MonitorInfo, MonitorDetail, MonitorAlert, MonitorRunResult, MonitorUpdateRequest, StrategyOption, StockOption } from '@/types/monitor'

export function listMonitors() {
  return api.get<MonitorInfo[]>('/monitors')
}

export function getMonitor(id: string) {
  return api.get<MonitorDetail>(`/monitors/${id}`)
}

export function updateMonitor(id: string, data: MonitorUpdateRequest) {
  return api.put<MonitorInfo>(`/monitors/${id}`, data)
}

export function deleteMonitor(id: string) {
  return api.delete<{ monitor_id: string; deleted: boolean }>(`/monitors/${id}`)
}

export function toggleMonitor(id: string) {
  return api.post<{ monitor_id: string; enabled: boolean }>(`/monitors/${id}/toggle`)
}

export function runMonitor(id: string) {
  return api.post<MonitorRunResult>(`/monitors/${id}/run`)
}

export function getMonitorLogs(params?: { monitor_id?: string; date?: string; limit?: number }) {
  return api.get<MonitorAlert[]>('/monitors/logs', { params })
}

export function searchStocks(q: string, limit = 20) {
  return api.get<StockOption[]>('/monitors/stock-search', { params: { q, limit } })
}

export function getStrategiesForMonitor() {
  return api.get<StrategyOption[]>('/monitors/strategies')
}
