export interface WatchlistStock {
  id: number
  ts_code: string
  symbol: string
  name: string
  added_at: string
}

export interface WatchlistGroup {
  id: number
  user_id: number
  name: string
  sort_order: number
  stocks: WatchlistStock[]
  created_at: string
  updated_at: string
}
