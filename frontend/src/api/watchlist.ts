import api from './index'
import type { WatchlistGroup, WatchlistStock } from '@/types/watchlist'

export function getWatchlistGroups() {
  return api.get<WatchlistGroup[]>('/watchlist/groups')
}

export function createGroup(name: string) {
  return api.post<WatchlistGroup>('/watchlist/groups', { name })
}

export function renameGroup(id: number, name: string) {
  return api.put<{ id: number; name: string; updated: boolean }>(`/watchlist/groups/${id}`, { name })
}

export function deleteGroup(id: number) {
  return api.delete<{ id: number; deleted: boolean }>(`/watchlist/groups/${id}`)
}

export function addStock(groupId: number, stock: { ts_code: string; symbol: string; name: string }) {
  return api.post<WatchlistStock>(`/watchlist/groups/${groupId}/stocks`, stock)
}

export function batchAddStocks(groupId: number, stocks: { ts_code: string; symbol: string; name: string }[]) {
  return api.post<{ added: number; skipped: number; codes: string[] }>(
    `/watchlist/groups/${groupId}/stocks/batch`,
    { stocks }
  )
}

export function removeStock(stockId: number) {
  return api.delete<{ id: number; deleted: boolean }>(`/watchlist/stocks/${stockId}`)
}
